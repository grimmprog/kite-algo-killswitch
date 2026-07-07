"""Property-based tests for market hours countdown correctness.

**Validates: Requirements 16.1**

Property 15: Market Hours Countdown Correctness
  - Verify pre_market status for times before 9:15 IST with correct countdown
  - Verify open status for times between 9:15 and 15:30 IST with correct countdown
  - Verify closed status for times after 15:30 IST
  - Verify countdown is always non-negative
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from hypothesis import given, assume, settings
from hypothesis import strategies as st
from datetime import datetime, timezone, timedelta

from src.api.routers.status import _compute_market_status_and_countdown


# ---------------------------------------------------------------------------
# Constants (mirrored from status router)
# ---------------------------------------------------------------------------

MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 15
MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MINUTE = 30

MARKET_OPEN_MINUTES = MARKET_OPEN_HOUR * 60 + MARKET_OPEN_MINUTE  # 555
MARKET_CLOSE_MINUTES = MARKET_CLOSE_HOUR * 60 + MARKET_CLOSE_MINUTE  # 930


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate datetime objects for any time of day
ist_datetime = st.builds(
    datetime,
    year=st.just(2024),
    month=st.integers(min_value=1, max_value=12),
    day=st.integers(min_value=1, max_value=28),  # safe for all months
    hour=st.integers(min_value=0, max_value=23),
    minute=st.integers(min_value=0, max_value=59),
    second=st.integers(min_value=0, max_value=59),
)

# Pre-market times: 0:00 to 9:14:59
pre_market_datetime = st.builds(
    datetime,
    year=st.just(2024),
    month=st.integers(min_value=1, max_value=12),
    day=st.integers(min_value=1, max_value=28),
    hour=st.integers(min_value=0, max_value=9),
    minute=st.integers(min_value=0, max_value=59),
    second=st.integers(min_value=0, max_value=59),
).filter(lambda dt: dt.hour * 60 + dt.minute < MARKET_OPEN_MINUTES)

# Market open times: 9:15 to 15:29:59
market_open_datetime = st.builds(
    datetime,
    year=st.just(2024),
    month=st.integers(min_value=1, max_value=12),
    day=st.integers(min_value=1, max_value=28),
    hour=st.integers(min_value=9, max_value=15),
    minute=st.integers(min_value=0, max_value=59),
    second=st.integers(min_value=0, max_value=59),
).filter(
    lambda dt: MARKET_OPEN_MINUTES <= dt.hour * 60 + dt.minute < MARKET_CLOSE_MINUTES
)

# Market closed times: 15:30 to 23:59:59
market_closed_datetime = st.builds(
    datetime,
    year=st.just(2024),
    month=st.integers(min_value=1, max_value=12),
    day=st.integers(min_value=1, max_value=28),
    hour=st.integers(min_value=15, max_value=23),
    minute=st.integers(min_value=0, max_value=59),
    second=st.integers(min_value=0, max_value=59),
).filter(lambda dt: dt.hour * 60 + dt.minute >= MARKET_CLOSE_MINUTES)


# ---------------------------------------------------------------------------
# Property 15: Market Hours Countdown Correctness
# ---------------------------------------------------------------------------


class TestMarketHoursCountdownProperty:
    """Property 15: Verify correct countdown before 9:15 IST and between 9:15-15:30 IST.

    **Validates: Requirements 16.1**
    """

    @given(ist_now=pre_market_datetime)
    @settings(max_examples=500)
    def test_pre_market_status_before_915(self, ist_now):
        """Before 9:15 IST, market_status is 'pre_market' with countdown to 9:15."""
        market_status, countdown_seconds = _compute_market_status_and_countdown(ist_now)

        assert market_status == "pre_market", (
            f"Expected 'pre_market' at {ist_now.strftime('%H:%M:%S')}, got '{market_status}'"
        )

        # Verify countdown: seconds until 9:15:00
        current_time_minutes = ist_now.hour * 60 + ist_now.minute
        expected_seconds = (MARKET_OPEN_MINUTES - current_time_minutes) * 60 - ist_now.second
        expected_seconds = max(0, expected_seconds)

        assert countdown_seconds == expected_seconds, (
            f"Expected countdown={expected_seconds}s at {ist_now.strftime('%H:%M:%S')}, "
            f"got {countdown_seconds}s"
        )

    @given(ist_now=market_open_datetime)
    @settings(max_examples=500)
    def test_open_status_between_915_and_1530(self, ist_now):
        """Between 9:15 and 15:30 IST, market_status is 'open' with countdown to 15:30."""
        market_status, countdown_seconds = _compute_market_status_and_countdown(ist_now)

        assert market_status == "open", (
            f"Expected 'open' at {ist_now.strftime('%H:%M:%S')}, got '{market_status}'"
        )

        # Verify countdown: seconds until 15:30:00
        current_time_minutes = ist_now.hour * 60 + ist_now.minute
        expected_seconds = (MARKET_CLOSE_MINUTES - current_time_minutes) * 60 - ist_now.second
        expected_seconds = max(0, expected_seconds)

        assert countdown_seconds == expected_seconds, (
            f"Expected countdown={expected_seconds}s at {ist_now.strftime('%H:%M:%S')}, "
            f"got {countdown_seconds}s"
        )

    @given(ist_now=market_closed_datetime)
    @settings(max_examples=500)
    def test_closed_status_after_1530(self, ist_now):
        """After 15:30 IST, market_status is 'closed' with countdown to next day 9:15."""
        market_status, countdown_seconds = _compute_market_status_and_countdown(ist_now)

        assert market_status == "closed", (
            f"Expected 'closed' at {ist_now.strftime('%H:%M:%S')}, got '{market_status}'"
        )

        # Verify countdown: seconds until next day 9:15
        current_time_minutes = ist_now.hour * 60 + ist_now.minute
        seconds_remaining_today = (24 * 60 - current_time_minutes) * 60 - ist_now.second
        seconds_to_open_next_day = MARKET_OPEN_MINUTES * 60
        expected_seconds = max(0, seconds_remaining_today + seconds_to_open_next_day)

        assert countdown_seconds == expected_seconds, (
            f"Expected countdown={expected_seconds}s at {ist_now.strftime('%H:%M:%S')}, "
            f"got {countdown_seconds}s"
        )

    @given(ist_now=ist_datetime)
    @settings(max_examples=500)
    def test_countdown_is_always_non_negative(self, ist_now):
        """Countdown is always >= 0 regardless of time of day."""
        market_status, countdown_seconds = _compute_market_status_and_countdown(ist_now)

        assert countdown_seconds >= 0, (
            f"Countdown should be non-negative, got {countdown_seconds} "
            f"at {ist_now.strftime('%H:%M:%S')}"
        )

    @given(ist_now=ist_datetime)
    @settings(max_examples=500)
    def test_status_covers_all_time_ranges(self, ist_now):
        """Every time of day maps to exactly one of pre_market, open, or closed."""
        market_status, countdown_seconds = _compute_market_status_and_countdown(ist_now)

        valid_statuses = {"pre_market", "open", "closed"}
        assert market_status in valid_statuses, (
            f"Unexpected market_status '{market_status}' at {ist_now.strftime('%H:%M:%S')}"
        )

        # Verify status aligns with time boundaries
        current_time_minutes = ist_now.hour * 60 + ist_now.minute
        if current_time_minutes < MARKET_OPEN_MINUTES:
            assert market_status == "pre_market"
        elif current_time_minutes < MARKET_CLOSE_MINUTES:
            assert market_status == "open"
        else:
            assert market_status == "closed"
