"""Property-based tests for token expiry time formatting (Property 2).

Uses Hypothesis to verify:
- Future datetimes produce "{N}h {M}m remaining" or "{M}m remaining" patterns
- Past datetimes produce "Expired"
- N and M values are consistent with the actual time difference

**Validates: Requirements 2.2, 2.6**
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import re
from datetime import datetime, timezone, timedelta

import pytest
from hypothesis import given, strategies as st, settings, assume
from unittest.mock import patch

from src.services.broker_settings_service import format_time_remaining


# ============================================================
# Strategies
# ============================================================

# Generate future datetimes: 1 second to 48 hours in the future
future_timedelta_strategy = st.timedeltas(
    min_value=timedelta(seconds=61),  # At least 1 minute + 1 second to avoid boundary
    max_value=timedelta(hours=48),
)

# Generate past datetimes: 1 second to 48 hours in the past
past_timedelta_strategy = st.timedeltas(
    min_value=timedelta(seconds=1),
    max_value=timedelta(hours=48),
)


# ============================================================
# Property 2: Token Expiry Time Formatting
# ============================================================


class TestTokenExpiryTimeFormattingProperty:
    """Property-based tests for token expiry time formatting.

    **Validates: Requirements 2.2, 2.6**

    Properties verified:
    - Future datetimes produce "{N}h {M}m remaining" or "{M}m remaining"
    - Past datetimes produce "Expired"
    - N and M values are consistent with the actual time difference
    """

    @given(delta=future_timedelta_strategy)
    @settings(max_examples=200, deadline=None)
    def test_future_datetime_produces_remaining_pattern(self, delta: timedelta):
        """For any future expiry datetime, format matches "{N}h {M}m remaining" or "{M}m remaining".

        **Validates: Requirements 2.2, 2.6**

        Property: For any future datetime representing a token expiry,
        format_time_remaining SHALL produce a string matching the pattern
        "{N}h {M}m remaining" or "{M}m remaining" where N and M are
        non-negative integers.
        """
        now = datetime.now(timezone.utc)
        expiry = now + delta

        result = format_time_remaining(expiry)

        # Must match one of the two patterns
        hours_minutes_pattern = re.compile(r"^\d+h \d+m remaining$")
        minutes_only_pattern = re.compile(r"^\d+m remaining$")

        assert hours_minutes_pattern.match(result) or minutes_only_pattern.match(result), (
            f"Expected '{result}' to match '{{N}}h {{M}}m remaining' or "
            f"'{{M}}m remaining' for delta={delta}"
        )

    @given(delta=future_timedelta_strategy)
    @settings(max_examples=200, deadline=None)
    def test_future_datetime_values_consistent_with_delta(self, delta: timedelta):
        """N and M values in the formatted string are consistent with the actual time difference.

        **Validates: Requirements 2.2, 2.6**

        Property: For any future datetime, the hours (N) and minutes (M) extracted
        from the formatted string are consistent with the actual timedelta between
        now and the expiry. We allow ±1 minute tolerance due to time elapsed during
        function execution.
        """
        now = datetime.now(timezone.utc)
        expiry = now + delta

        result = format_time_remaining(expiry)

        # Extract hours and minutes from the result
        hours_minutes_match = re.match(r"^(\d+)h (\d+)m remaining$", result)
        minutes_only_match = re.match(r"^(\d+)m remaining$", result)

        expected_total_seconds = delta.total_seconds()
        expected_hours = int(expected_total_seconds // 3600)
        expected_minutes = int((expected_total_seconds % 3600) // 60)

        if hours_minutes_match:
            actual_hours = int(hours_minutes_match.group(1))
            actual_minutes = int(hours_minutes_match.group(2))

            # Allow ±1 minute tolerance for execution time
            actual_total_minutes = actual_hours * 60 + actual_minutes
            expected_total_minutes = expected_hours * 60 + expected_minutes
            assert abs(actual_total_minutes - expected_total_minutes) <= 1, (
                f"Time mismatch: got {actual_hours}h {actual_minutes}m, "
                f"expected ~{expected_hours}h {expected_minutes}m for delta={delta}"
            )
        elif minutes_only_match:
            actual_minutes = int(minutes_only_match.group(1))

            # When hours is 0, only minutes pattern is used
            assert expected_hours == 0 or (expected_hours == 0 and actual_minutes <= 59), (
                f"Got minutes-only format '{result}' but expected_hours={expected_hours}"
            )
            # Allow ±1 minute tolerance
            assert abs(actual_minutes - expected_minutes) <= 1, (
                f"Minutes mismatch: got {actual_minutes}m, "
                f"expected ~{expected_minutes}m for delta={delta}"
            )
        else:
            pytest.fail(f"Result '{result}' didn't match any expected pattern")

    @given(delta=past_timedelta_strategy)
    @settings(max_examples=200, deadline=None)
    def test_past_datetime_produces_expired(self, delta: timedelta):
        """For any past expiry datetime, format_time_remaining returns "Expired".

        **Validates: Requirements 2.2, 2.6**

        Property: For any past datetime, format_time_remaining SHALL return "Expired".
        """
        now = datetime.now(timezone.utc)
        expiry = now - delta

        result = format_time_remaining(expiry)

        assert result == "Expired", (
            f"Expected 'Expired' for past expiry (delta={delta}), got '{result}'"
        )

    @given(delta=future_timedelta_strategy)
    @settings(max_examples=200, deadline=None)
    def test_hours_format_used_only_when_hours_positive(self, delta: timedelta):
        """The "{N}h {M}m remaining" format is used only when N > 0.

        **Validates: Requirements 2.2, 2.6**

        Property: The hours-and-minutes pattern is used when hours >= 1,
        the minutes-only pattern is used when hours == 0.
        """
        now = datetime.now(timezone.utc)
        expiry = now + delta

        result = format_time_remaining(expiry)

        expected_hours = int(delta.total_seconds() // 3600)

        hours_minutes_match = re.match(r"^(\d+)h (\d+)m remaining$", result)
        minutes_only_match = re.match(r"^(\d+)m remaining$", result)

        if hours_minutes_match:
            actual_hours = int(hours_minutes_match.group(1))
            # Hours value should be positive
            assert actual_hours > 0, (
                f"Hours format used but hours={actual_hours} is not positive"
            )
        elif minutes_only_match:
            # If we're using minutes-only, expected hours should be 0
            # Allow tolerance of ±1 minute which could push across boundary
            assert expected_hours <= 0 or delta.total_seconds() < 3660, (
                f"Minutes-only format used but expected_hours={expected_hours} "
                f"(delta={delta})"
            )
