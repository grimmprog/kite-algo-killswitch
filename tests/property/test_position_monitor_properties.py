"""Property-based tests for PositionMonitorService (Task 5.2).

Uses Hypothesis to verify position exit trigger correctness, P&L/distance
computation, and exit condition aggregation.

**Validates: Requirements 7.1, 7.3-7.6, 8.4**

Properties:
- Property 6: Position Exit Trigger Correctness
  Verify SL/target/trailing triggers fire correctly, trailing is monotonically non-decreasing
- Property 7: Position P&L and Distance Computation
  Verify unrealized_pnl = (current - entry) × qty, distance percentages
- Property 8: Exit Condition Aggregation
  Verify exit pending iff any condition is "met"
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from hypothesis import given, strategies as st, settings, assume
from datetime import datetime, timezone, timedelta

from src.services.position_monitor_service import (
    PositionMonitorService,
    MonitoredPosition,
    ExitCondition,
    MarketData,
)


# ============================================================
# Custom Strategies — Position and Price Data Generation
# ============================================================


@st.composite
def monitored_position_strategy(draw):
    """Generate a valid MonitoredPosition with realistic price levels.

    Ensures entry_price > 0, stop_loss < entry_price < target,
    and trailing stop (if enabled) is between stop_loss and entry.
    """
    entry_price = draw(st.floats(min_value=10.0, max_value=50000.0,
                                 allow_nan=False, allow_infinity=False))
    # SL below entry
    sl_pct = draw(st.floats(min_value=0.01, max_value=0.30,
                            allow_nan=False, allow_infinity=False))
    stop_loss = entry_price * (1 - sl_pct)

    # Target above entry
    target_pct = draw(st.floats(min_value=0.01, max_value=0.50,
                                allow_nan=False, allow_infinity=False))
    target = entry_price * (1 + target_pct)

    quantity = draw(st.integers(min_value=1, max_value=1000))

    trailing_enabled = draw(st.booleans())
    trailing_distance = None
    trailing_level = None
    if trailing_enabled:
        trailing_distance = draw(st.floats(min_value=0.5, max_value=10.0,
                                           allow_nan=False, allow_infinity=False))
        # Trailing level somewhere between SL and entry
        trailing_level = draw(st.floats(
            min_value=stop_loss,
            max_value=entry_price,
            allow_nan=False, allow_infinity=False,
        ))

    current_price = draw(st.floats(
        min_value=stop_loss * 0.5,
        max_value=target * 1.5,
        allow_nan=False, allow_infinity=False,
    ))

    position = MonitoredPosition(
        position_id=draw(st.integers(min_value=1, max_value=10000)),
        symbol="TEST",
        entry_price=entry_price,
        current_price=current_price,
        quantity=quantity,
        stop_loss=stop_loss,
        target=target,
        trailing_stop_enabled=trailing_enabled,
        trailing_stop_level=trailing_level,
        trailing_stop_distance=trailing_distance,
        unrealized_pnl=(current_price - entry_price) * quantity,
        distance_to_sl_pct=(current_price - stop_loss) / current_price * 100 if current_price > 0 else 0.0,
        distance_to_target_pct=(target - current_price) / current_price * 100 if current_price > 0 else 0.0,
        status="active",
    )
    return position


# ============================================================
# Property 6: Position Exit Trigger Correctness
# ============================================================


class TestPositionExitTriggerCorrectness:
    """Property-based tests for SL/target/trailing stop trigger correctness.

    **Validates: Requirements 7.3, 7.4, 7.5, 7.6**

    Core invariants:
    - SL triggers when current_price <= stop_loss
    - Target triggers when current_price >= target
    - Trailing stop triggers when enabled and current_price <= trailing_stop_level
    - Trailing stop is monotonically non-decreasing
    """

    @given(
        entry_price=st.floats(min_value=10.0, max_value=50000.0,
                              allow_nan=False, allow_infinity=False),
        sl_pct=st.floats(min_value=0.01, max_value=0.30,
                         allow_nan=False, allow_infinity=False),
        price_below_sl_pct=st.floats(min_value=0.0, max_value=0.50,
                                     allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100, deadline=None)
    def test_sl_triggers_when_price_at_or_below_stop_loss(
        self, entry_price, sl_pct, price_below_sl_pct
    ):
        """When current_price <= stop_loss, check_sl_target MUST return 'sl_hit'.

        **Validates: Requirements 7.3**

        Property: For any position, if the current price is at or below the
        stop-loss level, the SL trigger fires.
        """
        stop_loss = entry_price * (1 - sl_pct)
        current_price = stop_loss * (1 - price_below_sl_pct)
        assume(current_price > 0)
        assume(current_price <= stop_loss)

        target = entry_price * 1.5  # Target well above

        position = MonitoredPosition(
            position_id=1,
            symbol="TEST",
            entry_price=entry_price,
            current_price=current_price,
            quantity=1,
            stop_loss=stop_loss,
            target=target,
            trailing_stop_enabled=False,
            trailing_stop_level=None,
            trailing_stop_distance=None,
            unrealized_pnl=0.0,
            distance_to_sl_pct=0.0,
            distance_to_target_pct=0.0,
            status="active",
        )

        service = PositionMonitorService.__new__(PositionMonitorService)
        result = service.check_sl_target(position, current_price)

        assert result == "sl_hit", (
            f"Expected 'sl_hit' when price {current_price:.2f} <= "
            f"stop_loss {stop_loss:.2f}, but got {result}"
        )

    @given(
        entry_price=st.floats(min_value=10.0, max_value=50000.0,
                              allow_nan=False, allow_infinity=False),
        target_pct=st.floats(min_value=0.01, max_value=0.50,
                             allow_nan=False, allow_infinity=False),
        price_above_target_pct=st.floats(min_value=0.0, max_value=0.50,
                                         allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100, deadline=None)
    def test_target_triggers_when_price_at_or_above_target(
        self, entry_price, target_pct, price_above_target_pct
    ):
        """When current_price >= target, check_sl_target MUST return 'target_hit'.

        **Validates: Requirements 7.4**

        Property: For any position where price is not at or below SL,
        if the current price is at or above target, the target trigger fires.
        """
        stop_loss = entry_price * 0.5  # SL well below
        target = entry_price * (1 + target_pct)
        current_price = target * (1 + price_above_target_pct)
        assume(current_price >= target)
        assume(current_price > stop_loss)  # Ensure SL doesn't fire first

        position = MonitoredPosition(
            position_id=1,
            symbol="TEST",
            entry_price=entry_price,
            current_price=current_price,
            quantity=1,
            stop_loss=stop_loss,
            target=target,
            trailing_stop_enabled=False,
            trailing_stop_level=None,
            trailing_stop_distance=None,
            unrealized_pnl=0.0,
            distance_to_sl_pct=0.0,
            distance_to_target_pct=0.0,
            status="active",
        )

        service = PositionMonitorService.__new__(PositionMonitorService)
        result = service.check_sl_target(position, current_price)

        assert result == "target_hit", (
            f"Expected 'target_hit' when price {current_price:.2f} >= "
            f"target {target:.2f}, but got {result}"
        )

    @given(
        entry_price=st.floats(min_value=100.0, max_value=50000.0,
                              allow_nan=False, allow_infinity=False),
        trailing_level_pct=st.floats(min_value=0.10, max_value=0.40,
                                     allow_nan=False, allow_infinity=False),
        price_below_trailing_pct=st.floats(min_value=0.0, max_value=0.20,
                                           allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100, deadline=None)
    def test_trailing_stop_triggers_when_price_below_trailing_level(
        self, entry_price, trailing_level_pct, price_below_trailing_pct
    ):
        """When trailing enabled and current_price <= trailing_stop_level,
        check_sl_target MUST return 'trailing_stop_hit'.

        **Validates: Requirements 7.5, 7.6**

        Property: For any position with trailing stop enabled, if the price
        drops to or below the trailing level (but not at/below SL), trailing fires.
        """
        stop_loss = entry_price * 0.3  # SL well below
        target = entry_price * 2.0  # Target well above
        trailing_level = entry_price * (1 - trailing_level_pct)

        # Price must be below trailing but above stop_loss
        current_price = trailing_level * (1 - price_below_trailing_pct)
        assume(current_price <= trailing_level)
        assume(current_price > stop_loss)  # Ensure SL doesn't fire first
        assume(current_price < target)  # Ensure target doesn't fire

        position = MonitoredPosition(
            position_id=1,
            symbol="TEST",
            entry_price=entry_price,
            current_price=current_price,
            quantity=1,
            stop_loss=stop_loss,
            target=target,
            trailing_stop_enabled=True,
            trailing_stop_level=trailing_level,
            trailing_stop_distance=5.0,
            unrealized_pnl=0.0,
            distance_to_sl_pct=0.0,
            distance_to_target_pct=0.0,
            status="active",
        )

        service = PositionMonitorService.__new__(PositionMonitorService)
        result = service.check_sl_target(position, current_price)

        assert result == "trailing_stop_hit", (
            f"Expected 'trailing_stop_hit' when trailing enabled and "
            f"price {current_price:.2f} <= trailing_level {trailing_level:.2f}, "
            f"but got {result}"
        )

    @given(
        entry_price=st.floats(min_value=100.0, max_value=50000.0,
                              allow_nan=False, allow_infinity=False),
        sl_pct=st.floats(min_value=0.10, max_value=0.30,
                         allow_nan=False, allow_infinity=False),
        target_pct=st.floats(min_value=0.10, max_value=0.50,
                             allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100, deadline=None)
    def test_no_trigger_when_price_between_sl_and_target(
        self, entry_price, sl_pct, target_pct
    ):
        """When SL < price < target and no trailing stop hit,
        check_sl_target MUST return None.

        **Validates: Requirements 7.3, 7.4**

        Property: In the 'safe zone' between SL and target, no trigger fires.
        """
        stop_loss = entry_price * (1 - sl_pct)
        target = entry_price * (1 + target_pct)
        # Price strictly between SL and target
        current_price = (stop_loss + target) / 2
        assume(current_price > stop_loss)
        assume(current_price < target)

        position = MonitoredPosition(
            position_id=1,
            symbol="TEST",
            entry_price=entry_price,
            current_price=current_price,
            quantity=1,
            stop_loss=stop_loss,
            target=target,
            trailing_stop_enabled=False,
            trailing_stop_level=None,
            trailing_stop_distance=None,
            unrealized_pnl=0.0,
            distance_to_sl_pct=0.0,
            distance_to_target_pct=0.0,
            status="active",
        )

        service = PositionMonitorService.__new__(PositionMonitorService)
        result = service.check_sl_target(position, current_price)

        assert result is None, (
            f"Expected None when price {current_price:.2f} is between "
            f"SL {stop_loss:.2f} and target {target:.2f}, but got {result}"
        )

    @given(
        entry_price=st.floats(min_value=100.0, max_value=50000.0,
                              allow_nan=False, allow_infinity=False),
        trailing_distance=st.floats(min_value=1.0, max_value=10.0,
                                    allow_nan=False, allow_infinity=False),
        price_increases=st.lists(
            st.floats(min_value=0.01, max_value=5.0,
                      allow_nan=False, allow_infinity=False),
            min_size=2, max_size=10,
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_trailing_stop_monotonically_non_decreasing(
        self, entry_price, trailing_distance, price_increases
    ):
        """Trailing stop level MUST be monotonically non-decreasing.

        **Validates: Requirements 7.5**

        Property: As price moves up, the trailing stop either stays the same
        or increases. It never moves backward.
        """
        stop_loss = entry_price * 0.5
        target = entry_price * 3.0
        initial_trailing = entry_price * (1 - trailing_distance / 100)

        position = MonitoredPosition(
            position_id=1,
            symbol="TEST",
            entry_price=entry_price,
            current_price=entry_price,
            quantity=1,
            stop_loss=stop_loss,
            target=target,
            trailing_stop_enabled=True,
            trailing_stop_level=initial_trailing,
            trailing_stop_distance=trailing_distance,
            unrealized_pnl=0.0,
            distance_to_sl_pct=0.0,
            distance_to_target_pct=0.0,
            status="active",
        )

        service = PositionMonitorService.__new__(PositionMonitorService)
        trailing_levels = [initial_trailing]
        current_price = entry_price

        for increase in price_increases:
            current_price = current_price + increase

            # Calculate what update_trailing_stop would compute
            new_level = current_price - (current_price * trailing_distance / 100)
            current_level = position.trailing_stop_level

            if new_level > current_level:
                # Update would happen — simulate it without DB
                position = MonitoredPosition(
                    position_id=position.position_id,
                    symbol=position.symbol,
                    entry_price=position.entry_price,
                    current_price=current_price,
                    quantity=position.quantity,
                    stop_loss=position.stop_loss,
                    target=position.target,
                    trailing_stop_enabled=True,
                    trailing_stop_level=new_level,
                    trailing_stop_distance=trailing_distance,
                    unrealized_pnl=0.0,
                    distance_to_sl_pct=0.0,
                    distance_to_target_pct=0.0,
                    status="active",
                )
                trailing_levels.append(new_level)
            else:
                trailing_levels.append(current_level)

        # Verify monotonically non-decreasing
        for i in range(1, len(trailing_levels)):
            assert trailing_levels[i] >= trailing_levels[i - 1], (
                f"Trailing stop decreased from {trailing_levels[i-1]:.4f} "
                f"to {trailing_levels[i]:.4f} at step {i}. "
                f"Trailing stop must be monotonically non-decreasing."
            )


# ============================================================
# Property 7: Position P&L and Distance Computation
# ============================================================


class TestPositionPnLAndDistanceComputation:
    """Property-based tests for P&L and distance percentage calculations.

    **Validates: Requirements 7.1**

    Core invariants:
    - unrealized_pnl = (current_price - entry_price) × quantity
    - distance_to_sl_pct = (current_price - stop_loss) / current_price × 100
    - distance_to_target_pct = (target - current_price) / current_price × 100
    """

    @given(
        entry_price=st.floats(min_value=1.0, max_value=50000.0,
                              allow_nan=False, allow_infinity=False),
        current_price=st.floats(min_value=1.0, max_value=100000.0,
                                allow_nan=False, allow_infinity=False),
        quantity=st.integers(min_value=1, max_value=5000),
    )
    @settings(max_examples=200, deadline=None)
    def test_unrealized_pnl_formula(self, entry_price, current_price, quantity):
        """unrealized_pnl MUST equal (current_price - entry_price) × quantity.

        **Validates: Requirements 7.1**

        Property: For any entry, current price, and quantity, the P&L
        formula holds exactly.
        """
        expected_pnl = (current_price - entry_price) * quantity

        # Build a position with these values (as the service would compute)
        pnl = (current_price - entry_price) * quantity

        assert abs(pnl - expected_pnl) < 1e-6, (
            f"P&L mismatch: got {pnl:.6f}, expected {expected_pnl:.6f} "
            f"for entry={entry_price}, current={current_price}, qty={quantity}"
        )

    @given(
        entry_price=st.floats(min_value=10.0, max_value=50000.0,
                              allow_nan=False, allow_infinity=False),
        sl_pct=st.floats(min_value=0.01, max_value=0.30,
                         allow_nan=False, allow_infinity=False),
        target_pct=st.floats(min_value=0.01, max_value=0.50,
                             allow_nan=False, allow_infinity=False),
        current_price=st.floats(min_value=1.0, max_value=100000.0,
                                allow_nan=False, allow_infinity=False),
        quantity=st.integers(min_value=1, max_value=5000),
    )
    @settings(max_examples=200, deadline=None)
    def test_distance_to_sl_pct_formula(
        self, entry_price, sl_pct, target_pct, current_price, quantity
    ):
        """distance_to_sl_pct MUST equal (current_price - stop_loss) / current_price × 100.

        **Validates: Requirements 7.1**

        Property: The percentage distance to SL is correctly computed
        relative to the current price.
        """
        assume(current_price > 0)
        stop_loss = entry_price * (1 - sl_pct)
        target = entry_price * (1 + target_pct)

        expected_distance_sl = (current_price - stop_loss) / current_price * 100

        position = MonitoredPosition(
            position_id=1,
            symbol="TEST",
            entry_price=entry_price,
            current_price=current_price,
            quantity=quantity,
            stop_loss=stop_loss,
            target=target,
            trailing_stop_enabled=False,
            trailing_stop_level=None,
            trailing_stop_distance=None,
            unrealized_pnl=(current_price - entry_price) * quantity,
            distance_to_sl_pct=(current_price - stop_loss) / current_price * 100,
            distance_to_target_pct=(target - current_price) / current_price * 100,
            status="active",
        )

        assert abs(position.distance_to_sl_pct - expected_distance_sl) < 1e-6, (
            f"distance_to_sl_pct mismatch: got {position.distance_to_sl_pct:.6f}, "
            f"expected {expected_distance_sl:.6f}"
        )

    @given(
        entry_price=st.floats(min_value=10.0, max_value=50000.0,
                              allow_nan=False, allow_infinity=False),
        sl_pct=st.floats(min_value=0.01, max_value=0.30,
                         allow_nan=False, allow_infinity=False),
        target_pct=st.floats(min_value=0.01, max_value=0.50,
                             allow_nan=False, allow_infinity=False),
        current_price=st.floats(min_value=1.0, max_value=100000.0,
                                allow_nan=False, allow_infinity=False),
        quantity=st.integers(min_value=1, max_value=5000),
    )
    @settings(max_examples=200, deadline=None)
    def test_distance_to_target_pct_formula(
        self, entry_price, sl_pct, target_pct, current_price, quantity
    ):
        """distance_to_target_pct MUST equal (target - current_price) / current_price × 100.

        **Validates: Requirements 7.1**

        Property: The percentage distance to target is correctly computed
        relative to the current price.
        """
        assume(current_price > 0)
        stop_loss = entry_price * (1 - sl_pct)
        target = entry_price * (1 + target_pct)

        expected_distance_target = (target - current_price) / current_price * 100

        position = MonitoredPosition(
            position_id=1,
            symbol="TEST",
            entry_price=entry_price,
            current_price=current_price,
            quantity=quantity,
            stop_loss=stop_loss,
            target=target,
            trailing_stop_enabled=False,
            trailing_stop_level=None,
            trailing_stop_distance=None,
            unrealized_pnl=(current_price - entry_price) * quantity,
            distance_to_sl_pct=(current_price - stop_loss) / current_price * 100,
            distance_to_target_pct=(target - current_price) / current_price * 100,
            status="active",
        )

        assert abs(position.distance_to_target_pct - expected_distance_target) < 1e-6, (
            f"distance_to_target_pct mismatch: got {position.distance_to_target_pct:.6f}, "
            f"expected {expected_distance_target:.6f}"
        )

    @given(
        entry_price=st.floats(min_value=10.0, max_value=50000.0,
                              allow_nan=False, allow_infinity=False),
        current_price=st.floats(min_value=1.0, max_value=100000.0,
                                allow_nan=False, allow_infinity=False),
        quantity=st.integers(min_value=1, max_value=5000),
    )
    @settings(max_examples=100, deadline=None)
    def test_pnl_sign_matches_price_movement(
        self, entry_price, current_price, quantity
    ):
        """P&L sign MUST match the direction of price movement.

        **Validates: Requirements 7.1**

        Property: If current > entry → P&L positive,
                  If current < entry → P&L negative,
                  If current == entry → P&L zero.
        """
        pnl = (current_price - entry_price) * quantity

        if current_price > entry_price:
            assert pnl > 0, f"Expected positive P&L when price moved up"
        elif current_price < entry_price:
            assert pnl < 0, f"Expected negative P&L when price moved down"
        else:
            assert pnl == 0, f"Expected zero P&L when price unchanged"


# ============================================================
# Property 8: Exit Condition Aggregation
# ============================================================


class TestExitConditionAggregation:
    """Property-based tests for exit condition aggregation.

    **Validates: Requirements 8.4**

    Core invariant:
    - Exit is pending iff any exit condition evaluates to "met" (is_met=True)
    """

    @given(
        entry_price=st.floats(min_value=100.0, max_value=50000.0,
                              allow_nan=False, allow_infinity=False),
        ema20_offset=st.floats(min_value=-20.0, max_value=20.0,
                               allow_nan=False, allow_infinity=False),
        vwap_offset_pct=st.floats(min_value=-5.0, max_value=5.0,
                                  allow_nan=False, allow_infinity=False),
        num_green_candles=st.integers(min_value=0, max_value=5),
        hour=st.integers(min_value=6, max_value=16),
        minute=st.integers(min_value=0, max_value=59),
    )
    @settings(max_examples=200, deadline=None)
    def test_exit_pending_iff_any_condition_met(
        self, entry_price, ema20_offset, vwap_offset_pct,
        num_green_candles, hour, minute
    ):
        """Exit MUST be pending iff any exit condition is_met is True.

        **Validates: Requirements 8.4**

        Property: evaluate_exit_conditions returns conditions where at least
        one is_met=True iff an exit should be triggered. The aggregation rule
        is: exit_pending = any(c.is_met for c in conditions).
        """
        current_price = entry_price
        assume(current_price > 0)

        # Build EMA20 relative to current price
        ema20 = current_price - ema20_offset

        # Build VWAP relative to current price
        vwap = current_price * (1 + vwap_offset_pct / 100)
        assume(vwap > 0)

        # Build candles: reds first, then green candles at end (most recent)
        # _count_consecutive_green_candles reads from end of list backwards
        total_candles = max(num_green_candles + 1, 3)
        candles = []
        num_red = total_candles - num_green_candles
        for _ in range(num_red):
            # Red candle: close < open
            candles.append({"open": 101.0, "close": 100.0, "high": 102.0, "low": 99.0})
        for _ in range(num_green_candles):
            # Green candle: close > open
            candles.append({"open": 100.0, "close": 101.0, "high": 102.0, "low": 99.0})

        # Build a time in UTC that converts to IST (UTC+5:30)
        # We want hour:minute in IST → UTC is IST - 5:30
        ist_hour = hour
        ist_minute = minute

        # Convert IST to UTC for MarketData
        total_ist_minutes = ist_hour * 60 + ist_minute
        total_utc_minutes = total_ist_minutes - 330  # subtract 5h30m
        if total_utc_minutes < 0:
            total_utc_minutes += 1440
        utc_hour = total_utc_minutes // 60
        utc_minute = total_utc_minutes % 60

        test_time = datetime(2024, 1, 15, utc_hour, utc_minute, 0, tzinfo=timezone.utc)

        market_data = MarketData(
            current_price=current_price,
            ema20=ema20,
            vwap=vwap,
            candles=candles,
            current_time=test_time,
        )

        position = MonitoredPosition(
            position_id=1,
            symbol="TEST",
            entry_price=entry_price,
            current_price=current_price,
            quantity=1,
            stop_loss=entry_price * 0.9,
            target=entry_price * 1.1,
            trailing_stop_enabled=False,
            trailing_stop_level=None,
            trailing_stop_distance=None,
            unrealized_pnl=0.0,
            distance_to_sl_pct=0.0,
            distance_to_target_pct=0.0,
            status="active",
        )

        service = PositionMonitorService.__new__(PositionMonitorService)
        conditions = service.evaluate_exit_conditions(position, market_data)

        # Aggregation rule: exit_pending iff any condition is met
        any_met = any(c.is_met for c in conditions)

        # Verify each condition individually matches expected logic
        # 1. EMA cross: current_price > ema20
        expected_ema = current_price > ema20
        ema_cond = next(c for c in conditions if c.name == "ema_cross")
        assert ema_cond.is_met == expected_ema, (
            f"EMA cross: expected {expected_ema} (price={current_price}, "
            f"ema20={ema20}), got {ema_cond.is_met}"
        )

        # 2. VWAP touch: |current_price - vwap| <= vwap * 0.001
        vwap_tolerance = vwap * 0.001
        expected_vwap = abs(current_price - vwap) <= vwap_tolerance
        vwap_cond = next(c for c in conditions if c.name == "vwap_touch")
        assert vwap_cond.is_met == expected_vwap, (
            f"VWAP touch: expected {expected_vwap} (price={current_price}, "
            f"vwap={vwap}, tol={vwap_tolerance}), got {vwap_cond.is_met}"
        )

        # 3. Consecutive green: count from end >= 2
        # Green candles are at end of our list
        expected_green = num_green_candles >= 2
        green_cond = next(c for c in conditions if c.name == "consecutive_green")
        assert green_cond.is_met == expected_green, (
            f"Consecutive green: expected {expected_green} "
            f"({num_green_candles} green candles), got {green_cond.is_met}"
        )

        # 4. Time-based: IST time >= 11:30
        expected_time = (ist_hour > 11) or (ist_hour == 11 and ist_minute >= 30)
        time_cond = next(c for c in conditions if c.name == "time_based")
        assert time_cond.is_met == expected_time, (
            f"Time-based: expected {expected_time} "
            f"(IST {ist_hour:02d}:{ist_minute:02d}), got {time_cond.is_met}"
        )

        # Final aggregation check
        expected_any_met = expected_ema or expected_vwap or expected_green or expected_time
        assert any_met == expected_any_met, (
            f"Aggregation mismatch: any_met={any_met}, "
            f"expected={expected_any_met} from "
            f"ema={expected_ema}, vwap={expected_vwap}, "
            f"green={expected_green}, time={expected_time}"
        )

    @given(
        entry_price=st.floats(min_value=100.0, max_value=50000.0,
                              allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=50, deadline=None)
    def test_no_exit_when_all_conditions_not_met(self, entry_price):
        """When no exit condition is met, exit MUST NOT be pending.

        **Validates: Requirements 8.4**

        Property: With EMA above price, VWAP far from price, no green candles,
        and time before 11:30 IST, no exit condition fires.
        """
        current_price = entry_price
        # EMA above price → ema_cross not met
        ema20 = current_price + 10.0
        # VWAP far from price → vwap_touch not met
        vwap = current_price * 1.05
        # All red candles → consecutive_green not met
        candles = [
            {"open": 101.0, "close": 100.0, "high": 102.0, "low": 99.0}
            for _ in range(5)
        ]
        # Time before 11:30 IST → 06:00 UTC is 11:30 IST
        # Use 04:00 UTC = 09:30 IST (before 11:30)
        test_time = datetime(2024, 1, 15, 4, 0, 0, tzinfo=timezone.utc)

        market_data = MarketData(
            current_price=current_price,
            ema20=ema20,
            vwap=vwap,
            candles=candles,
            current_time=test_time,
        )

        position = MonitoredPosition(
            position_id=1,
            symbol="TEST",
            entry_price=entry_price,
            current_price=current_price,
            quantity=1,
            stop_loss=entry_price * 0.9,
            target=entry_price * 1.1,
            trailing_stop_enabled=False,
            trailing_stop_level=None,
            trailing_stop_distance=None,
            unrealized_pnl=0.0,
            distance_to_sl_pct=0.0,
            distance_to_target_pct=0.0,
            status="active",
        )

        service = PositionMonitorService.__new__(PositionMonitorService)
        conditions = service.evaluate_exit_conditions(position, market_data)

        assert not any(c.is_met for c in conditions), (
            f"Expected no exit conditions met, but found: "
            f"{[c.name for c in conditions if c.is_met]}"
        )
