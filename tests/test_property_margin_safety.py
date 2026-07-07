"""Property-based tests for margin safety property (Task 23.5).

Uses Hypothesis to verify that the risk engine's threshold checking
correctly identifies margin breaches: when margin_used > 90% of capital,
the kill switch should trigger; when margin_used <= 90% of capital,
trading is allowed.

**Validates: Requirements 1.4.4, 1.4.8, 6.3.5**

Sub-tasks:
- 23.5.1: Generate random trades (varying positions and capital)
- 23.5.2: Execute trades (run risk engine threshold checking)
- 23.5.3: Verify margin constraint (margin > 90% triggers, margin <= 90% allows)
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock
from hypothesis import given, strategies as st, settings, assume
from dataclasses import dataclass
from typing import List, Dict

from src.workers.risk_engine_worker import RiskEngineWorker


# ============================================================
# 23.5.1: Custom Strategies - Generate Random Trade Scenarios
# ============================================================

VALID_SYMBOLS = [
    "NIFTY23DEC21000CE",
    "NIFTY23DEC21000PE",
    "BANKNIFTY23DEC45000CE",
    "BANKNIFTY23DEC45000PE",
    "RELIANCE",
    "TCS",
    "INFY",
    "HDFCBANK",
]

VALID_EXCHANGES = ["NSE", "NFO", "BSE", "BFO"]


@dataclass
class TradeScenario:
    """Generated trade scenario for margin safety tests."""

    capital: float
    daily_loss_limit_pct: float
    positions: List[Dict]


def position_with_margin_strategy():
    """Generate a single position with margin and P&L values."""
    return st.fixed_dictionaries({
        "tradingsymbol": st.sampled_from(VALID_SYMBOLS),
        "exchange": st.sampled_from(VALID_EXCHANGES),
        "quantity": st.integers(min_value=1, max_value=500),
        "pnl": st.floats(min_value=-5000.0, max_value=5000.0, allow_nan=False, allow_infinity=False),
        "margin": st.floats(min_value=0.0, max_value=500000.0, allow_nan=False, allow_infinity=False),
        "delta": st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        "gamma": st.floats(min_value=0.0, max_value=0.1, allow_nan=False, allow_infinity=False),
        "vega": st.floats(min_value=-500.0, max_value=500.0, allow_nan=False, allow_infinity=False),
    })


def trade_scenario_strategy():
    """Generate a complete trade scenario with capital and positions."""
    return st.builds(
        TradeScenario,
        capital=st.floats(min_value=100000.0, max_value=10000000.0, allow_nan=False, allow_infinity=False),
        daily_loss_limit_pct=st.floats(min_value=1.0, max_value=10.0, allow_nan=False, allow_infinity=False),
        positions=st.lists(position_with_margin_strategy(), min_size=1, max_size=10),
    )


# ============================================================
# Test Infrastructure
# ============================================================


def create_risk_engine(user_id: int = 1) -> RiskEngineWorker:
    """Create a RiskEngineWorker with mocked dependencies."""
    kite_mock = MagicMock()
    redis_mock = MagicMock()
    db_mock = MagicMock()

    return RiskEngineWorker(
        user_id=user_id,
        kite_client=kite_mock,
        redis_client=redis_mock,
        db_session=db_mock,
    )


# ============================================================
# 23.5.2 & 23.5.3: Property Tests - Execute & Verify Margin Constraint
# ============================================================


class TestMarginSafetyProperty:
    """Property-based tests for margin safety invariant.

    **Validates: Requirements 1.4.4, 1.4.8, 6.3.5**

    Core invariant:
    - If margin_used > 90% of capital → threshold breached, kill switch triggers
    - If margin_used <= 90% of capital → within limits, trading allowed
    """

    @given(
        capital=st.floats(min_value=100000.0, max_value=10000000.0, allow_nan=False, allow_infinity=False),
        margin_ratio=st.floats(min_value=0.901, max_value=2.0, allow_nan=False, allow_infinity=False),
        daily_loss_limit_pct=st.floats(min_value=1.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100, deadline=None)
    def test_margin_above_90_percent_triggers_breach(self, capital, margin_ratio, daily_loss_limit_pct):
        """When margin_used > 90% of capital, threshold check returns breached.

        **Validates: Requirements 1.4.8**

        Property: For any capital and margin_used where margin_used/capital > 0.90,
        check_thresholds returns (True, reason) indicating margin breach.
        """
        engine = create_risk_engine()

        margin_used = capital * margin_ratio  # Always > 90% of capital
        # Use a small positive pnl to ensure daily loss does NOT trigger
        pnl = 0.0

        breached, reason = engine.check_thresholds(
            pnl=pnl,
            capital=capital,
            daily_loss_limit_pct=daily_loss_limit_pct,
            margin_used=margin_used,
        )

        assert breached is True, (
            f"Threshold should be breached when margin_used ({margin_used:.2f}) > "
            f"90% of capital ({capital * 0.9:.2f}), but got breached=False. "
            f"Margin ratio: {margin_ratio:.4f}"
        )
        assert "Margin" in reason or "margin" in reason, (
            f"Breach reason should mention margin, got: '{reason}'"
        )

    @given(
        capital=st.floats(min_value=100000.0, max_value=10000000.0, allow_nan=False, allow_infinity=False),
        margin_ratio=st.floats(min_value=0.0, max_value=0.899, allow_nan=False, allow_infinity=False),
        daily_loss_limit_pct=st.floats(min_value=1.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100, deadline=None)
    def test_margin_below_90_percent_allows_trading(self, capital, margin_ratio, daily_loss_limit_pct):
        """When margin_used <= 90% of capital and no loss breach, trading is allowed.

        **Validates: Requirements 1.4.8**

        Property: For any capital and margin_used where margin_used/capital < 0.90
        and pnl is not breaching daily loss limit, check_thresholds returns
        (False, "Within limits").
        """
        engine = create_risk_engine()

        margin_used = capital * margin_ratio  # Always < 90% of capital
        # Use small pnl that won't breach daily loss limit
        pnl = 0.0

        breached, reason = engine.check_thresholds(
            pnl=pnl,
            capital=capital,
            daily_loss_limit_pct=daily_loss_limit_pct,
            margin_used=margin_used,
        )

        assert breached is False, (
            f"Threshold should NOT be breached when margin_used ({margin_used:.2f}) < "
            f"90% of capital ({capital * 0.9:.2f}), but got breached=True. "
            f"Reason: '{reason}', margin ratio: {margin_ratio:.4f}"
        )
        assert reason == "Within limits", (
            f"Reason should be 'Within limits' when no breach, got: '{reason}'"
        )

    @given(scenario=trade_scenario_strategy())
    @settings(max_examples=100, deadline=None)
    def test_margin_threshold_boundary_correctness(self, scenario):
        """The 90% threshold is applied correctly at the boundary.

        **Validates: Requirements 1.4.4, 1.4.8**

        Property: For any trade scenario, compute the margin, then check:
        - If computed margin >= 90% of capital → breached (assuming no prior daily loss breach)
        - If computed margin < 90% of capital → not breached (assuming no daily loss breach)
        """
        engine = create_risk_engine()

        # Compute margin from positions
        margin_used = engine.compute_margin_used(scenario.positions)
        # Use neutral pnl to isolate margin check
        pnl = 0.0

        breached, reason = engine.check_thresholds(
            pnl=pnl,
            capital=scenario.capital,
            daily_loss_limit_pct=scenario.daily_loss_limit_pct,
            margin_used=margin_used,
        )

        margin_pct = (margin_used / scenario.capital) * 100

        if margin_pct >= 90.0:
            assert breached is True, (
                f"Threshold should be breached at {margin_pct:.2f}% margin usage "
                f"(margin={margin_used:.2f}, capital={scenario.capital:.2f})"
            )
        else:
            assert breached is False, (
                f"Threshold should NOT be breached at {margin_pct:.2f}% margin usage "
                f"(margin={margin_used:.2f}, capital={scenario.capital:.2f}), "
                f"but got reason: '{reason}'"
            )

    @given(
        capital=st.floats(min_value=100000.0, max_value=10000000.0, allow_nan=False, allow_infinity=False),
        daily_loss_limit_pct=st.floats(min_value=1.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100, deadline=None)
    def test_daily_loss_breach_triggers_before_margin(self, capital, daily_loss_limit_pct):
        """Daily loss breach is checked before margin and triggers kill switch.

        **Validates: Requirements 1.4.7, 1.4.8**

        Property: When daily loss exceeds the configured limit, threshold is
        breached regardless of margin usage.
        """
        engine = create_risk_engine()

        # Create a loss that breaches daily limit
        pnl = -(capital * (daily_loss_limit_pct / 100.0)) - 1.0  # Slightly beyond limit
        margin_used = 0.0  # No margin used — isolate daily loss check

        breached, reason = engine.check_thresholds(
            pnl=pnl,
            capital=capital,
            daily_loss_limit_pct=daily_loss_limit_pct,
            margin_used=margin_used,
        )

        assert breached is True, (
            f"Should be breached with pnl={pnl:.2f}, capital={capital:.2f}, "
            f"daily_loss_limit={daily_loss_limit_pct:.2f}%"
        )
        assert "loss" in reason.lower() or "Loss" in reason, (
            f"Breach reason should mention loss, got: '{reason}'"
        )

    @given(
        capital=st.floats(min_value=100000.0, max_value=10000000.0, allow_nan=False, allow_infinity=False),
        daily_loss_limit_pct=st.floats(min_value=1.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100, deadline=None)
    def test_no_breach_when_both_within_limits(self, capital, daily_loss_limit_pct):
        """No breach when both daily loss and margin are within safe limits.

        **Validates: Requirements 1.4.6, 1.4.7, 1.4.8**

        Property: When pnl loss is within daily limit AND margin < 90%,
        check_thresholds returns (False, "Within limits").
        """
        engine = create_risk_engine()

        # Small loss within limits (half the limit)
        pnl = -(capital * (daily_loss_limit_pct / 100.0)) * 0.5
        # Margin well under 90%
        margin_used = capital * 0.5

        breached, reason = engine.check_thresholds(
            pnl=pnl,
            capital=capital,
            daily_loss_limit_pct=daily_loss_limit_pct,
            margin_used=margin_used,
        )

        assert breached is False, (
            f"Should NOT be breached: pnl={pnl:.2f} (limit={daily_loss_limit_pct}%), "
            f"margin={margin_used:.2f} (50% of capital={capital:.2f}). "
            f"Got reason: '{reason}'"
        )
        assert reason == "Within limits"

    @given(
        capital=st.floats(min_value=100000.0, max_value=10000000.0, allow_nan=False, allow_infinity=False),
        margin_ratio=st.floats(min_value=0.901, max_value=2.0, allow_nan=False, allow_infinity=False),
        daily_loss_limit_pct=st.floats(min_value=1.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100, deadline=None)
    def test_margin_percentage_calculation_correctness(self, capital, margin_ratio, daily_loss_limit_pct):
        """Margin percentage is calculated correctly as (margin_used / capital) * 100.

        **Validates: Requirements 1.4.4**

        Property: compute_margin_percentage returns the correct mathematical
        result for any valid capital and margin_used combination.
        """
        engine = create_risk_engine()

        margin_used = capital * margin_ratio
        expected_pct = margin_ratio * 100.0

        result_pct = engine.compute_margin_percentage(margin_used, capital)

        assert abs(result_pct - expected_pct) < 1e-6, (
            f"Margin percentage mismatch: expected {expected_pct:.4f}%, "
            f"got {result_pct:.4f}% (margin={margin_used:.2f}, capital={capital:.2f})"
        )

    @given(
        capital=st.floats(min_value=100000.0, max_value=10000000.0, allow_nan=False, allow_infinity=False),
        extra_margin=st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=50, deadline=None)
    def test_margin_just_above_90_percent_triggers_breach(self, capital, extra_margin):
        """Margin just above 90% of capital triggers the threshold.

        **Validates: Requirements 1.4.8**

        Property: When margin_used is clearly above 90% of capital (by a
        non-trivial amount), the threshold IS breached (>= 90.0 check).
        We add a small extra margin to avoid floating-point boundary issues.
        """
        engine = create_risk_engine()

        margin_used = capital * 0.9 + extra_margin  # Clearly above 90%
        pnl = 0.0

        breached, reason = engine.check_thresholds(
            pnl=pnl,
            capital=capital,
            daily_loss_limit_pct=5.0,
            margin_used=margin_used,
        )

        assert breached is True, (
            f"Threshold should be breached when margin_used ({margin_used:.2f}) > "
            f"90% of capital ({capital * 0.9:.2f})"
        )

    @given(
        positions=st.lists(position_with_margin_strategy(), min_size=1, max_size=10),
        capital=st.floats(min_value=100000.0, max_value=10000000.0, allow_nan=False, allow_infinity=False),
        daily_loss_limit_pct=st.floats(min_value=1.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100, deadline=None)
    def test_end_to_end_margin_safety_with_computed_positions(self, positions, capital, daily_loss_limit_pct):
        """End-to-end: compute margin from positions, then check thresholds.

        **Validates: Requirements 1.4.4, 1.4.8, 6.3.5**

        Property: The full pipeline (compute_margin_used → check_thresholds)
        correctly identifies whether margin is safe or breached.
        """
        engine = create_risk_engine()

        # Compute metrics from positions
        margin_used = engine.compute_margin_used(positions)
        pnl = engine.compute_live_pnl(positions)

        breached, reason = engine.check_thresholds(
            pnl=pnl,
            capital=capital,
            daily_loss_limit_pct=daily_loss_limit_pct,
            margin_used=margin_used,
        )

        # Verify the result is consistent with the computed values
        margin_pct = (margin_used / capital) * 100
        loss_pct = (pnl / capital) * 100

        if loss_pct <= -daily_loss_limit_pct:
            # Daily loss should trigger first
            assert breached is True, (
                f"Should breach on daily loss: {loss_pct:.2f}% vs limit -{daily_loss_limit_pct}%"
            )
        elif margin_pct >= 90.0:
            # Margin should trigger
            assert breached is True, (
                f"Should breach on margin: {margin_pct:.2f}% >= 90%"
            )
        else:
            # Neither should trigger
            assert breached is False, (
                f"Should NOT breach: loss={loss_pct:.2f}% (limit={daily_loss_limit_pct}%), "
                f"margin={margin_pct:.2f}% < 90%. Got reason: '{reason}'"
            )
