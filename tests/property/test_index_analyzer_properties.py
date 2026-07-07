"""Property-based tests for IndexAnalyzerService (Task 3.4).

**Property 3: Index Recommendation Correctness**
- Verify best index selection picks highest composite_score among available indices
- Verify option_type is "CE" if trend_direction is "bullish", else "PE"
- Verify recommended_strike equals round(current_price / strike_step) * strike_step
- Verify STRIKE_STEPS mapping: NIFTY 50→50, BANK NIFTY→100, SENSEX→100
- Verify compute_composite_score: result equals momentum*0.4 + volume*0.3 + trend_score*0.3

**Validates: Requirements 3.3, 3.4, 3.5**
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from hypothesis import given, strategies as st, settings, assume

from src.services.index_analyzer_service import (
    IndexAnalyzerService,
    IndexMetrics,
    STRIKE_STEPS,
    TREND_SCORES,
    WEIGHT_MOMENTUM,
    WEIGHT_VOLUME,
    WEIGHT_TREND,
)


# ============================================================
# Custom Strategies
# ============================================================

VALID_SYMBOLS = ["NIFTY 50", "BANK NIFTY", "SENSEX"]
VALID_TRENDS = ["bullish", "bearish", "neutral"]


def index_metrics_strategy(data_available: bool = True):
    """Generate a random IndexMetrics instance."""
    return st.builds(
        IndexMetrics,
        symbol=st.sampled_from(VALID_SYMBOLS),
        current_price=st.floats(
            min_value=1000.0, max_value=100000.0,
            allow_nan=False, allow_infinity=False,
        ),
        change_1h_pct=st.floats(
            min_value=-10.0, max_value=10.0,
            allow_nan=False, allow_infinity=False,
        ),
        change_daily_pct=st.floats(
            min_value=-10.0, max_value=10.0,
            allow_nan=False, allow_infinity=False,
        ),
        momentum_score=st.floats(
            min_value=0.0, max_value=100.0,
            allow_nan=False, allow_infinity=False,
        ),
        volume_score=st.floats(
            min_value=0.0, max_value=100.0,
            allow_nan=False, allow_infinity=False,
        ),
        trend_direction=st.sampled_from(VALID_TRENDS),
        composite_score=st.floats(
            min_value=0.0, max_value=100.0,
            allow_nan=False, allow_infinity=False,
        ),
        data_available=st.just(data_available),
    )


def metrics_list_strategy():
    """Generate a list of 1-3 IndexMetrics with at least one data_available=True."""
    return st.lists(
        index_metrics_strategy(data_available=True),
        min_size=1,
        max_size=3,
    )


def mixed_metrics_list_strategy():
    """Generate a list with mix of available and unavailable metrics."""
    available = st.lists(
        index_metrics_strategy(data_available=True),
        min_size=1,
        max_size=2,
    )
    unavailable = st.lists(
        index_metrics_strategy(data_available=False),
        min_size=0,
        max_size=2,
    )
    return st.tuples(available, unavailable).map(lambda t: t[0] + t[1])


# ============================================================
# Property 3: Index Recommendation Correctness
# ============================================================


class TestIndexRecommendationCorrectness:
    """Property-based tests verifying index recommendation correctness.

    **Validates: Requirements 3.3, 3.4, 3.5**
    """

    @given(metrics=metrics_list_strategy())
    @settings(max_examples=100, deadline=None)
    def test_recommend_trade_picks_highest_composite_score(self, metrics):
        """Best index selection picks the highest composite_score among available indices.

        **Validates: Requirements 3.3**

        Property: For any list of IndexMetrics with data_available=True,
        recommend_trade returns the index with the highest composite_score.
        """
        service = IndexAnalyzerService()

        # Ensure distinct composite scores to avoid tie ambiguity
        scores = [m.composite_score for m in metrics]
        assume(len(set(scores)) == len(scores))

        result = service.recommend_trade(metrics)

        assert result is not None
        expected_best = max(metrics, key=lambda m: m.composite_score)
        assert result.best_index == expected_best.symbol, (
            f"Expected best_index='{expected_best.symbol}' "
            f"(score={expected_best.composite_score}), "
            f"got '{result.best_index}'"
        )

    @given(metrics=mixed_metrics_list_strategy())
    @settings(max_examples=100, deadline=None)
    def test_recommend_trade_filters_unavailable_indices(self, metrics):
        """Best index selection only considers indices with data_available=True.

        **Validates: Requirements 3.3**

        Property: For any mix of available/unavailable indices,
        recommend_trade only picks from those with data_available=True.
        """
        service = IndexAnalyzerService()

        available = [m for m in metrics if m.data_available]
        assume(len(available) >= 1)

        # Ensure distinct composite scores among available
        scores = [m.composite_score for m in available]
        assume(len(set(scores)) == len(scores))

        result = service.recommend_trade(metrics)

        assert result is not None
        expected_best = max(available, key=lambda m: m.composite_score)
        assert result.best_index == expected_best.symbol

    @given(metrics=metrics_list_strategy())
    @settings(max_examples=100, deadline=None)
    def test_option_type_ce_if_bullish_else_pe(self, metrics):
        """Option type is "CE" if trend_direction is "bullish", else "PE".

        **Validates: Requirements 3.4**

        Property: For any set of metrics, the recommended option type
        is "CE" when the best index has trend_direction="bullish",
        and "PE" otherwise (bearish or neutral).
        """
        service = IndexAnalyzerService()

        # Ensure distinct composite scores
        scores = [m.composite_score for m in metrics]
        assume(len(set(scores)) == len(scores))

        result = service.recommend_trade(metrics)

        assert result is not None
        best = max(metrics, key=lambda m: m.composite_score)

        if best.trend_direction == "bullish":
            assert result.option_type == "CE", (
                f"Expected CE for bullish trend, got {result.option_type}"
            )
        else:
            assert result.option_type == "PE", (
                f"Expected PE for {best.trend_direction} trend, "
                f"got {result.option_type}"
            )

    @given(metrics=metrics_list_strategy())
    @settings(max_examples=100, deadline=None)
    def test_recommended_strike_calculation(self, metrics):
        """Recommended strike equals round(current_price / strike_step) * strike_step.

        **Validates: Requirements 3.5**

        Property: For any set of metrics, the recommended_strike is
        the nearest ATM strike at the configured step size for that index.
        """
        service = IndexAnalyzerService()

        # Ensure distinct composite scores
        scores = [m.composite_score for m in metrics]
        assume(len(set(scores)) == len(scores))

        result = service.recommend_trade(metrics)

        assert result is not None
        best = max(metrics, key=lambda m: m.composite_score)

        strike_step = STRIKE_STEPS.get(best.symbol, 100)
        expected_strike = round(best.current_price / strike_step) * strike_step

        assert result.recommended_strike == expected_strike, (
            f"Expected strike={expected_strike} for price={best.current_price} "
            f"with step={strike_step}, got {result.recommended_strike}"
        )

    @given(metrics=metrics_list_strategy())
    @settings(max_examples=100, deadline=None)
    def test_strike_step_mapping(self, metrics):
        """STRIKE_STEPS mapping: NIFTY 50→50, BANK NIFTY→100, SENSEX→100.

        **Validates: Requirements 3.5**

        Property: The strike_step in the recommendation matches the
        STRIKE_STEPS constant for the chosen index.
        """
        service = IndexAnalyzerService()

        # Ensure distinct composite scores
        scores = [m.composite_score for m in metrics]
        assume(len(set(scores)) == len(scores))

        result = service.recommend_trade(metrics)

        assert result is not None
        expected_step = STRIKE_STEPS.get(result.best_index, 100)
        assert result.strike_step == expected_step, (
            f"Expected strike_step={expected_step} for {result.best_index}, "
            f"got {result.strike_step}"
        )

    @given(
        momentum=st.floats(
            min_value=0.0, max_value=100.0,
            allow_nan=False, allow_infinity=False,
        ),
        volume=st.floats(
            min_value=0.0, max_value=100.0,
            allow_nan=False, allow_infinity=False,
        ),
        trend=st.sampled_from(VALID_TRENDS),
    )
    @settings(max_examples=100, deadline=None)
    def test_composite_score_formula(self, momentum, volume, trend):
        """Composite score equals momentum*0.4 + volume*0.3 + trend_score*0.3.

        **Validates: Requirements 3.3**

        Property: For any valid momentum (0-100), volume (0-100), and trend
        direction, compute_composite_score returns the correctly weighted sum.
        """
        service = IndexAnalyzerService()

        result = service.compute_composite_score(momentum, volume, trend)

        trend_score = TREND_SCORES[trend]
        expected = round(
            momentum * WEIGHT_MOMENTUM
            + volume * WEIGHT_VOLUME
            + trend_score * WEIGHT_TREND,
            2,
        )

        assert result == expected, (
            f"Expected composite={expected} for momentum={momentum}, "
            f"volume={volume}, trend={trend} (score={trend_score}), "
            f"got {result}"
        )
