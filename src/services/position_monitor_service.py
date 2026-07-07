"""Position Monitor Service — real-time SL/Target tracking with auto-exit logic.

Tracks stop-loss, target, and trailing stop per position. Evaluates exit
conditions (EMA cross, VWAP touch, consecutive green candles, time-based)
and triggers auto-exits when conditions are met.

Implements Requirements: 7.1-7.7, 8.1-8.5
"""

import logging
from datetime import datetime, time, timezone, timedelta
from typing import Any, Dict, List, Optional

from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.database.models.position_monitor import PositionMonitorState

logger = logging.getLogger(__name__)

# IST offset: UTC+5:30
IST_OFFSET = timedelta(hours=5, minutes=30)

# Time-based exit threshold (11:30 IST)
TIME_BASED_EXIT = time(11, 30)


class MonitoredPosition(BaseModel):
    """Pydantic model representing a monitored position with computed metrics."""

    position_id: int
    symbol: str
    entry_price: float
    current_price: float
    quantity: int
    stop_loss: float
    target: float
    trailing_stop_enabled: bool
    trailing_stop_level: Optional[float] = None
    trailing_stop_distance: Optional[float] = None
    unrealized_pnl: float
    distance_to_sl_pct: float
    distance_to_target_pct: float
    status: str  # "active", "sl_hit", "target_hit", "trailing_stop_hit", "closed"


class ExitCondition(BaseModel):
    """Pydantic model representing an exit condition evaluation result."""

    name: str  # "ema_cross", "vwap_touch", "consecutive_green", "time_based"
    description: str
    is_met: bool
    details: Optional[str] = None


class MarketData(BaseModel):
    """Market data snapshot for exit condition evaluation."""

    current_price: float
    ema20: float
    vwap: float
    candles: List[Dict[str, float]]  # List of {"open": ..., "close": ..., "high": ..., "low": ...}
    current_time: Optional[datetime] = None


