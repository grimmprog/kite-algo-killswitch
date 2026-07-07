"""Auto-Monitor Worker for background P&L tracking and threshold proximity alerts.

Runs periodically for each user with monitoring enabled. Fetches current P&L,
compares against kill switch thresholds (daily loss, profit target, drawdown),
and pushes warning notifications via Redis PubSub when P&L is within 10% of
any threshold.

Publishes:
- monitor:threshold_warning:{user_id} — when P&L approaches a threshold
- monitor:status:{user_id} — current P&L value and distance to nearest threshold

Requirements covered:
- 10.2: Start backend P&L monitoring process on toggle
- 10.3: Stop backend P&L monitoring process on toggle
- 10.4: Push warning notification when P&L within 10% of threshold
- 10.5: Display current P&L value and distance to nearest threshold
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from src.cache.redis_client import RedisClient, get_redis_client
from src.cache.redis_keys import RedisKeys
from src.services.notification_service import check_threshold_proximity

logger = logging.getLogger(__name__)

# Redis key patterns for auto-monitor state
MONITOR_STATE_KEY = "user:{user_id}:monitor:active"
MONITOR_THRESHOLD_WARNING_CHANNEL = "monitor:threshold_warning:{user_id}"
MONITOR_STATUS_CHANNEL = "monitor:status:{user_id}"

# Proximity percentage for warning (10%)
PROXIMITY_PCT = 0.10


def _monitor_state_key(user_id: int) -> str:
    """Redis key for user's monitor active/inactive state."""
    return f"user:{user_id}:monitor:active"


def _threshold_warning_channel(user_id: int) -> str:
    """Redis PubSub channel for threshold proximity warnings."""
    return f"monitor:threshold_warning:{user_id}"


def _status_channel(user_id: int) -> str:
    """Redis PubSub channel for current monitor status."""
    return f"monitor:status:{user_id}"


