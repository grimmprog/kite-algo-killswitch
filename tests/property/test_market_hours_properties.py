"""Property-based tests for market hours countdown correctness (Property 15).

Uses Hypothesis to verify:
- Before market open (before 9:15 IST): countdown shows time remaining until 9:15
- During market hours (9:15-15:30 IST): countdown shows time remaining until 15:30
- After market close (after 15:30 IST): countdown shows time until next day's 9:15

**Validates: Requirements 16.1**
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from datetime import datetime, timezone, timedelta

import pytest
from hypothesis import given, strategies as st, settings, assume

from src.api.routers.status import (
    _compute_market_status_and_countdown,
    IST_OFFSET,
    MARKET_OPEN_HOUR,
    MARKET_OPEN_MINUTE,
    MARKET_CLOSE_HOUR,
    MARKET_CLOSE_MINUTE,
)


# ============================================================
# Strategies
# ============================================================

# Generate any time of day as an IST datetime (hour 0-23, minute 0-59, second 0-59)
ist_datetime_strategy = st.builds(
    lambda hour, minute, second: datetime(
        2025, 1, 15, hour, minute, second, tzinfo=timezone(IST_OFFSET)
    ),
    hour=st.integers(min_value=0, max_value=23),
    minute=st.integers(min_value=0, max_value=59),
    second=st.integers(min_value=0, max_value=59),
)

# Pre-market times: 00:00 to 09:14
pre_market_strategy = st.builds(
    lambda hour, minute, second: datetime(
        2025, 1, 15, hour, minute, second, tzinfo=timezone(IST_OFFSET)
    ),
    hour=st.integers(min_value=0, max_value=9),
    minute=st.integers(min_value=0, max_value=59),
    second=st.integers(min_value=0, max_value=59),
).filter(lambda dt: dt.hour * 60 + dt.minute < MARKET_OPEN_HOUR * 60 + MARKET_OPEN_MINUTE)

# Market hours times: 09:15 to 15:29
market_hours_strategy = st.builds(
    lambda hour, minute, second: datetime(
        2025, 1, 15, hour, minute, second, tzinfo=timezone(IST_OFFSET)
    ),
    hour=st.integers(min_value=9, max_value=15),
    minute=st.integers(min_value=0, max_value=59),
    second=st.integers(min_value=0, max_value=59),
).filter(
    lambda dt: (
        MARKET_OPEN_HOUR * 60 + MARKET_OPEN_MINUTE
        <= dt.hour * 60 + dt.minute
        < MARKET_CLOSE_HOUR * 60 + MARKET_CLOSE_MINUTE
    )
)

# After market close: 15:30 to 23:59
post_market_strategy = st.builds(
    lambda hour, minute, second: datetime(
        2025, 1, 15, hour, minute, second, tzinfo=timezone(IST_OFFSET)
    ),
    hour=st.integers(min_value=15, max_value=23),
    minute=st.integers(min_value=0, max_value=59),
    second=st.integers(min_value=0, max_value=59),
).filter(lambda dt: dt.hour * 60 + dt.minute >= MARKET_CLOSE_HOUR * 60 + MARKET_CLOSE_MINUTE)


# ============================================================
# Property 15: Market Hours Countdown Correctness
# ============================================================


class TestMarketHoursCountdownProperty:
    """Property-based tests for market hours countdown correctness.

    **Validates: Requirements 16.1**

    Properties verified:
    - Pre-market: status is "pre_market" and countdown equals seconds until 9:15 IST
    - During market: status is "open" and countdown equals seconds until 15:30 IST
    - After close: status is "closed" and countdown equals seconds until next day 9:15 IST
    - Countdown is always non-negative
    """

    @given(ist_now=pre_market_strategy)
    @settings(max_examples=200, deadline=None)
    def test_pre_market_countdown_to_open(self, ist_now: datetime):
        """Before 9:15 IST, market status is 'pre_market' and countdown is time until 9:15.

        **Validates: Requirements 16.1**

        Property: For any time before 9:15 IST, the countdown should equal
        the number of seconds remaining until 9:15:00.
        """
        market_status, countdown_seconds = _compute_market_status_and_countdown(ist_now)

        assert market_status == "pre_market"
        assert countdown_seconds >= 0

        # Expected countdown: seconds from ist_now to 9:15:00
        current_time_minutes = ist_now.hour * 60 + ist_now.minute
        market_open_minutes = MARKET_OPEN_HOUR * 60 + MARKET_OPEN_MINUTE
        expected_seconds = (market_open_minutes - current_time_minutes) * 60 - ist_now.second

        assert countdown_seconds == max(0, expected_seconds)

    @given(ist_now=market_hours_strategy)
    @settings(max_examples=200, deadline=None)
    def test_market_open_countdown_to_close(self, ist_now: datetime):
        """Between 9:15 and 15:30 IST, market status is 'open' and countdown is time until 15:30.

        **Validates: Requirements 16.1**

        Property: For any time during market hours (9:15-15:29), the countdown
        should equal the number of seconds remaining until 15:30:00.
        """
        market_status, countdown_seconds = _compute_market_status_and_countdown(ist_now)

        assert market_status == "open"
        assert countdown_seconds >= 0

        # Expected countdown: seconds from ist_now to 15:30:00
        current_time_minutes = ist_now.hour * 60 + ist_now.minute
        market_close_minutes = MARKET_CLOSE_HOUR * 60 + MARKET_CLOSE_MINUTE
        expected_seconds = (market_close_minutes - current_time_minutes) * 60 - ist_now.second

        assert countdown_seconds == max(0, expected_seconds)

    @given(ist_now=post_market_strategy)
    @settings(max_examples=200, deadline=None)
    def test_post_market_countdown_to_next_open(self, ist_now: datetime):
        """After 15:30 IST, market status is 'closed' and countdown is time until next day 9:15.

        **Validates: Requirements 16.1**

        Property: For any time after 15:30 IST, the countdown should equal
        the number of seconds remaining until 9:15:00 the next day.
        """
        market_status, countdown_seconds = _compute_market_status_and_countdown(ist_now)

        assert market_status == "closed"
        assert countdown_seconds >= 0

        # Expected: seconds remaining today + seconds from midnight to 9:15
        current_time_minutes = ist_now.hour * 60 + ist_now.minute
        market_open_minutes = MARKET_OPEN_HOUR * 60 + MARKET_OPEN_MINUTE
        seconds_remaining_today = (24 * 60 - current_time_minutes) * 60 - ist_now.second
        seconds_to_open_next_day = market_open_minutes * 60
        expected_seconds = seconds_remaining_today + seconds_to_open_next_day

        assert countdown_seconds == max(0, expected_seconds)

    @given(ist_now=ist_datetime_strategy)
    @settings(max_examples=300, deadline=None)
    def test_countdown_always_non_negative(self, ist_now: datetime):
        """For any time of day, countdown is always non-negative.

        **Validates: Requirements 16.1**

        Property: For any valid datetime, _compute_market_status_and_countdown
        always returns a countdown_seconds >= 0.
        """
        market_status, countdown_seconds = _compute_market_status_and_countdown(ist_now)

        assert countdown_seconds >= 0
        assert market_status in ("pre_market", "open", "closed")

    @given(ist_now=ist_datetime_strategy)
    @settings(max_examples=300, deadline=None)
    def test_market_status_partitions_day_correctly(self, ist_now: datetime):
        """Market status correctly partitions the day into three phases.

        **Validates: Requirements 16.1**

        Property: For any time of day:
        - Before 9:15 → pre_market
        - 9:15 to 15:29 → open
        - 15:30 onwards → closed
        """
        market_status, _ = _compute_market_status_and_countdown(ist_now)
        current_minutes = ist_now.hour * 60 + ist_now.minute
        open_minutes = MARKET_OPEN_HOUR * 60 + MARKET_OPEN_MINUTE
        close_minutes = MARKET_CLOSE_HOUR * 60 + MARKET_CLOSE_MINUTE

        if current_minutes < open_minutes:
            assert market_status == "pre_market"
        elif current_minutes < close_minutes:
            assert market_status == "open"
        else:
            assert market_status == "closed"
