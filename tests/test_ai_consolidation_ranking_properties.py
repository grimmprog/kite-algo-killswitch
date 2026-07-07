"""Property-based tests for AITradingService consolidation ranking (Task 7.6).

**Property 20: Consolidation Ranking**
- Verify output is sorted by breakout_probability in descending order
- Verify exactly one entry has best_trade = True (the first one)
- Verify all other entries have best_trade = False
- Verify output length equals input length
- Verify empty input returns empty list

**Validates: Requirements 20.4**
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock
from hypothesis import given, strategies as st, settings, assume

from src.services.ai_trading_service import (
    AIProvider,
    AITradingService,
)


# ============================================================
# Custom Strategies
# ============================================================

VALID_TRENDS = ["bullish", "bearish", "neutral"]
VALID_DIRECTIONS = ["up", "down"]


def consolidation_pattern_strategy():
    """Generate a random consolidation pattern dictionary."""
    return st.fixed_dictionaries({
        "range_high": st.floats(
            min_value=100.0, max_value=50000.0,
            allow_nan=False, allow_infinity=False,
        ),
        "range_low": st.floats(
            min_value=50.0, max_value=49000.0,
            allow_nan=False, allow_infinity=False,
        ),
        "avg_price": st.floats(
            min_value=75.0, max_value=49500.0,
            allow_nan=False, allow_infinity=False,
        ),
        "candle_count": st.integers(min_value=3, max_value=30),
        "duration_minutes": st.integers(min_value=5, max_value=120),
        "volume_avg": st.floats(
            min_value=100.0, max_value=100000.0,
            allow_nan=False, allow_infinity=False,
        ),
        "breakout_volume": st.floats(
            min_value=50.0, max_value=150000.0,
            allow_nan=False, allow_infinity=False,
        ),
        "breakout_direction": st.sampled_from(VALID_DIRECTIONS),
    })


def market_context_strategy():
    """Generate a random market context dictionary."""
    return st.fixed_dictionaries({
        "trend_direction": st.sampled_from(VALID_TRENDS),
        "volume_profile": st.just({"avg": 5000, "current": 6000}),
        "time_of_day": st.sampled_from(["09:30", "10:15", "11:00", "13:00", "14:30"]),
        "key_levels": st.just({"support": [100.0], "resistance": [200.0]}),
        "vwap": st.floats(
            min_value=100.0, max_value=50000.0,
            allow_nan=False, allow_infinity=False,
        ),
    })


def patterns_list_strategy():
    """Generate a list of 1-10 consolidation patterns."""
    return st.lists(
        consolidation_pattern_strategy(),
        min_size=1,
        max_size=10,
    )


# ============================================================
# Helper: Create service with mocked LLM (forces fallback heuristic)
# ============================================================

def create_service_with_mocked_llm():
    """Create an AITradingService where _make_request returns an error,
    forcing the fallback heuristic in analyze_consolidation."""
    service = AITradingService(
        provider=AIProvider.GEMINI,
        api_key="test-key-for-property-tests",
    )
    # Mock _make_request to always return an error,
    # which triggers the deterministic local fallback heuristic
    service._make_request = MagicMock(return_value={"error": "AI unavailable"})
    return service


# ============================================================
# Property 20: Consolidation Ranking
# ============================================================


class TestConsolidationRanking:
    """Property-based tests verifying consolidation ranking correctness.

    **Validates: Requirements 20.4**
    """

    @given(
        patterns=patterns_list_strategy(),
        market_context=market_context_strategy(),
    )
    @settings(max_examples=100, deadline=None)
    def test_output_sorted_by_breakout_probability_descending(
        self, patterns, market_context
    ):
        """Output is sorted by breakout_probability in descending order.

        **Validates: Requirements 20.4**

        Property: For any list of consolidation patterns, rank_consolidations
        returns results sorted by breakout_probability from highest to lowest.
        """
        service = create_service_with_mocked_llm()

        result = service.rank_consolidations(patterns, market_context)

        probabilities = [entry["breakout_probability"] for entry in result]
        assert probabilities == sorted(probabilities, reverse=True), (
            f"Expected descending order, got probabilities: {probabilities}"
        )

    @given(
        patterns=patterns_list_strategy(),
        market_context=market_context_strategy(),
    )
    @settings(max_examples=100, deadline=None)
    def test_exactly_one_best_trade_designation(self, patterns, market_context):
        """Exactly one entry has best_trade = True (the first one).

        **Validates: Requirements 20.4**

        Property: For any non-empty list of patterns, the first entry
        in the ranked result has best_trade=True and it is the only one.
        """
        service = create_service_with_mocked_llm()

        result = service.rank_consolidations(patterns, market_context)

        assert len(result) > 0
        assert result[0]["best_trade"] is True, (
            f"Expected first entry to have best_trade=True, got {result[0]['best_trade']}"
        )

        best_trade_count = sum(1 for entry in result if entry["best_trade"] is True)
        assert best_trade_count == 1, (
            f"Expected exactly 1 best_trade=True, found {best_trade_count}"
        )

    @given(
        patterns=patterns_list_strategy(),
        market_context=market_context_strategy(),
    )
    @settings(max_examples=100, deadline=None)
    def test_all_non_first_entries_have_best_trade_false(
        self, patterns, market_context
    ):
        """All entries except the first have best_trade = False.

        **Validates: Requirements 20.4**

        Property: For any non-empty list of patterns, all entries after
        the first in the ranked result have best_trade=False.
        """
        service = create_service_with_mocked_llm()

        result = service.rank_consolidations(patterns, market_context)

        for i, entry in enumerate(result[1:], start=1):
            assert entry["best_trade"] is False, (
                f"Entry at index {i} has best_trade={entry['best_trade']}, "
                f"expected False"
            )

    @given(
        patterns=patterns_list_strategy(),
        market_context=market_context_strategy(),
    )
    @settings(max_examples=100, deadline=None)
    def test_output_length_equals_input_length(self, patterns, market_context):
        """Output length equals input length.

        **Validates: Requirements 20.4**

        Property: For any list of patterns, the number of ranked results
        equals the number of input patterns.
        """
        service = create_service_with_mocked_llm()

        result = service.rank_consolidations(patterns, market_context)

        assert len(result) == len(patterns), (
            f"Expected {len(patterns)} results, got {len(result)}"
        )

    @given(market_context=market_context_strategy())
    @settings(max_examples=20, deadline=None)
    def test_empty_input_returns_empty_list(self, market_context):
        """Empty input returns empty list.

        **Validates: Requirements 20.4**

        Property: When given an empty list of patterns,
        rank_consolidations returns an empty list.
        """
        service = create_service_with_mocked_llm()

        result = service.rank_consolidations([], market_context)

        assert result == [], (
            f"Expected empty list for empty input, got {result}"
        )
