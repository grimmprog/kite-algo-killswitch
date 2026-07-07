"""Signal Expiry Worker — periodic Celery beat task for signal countdown expiry.

Checks all pending signals for countdown expiry and updates their status
to "expired" when the Redis TTL key has expired (countdown reached zero).

This worker runs every 5 seconds via Celery Beat and ensures signals
that were not approved or rejected within their countdown window are
automatically marked as expired in the database.

Requirements covered:
- 4.5: Display countdown timer for each pending signal, auto-expire on timeout
- 4.6: Mark signal as expired and move to history when countdown expires
"""

import logging
import os
from datetime import datetime, timezone
from typing import Dict, List

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.cache.redis_client import get_redis_client
from src.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Database URL from environment
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/trading_platform",
)

# Module-level engine/session factory (lazy init)
_engine = None
_SessionFactory = None

# Redis key prefix (must match signal_service.py)
SIGNAL_EXPIRY_KEY_PREFIX = "signal_expiry"


def _get_session_factory():
    """Get or create the SQLAlchemy session factory (lazy singleton).

    Returns:
        A sessionmaker bound to the database engine.
    """
    global _engine, _SessionFactory
    if _SessionFactory is None:
        _engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        _SessionFactory = sessionmaker(bind=_engine)
    return _SessionFactory


def _get_db_session() -> Session:
    """Create a new database session.

    Returns:
        A new SQLAlchemy Session instance.
    """
    factory = _get_session_factory()
    return factory()


def _signal_expiry_key(signal_id: int) -> str:
    """Build the Redis key for tracking signal countdown TTL.

    Args:
        signal_id: The database ID of the signal.

    Returns:
        Redis key string, e.g. "signal_expiry:42"
    """
    return f"{SIGNAL_EXPIRY_KEY_PREFIX}:{signal_id}"


@celery_app.task(name="src.workers.signal_expiry_worker.check_signal_expiry")
def check_signal_expiry() -> Dict:
    """Celery beat task: Check all pending signals for countdown expiry.

    Queries the database for all signals with status="pending", checks
    if their Redis TTL key has expired (key no longer exists), and marks
    them as "expired" in the database.

    This ensures that signals which were not approved or rejected within
    their countdown window are automatically cleaned up.

    Requirements covered:
    - 4.5: Countdown timer auto-expiry
    - 4.6: Mark signal as expired when countdown expires

    Returns:
        A dict summarizing the run:
            - "status" (str): "success" or "error"
            - "expired_count" (int): Number of signals expired this cycle
            - "pending_checked" (int): Total pending signals checked
            - "reason" (str): Description of the outcome
    """
    try:
        return _execute_check_signal_expiry()
    except Exception as e:
        logger.error(
            "Unexpected error in check_signal_expiry: %s: %s",
            type(e).__name__,
            str(e),
            exc_info=True,
        )
        return {
            "status": "error",
            "expired_count": 0,
            "pending_checked": 0,
            "reason": f"Unexpected error: {type(e).__name__}: {str(e)}",
        }


def _execute_check_signal_expiry() -> Dict:
    """Internal implementation of signal expiry checking.

    Separated from the task function to allow clean error handling
    at the top level without nested try/except blocks.

    Steps:
    1. Query all pending signals from the database
    2. For each pending signal, check if the Redis TTL key still exists
    3. If the key is gone (TTL expired), mark the signal as "expired"
    4. Also check expires_at timestamp as a fallback (in case Redis key
       was lost due to restart or eviction)

    Returns:
        Summary dict with status, counts, and reason.
    """
    from src.database.models.scan_signal import ScanSignal

    redis_client = get_redis_client()
    db_session = _get_db_session()

    try:
        # Query all pending signals
        pending_signals = (
            db_session.query(ScanSignal)
            .filter(ScanSignal.status == "pending")
            .all()
        )

        if not pending_signals:
            logger.debug("No pending signals to check for expiry")
            return {
                "status": "success",
                "expired_count": 0,
                "pending_checked": 0,
                "reason": "No pending signals",
            }

        expired_count = 0
        now = datetime.now(timezone.utc)

        for signal in pending_signals:
            should_expire = False

            # Check 1: Redis TTL key no longer exists (countdown expired)
            redis_key = _signal_expiry_key(signal.id)
            ttl = redis_client.ttl(redis_key)

            # ttl returns -2 if key doesn't exist (expired/never set)
            # ttl returns -1 if key exists but has no expiry
            # ttl returns >0 if key exists with remaining time
            if ttl == -2:
                should_expire = True

            # Check 2: Fallback — expires_at timestamp has passed
            # This handles cases where Redis key was lost (restart, eviction)
            if not should_expire and signal.expires_at is not None:
                # Ensure expires_at is timezone-aware for comparison
                expires_at = signal.expires_at
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)

                if now >= expires_at:
                    should_expire = True

            if should_expire:
                signal.status = "expired"
                signal.updated_at = now
                expired_count += 1

                # Defensive cleanup — remove Redis key if it somehow still exists
                redis_client.delete(redis_key)

                # Publish signal_expired event for WebSocket relay
                from src.services.signal_pipeline import publish_signal_expired

                publish_signal_expired(
                    user_id=signal.user_id,
                    signal_id=signal.id,
                    symbol=signal.symbol,
                )

                logger.info(
                    "Signal %d expired (user_id=%d, symbol=%s)",
                    signal.id,
                    signal.user_id,
                    signal.symbol,
                )

        # Commit all expiry updates in one batch
        if expired_count > 0:
            db_session.commit()
            logger.info(
                "Expired %d signals out of %d pending",
                expired_count,
                len(pending_signals),
            )

        return {
            "status": "success",
            "expired_count": expired_count,
            "pending_checked": len(pending_signals),
            "reason": (
                f"Expired {expired_count} signals"
                if expired_count > 0
                else "All pending signals still within countdown"
            ),
        }

    except Exception as e:
        db_session.rollback()
        logger.error(
            "Error checking signal expiry: %s: %s",
            type(e).__name__,
            str(e),
            exc_info=True,
        )
        raise
    finally:
        db_session.close()