class AutoMonitorWorker:
    """Background P&L monitor that tracks thresholds and pushes alerts.

    Checks a user's current P&L against configured kill switch thresholds
    and publishes status updates and warning notifications via Redis PubSub.

    Args:
        user_id: The user's database ID.
        redis_client: RedisClient instance for state and PubSub.
    """

    def __init__(self, user_id: int, redis_client: RedisClient) -> None:
        """Initialize AutoMonitorWorker.

        Args:
            user_id: The user's database ID.
            redis_client: RedisClient instance for caching and PubSub.

        Raises:
            ValueError: If user_id is invalid or redis_client is None.
        """
        if not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("user_id must be a positive integer")
        if redis_client is None:
            raise ValueError("redis_client cannot be None")

        self.user_id = user_id
        self.redis = redis_client

    def is_monitoring_active(self) -> bool:
        """Check if monitoring is enabled for this user.

        Reads the monitor state key from Redis.

        Returns:
            True if monitoring is active, False otherwise.
        """
        key = _monitor_state_key(self.user_id)
        value = self.redis.get(key)
        return value == "true"

    @staticmethod
    def activate_monitoring(user_id: int, redis_client: RedisClient) -> bool:
        """Enable monitoring for a user (store state in Redis).

        Args:
            user_id: The user's database ID.
            redis_client: RedisClient instance.

        Returns:
            True if state was set successfully.
        """
        key = _monitor_state_key(user_id)
        return redis_client.set(key, "true")

    @staticmethod
    def deactivate_monitoring(user_id: int, redis_client: RedisClient) -> bool:
        """Disable monitoring for a user (store state in Redis).

        Args:
            user_id: The user's database ID.
            redis_client: RedisClient instance.

        Returns:
            True if state was set successfully.
        """
        key = _monitor_state_key(user_id)
        return redis_client.set(key, "false")

    def get_current_pnl(self) -> Optional[float]:
        """Fetch the current P&L from the cached risk metrics in Redis.

        The risk engine worker updates user:{user_id}:risk every 2-3 seconds.
        We read the cached pnl value from there.

        Returns:
            Current P&L as float, or None if unavailable.
        """
        risk_key = RedisKeys.user_risk(self.user_id)
        pnl_str = self.redis.hget(risk_key, "pnl")

        if pnl_str is None:
            logger.debug(
                "No cached P&L found for user %d (risk key not populated yet)",
                self.user_id,
            )
            return None

        try:
            return float(pnl_str)
        except (TypeError, ValueError):
            logger.warning(
                "Non-numeric P&L value '%s' in risk cache for user %d",
                pnl_str,
                self.user_id,
            )
            return None

    def get_thresholds(self, db_session) -> Optional[Dict[str, float]]:
        """Fetch kill switch thresholds, preferring Redis cache over DB.

        First attempts to read from Redis cache (populated by settings service
        on every threshold update). Falls back to DB via SettingsService if cache
        is empty. This ensures threshold changes apply immediately (within the
        next 5-second cycle) as per Requirement 6.4.

        Args:
            db_session: SQLAlchemy session for database access (fallback).

        Returns:
            Dict with 'daily_loss', 'profit_target', 'drawdown' as absolute amounts,
            plus 'capital'. Returns None on error.
        """
        from src.services.settings_service import SettingsService

        try:
            # Try Redis cache first (updated immediately on settings change)
            cached = SettingsService.get_cached_killswitch_thresholds(self.user_id)
            if cached:
                return {
                    "daily_loss": cached.get("daily_loss_amount", 0),
                    "profit_target": cached.get("profit_target_amount", 0),
                    "drawdown": cached.get("drawdown_amount", 0),
                    "capital": cached.get("capital", 0),
                }

            # Fallback to DB query
            settings_service = SettingsService()
            thresholds_response = settings_service.get_killswitch_thresholds(
                db_session, self.user_id
            )

            return {
                "daily_loss": thresholds_response.daily_loss_amount,
                "profit_target": thresholds_response.profit_target_amount,
                "drawdown": thresholds_response.drawdown_amount,
                "capital": thresholds_response.capital,
            }
        except Exception as e:
            logger.error(
                "Failed to fetch thresholds for user %d: %s: %s",
                self.user_id,
                type(e).__name__,
                str(e),
            )
            return None

    def compute_distance_to_thresholds(
        self, current_pnl: float, thresholds: Dict[str, float]
    ) -> Dict[str, Dict[str, float]]:
        """Compute distance from current P&L to each threshold.

        For loss thresholds (daily_loss, drawdown): measured from negative P&L
        to the negative threshold level.
        For profit thresholds (profit_target): measured from positive P&L
        to the positive threshold level.

        Args:
            current_pnl: Current P&L value (negative = loss, positive = profit).
            thresholds: Dict with daily_loss, profit_target, drawdown amounts.

        Returns:
            Dict keyed by threshold name, each containing:
                - 'threshold_value': the absolute threshold amount
                - 'current_distance': absolute distance to threshold
                - 'distance_pct': distance as percentage of threshold (0-100)
                - 'is_approaching': True if P&L is on the warning side
        """
        distances = {}

        # Daily loss threshold — triggers when loss exceeds threshold
        daily_loss = thresholds.get("daily_loss", 0)
        if daily_loss > 0:
            # Current loss is abs(pnl) when pnl is negative
            current_loss = abs(min(current_pnl, 0))
            distance = max(daily_loss - current_loss, 0)
            distance_pct = (distance / daily_loss * 100) if daily_loss > 0 else 100
            distances["daily_loss"] = {
                "threshold_value": daily_loss,
                "current_distance": distance,
                "distance_pct": distance_pct,
                "is_approaching": current_pnl < 0,
            }

        # Profit target threshold — triggers when profit exceeds threshold
        profit_target = thresholds.get("profit_target", 0)
        if profit_target > 0:
            current_profit = max(current_pnl, 0)
            distance = max(profit_target - current_profit, 0)
            distance_pct = (distance / profit_target * 100) if profit_target > 0 else 100
            distances["profit_target"] = {
                "threshold_value": profit_target,
                "current_distance": distance,
                "distance_pct": distance_pct,
                "is_approaching": current_pnl > 0,
            }

        # Drawdown threshold — triggers on intra-day drawdown from peak
        drawdown = thresholds.get("drawdown", 0)
        if drawdown > 0:
            # Simplified: treat drawdown same as daily_loss for proximity detection
            current_loss = abs(min(current_pnl, 0))
            distance = max(drawdown - current_loss, 0)
            distance_pct = (distance / drawdown * 100) if drawdown > 0 else 100
            distances["drawdown"] = {
                "threshold_value": drawdown,
                "current_distance": distance,
                "distance_pct": distance_pct,
                "is_approaching": current_pnl < 0,
            }

        return distances

    def find_nearest_threshold(
        self, distances: Dict[str, Dict[str, float]]
    ) -> Tuple[str, float]:
        """Find the threshold with the smallest distance.

        Args:
            distances: Output from compute_distance_to_thresholds.

        Returns:
            Tuple of (threshold_name, distance_pct). Returns ("none", 100.0) if empty.
        """
        if not distances:
            return ("none", 100.0)

        nearest_name = "none"
        nearest_pct = 100.0

        for name, data in distances.items():
            if data["is_approaching"] and data["distance_pct"] < nearest_pct:
                nearest_pct = data["distance_pct"]
                nearest_name = name

        # If nothing is approaching, find the absolute nearest
        if nearest_name == "none":
            for name, data in distances.items():
                if data["distance_pct"] < nearest_pct:
                    nearest_pct = data["distance_pct"]
                    nearest_name = name

        return (nearest_name, nearest_pct)

    def check_proximity_warnings(
        self, current_pnl: float, thresholds: Dict[str, float]
    ) -> List[Dict[str, any]]:
        """Check if P&L is within 10% of any threshold and build warning list.

        Uses the check_threshold_proximity function from notification_service
        and additionally provides details about which thresholds are close.

        Args:
            current_pnl: Current P&L value.
            thresholds: Dict with daily_loss, profit_target, drawdown amounts.

        Returns:
            List of warning dicts for thresholds within proximity, each containing:
                - 'threshold_name': name of the threshold
                - 'threshold_value': the threshold amount
                - 'current_value': current P&L or relevant metric
                - 'distance_pct': percentage distance remaining
        """
        warnings = []

        # Check loss thresholds (daily_loss, drawdown) against negative P&L
        if current_pnl < 0:
            current_loss = abs(current_pnl)

            for threshold_name in ("daily_loss", "drawdown"):
                threshold_value = thresholds.get(threshold_name, 0)
                if threshold_value <= 0:
                    continue

                # Warning zone: within 10% of threshold
                warning_level = threshold_value * (1.0 - PROXIMITY_PCT)
                if current_loss >= warning_level:
                    distance_pct = (
                        (threshold_value - current_loss) / threshold_value * 100
                        if threshold_value > 0
                        else 0
                    )
                    warnings.append(
                        {
                            "threshold_name": threshold_name,
                            "threshold_value": threshold_value,
                            "current_value": current_loss,
                            "distance_pct": max(distance_pct, 0),
                        }
                    )

        # Check profit target threshold against positive P&L
        if current_pnl > 0:
            profit_target = thresholds.get("profit_target", 0)
            if profit_target > 0:
                warning_level = profit_target * (1.0 - PROXIMITY_PCT)
                if current_pnl >= warning_level:
                    distance_pct = (
                        (profit_target - current_pnl) / profit_target * 100
                        if profit_target > 0
                        else 0
                    )
                    warnings.append(
                        {
                            "threshold_name": "profit_target",
                            "threshold_value": profit_target,
                            "current_value": current_pnl,
                            "distance_pct": max(distance_pct, 0),
                        }
                    )

        return warnings

    def publish_status(
        self,
        current_pnl: float,
        distances: Dict[str, Dict[str, float]],
        nearest_threshold: str,
        nearest_distance_pct: float,
    ) -> bool:
        """Publish current monitor status via Redis PubSub.

        Publishes to channel monitor:status:{user_id} with the current P&L,
        distance to each threshold, and the nearest threshold info.

        Args:
            current_pnl: Current P&L value.
            distances: Distance data for all thresholds.
            nearest_threshold: Name of the nearest threshold.
            nearest_distance_pct: Distance percentage to nearest threshold.

        Returns:
            True if published successfully, False otherwise.
        """
        channel = _status_channel(self.user_id)
        payload = {
            "user_id": self.user_id,
            "current_pnl": current_pnl,
            "nearest_threshold": nearest_threshold,
            "nearest_distance_pct": round(nearest_distance_pct, 2),
            "distances": {
                name: {
                    "threshold_value": data["threshold_value"],
                    "current_distance": round(data["current_distance"], 2),
                    "distance_pct": round(data["distance_pct"], 2),
                }
                for name, data in distances.items()
            },
            "monitoring_active": True,
            "timestamp": datetime.now().isoformat(),
        }

        try:
            self.redis.client.publish(channel, json.dumps(payload))
            logger.debug(
                "Published monitor status for user %d: pnl=%.2f, nearest=%s (%.1f%%)",
                self.user_id,
                current_pnl,
                nearest_threshold,
                nearest_distance_pct,
            )
            return True
        except Exception as e:
            logger.error(
                "Failed to publish monitor status for user %d: %s",
                self.user_id,
                e,
            )
            return False

    def publish_threshold_warning(self, warnings: List[Dict]) -> bool:
        """Publish threshold proximity warnings via Redis PubSub.

        Publishes to channel monitor:threshold_warning:{user_id} when P&L
        is within 10% of any kill switch threshold.

        Args:
            warnings: List of warning dicts from check_proximity_warnings.

        Returns:
            True if published successfully, False otherwise.
        """
        if not warnings:
            return True

        channel = _threshold_warning_channel(self.user_id)
        payload = {
            "user_id": self.user_id,
            "warnings": warnings,
            "timestamp": datetime.now().isoformat(),
        }

        try:
            self.redis.client.publish(channel, json.dumps(payload))
            logger.info(
                "Published %d threshold warning(s) for user %d",
                len(warnings),
                self.user_id,
            )
            return True
        except Exception as e:
            logger.error(
                "Failed to publish threshold warning for user %d: %s",
                self.user_id,
                e,
            )
            return False

    def run_monitor_cycle(self, db_session) -> Dict:
        """Execute a single P&L monitoring cycle for this user.

        Full cycle:
        1. Check if monitoring is active
        2. Fetch current P&L from Redis risk cache
        3. Fetch kill switch thresholds from DB
        4. Compute distance to each threshold
        5. Check for proximity warnings (within 10%)
        6. Publish status update via Redis PubSub
        7. Publish threshold warnings if any

        Args:
            db_session: SQLAlchemy session for database access.

        Returns:
            Dict summarizing the cycle result:
                - "status": "success", "skipped", or "error"
                - "user_id": user ID
                - "reason": description of outcome
                - "warnings_count": number of warnings published (if success)
        """
        # Step 1: Check if monitoring is active
        if not self.is_monitoring_active():
            return {
                "status": "skipped",
                "user_id": self.user_id,
                "reason": "Monitoring inactive",
            }

        # Step 2: Fetch current P&L from Redis risk cache
        current_pnl = self.get_current_pnl()
        if current_pnl is None:
            return {
                "status": "skipped",
                "user_id": self.user_id,
                "reason": "No P&L data available in cache",
            }

        # Step 3: Fetch thresholds from DB
        thresholds = self.get_thresholds(db_session)
        if thresholds is None:
            return {
                "status": "error",
                "user_id": self.user_id,
                "reason": "Failed to fetch thresholds",
            }

        # Step 4: Compute distances to thresholds
        distances = self.compute_distance_to_thresholds(current_pnl, thresholds)

        # Step 5: Find nearest threshold
        nearest_name, nearest_pct = self.find_nearest_threshold(distances)

        # Step 6: Check proximity warnings
        warnings = self.check_proximity_warnings(current_pnl, thresholds)

        # Step 7: Publish status
        self.publish_status(current_pnl, distances, nearest_name, nearest_pct)

        # Step 8: Publish warnings if any
        if warnings:
            self.publish_threshold_warning(warnings)

        return {
            "status": "success",
            "user_id": self.user_id,
            "reason": "Monitor cycle completed",
            "warnings_count": len(warnings),
            "current_pnl": current_pnl,
            "nearest_threshold": nearest_name,
            "nearest_distance_pct": nearest_pct,
        }
