"""Notification Service — manages notification creation, storage, and WebSocket delivery.

Creates notifications, persists them to the database, and pushes real-time
updates via Redis PubSub for WebSocket relay to connected clients.

Feed retention: max 100 most recent notifications in the feed query.
Full history is retained in the database for paginated access.

Also provides threshold proximity checking for kill switch warnings:
a warning is triggered iff current P&L is within 10% of any threshold.

Implements Requirements: 10.4, 10.5, 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from src.cache.redis_client import RedisClient
from src.database.models.notification import Notification

logger = logging.getLogger(__name__)

# Redis PubSub channel prefix for user notifications
NOTIFICATION_CHANNEL_PREFIX = "notifications"


def _notification_channel(user_id: int) -> str:
    """Build the Redis PubSub channel name for a user's notifications.

    Args:
        user_id: The user's database ID.

    Returns:
        Channel name string, e.g. "notifications:42"
    """
    return f"{NOTIFICATION_CHANNEL_PREFIX}:{user_id}"


class NotificationService:
    """Creates and delivers notifications via WebSocket (Redis PubSub).

    Provides push_notification for creating and broadcasting new notifications,
    get_recent for the dashboard feed (max 100, reverse chronological),
    get_all for paginated full history, and mark_read for read state updates.
    """

    def __init__(self, db: Session, redis_client: RedisClient) -> None:
        """Initialize NotificationService.

        Args:
            db: SQLAlchemy session for database operations.
            redis_client: RedisClient instance for PubSub broadcasting.
        """
        if db is None:
            raise ValueError("db cannot be None")
        if redis_client is None:
            raise ValueError("redis_client cannot be None")

        self.db = db
        self.redis = redis_client

    def push_notification(
        self,
        user_id: int,
        severity: str,
        title: str,
        message: str,
        category: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Notification:
        """Create a notification record and push it via Redis PubSub.

        Persists the notification to the database and publishes a JSON
        payload to the user's Redis PubSub channel for WebSocket relay.

        Args:
            user_id: The user who will receive this notification.
            severity: Notification severity level ("info", "warning", "critical").
            title: Short notification title.
            message: Full notification message text.
            category: Notification category ("signal", "trade", "killswitch",
                      "threshold", "ai", "system").
            metadata: Optional additional metadata dict (e.g., signal_id, trade details).

        Returns:
            The created Notification ORM instance.

        Raises:
            ValueError: If severity or category values are invalid (via model validators).
        """
        notification = Notification(
            user_id=user_id,
            severity=severity,
            title=title,
            message=message,
            category=category,
            metadata_json=metadata,
        )

        self.db.add(notification)
        self.db.commit()
        self.db.refresh(notification)

        # Build payload for WebSocket push
        payload = {
            "id": notification.id,
            "user_id": notification.user_id,
            "severity": notification.severity,
            "title": notification.title,
            "message": notification.message,
            "category": notification.category,
            "is_read": notification.is_read,
            "metadata": notification.metadata_json,
            "created_at": notification.created_at.isoformat()
            if notification.created_at
            else None,
        }

        # Publish to Redis PubSub channel for WebSocket relay
        channel = _notification_channel(user_id)
        try:
            self.redis.client.publish(channel, json.dumps(payload))
            logger.info(
                "Notification %d pushed to channel '%s' for user %d",
                notification.id,
                channel,
                user_id,
            )
        except Exception as e:
            # Log but don't fail — notification is already persisted in DB
            logger.error(
                "Failed to publish notification %d to Redis PubSub: %s",
                notification.id,
                e,
            )

        return notification

    def get_recent(
        self,
        user_id: int,
        limit: int = 100,
    ) -> List[Notification]:
        """Get most recent notifications for the dashboard feed.

        Returns notifications ordered by created_at descending (reverse
        chronological), limited to the specified count. Default limit is
        100, matching the feed retention requirement.

        Args:
            user_id: The user to fetch notifications for.
            limit: Maximum number of notifications to return (default 100).

        Returns:
            List of Notification ORM instances, newest first.
        """
        notifications = (
            self.db.query(Notification)
            .filter(Notification.user_id == user_id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
            .all()
        )

        return notifications

    def get_all(
        self,
        user_id: int,
        offset: int = 0,
        limit: int = 50,
    ) -> Tuple[List[Notification], int]:
        """Get paginated notification history with total count.

        Returns full notification history from the database with pagination
        support. Ordered by created_at descending (reverse chronological).

        Args:
            user_id: The user to fetch notifications for.
            offset: Number of records to skip (for pagination).
            limit: Maximum number of records to return per page (default 50).

        Returns:
            Tuple of (notifications list, total count).
        """
        query = self.db.query(Notification).filter(
            Notification.user_id == user_id
        )

        total = query.count()

        notifications = (
            query.order_by(Notification.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        return notifications, total

    def mark_read(
        self,
        user_id: int,
        notification_id: int,
    ) -> Notification:
        """Mark a notification as read.

        Sets is_read=True for the specified notification after verifying
        ownership (notification belongs to the given user).

        Args:
            user_id: The user who owns the notification (ownership check).
            notification_id: The ID of the notification to mark as read.

        Returns:
            The updated Notification ORM instance.

        Raises:
            ValueError: If notification not found or not owned by user.
        """
        notification = (
            self.db.query(Notification)
            .filter(Notification.id == notification_id)
            .first()
        )

        if notification is None:
            raise ValueError(f"Notification {notification_id} not found")

        if notification.user_id != user_id:
            raise ValueError(
                f"Notification {notification_id} does not belong to user {user_id}"
            )

        notification.is_read = True
        self.db.commit()
        self.db.refresh(notification)

        logger.info(
            "Notification %d marked as read for user %d",
            notification_id,
            user_id,
        )

        return notification


def check_threshold_proximity(
    current_pnl: float,
    thresholds: List[float],
    proximity_pct: float = 0.10,
) -> bool:
    """Check if current P&L is within a proximity percentage of any threshold.

    A threshold proximity warning should be triggered when the current P&L
    is within 10% (default) of any kill switch threshold value. This checks
    both loss thresholds (negative P&L approaching negative thresholds) and
    profit thresholds (positive P&L approaching positive thresholds).

    The check is: for any threshold T, if abs(T) > 0, warning iff
    abs(current_pnl) >= abs(T) * (1 - proximity_pct).

    This means we warn when P&L has reached at least 90% of the threshold
    (i.e., it is within the last 10% before hitting the threshold).

    Args:
        current_pnl: The user's current day P&L value (can be negative for loss).
        thresholds: List of threshold values to check against. Loss thresholds
                    should be positive values representing the absolute loss limit.
                    Profit thresholds should be positive values representing the
                    profit target.
        proximity_pct: The proximity percentage (default 0.10 = 10%).

    Returns:
        True if current_pnl is within proximity_pct of any threshold, False otherwise.

    Implements Requirements: 10.4, 10.5
    """
    if not thresholds:
        return False

    abs_pnl = abs(current_pnl)

    for threshold in thresholds:
        if threshold <= 0:
            continue
        # Warning zone starts at threshold * (1 - proximity_pct)
        warning_level = threshold * (1.0 - proximity_pct)
        if abs_pnl >= warning_level:
            return True

    return False
