"""Property-based tests for AI Narrative Length Constraint (Task 7.10).

Uses Hypothesis to verify that format_narrative always enforces the max 5
key_points constraint and validates bias to one of bullish/bearish/neutral.

**Validates: Requirements 22.5**

Properties:
- Property 21: AI Narrative Length Constraint
  Verify key_points list ≤ 5 items regardless of input size.
  Also verify bias is always one of ["bullish", "bearish", "neutral"].
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from hypothesis import given, strategies as st, settings, assume

from src.services.ai_trading_service import (
    AIMarketNarrative,
    format_narrative,
)


# ============================================================
# Custom Strategies — Raw Response Generation
# ============================================================

VALID_BIASES = ["bullish", "bearish", "neutral"]
VALID_SESSION_TYPES = ["morning_brief", "mid_morning", "lunch", "afternoon"]


def key_points_strategy(min_size=0, max_size=20):
    """Generate a list of random string key points of varying lengths."""
    return st.lists(
        st.text(min_size=1, max_size=200),
        min_size=min_size,
        max_size=max_size,
    )


@st.composite
def raw_narrative_response(draw):
    """Generate a raw_response dict simulating an LLM response with arbitrary key_points.

    Generates key_points lists of 0-20 items, random bias strings (both valid and invalid),
    and optional fields to stress-test format_narrative.
    """
    key_points = draw(key_points_strategy(min_size=0, max_size=20))

    # Mix of valid and invalid biases
    bias = draw(st.one_of(
        st.sampled_from(VALID_BIASES),
        st.text(min_size=0, max_size=50),
    ))

    # Mix of valid and invalid session types
    session_type = draw(st.one_of(
        st.sampled_from(VALID_SESSION_TYPES),
        st.text(min_size=0, max_size=50),
    ))

    expected_range = draw(st.one_of(
        st.fixed_dictionaries({
            "low": st.floats(min_value=0, max_value=100000, allow_nan=False, allow_infinity=False),
            "high": st.floats(min_value=0, max_value=100000, allow_nan=False, allow_infinity=False),
        }),
        st.just({}),
        st.just(None),
    ))

    key_levels = draw(st.one_of(
        st.fixed_dictionaries({
            "support": st.lists(st.floats(min_value=0, max_value=100000, allow_nan=False, allow_infinity=False), max_size=5),
            "resistance": st.lists(st.floats(min_value=0, max_value=100000, allow_nan=False, allow_infinity=False), max_size=5),
        }),
        st.just({}),
        st.just(None),
    ))

    response = {
        "key_points": key_points,
        "bias": bias,
        "session_type": session_type,
    }

    if expected_range is not None:
        response["expected_range"] = expected_range
    if key_levels is not None:
        response["key_levels"] = key_levels

    # Optionally include detailed_analysis
    if draw(st.booleans()):
        response["detailed_analysis"] = draw(st.text(min_size=0, max_size=500))

    return response


@st.composite
def raw_response_with_invalid_fields(draw):
    """Generate raw_response dicts with missing or invalid field types.

    Tests that format_narrative applies defaults gracefully.
    """
    # key_points could be missing, None, a string, or a number
    key_points = draw(st.one_of(
        st.just(None),
        st.just("not a list"),
        st.just(42),
        st.lists(st.text(min_size=1, max_size=100), min_size=0, max_size=20),
    ))

    # bias could be missing, None, empty, or garbage
    bias = draw(st.one_of(
        st.just(None),
        st.just(""),
        st.just("BULLISH"),  # wrong case
        st.just("up"),
        st.just(123),
        st.sampled_from(VALID_BIASES),
    ))

    response = {}
    if key_points is not None:
        response["key_points"] = key_points
    if bias is not None:
        response["bias"] = bias

    return response


# ============================================================
# Property 21: AI Narrative Length Constraint
# ============================================================


class TestAINarrativeLengthConstraintProperty:
    """Property-based tests for AI narrative key_points length constraint.

    **Validates: Requirements 22.5**

    Core invariants:
    - key_points list always has at most 5 items after format_narrative
    - bias is always one of ["bullish", "bearish", "neutral"] after format_narrative
    - session_type is always one of valid session types after format_narrative
    """

    @given(data=raw_narrative_response())
    @settings(max_examples=200, deadline=None)
    def test_key_points_always_at_most_5_items(self, data):
        """For any raw LLM response with 0-20 key_points, format_narrative
        MUST produce a result with at most 5 key_points.

        **Validates: Requirements 22.5**

        Property: len(result.key_points) <= 5 for any input list size.
        """
        result = format_narrative(data)

        assert isinstance(result, AIMarketNarrative)
        assert len(result.key_points) <= 5, (
            f"Expected at most 5 key_points, got {len(result.key_points)} "
            f"from input with {len(data.get('key_points', []))} items"
        )

    @given(data=raw_narrative_response())
    @settings(max_examples=200, deadline=None)
    def test_bias_always_valid(self, data):
        """For any raw LLM response with arbitrary bias value, format_narrative
        MUST produce a result with bias in ["bullish", "bearish", "neutral"].

        **Validates: Requirements 22.5**

        Property: result.bias in VALID_BIASES for any input bias string.
        """
        result = format_narrative(data)

        assert isinstance(result, AIMarketNarrative)
        assert result.bias in VALID_BIASES, (
            f"Expected bias to be one of {VALID_BIASES}, got '{result.bias}' "
            f"from input bias '{data.get('bias')}'"
        )

    @given(data=raw_narrative_response())
    @settings(max_examples=200, deadline=None)
    def test_session_type_always_valid(self, data):
        """For any raw LLM response with arbitrary session_type, format_narrative
        MUST produce a result with a valid session type.

        **Validates: Requirements 22.5**

        Property: result.session_type in VALID_SESSION_TYPES for any input.
        """
        result = format_narrative(data)

        assert isinstance(result, AIMarketNarrative)
        assert result.session_type in VALID_SESSION_TYPES, (
            f"Expected session_type to be one of {VALID_SESSION_TYPES}, "
            f"got '{result.session_type}' from input '{data.get('session_type')}'"
        )

    @given(data=raw_response_with_invalid_fields())
    @settings(max_examples=100, deadline=None)
    def test_defaults_applied_for_invalid_or_missing_fields(self, data):
        """For any raw LLM response with invalid/missing fields, format_narrative
        MUST still produce a valid AIMarketNarrative with sensible defaults.

        **Validates: Requirements 22.5**

        Property: format_narrative never raises on malformed input and always
        returns a valid AIMarketNarrative with key_points <= 5 and valid bias.
        """
        result = format_narrative(data)

        assert isinstance(result, AIMarketNarrative)
        assert len(result.key_points) <= 5, (
            f"Expected at most 5 key_points with invalid input, got {len(result.key_points)}"
        )
        assert result.bias in VALID_BIASES, (
            f"Expected valid bias with invalid input, got '{result.bias}'"
        )
        assert result.session_type in VALID_SESSION_TYPES, (
            f"Expected valid session_type with invalid input, got '{result.session_type}'"
        )

    @given(
        num_points=st.integers(min_value=6, max_value=20),
    )
    @settings(max_examples=50, deadline=None)
    def test_key_points_truncated_preserves_first_five(self, num_points):
        """When key_points has more than 5 items, format_narrative MUST keep
        only the first 5 items (preserving order).

        **Validates: Requirements 22.5**

        Property: result.key_points == input_key_points[:5] when len(input) > 5.
        """
        key_points = [f"point_{i}" for i in range(num_points)]
        raw_response = {
            "key_points": key_points,
            "bias": "bullish",
            "session_type": "morning_brief",
            "expected_range": {"low": 100.0, "high": 200.0},
            "key_levels": {"support": [100.0], "resistance": [200.0]},
        }

        result = format_narrative(raw_response)

        assert len(result.key_points) == 5, (
            f"Expected exactly 5 key_points from {num_points} input items, "
            f"got {len(result.key_points)}"
        )
        assert result.key_points == key_points[:5], (
            f"Expected first 5 items preserved in order, "
            f"got {result.key_points} instead of {key_points[:5]}"
        )
