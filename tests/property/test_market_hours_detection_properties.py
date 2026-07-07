"""Property-based tests for Market Hours Detection (Property 9).

Uses Hypothesis to verify:
- For any datetime on a weekday between 9:15 AM and 3:30 PM IST,
  _is_market_open_at() SHALL return True.
- For any datetime outside this window or on a weekend,
  _is_market_open_at() SHALL return False.

**Validates: Requirements 7.4**
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given, strategies as st, settings
from unittest.mock import MagicMock

from src.services.market_data_service import MarketDataService

IST = ZoneInfo("Asia/Kolkata")

# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def service():
    """Create a MarketDataService with mocked dependencies (only need the method)."""
    mock_db = MagicMock()
    mock_redis = MagicMock()
    return MarketDataService(db=mock_db, redis_client=mock_redis)


# ============================================================
# Strategies
# ============================================================

# Weekdays: Monday=0 through Friday=4
# Weekends: Saturday=5 and Sunday=6

# Date strategy: pick a year/month/day that results in a specific weekday
# Using a fixed date range to keep things simple and fast
weekday_dates = st.dates(
    min_value=datetime(2024, 1, 1).date(),
    max_value=datetime(2025, 12, 31).date(),
).filter(lambda d: d.weekday() < 5)

weekend_dates = st.dates(
    min_value=datetime(2024, 1, 1).date(),
    max_value=datetime(2025, 12, 31).date(),
).filter(lambda d: d.weekday() >= 5)


def market_hours_time():
    """Generate times within market hours: 9:15:00 to 15:30:00 IST (inclusive)."""
    return st.builds(
        time,
        hour=st.integers(min_value=9, max_value=15),
        minute=st.integers(min_value=0, max_value=59),
        second=st.integers(min_value=0, max_value=59),
    ).filter(
        lambda t: time(9, 15, 0) <= t <= time(15, 30, 0)
    )


def before_market_time():
    """Generate times before market opens: 00:00:00 to 09:14:59 IST."""
    return st.builds(
        time,
        hour=st.integers(min_value=0, max_value=9),
        minute=st.integers(min_value=0, max_value=59),
        second=st.integers(min_value=0, max_value=59),
    ).filter(
        lambda t: t < time(9, 15, 0)
    )


def after_market_time():
    """Generate times after market closes: 15:30:01 to 23:59:59 IST."""
    return st.builds(
        time,
        hour=st.integers(min_value=15, max_value=23),
        minute=st.integers(min_value=0, max_value=59),
        second=st.integers(min_value=0, max_value=59),
    ).filter(
        lambda t: t > time(15, 30, 0)
    )


def build_ist_datetime(date, t):
    """Combine a date and time into an IST-aware datetime."""
    return datetime(
        date.year, date.month, date.day,
        t.hour, t.minute, t.second,
        tzinfo=IST,
    )


# ============================================================
# Property 9: Market Hours Detection
# ============================================================


class TestMarketHoursDetectionProperty:
    """Property-based tests for market hours detection.

    **Validates: Requirements 7.4**

    Core invariant:
    - For any datetime on a weekday between 9:15 AM and 3:30 PM IST,
      _is_market_open_at() returns True.
    - For any datetime outside this window or on a weekend,
      _is_market_open_at() returns False.
    """

    @given(date=weekday_dates, t=market_hours_time())
    @settings(max_examples=200, deadline=None)
    def test_weekday_during_market_hours_returns_true(self, date, t):
        """Weekday datetimes within 9:15-15:30 IST return True.

        **Validates: Requirements 7.4**

        Property: For any datetime on a weekday (Mon-Fri) between
        9:15:00 AM and 3:30:00 PM IST (inclusive), _is_market_open_at()
        SHALL return True.
        """
        mock_db = MagicMock()
        mock_redis = MagicMock()
        service = MarketDataService(db=mock_db, redis_client=mock_redis)

        dt = build_ist_datetime(date, t)
        result = service._is_market_open_at(dt)

        assert result is True, (
            f"Expected True for weekday {date} (weekday={date.weekday()}) "
            f"at {t}, got {result}"
        )

    @given(date=weekday_dates, t=before_market_time())
    @settings(max_examples=200, deadline=None)
    def test_weekday_before_market_hours_returns_false(self, date, t):
        """Weekday datetimes before 9:15 IST return False.

        **Validates: Requirements 7.4**

        Property: For any datetime on a weekday before 9:15:00 AM IST,
        _is_market_open_at() SHALL return False.
        """
        mock_db = MagicMock()
        mock_redis = MagicMock()
        service = MarketDataService(db=mock_db, redis_client=mock_redis)

        dt = build_ist_datetime(date, t)
        result = service._is_market_open_at(dt)

        assert result is False, (
            f"Expected False for weekday {date} at {t} (before market open), "
            f"got {result}"
        )

    @given(date=weekday_dates, t=after_market_time())
    @settings(max_examples=200, deadline=None)
    def test_weekday_after_market_hours_returns_false(self, date, t):
        """Weekday datetimes after 15:30 IST return False.

        **Validates: Requirements 7.4**

        Property: For any datetime on a weekday after 3:30:00 PM IST,
        _is_market_open_at() SHALL return False.
        """
        mock_db = MagicMock()
        mock_redis = MagicMock()
        service = MarketDataService(db=mock_db, redis_client=mock_redis)

        dt = build_ist_datetime(date, t)
        result = service._is_market_open_at(dt)

        assert result is False, (
            f"Expected False for weekday {date} at {t} (after market close), "
            f"got {result}"
        )

    @given(
        date=weekend_dates,
        t=st.builds(
            time,
            hour=st.integers(min_value=0, max_value=23),
            minute=st.integers(min_value=0, max_value=59),
            second=st.integers(min_value=0, max_value=59),
        ),
    )
    @settings(max_examples=200, deadline=None)
    def test_weekend_any_time_returns_false(self, date, t):
        """Weekend datetimes at any time return False.

        **Validates: Requirements 7.4**

        Property: For any datetime on a weekend (Saturday or Sunday)
        at any time of day, _is_market_open_at() SHALL return False.
        """
        mock_db = MagicMock()
        mock_redis = MagicMock()
        service = MarketDataService(db=mock_db, redis_client=mock_redis)

        dt = build_ist_datetime(date, t)
        result = service._is_market_open_at(dt)

        assert result is False, (
            f"Expected False for weekend {date} (weekday={date.weekday()}) "
            f"at {t}, got {result}"
        )
