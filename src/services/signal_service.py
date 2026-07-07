"""Signal Approval Service — manages signal lifecycle with countdown timer.

Handles creation, approval, rejection, and expiry of trading signals.
Uses Redis TTL for server-side countdown tracking.

Signal lifecycle: pending → approved / rejected / expired

Implements Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.cache.redis_client import RedisClient
from src.database.models.scan_signal import ScanSignal

logger = logging.getLogger(__name__)

# Redis key prefix for signal expiry tracking
SIGNAL_EXPIRY_KEY_PREFIX = "signal_expiry"


def _signal_expiry_key(signal_id: int) -> str:
    """Build the Redis key for tracking signal countdown TTL.

    Args:
        signal_id: The database ID of the signal.

    Returns:
        Redis key string, e.g. "signal_expiry:42"
    """
    return f"{SIGNAL_EXPIRY_KEY_PREFIX}:{signal_id}"


class SignalService:
    """Manages signal approval workflow with countdown timer.

    Provides create, approve, reject, expire, and query operations
    for trading signals. Uses Redis TTL to track server-side countdown
    so that signals auto-expire when the timer runs out.
    """

    def __init__(self, db: Session, redis_client: RedisClient) -> None:
        """Initialize SignalService.

        Args:
            db: SQLAlchemy session for database operations.
            redis_client: RedisClient instance for countdown TTL tracking.
        """
        if db is None:
            raise ValueError("db cannot be None")
        if redis_client is None:
            raise ValueError("redis_client cannot be None")

        self.db = db
        self.redis = redis_client

    def create_signal(
        self,
        user_id: int,
        scan_signal_data: Dict[str, Any],
        countdown_seconds: int = 60,
    ) -> ScanSignal:
        """Create a pending signal from scan data with server-side expiry timer.

        Creates a ScanSignal record with status="pending", sets expires_at,
        and stores a Redis key with TTL for countdown tracking.

        Args:
            user_id: The user who owns this signal.
            scan_signal_data: Dictionary with signal fields:
                - signal_type (str): "trend_pullback" or "consolidation_breakout"
                - symbol (str): Trading symbol
                - confidence_score (float): 50-100
                - entry_price (float): Suggested entry price
                - stop_loss (float): Stop-loss level
                - target_price (float): Target price
                - max_potential_loss (float): Maximum potential loss amount
                - ai_quality_rating (str, optional): AI quality assessment
                - ai_warnings (list, optional): AI warning messages
                - ai_explanation (str, optional): AI explanation text
                - metadata (dict, optional): Additional signal metadata
            countdown_seconds: Seconds until signal expires (default 60).

        Returns:
            The created ScanSignal instance.

        Raises:
            ValueError: If required fields are missing or invalid.
        """
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=countdown_seconds)

        signal = ScanSignal(
            user_id=user_id,
            signal_type=scan_signal_data["signal_type"],
            symbol=scan_signal_data["symbol"],
            confidence_score=scan_signal_data["confidence_score"],
            entry_price=scan_signal_data["entry_price"],
            stop_loss=scan_signal_data["stop_loss"],
            target_price=scan_signal_data["target_price"],
            max_potential_loss=scan_signal_data["max_potential_loss"],
            status="pending",
            countdown_seconds=countdown_seconds,
            expires_at=expires_at,
            ai_quality_rating=scan_signal_data.get("ai_quality_rating"),
            ai_warnings=scan_signal_data.get("ai_warnings"),
            ai_explanation=scan_signal_data.get("ai_explanation"),
            metadata_json=scan_signal_data.get("metadata"),
        )

        self.db.add(signal)
        self.db.commit()
        self.db.refresh(signal)

        # Store Redis key with TTL for countdown tracking
        redis_key = _signal_expiry_key(signal.id)
        self.redis.set(redis_key, str(signal.id), ttl=countdown_seconds)

        logger.info(
            "Created signal %d for user %d, expires in %ds",
            signal.id,
            user_id,
            countdown_seconds,
        )

        return signal

    def approve_signal(self, signal_id: int, user_id: int) -> Dict[str, Any]:
        """Approve a pending signal and return trade execution data.

        Verifies the signal is pending and belongs to the user, updates
        status to "approved", and removes the Redis TTL key.

        Args:
            signal_id: The ID of the signal to approve.
            user_id: The user performing the approval (ownership check).

        Returns:
            Dictionary with trade execution data:
                - signal_id (int)
                - symbol (str)
                - entry_price (float)
                - stop_loss (float)
                - target_price (float)
                - signal_type (str)
                - confidence_score (float)

        Raises:
            ValueError: If signal not found, not pending, or not owned by user.
        """
        signal = self.db.query(ScanSignal).filter(ScanSignal.id == signal_id).first()

        if signal is None:
            raise ValueError(f"Signal {signal_id} not found")

        if signal.user_id != user_id:
            raise ValueError(f"Signal {signal_id} does not belong to user {user_id}")

        if signal.status != "pending":
            raise ValueError(
                f"Signal {signal_id} is not pending (current status: {signal.status})"
            )

        signal.status = "approved"
        signal.updated_at = datetime.now(timezone.utc)
        self.db.commit()

        # Remove Redis TTL key since signal is no longer pending
        redis_key = _signal_expiry_key(signal_id)
        self.redis.delete(redis_key)

        logger.info("Signal %d approved by user %d", signal_id, user_id)

        return {
            "signal_id": signal.id,
            "symbol": signal.symbol,
            "entry_price": signal.entry_price,
            "stop_loss": signal.stop_loss,
            "target_price": signal.target_price,
            "signal_type": signal.signal_type,
            "confidence_score": signal.confidence_score,
        }

    def reject_signal(self, signal_id: int, user_id: int) -> Dict[str, Any]:
        """Reject a pending signal and dismiss it.

        Updates status to "rejected" and removes the Redis TTL key.

        Args:
            signal_id: The ID of the signal to reject.
            user_id: The user performing the rejection (ownership check).

        Returns:
            Dictionary with rejection confirmation:
                - signal_id (int)
                - status (str): "rejected"

        Raises:
            ValueError: If signal not found, not pending, or not owned by user.
        """
        signal = self.db.query(ScanSignal).filter(ScanSignal.id == signal_id).first()

        if signal is None:
            raise ValueError(f"Signal {signal_id} not found")

        if signal.user_id != user_id:
            raise ValueError(f"Signal {signal_id} does not belong to user {user_id}")

        if signal.status != "pending":
            raise ValueError(
                f"Signal {signal_id} is not pending (current status: {signal.status})"
            )

        signal.status = "rejected"
        signal.updated_at = datetime.now(timezone.utc)
        self.db.commit()

        # Remove Redis TTL key
        redis_key = _signal_expiry_key(signal_id)
        self.redis.delete(redis_key)

        logger.info("Signal %d rejected by user %d", signal_id, user_id)

        return {"signal_id": signal.id, "status": "rejected"}

    def expire_signal(self, signal_id: int) -> Dict[str, Any]:
        """Mark a signal as expired (called by background worker).

        Updates status to "expired". The Redis key should already be
        gone (TTL expired), but we clean up defensively.

        Args:
            signal_id: The ID of the signal to expire.

        Returns:
            Dictionary with expiry confirmation:
                - signal_id (int)
                - status (str): "expired"

        Raises:
            ValueError: If signal not found or not in pending state.
        """
        signal = self.db.query(ScanSignal).filter(ScanSignal.id == signal_id).first()

        if signal is None:
            raise ValueError(f"Signal {signal_id} not found")

        if signal.status != "pending":
            raise ValueError(
                f"Signal {signal_id} is not pending (current status: {signal.status})"
            )

        signal.status = "expired"
        signal.updated_at = datetime.now(timezone.utc)
        self.db.commit()

        # Defensive cleanup — Redis key may already be gone due to TTL
        redis_key = _signal_expiry_key(signal_id)
        self.redis.delete(redis_key)

        logger.info("Signal %d expired", signal_id)

        return {"signal_id": signal.id, "status": "expired"}

    def get_pending_signals(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all pending signals for a user with remaining countdown.

        Fetches signals with status="pending" for the given user and
        calculates the remaining seconds from the Redis TTL.

        Args:
            user_id: The user to fetch pending signals for.

        Returns:
            List of dictionaries, each containing:
                - id (int)
                - symbol (str)
                - signal_type (str)
                - confidence_score (float)
                - entry_price (float)
                - stop_loss (float)
                - target_price (float)
                - max_potential_loss (float)
                - status (str)
                - countdown_seconds (int): Original countdown duration
                - remaining_seconds (int): Seconds left before expiry
                - expires_at (str): ISO-format expiry timestamp
                - created_at (str): ISO-format creation timestamp
                - ai_quality_rating (str or None)
                - ai_warnings (list or None)
                - ai_explanation (str or None)
        """
        signals = (
            self.db.query(ScanSignal)
            .filter(
                ScanSignal.user_id == user_id,
                ScanSignal.status == "pending",
            )
            .order_by(ScanSignal.created_at.desc())
            .all()
        )

        result = []
        for signal in signals:
            # Get remaining time from Redis TTL
            redis_key = _signal_expiry_key(signal.id)
            ttl = self.redis.ttl(redis_key)

            # TTL returns -2 if key doesn't exist, -1 if no expiry
            # If key is gone, remaining is 0 (signal should be expired)
            remaining_seconds = max(0, ttl) if ttl > 0 else 0

            result.append(
                {
                    "id": signal.id,
                    "symbol": signal.symbol,
                    "signal_type": signal.signal_type,
                    "confidence_score": signal.confidence_score,
                    "entry_price": signal.entry_price,
                    "stop_loss": signal.stop_loss,
                    "target_price": signal.target_price,
                    "max_potential_loss": signal.max_potential_loss,
                    "status": signal.status,
                    "countdown_seconds": signal.countdown_seconds,
                    "remaining_seconds": remaining_seconds,
                    "expires_at": (
                        signal.expires_at.isoformat() if signal.expires_at else None
                    ),
                    "created_at": (
                        signal.created_at.isoformat() if signal.created_at else None
                    ),
                    "ai_quality_rating": signal.ai_quality_rating,
                    "ai_warnings": signal.ai_warnings,
                    "ai_explanation": signal.ai_explanation,
                }
            )

        return result