class PositionMonitorService:
    """Real-time SL/Target tracking with auto-exit logic.

    Provides position monitoring with P&L calculation, distance metrics,
    exit condition evaluation, trailing stop management, and auto-exit
    triggering.
    """

    def __init__(self, db: Session) -> None:
        """Initialize PositionMonitorService.

        Args:
            db: SQLAlchemy session for database operations.
        """
        if db is None:
            raise ValueError("db cannot be None")
        self.db = db

    def get_monitored_positions(self, user_id: int) -> List[MonitoredPosition]:
        """Get all active positions with live SL/Target status and computed metrics.

        Loads all active PositionMonitorState records for the user,
        computes unrealized P&L and distance percentages.

        P&L formula (long): (current_price - entry_price) × quantity
        Distance to SL: (current_price - stop_loss) / current_price × 100
        Distance to target: (target - current_price) / current_price × 100

        Args:
            user_id: The user whose positions to fetch.

        Returns:
            List of MonitoredPosition objects with computed metrics.
        """
        positions = (
            self.db.query(PositionMonitorState)
            .filter(
                PositionMonitorState.user_id == user_id,
                PositionMonitorState.status == "active",
            )
            .all()
        )

        result = []
        for pos in positions:
            current_price = pos.current_price if pos.current_price else pos.entry_price

            # Get quantity from the related trade
            quantity = pos.trade.qty if pos.trade else 1

            # Compute unrealized P&L: (current - entry) × quantity
            unrealized_pnl = (current_price - pos.entry_price) * quantity

            # Compute distance percentages (guard against zero current_price)
            if current_price > 0:
                distance_to_sl_pct = (
                    (current_price - pos.stop_loss) / current_price * 100
                )
                distance_to_target_pct = (
                    (pos.target - current_price) / current_price * 100
                )
            else:
                distance_to_sl_pct = 0.0
                distance_to_target_pct = 0.0

            result.append(
                MonitoredPosition(
                    position_id=pos.id,
                    symbol=pos.symbol,
                    entry_price=pos.entry_price,
                    current_price=current_price,
                    quantity=quantity,
                    stop_loss=pos.stop_loss,
                    target=pos.target,
                    trailing_stop_enabled=pos.trailing_stop_enabled,
                    trailing_stop_level=pos.trailing_stop_level,
                    trailing_stop_distance=pos.trailing_stop_distance,
                    unrealized_pnl=unrealized_pnl,
                    distance_to_sl_pct=distance_to_sl_pct,
                    distance_to_target_pct=distance_to_target_pct,
                    status=pos.status,
                )
            )

        return result

    def evaluate_exit_conditions(
        self, position: MonitoredPosition, market_data: MarketData
    ) -> List[ExitCondition]:
        """Evaluate all exit rules for a position given market data.

        Checks 4 exit conditions:
        1. EMA cross: close price is above EMA(20)
        2. VWAP touch: current price touches VWAP (within 0.1% tolerance)
        3. Consecutive green: 2+ consecutive green candles
        4. Time-based: current time >= 11:30 IST

        Args:
            position: The MonitoredPosition to evaluate.
            market_data: Current market data snapshot with indicators.

        Returns:
            List of ExitCondition objects with is_met boolean for each.
        """
        conditions: List[ExitCondition] = []

        # 1. EMA cross: close above EMA20
        ema_cross_met = market_data.current_price > market_data.ema20
        conditions.append(
            ExitCondition(
                name="ema_cross",
                description="Close above 20 EMA",
                is_met=ema_cross_met,
                details=(
                    f"Price {market_data.current_price:.2f} > EMA20 {market_data.ema20:.2f}"
                    if ema_cross_met
                    else f"Price {market_data.current_price:.2f} <= EMA20 {market_data.ema20:.2f}"
                ),
            )
        )

        # 2. VWAP touch: price touches VWAP (within 0.1% tolerance)
        vwap_tolerance = market_data.vwap * 0.001  # 0.1%
        vwap_touch_met = (
            abs(market_data.current_price - market_data.vwap) <= vwap_tolerance
        )
        conditions.append(
            ExitCondition(
                name="vwap_touch",
                description="Price touches VWAP",
                is_met=vwap_touch_met,
                details=(
                    f"Price {market_data.current_price:.2f} within 0.1% of VWAP {market_data.vwap:.2f}"
                    if vwap_touch_met
                    else f"Price {market_data.current_price:.2f} not at VWAP {market_data.vwap:.2f}"
                ),
            )
        )

        # 3. Consecutive green candles: 2+ consecutive green candles
        consecutive_green = self._count_consecutive_green_candles(market_data.candles)
        consecutive_green_met = consecutive_green >= 2
        conditions.append(
            ExitCondition(
                name="consecutive_green",
                description="2 consecutive green candles",
                is_met=consecutive_green_met,
                details=(
                    f"{consecutive_green} consecutive green candle(s) detected"
                ),
            )
        )

        # 4. Time-based: current time >= 11:30 IST
        current_time = market_data.current_time or datetime.now(timezone.utc)
        ist_time = (current_time + IST_OFFSET).time()
        time_based_met = ist_time >= TIME_BASED_EXIT
        conditions.append(
            ExitCondition(
                name="time_based",
                description="Time-based exit (after 11:30 IST)",
                is_met=time_based_met,
                details=(
                    f"Current IST time {ist_time.strftime('%H:%M')} >= 11:30"
                    if time_based_met
                    else f"Current IST time {ist_time.strftime('%H:%M')} < 11:30"
                ),
            )
        )

        return conditions

    def update_trailing_stop(
        self, position: MonitoredPosition, current_price: float
    ) -> Optional[float]:
        """Update trailing stop level as price moves favorably.

        Trailing stop is monotonically non-decreasing — it only moves up,
        never down. New level = current_price - (current_price × trailing_stop_distance / 100).

        Only updates if trailing_stop_enabled is True and the new level
        is higher than the existing trailing_stop_level.

        Args:
            position: The MonitoredPosition to update trailing stop for.
            current_price: The current market price.

        Returns:
            New trailing_stop_level if updated, None if unchanged or not enabled.
        """
        if not position.trailing_stop_enabled:
            return None

        if position.trailing_stop_distance is None:
            return None

        # Calculate new trailing stop level
        new_level = current_price - (
            current_price * position.trailing_stop_distance / 100
        )

        # Trailing stop is monotonically non-decreasing
        current_level = position.trailing_stop_level
        if current_level is not None and new_level <= current_level:
            return None

        # Update in database
        db_position = (
            self.db.query(PositionMonitorState)
            .filter(PositionMonitorState.id == position.position_id)
            .first()
        )

        if db_position:
            db_position.trailing_stop_level = new_level
            db_position.updated_at = datetime.now(timezone.utc)
            self.db.commit()

            logger.info(
                "Trailing stop updated for position %d: %.2f -> %.2f",
                position.position_id,
                current_level or 0.0,
                new_level,
            )

        return new_level

    def trigger_auto_exit(
        self, position_id: int, reason: str
    ) -> Dict[str, Any]:
        """Execute auto-exit for a position by updating status and returning trade data.

        Updates position status to the exit reason (sl_hit, target_hit,
        trailing_stop_hit, or closed) and returns trade execution data
        needed to place the exit order.

        Args:
            position_id: The ID of the position to exit.
            reason: The exit reason — one of "sl_hit", "target_hit",
                    "trailing_stop_hit", "closed".

        Returns:
            Dictionary with trade execution data:
                - position_id (int)
                - symbol (str)
                - entry_price (float)
                - current_price (float)
                - quantity (int)
                - exit_reason (str)
                - trade_id (int)

        Raises:
            ValueError: If position not found or reason is invalid.
        """
        valid_reasons = ("sl_hit", "target_hit", "trailing_stop_hit", "closed")
        if reason not in valid_reasons:
            raise ValueError(
                f"Exit reason must be one of: {', '.join(valid_reasons)}. Got: {reason}"
            )

        position = (
            self.db.query(PositionMonitorState)
            .filter(PositionMonitorState.id == position_id)
            .first()
        )

        if position is None:
            raise ValueError(f"Position {position_id} not found")

        if position.status != "active":
            raise ValueError(
                f"Position {position_id} is not active (current status: {position.status})"
            )

        # Update status
        position.status = reason
        position.updated_at = datetime.now(timezone.utc)
        self.db.commit()

        # Get quantity from related trade
        quantity = position.trade.qty if position.trade else 1

        logger.info(
            "Auto-exit triggered for position %d, reason: %s",
            position_id,
            reason,
        )

        return {
            "position_id": position.id,
            "symbol": position.symbol,
            "entry_price": position.entry_price,
            "current_price": position.current_price,
            "quantity": quantity,
            "exit_reason": reason,
            "trade_id": position.trade_id,
        }

    def check_sl_target(
        self, position: MonitoredPosition, current_price: float
    ) -> Optional[str]:
        """Check if current price has hit stop-loss, target, or trailing stop.

        Evaluation order:
        1. "sl_hit" if current_price <= stop_loss
        2. "target_hit" if current_price >= target
        3. "trailing_stop_hit" if trailing_stop_enabled and current_price <= trailing_stop_level
        4. None otherwise

        Args:
            position: The MonitoredPosition to check.
            current_price: The current market price.

        Returns:
            "sl_hit", "target_hit", "trailing_stop_hit", or None.
        """
        # Check stop-loss
        if current_price <= position.stop_loss:
            return "sl_hit"

        # Check target
        if current_price >= position.target:
            return "target_hit"

        # Check trailing stop
        if (
            position.trailing_stop_enabled
            and position.trailing_stop_level is not None
            and current_price <= position.trailing_stop_level
        ):
            return "trailing_stop_hit"

        return None

    @staticmethod
    def _count_consecutive_green_candles(
        candles: List[Dict[str, float]],
    ) -> int:
        """Count consecutive green candles from the most recent candle backwards.

        A candle is green if close > open.

        Args:
            candles: List of candle dictionaries with "open" and "close" keys,
                     ordered chronologically (most recent last).

        Returns:
            Number of consecutive green candles from the end of the list.
        """
        if not candles:
            return 0

        count = 0
        for candle in reversed(candles):
            if candle.get("close", 0) > candle.get("open", 0):
                count += 1
            else:
                break

        return count
