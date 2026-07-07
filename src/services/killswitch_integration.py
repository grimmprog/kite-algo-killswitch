"""Kill Switch Integration — wires kill switch activation to segment deactivation and notifications.

When the kill switch triggers (risk_engine_worker detects threshold breach):
1. Push a critical notification via NotificationService with trigger reason
2. Store segment deactivation state in Redis (so SegmentManager shows kill switch badge)
3. Publish notification event via WebSocket for real-time delivery

The segment deactivation state is stored in Redis as a JSON list of segments
that were deactivated by the kill switch. The SettingsService.get_segments()
method reads this key to populate deactivated_by_killswitch on each segment.

Requirements covered:
- 12.4: When kill switch activates, indicate which segments were deactivated
- 11.4: When kill switch triggers, push critical notification with trigger reason
"""

import json
import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from src.cache.redis_client import RedisClient
from src.cache.redis_keys import RedisKeys
from src.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

# Redis key for tracking which segments were deactivated by kill switch
KILLSWITCH_SEGMENTS_KEY_PREFIX = "user:{user_id}:killswitch:segments"

# Default segments that get deactivated when kill switch triggers
DEFAULT_ACTIVE_SEGMENTS = ["NSE", "BSE", "NFO", "BFO"]


def _killswitch_segments_key(user_id: int) -> str:
    """Redis key storing segments deactivated by kill switch for a user.

    Args:
        user_id: The user's database ID.

    Returns:
        Redis key string, e.g. "user:42:killswitch:segments"
    """
    return f"user:{user_id}:killswitch:segments"


def handle_killswitch_activation(
    user_id: int,
    reason: str,
    positions_closed: int,
    redis_client: RedisClient,
    db_session: Session,
    deactivated_segments: Optional[List[str]] = None,
) -> bool:
    """Handle kill switch activation by pushing notification and marking segments.

    This is the integration entry point called when the kill switch triggers.
    It performs two actions:
    1. Pushes a critical notification via NotificationService (persisted to DB
       and broadcast via Redis PubSub for WebSocket delivery).
    2. Stores the list of deactivated segments in Redis so the frontend
       SegmentManager can display the kill switch badge.

    Args:
        user_id: The user whose kill switch was triggered.
        reason: Human-readable reason for kill switch activation
                (e.g., "Daily loss limit breached: -3.50%").
        positions_closed: Number of positions queued for exit.
        redis_client: RedisClient instance for Redis operations.
        db_session: SQLAlchemy session for notification persistence.
        deactivated_segments: List of segment names deactivated. Defaults to
                             all active segments (NSE, BSE, NFO, BFO).

    Returns:
        True if both notification and segment state were updated successfully.
        False if any step failed (partial success is possible).
    """
    if deactivated_segments is None:
        deactivated_segments = DEFAULT_ACTIVE_SEGMENTS.copy()

    success = True

    # Step 1: Push critical notification via NotificationService
    notification_ok = _push_killswitch_notification(
        user_id=user_id,
        reason=reason,
        positions_closed=positions_closed,
        redis_client=redis_client,
        db_session=db_session,
    )
    if not notification_ok:
        success = False

    # Step 2: Mark segments as deactivated by kill switch in Redis
    segments_ok = _mark_segments_deactivated(
        user_id=user_id,
        segments=deactivated_segments,
        redis_client=redis_client,
    )
    if not segments_ok:
        success = False

    return success


def _push_killswitch_notification(
    user_id: int,
    reason: str,
    positions_closed: int,
    redis_client: RedisClient,
    db_session: Session,
) -> bool:
    """Push a critical notification for kill switch activation.

    Creates a persistent notification record in the database and publishes
    it via Redis PubSub for real-time WebSocket delivery.

    Args:
        user_id: The user receiving the notification.
        reason: Kill switch trigger reason.
        positions_closed: Number of positions queued for exit.
        redis_client: RedisClient for PubSub broadcasting.
        db_session: SQLAlchemy session for DB persistence.

    Returns:
        True if notification was created successfully, False otherwise.
    """
    try:
        notification_service = NotificationService(db=db_session, redis_client=redis_client)

        title = "Kill Switch Activated"
        message = (
            f"Kill switch triggered: {reason}. "
            f"{positions_closed} position(s) queued for exit. "
            f"All trading segments have been deactivated."
        )

        notification_service.push_notification(
            user_id=user_id,
            severity="critical",
            title=title,
            message=message,
            category="killswitch",
            metadata={
                "reason": reason,
                "positions_closed": positions_closed,
                "triggered_at": datetime.now().isoformat(),
            },
        )

        logger.info(
            "Kill switch critical notification pushed for user %d: %s",
            user_id,
            reason,
        )
        return True

    except Exception as e:
        logger.error(
            "Failed to push kill switch notification for user %d: %s: %s",
            user_id,
            type(e).__name__,
            str(e),
        )
        return False


def _mark_segments_deactivated(
    user_id: int,
    segments: List[str],
    redis_client: RedisClient,
) -> bool:
    """Store the list of segments deactivated by kill switch in Redis.

    This is read by SettingsService.get_segments() to populate the
    deactivated_by_killswitch field on each SegmentStatus.

    The key persists until the kill switch is manually cleared (same
    lifecycle as the kill switch flag itself).

    Args:
        user_id: The user's database ID.
        segments: List of segment names that were deactivated.
        redis_client: RedisClient instance.

    Returns:
        True if state was stored successfully, False otherwise.
    """
    try:
        key = _killswitch_segments_key(user_id)
        value = json.dumps(segments)
        redis_client.set(key, value)

        logger.info(
            "Marked segments as deactivated by kill switch for user %d: %s",
            user_id,
            segments,
        )
        return True

    except Exception as e:
        logger.error(
            "Failed to mark segments deactivated for user %d: %s: %s",
            user_id,
            type(e).__name__,
            str(e),
        )
        return False


def clear_killswitch_segments(user_id: int, redis_client: RedisClient) -> bool:
    """Clear the kill switch segment deactivation state.

    Called when the kill switch is manually deactivated/cleared, restoring
    segments to their normal state (no longer showing kill switch badge).

    Args:
        user_id: The user's database ID.
        redis_client: RedisClient instance.

    Returns:
        True if cleared successfully, False otherwise.
    """
    try:
        key = _killswitch_segments_key(user_id)
        redis_client.delete(key)

        logger.info(
            "Cleared kill switch segment state for user %d", user_id
        )
        return True

    except Exception as e:
        logger.error(
            "Failed to clear kill switch segments for user %d: %s: %s",
            user_id,
            type(e).__name__,
            str(e),
        )
        return False


def get_killswitch_deactivated_segments(
    user_id: int, redis_client: RedisClient
) -> List[str]:
    """Get the list of segments deactivated by the kill switch.

    Returns an empty list if the kill switch is not active or if
    no segment deactivation state is stored.

    Args:
        user_id: The user's database ID.
        redis_client: RedisClient instance.

    Returns:
        List of segment names deactivated by kill switch, or empty list.
    """
    try:
        key = _killswitch_segments_key(user_id)
        value = redis_client.get(key)

        if value is None:
            return []

        segments = json.loads(value)
        return segments if isinstance(segments, list) else []

    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(
            "Invalid kill switch segments data for user %d: %s",
            user_id,
            e,
        )
        return []

    except Exception as e:
        logger.error(
            "Error reading kill switch segments for user %d: %s: %s",
            user_id,
            type(e).__name__,
            str(e),
        )
        return []
