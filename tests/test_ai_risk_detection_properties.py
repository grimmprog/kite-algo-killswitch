"""Property-based tests for AI risk detection.

**Validates: Requirements 24.3, 24.4, 24.5**

Property 23: Behavioral Anomaly Detection
  - Verify break suggestion at 3 consecutive losses
  - Verify revenge trading detection within 5 min of loss on same/correlated symbol

Property 24: Risk Rule Violation Blocking
  - Verify blocking warning on rule violations (max trades, trading hours, loss limit)
  - All violations have requires_acknowledgment=True
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from hypothesis import given, assume, settings
from hypothesis import strategies as st

from src.services.risk_detection import (
    should_suggest_break,
    is_revenge_trading,
    detect_rule_violations,
)


# ---------------------------------------------------------------------------
# Property 23: Behavioral Anomaly Detection
# ---------------------------------------------------------------------------


class TestBehavioralAnomalyDetectionProperty:
    """Property 23: Verify break suggestion at 3 losses, revenge trading within 5 min.

    **Validates: Requirements 24.3, 24.5**
    """

    # --- Break suggestion ---

    @given(consecutive_losses=st.integers(min_value=0, max_value=20))
    @settings(max_examples=500)
    def test_break_suggestion_iff_three_or_more_losses(self, consecutive_losses):
        """Break suggestion is True iff consecutive_losses >= 3."""
        result = should_suggest_break(consecutive_losses)
        expected = consecutive_losses >= 3

        assert result == expected, (
            f"should_suggest_break({consecutive_losses}) = {result}, "
            f"expected {expected}"
        )

    @given(consecutive_losses=st.integers(min_value=3, max_value=20))
    @settings(max_examples=200)
    def test_break_always_suggested_at_three_plus(self, consecutive_losses):
        """Break is always suggested when losses >= 3."""
        assert should_suggest_break(consecutive_losses) is True

    @given(consecutive_losses=st.integers(min_value=0, max_value=2))
    @settings(max_examples=200)
    def test_no_break_suggested_below_three(self, consecutive_losses):
        """Break is never suggested when losses < 3."""
        assert should_suggest_break(consecutive_losses) is False

    # --- Revenge trading detection ---

    @given(
        last_loss_time_minutes=st.floats(min_value=0.0, max_value=60.0, allow_nan=False, allow_infinity=False),
        same_or_correlated_symbol=st.booleans(),
    )
    @settings(max_examples=500)
    def test_revenge_trading_iff_within_five_min_and_correlated(
        self, last_loss_time_minutes, same_or_correlated_symbol
    ):
        """Revenge trading detected iff time <= 5 AND same/correlated symbol."""
        result = is_revenge_trading(last_loss_time_minutes, same_or_correlated_symbol)
        expected = last_loss_time_minutes <= 5.0 and same_or_correlated_symbol

        assert result == expected, (
            f"is_revenge_trading({last_loss_time_minutes}, {same_or_correlated_symbol}) "
            f"= {result}, expected {expected}"
        )

    @given(
        last_loss_time_minutes=st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=200)
    def test_revenge_trading_true_within_five_min_correlated(self, last_loss_time_minutes):
        """Revenge trading detected when within 5 min and correlated symbol."""
        assert is_revenge_trading(last_loss_time_minutes, True) is True

    @given(
        last_loss_time_minutes=st.floats(min_value=0.0, max_value=60.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=200)
    def test_no_revenge_trading_different_symbol(self, last_loss_time_minutes):
        """No revenge trading detected when symbol is not correlated, regardless of time."""
        assert is_revenge_trading(last_loss_time_minutes, False) is False

    @given(
        last_loss_time_minutes=st.floats(
            min_value=5.001, max_value=60.0, allow_nan=False, allow_infinity=False
        ),
    )
    @settings(max_examples=200)
    def test_no_revenge_trading_after_five_minutes(self, last_loss_time_minutes):
        """No revenge trading detected when more than 5 min have passed, even on correlated symbol."""
        assert is_revenge_trading(last_loss_time_minutes, True) is False


# ---------------------------------------------------------------------------
# Property 24: Risk Rule Violation Blocking
# ---------------------------------------------------------------------------


class TestRiskRuleViolationBlockingProperty:
    """Property 24: Verify blocking warning on rule violations.

    **Validates: Requirements 24.4**
    """

    @given(
        current_trades=st.integers(min_value=0, max_value=20),
        max_trades=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=500)
    def test_max_trades_violation_detected(self, current_trades, max_trades):
        """Violation detected iff current_trades >= max_trades."""
        user_state = {
            "current_trades": current_trades,
            "max_trades": max_trades,
        }
        violations = detect_rule_violations(user_state)

        has_max_trades_violation = any(
            "Max trades" in v["message"] for v in violations
        )
        expected = current_trades >= max_trades

        assert has_max_trades_violation == expected, (
            f"current_trades={current_trades}, max_trades={max_trades}: "
            f"violation_detected={has_max_trades_violation}, expected={expected}"
        )

    @given(
        current_hour=st.floats(min_value=0.0, max_value=24.0, allow_nan=False, allow_infinity=False),
        trading_start_hour=st.floats(min_value=0.0, max_value=23.0, allow_nan=False, allow_infinity=False),
        trading_end_hour=st.floats(min_value=0.5, max_value=24.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=500)
    def test_trading_hours_violation_detected(
        self, current_hour, trading_start_hour, trading_end_hour
    ):
        """Violation detected iff current_hour < start OR current_hour > end."""
        assume(trading_start_hour < trading_end_hour)

        user_state = {
            "current_hour": current_hour,
            "trading_start_hour": trading_start_hour,
            "trading_end_hour": trading_end_hour,
            "current_trades": 0,
            "max_trades": 10,
        }
        violations = detect_rule_violations(user_state)

        has_hours_violation = any(
            "outside configured trading hours" in v["message"] for v in violations
        )
        expected = current_hour < trading_start_hour or current_hour > trading_end_hour

        assert has_hours_violation == expected, (
            f"current_hour={current_hour}, start={trading_start_hour}, "
            f"end={trading_end_hour}: violation_detected={has_hours_violation}, "
            f"expected={expected}"
        )

    @given(
        daily_loss=st.floats(min_value=0.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        loss_limit=st.floats(min_value=0.01, max_value=100000.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=500)
    def test_loss_limit_violation_detected(self, daily_loss, loss_limit):
        """Violation detected iff daily_loss >= loss_limit."""
        user_state = {
            "daily_loss": daily_loss,
            "loss_limit": loss_limit,
            "current_trades": 0,
            "max_trades": 10,
        }
        violations = detect_rule_violations(user_state)

        has_loss_violation = any(
            "Daily loss limit" in v["message"] for v in violations
        )
        expected = daily_loss >= loss_limit

        assert has_loss_violation == expected, (
            f"daily_loss={daily_loss}, loss_limit={loss_limit}: "
            f"violation_detected={has_loss_violation}, expected={expected}"
        )

    @given(
        current_trades=st.integers(min_value=0, max_value=20),
        max_trades=st.integers(min_value=1, max_value=10),
        current_hour=st.floats(min_value=0.0, max_value=24.0, allow_nan=False, allow_infinity=False),
        trading_start_hour=st.just(9.25),
        trading_end_hour=st.just(15.5),
        daily_loss=st.floats(min_value=0.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        loss_limit=st.floats(min_value=0.01, max_value=100000.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=500)
    def test_all_violations_require_acknowledgment(
        self,
        current_trades,
        max_trades,
        current_hour,
        trading_start_hour,
        trading_end_hour,
        daily_loss,
        loss_limit,
    ):
        """All detected violations must have requires_acknowledgment=True."""
        user_state = {
            "current_trades": current_trades,
            "max_trades": max_trades,
            "current_hour": current_hour,
            "trading_start_hour": trading_start_hour,
            "trading_end_hour": trading_end_hour,
            "daily_loss": daily_loss,
            "loss_limit": loss_limit,
        }
        violations = detect_rule_violations(user_state)

        for violation in violations:
            assert violation["requires_acknowledgment"] is True, (
                f"Violation missing requires_acknowledgment=True: {violation}"
            )

    @given(
        current_trades=st.integers(min_value=0, max_value=20),
        max_trades=st.integers(min_value=1, max_value=10),
        current_hour=st.floats(min_value=0.0, max_value=24.0, allow_nan=False, allow_infinity=False),
        trading_start_hour=st.just(9.25),
        trading_end_hour=st.just(15.5),
        daily_loss=st.floats(min_value=0.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        loss_limit=st.floats(min_value=0.01, max_value=100000.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=500)
    def test_all_violations_have_rule_violation_category(
        self,
        current_trades,
        max_trades,
        current_hour,
        trading_start_hour,
        trading_end_hour,
        daily_loss,
        loss_limit,
    ):
        """All detected violations must have category='rule_violation'."""
        user_state = {
            "current_trades": current_trades,
            "max_trades": max_trades,
            "current_hour": current_hour,
            "trading_start_hour": trading_start_hour,
            "trading_end_hour": trading_end_hour,
            "daily_loss": daily_loss,
            "loss_limit": loss_limit,
        }
        violations = detect_rule_violations(user_state)

        for violation in violations:
            assert violation["category"] == "rule_violation", (
                f"Violation has wrong category: {violation}"
            )
