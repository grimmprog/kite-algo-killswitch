"""Celery task for auto-monitor P&L tracking and threshold proximity alerts.

Schedules the AutoMonitorWorker to run for each user with monitoring enabled.
A beat-scheduled task (schedule_pnl_monitoring) dispatches individual
run_pnl_monitor tasks per user, enabling parallel monitoring.

Requirements covered:
- 10.2: Start backend P&L monitoring process on toggle
- 10.3: Stop backend P&L monitoring process on toggle
- 10.4: Push warning notification when P&L within 10% of threshold
- 10.5: Display current P&L value and distance to nearest threshold
"""

import logging
import os
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


def get_db_session() -> Session:
    """Create a new database session.

    Returns:
        A new SQLAlchemy Session instance.
    """
    factory = _get_session_factory()
    return factory()


def get_monitored_user_ids(redis_client) -> List[int]:
    """Get all user IDs that have monitoring active.

    Scans Redis for user:*:monitor:active keys with value "true".
    In production, this would use SCAN with a pattern match or maintain
    a Redis set of active monitor users.

    Args:
        redis_client: RedisClient instance.

    Returns:
        List of user IDs with active monitoring.
    """
    try:
        # Use SCAN to find all monitor state keys
        cursor = 0
        active_user_ids = []
        pattern = "user:*:monitor:active"

        while True:
            cursor, keys = redis_client.client.scan(
                cursor=cursor, match=pattern, count=100
            )
            for key in keys:
                # key format: "user:{user_id}:monitor:active"
                # Handle both str and bytes
                key_str = key if isinstance(key, str) else key.decode()
                value = redis_client.get(key_str)
                if value == "true":
                    # Extract user_id from key
                    parts = key_str.split(":")
                    if len(parts) >= 2:
                        try:
                            user_id = int(parts[1])
                            active_user_ids.append(user_id)
                        except (ValueError, IndexError):
                            continue
            if cursor == 0:
                break

        return active_user_ids

    except Exception as e:
        logger.error(
            "Error scanning for monitored users: %s: %s",
            type(e).__name__,
            str(e),
        )
        return []


@celery_app.task(name="src.workers.auto_monitor_task.run_pnl_monitor")
def run_pnl_monitor(user_id: int) -> Dict:
    """Celery task: Run P&L monitor cycle for a specific user.

    Executes a full monitoring cycle:
    1. Check if monitoring is active for the user
    2. Fetch current P&L from Redis risk cache
    3. Compare against kill switch thresholds
    4. Publish status and threshold proximity warnings

    Requirements covered:
    - 10.4: Push warning notification when P&L within 10% of threshold
    - 10.5: Display current P&L value and distance to nearest threshold

    Args:
        user_id: The user's database ID.

    Returns:
        Dict summarizing the run:
            - "status": "success", "skipped", or "error"
            - "user_id": The user's ID
            - "reason": Description of the outcome
    """
    try:
        return _execute_pnl_monitor(user_id)
    except Exception as e:
        logger.error(
            "Unexpected top-level error in run_pnl_monitor for user %d: %s: %s",
            user_id,
            type(e).__name__,
            str(e),
        )
        return {
            "status": "error",
            "user_id": user_id,
            "reason": f"Unexpected error: {type(e).__name__}: {str(e)}",
        }


def _execute_pnl_monitor(user_id: int) -> Dict:
    """Internal implementation of P&L monitor for one user.

    Creates the AutoMonitorWorker and runs a single monitor cycle.
    """
    from src.workers.auto_monitor_worker import AutoMonitorWorker

    redis_client = get_redis_client()

    # Create worker instance
    worker = AutoMonitorWorker(user_id=user_id, redis_client=redis_client)

    # Quick check: if monitoring is not active, skip without DB session
    if not worker.is_monitoring_active():
        return {
            "status": "skipped",
            "user_id": user_id,
            "reason": "Monitoring inactive",
        }

    # Get database session for threshold fetching
    db_session = get_db_session()
    try:
        result = worker.run_monitor_cycle(db_session)
        return result
    except Exception as e:
        logger.error(
            "Error running P&L monitor for user %d: %s: %s",
            user_id,
            type(e).__name__,
            str(e),
            exc_info=True,
        )
        return {
            "status": "error",
            "user_id": user_id,
            "reason": f"{type(e).__name__}: {str(e)}",
        }
    finally:
        db_session.close()


@celery_app.task(name="src.workers.auto_monitor_task.schedule_pnl_monitoring")
def schedule_pnl_monitoring() -> Dict:
    """Celery beat task: Dispatch P&L monitor for each user with active monitoring.

    Scans Redis for users with monitoring enabled and dispatches individual
    run_pnl_monitor tasks for each one via Celery.

    Requirements covered:
    - 10.2: Start backend P&L monitoring process
    - 10.3: Stop backend P&L monitoring process (users with inactive state are skipped)

    Returns:
        Dict summarizing the dispatch:
            - "status": "success" or "error"
            - "users_dispatched": Number of tasks sent
            - "reason": Description of the outcome
    """
    try:
        return _execute_schedule_pnl_monitoring()
    except Exception as e:
        logger.error(
            "Unexpected top-level error in schedule_pnl_monitoring: %s: %s",
            type(e).__name__,
            str(e),
        )
        return {
            "status": "error",
            "users_dispatched": 0,
            "reason": f"Unexpected error: {type(e).__name__}: {str(e)}",
        }


def _execute_schedule_pnl_monitoring() -> Dict:
    """Internal implementation of the P&L monitoring scheduler.

    Finds users with active monitoring and dispatches monitor tasks.
    """
    redis_client = get_redis_client()
    active_user_ids = get_monitored_user_ids(redis_client)

    if not active_user_ids:
        logger.debug("No users with active P&L monitoring")
        return {
            "status": "success",
            "users_dispatched": 0,
            "reason": "No users with active monitoring",
        }

    # Dispatch a run_pnl_monitor task for each active user
    dispatched_count = 0
    for user_id in active_user_ids:
        try:
            run_pnl_monitor.delay(user_id)
            dispatched_count += 1
        except Exception as e:
            logger.error(
                "Failed to dispatch P&L monitor for user %d: %s: %s",
                user_id,
                type(e).__name__,
                str(e),
            )

    logger.info(
        "P&L monitoring scheduled: dispatched %d/%d user tasks",
        dispatched_count,
        len(active_user_ids),
    )

    return {
        "status": "success",
        "users_dispatched": dispatched_count,
        "reason": f"Dispatched {dispatched_count} user P&L monitor tasks",
    }
