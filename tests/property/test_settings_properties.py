"""Property-based tests for SettingsService (Task 4.4).

Uses Hypothesis to verify:
- Property 4: Settings Validation Correctness — acceptance iff value within bounds
- Property 5: Kill Switch Threshold Calculation — amount = capital × pct / 100, warning iff > 25%

**Validates: Requirements 5.3-5.6, 6.3, 6.5, 6.6**
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from hypothesis import given, strategies as st, settings, assume
from pydantic import ValidationError

from src.services.settings_service import (
    StrategySettings,
    _compute_amount,
    _check_daily_loss_warning,
)


# ============================================================
# Property 4: Settings Validation Correctness
# ============================================================


class TestSettingsValidationCorrectness:
    """Property-based tests for StrategySettings Pydantic validation.

    **Validates: Requirements 5.3, 5.4, 5.5, 5.6**

    Core invariant:
    - confidence_threshold accepted iff 50 <= value <= 100
    - max_trades_per_day accepted iff 1 <= value <= 10
    - capital accepted iff value > 0
    """

    def _make_valid_settings_kwargs(self, **overrides):
        """Create a valid StrategySettings kwargs dict with optional overrides."""
        base = {
            "watchlist": ["NIFTY", "BANKNIFTY"],
            "trading_start_time": "09:15",
            "trading_end_time": "15:30",
            "confidence_threshold": 75,
            "max_trades_per_day": 5,
            "max_active_trades": 3,
            "capital": 100000.0,
            "lot_sizes": {"NIFTY": 25, "BANKNIFTY": 15},
        }
        base.update(overrides)
        return base

    @given(confidence=st.integers(min_value=50, max_value=100))
    @settings(max_examples=50, deadline=None)
    def test_valid_confidence_threshold_accepted(self, confidence):
        """Valid confidence threshold (50-100) is accepted by StrategySettings.

        **Validates: Requirements 5.3**

        Property: For any integer in [50, 100], StrategySettings model
        accepts the value without raising ValidationError.
        """
        kwargs = self._make_valid_settings_kwargs(confidence_threshold=confidence)
        model = StrategySettings(**kwargs)
        assert model.confidence_threshold == confidence

    @given(
        confidence=st.integers(min_value=0, max_value=200).filter(
            lambda x: x < 50 or x > 100
        )
    )
    @settings(max_examples=50, deadline=None)
    def test_invalid_confidence_threshold_rejected(self, confidence):
        """Invalid confidence threshold (outside 50-100) is rejected.

        **Validates: Requirements 5.3**

        Property: For any integer outside [50, 100], StrategySettings model
        raises ValidationError.
        """
        kwargs = self._make_valid_settings_kwargs(confidence_threshold=confidence)
        with pytest.raises(ValidationError):
            StrategySettings(**kwargs)

    @given(max_trades=st.integers(min_value=1, max_value=10))
    @settings(max_examples=50, deadline=None)
    def test_valid_max_trades_per_day_accepted(self, max_trades):
        """Valid max_trades_per_day (1-10) is accepted by StrategySettings.

        **Validates: Requirements 5.6**

        Property: For any integer in [1, 10], StrategySettings model
        accepts the value without raising ValidationError.
        """
        kwargs = self._make_valid_settings_kwargs(max_trades_per_day=max_trades)
        model = StrategySettings(**kwargs)
        assert model.max_trades_per_day == max_trades

    @given(
        max_trades=st.integers(min_value=0, max_value=20).filter(
            lambda x: x < 1 or x > 10
        )
    )
    @settings(max_examples=50, deadline=None)
    def test_invalid_max_trades_per_day_rejected(self, max_trades):
        """Invalid max_trades_per_day (outside 1-10) is rejected.

        **Validates: Requirements 5.6**

        Property: For any integer outside [1, 10], StrategySettings model
        raises ValidationError.
        """
        kwargs = self._make_valid_settings_kwargs(max_trades_per_day=max_trades)
        with pytest.raises(ValidationError):
            StrategySettings(**kwargs)

    @given(
        capital=st.floats(
            min_value=0.01, max_value=500000.0,
            allow_nan=False, allow_infinity=False,
        ).filter(lambda x: x > 0)
    )
    @settings(max_examples=50, deadline=None)
    def test_valid_capital_accepted(self, capital):
        """Positive capital is accepted by StrategySettings.

        **Validates: Requirements 5.5**

        Property: For any float > 0, StrategySettings model
        accepts the value without raising ValidationError.
        """
        kwargs = self._make_valid_settings_kwargs(capital=capital)
        model = StrategySettings(**kwargs)
        assert model.capital == capital

    @given(
        capital=st.floats(
            min_value=-1000.0, max_value=0.0,
            allow_nan=False, allow_infinity=False,
        )
    )
    @settings(max_examples=50, deadline=None)
    def test_invalid_capital_rejected(self, capital):
        """Non-positive capital (<=0) is rejected by StrategySettings.

        **Validates: Requirements 5.5**

        Property: For any float <= 0, StrategySettings model
        raises ValidationError.
        """
        kwargs = self._make_valid_settings_kwargs(capital=capital)
        with pytest.raises(ValidationError):
            StrategySettings(**kwargs)


# ============================================================
# Property 5: Kill Switch Threshold Calculation
# ============================================================


class TestKillSwitchThresholdCalculation:
    """Property-based tests for kill switch threshold computation and warnings.

    **Validates: Requirements 6.3, 6.5, 6.6**

    Core invariants:
    - For "percentage" type: amount = capital × value / 100
    - For "absolute" type: amount = value directly
    - Warning iff daily_loss > 25% of capital (percentage type: value > 25,
      absolute type: value > capital * 0.25)
    """

    @given(
        capital=st.floats(
            min_value=1000.0, max_value=10000000.0,
            allow_nan=False, allow_infinity=False,
        ),
        value=st.floats(
            min_value=0.1, max_value=100.0,
            allow_nan=False, allow_infinity=False,
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_percentage_type_computes_correct_amount(self, capital, value):
        """For percentage type, _compute_amount returns capital × value / 100.

        **Validates: Requirements 6.3**

        Property: For any positive capital and positive value,
        _compute_amount("percentage", value) == capital * value / 100.
        """
        result = _compute_amount(capital, "percentage", value)
        expected = capital * value / 100.0
        assert abs(result - expected) < 1e-6, (
            f"Expected {expected}, got {result} for capital={capital}, value={value}"
        )

    @given(
        capital=st.floats(
            min_value=1000.0, max_value=10000000.0,
            allow_nan=False, allow_infinity=False,
        ),
        value=st.floats(
            min_value=0.1, max_value=500000.0,
            allow_nan=False, allow_infinity=False,
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_absolute_type_returns_value_directly(self, capital, value):
        """For absolute type, _compute_amount returns value directly.

        **Validates: Requirements 6.3**

        Property: For any positive capital and positive value,
        _compute_amount("absolute", value) == value.
        """
        result = _compute_amount(capital, "absolute", value)
        assert result == value, (
            f"Expected {value}, got {result} for absolute type"
        )

    @given(
        capital=st.floats(
            min_value=1000.0, max_value=10000000.0,
            allow_nan=False, allow_infinity=False,
        ),
        daily_loss_value=st.floats(
            min_value=25.01, max_value=100.0,
            allow_nan=False, allow_infinity=False,
        ),
    )
    @settings(max_examples=50, deadline=None)
    def test_percentage_warning_when_exceeds_25_percent(self, capital, daily_loss_value):
        """Warning is returned when percentage daily loss > 25%.

        **Validates: Requirements 6.6**

        Property: For any capital and daily_loss_value > 25 (percentage type),
        _check_daily_loss_warning returns a non-None warning string.
        """
        assume(daily_loss_value > 25)
        result = _check_daily_loss_warning(capital, "percentage", daily_loss_value)
        assert result is not None, (
            f"Expected warning for percentage daily_loss_value={daily_loss_value} > 25%, "
            f"but got None"
        )

    @given(
        capital=st.floats(
            min_value=1000.0, max_value=10000000.0,
            allow_nan=False, allow_infinity=False,
        ),
        daily_loss_value=st.floats(
            min_value=0.1, max_value=24.99,
            allow_nan=False, allow_infinity=False,
        ),
    )
    @settings(max_examples=50, deadline=None)
    def test_percentage_no_warning_when_at_or_below_25_percent(self, capital, daily_loss_value):
        """No warning when percentage daily loss <= 25%.

        **Validates: Requirements 6.6**

        Property: For any capital and daily_loss_value <= 25 (percentage type),
        _check_daily_loss_warning returns None.
        """
        assume(daily_loss_value <= 25)
        result = _check_daily_loss_warning(capital, "percentage", daily_loss_value)
        assert result is None, (
            f"Expected no warning for percentage daily_loss_value={daily_loss_value} <= 25%, "
            f"but got: {result}"
        )

    @given(
        capital=st.floats(
            min_value=1000.0, max_value=10000000.0,
            allow_nan=False, allow_infinity=False,
        ),
    )
    @settings(max_examples=50, deadline=None)
    def test_absolute_warning_when_exceeds_25_percent_of_capital(self, capital):
        """Warning is returned when absolute daily loss > 25% of capital.

        **Validates: Requirements 6.6**

        Property: For any capital, when absolute daily_loss_value > capital * 0.25,
        _check_daily_loss_warning returns a non-None warning string.
        """
        # Generate a value that exceeds 25% of capital
        threshold = capital * 0.25
        daily_loss_value = threshold + 1.0  # Ensure it's above threshold

        result = _check_daily_loss_warning(capital, "absolute", daily_loss_value)
        assert result is not None, (
            f"Expected warning for absolute daily_loss_value={daily_loss_value} > "
            f"25% of capital ({threshold}), but got None"
        )

    @given(
        capital=st.floats(
            min_value=1000.0, max_value=10000000.0,
            allow_nan=False, allow_infinity=False,
        ),
    )
    @settings(max_examples=50, deadline=None)
    def test_absolute_no_warning_when_at_or_below_25_percent_of_capital(self, capital):
        """No warning when absolute daily loss <= 25% of capital.

        **Validates: Requirements 6.6**

        Property: For any capital, when absolute daily_loss_value <= capital * 0.25,
        _check_daily_loss_warning returns None.
        """
        # Generate a value that's within 25% of capital
        threshold = capital * 0.25
        daily_loss_value = threshold * 0.5  # Well below threshold

        result = _check_daily_loss_warning(capital, "absolute", daily_loss_value)
        assert result is None, (
            f"Expected no warning for absolute daily_loss_value={daily_loss_value} <= "
            f"25% of capital ({threshold}), but got: {result}"
        )

    @given(
        capital=st.floats(
            min_value=1000.0, max_value=10000000.0,
            allow_nan=False, allow_infinity=False,
        ),
        daily_loss_value=st.floats(
            min_value=0.1, max_value=500000.0,
            allow_nan=False, allow_infinity=False,
        ),
    )
    @settings(max_examples=50, deadline=None)
    def test_absolute_warning_biconditional(self, capital, daily_loss_value):
        """Warning iff absolute daily loss > capital * 0.25 (biconditional).

        **Validates: Requirements 6.5, 6.6**

        Property: _check_daily_loss_warning returns non-None iff
        daily_loss_value > capital * 0.25 for absolute type.
        """
        threshold = capital * 0.25
        result = _check_daily_loss_warning(capital, "absolute", daily_loss_value)

        if daily_loss_value > threshold:
            assert result is not None, (
                f"Expected warning for daily_loss_value={daily_loss_value} > "
                f"threshold={threshold}"
            )
        else:
            assert result is None, (
                f"Expected no warning for daily_loss_value={daily_loss_value} <= "
                f"threshold={threshold}, but got: {result}"
            )

    @given(
        capital=st.floats(
            min_value=1000.0, max_value=10000000.0,
            allow_nan=False, allow_infinity=False,
        ),
        daily_loss_value=st.floats(
            min_value=0.1, max_value=100.0,
            allow_nan=False, allow_infinity=False,
        ),
    )
    @settings(max_examples=50, deadline=None)
    def test_percentage_warning_biconditional(self, capital, daily_loss_value):
        """Warning iff percentage daily loss > 25 (biconditional).

        **Validates: Requirements 6.5, 6.6**

        Property: _check_daily_loss_warning returns non-None iff
        daily_loss_value > 25 for percentage type.
        """
        result = _check_daily_loss_warning(capital, "percentage", daily_loss_value)

        if daily_loss_value > 25:
            assert result is not None, (
                f"Expected warning for daily_loss_value={daily_loss_value}% > 25%"
            )
        else:
            assert result is None, (
                f"Expected no warning for daily_loss_value={daily_loss_value}% <= 25%, "
                f"but got: {result}"
            )
