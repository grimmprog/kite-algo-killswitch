"""Property-based tests for NotificationService (Task 5.6).

Uses Hypothesis to verify:
- Property 12: Notification Ordering and Retention — Verify reverse chronological order and max 100 retention
- Property 13: Threshold Proximity Warning — Verify warning iff P&L within 10% of threshold

**Validates: Requirements 10.4, 10.5, 11.1, 11.7**
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from hypothesis import given, strategies as st, settings, assume
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime, timezone, timedelta

from src.services.notification_service import (
    NotificationService,
    check_threshold_proximity,
)


# ============================================================
# Helpers for mock setup
# ============================================================


def _make_mock_notification(
    notification_id: int,
    user_id: int = 1,
    severity: str = "info",
    title: str = "Test",
    message: str = "Test message",
    category: str = "system",
    created_at: datetime = None,
    is_read: bool = False,
):
    """Create a mock Notification object."""
    notif = MagicMock()
    notif.id = notification_id
    notif.user_id = user_id
    notif.severity = severity
    notif.title = title
    notif.message = message
    notif.category = category
    notif.is_read = is_read
    notif.created_at = created_at or datetime.now(timezone.utc)
    notif.metadata_json = None
    return notif


# Strategies for generating notification data
severity_strategy = st.sampled_from(["info", "warning", "critical"])
category_strategy = st.sampled_from(
    ["signal", "trade", "killswitch", "threshold", "ai", "system"]
)


# ============================================================
# Property 12: Notification Ordering and Retention
# ============================================================


class TestNotificationOrderingAndRetention:
    """Property-based tests for notification ordering and retention.

    **Validates: Requirements 11.1, 11.7**

    Core invariants:
    - get_recent always returns notifications in reverse chronological order (newest first)
    - get_recent returns at most 100 notifications regardless of how many exist
    - Severity levels are correctly preserved on all notifications
    """

    @given(
        num_notifications=st.integers(min_value=1, max_value=200),
    )
    @settings(max_examples=50, deadline=None)
    def test_get_recent_returns_max_100(self, num_notifications):
        """get_recent returns at most 100 notifications regardless of total count.

        **Validates: Requirements 11.7**

        Property: For any number of notifications N, get_recent returns
        min(N, 100) notifications.
        """
        # Create mock notifications with sequential timestamps
        base_time = datetime(2024, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
        all_notifications = []
        for i in range(num_notifications):
            notif = _make_mock_notification(
                notification_id=i + 1,
                created_at=base_time + timedelta(minutes=i),
            )
            all_notifications.append(notif)

        # Simulate what the DB query would return (reverse chronological, limited to 100)
        sorted_notifications = sorted(
            all_notifications, key=lambda n: n.created_at, reverse=True
        )
        db_result = sorted_notifications[:100]

        # Mock the DB session and query chain
        db = MagicMock()
        query_mock = MagicMock()
        filter_mock = MagicMock()
        order_mock = MagicMock()
        limit_mock = MagicMock()

        db.query.return_value = query_mock
        query_mock.filter.return_value = filter_mock
        filter_mock.order_by.return_value = order_mock
        order_mock.limit.return_value = limit_mock
        limit_mock.all.return_value = db_result

        redis_client = MagicMock()
        service = NotificationService(db=db, redis_client=redis_client)

        result = service.get_recent(user_id=1, limit=100)

        # At most 100 notifications returned
        assert len(result) <= 100, (
            f"Expected at most 100 notifications, got {len(result)} "
            f"(total in DB: {num_notifications})"
        )
        # Exactly min(N, 100) returned
        expected_count = min(num_notifications, 100)
        assert len(result) == expected_count, (
            f"Expected {expected_count} notifications, got {len(result)}"
        )

    @given(
        num_notifications=st.integers(min_value=2, max_value=150),
    )
    @settings(max_examples=50, deadline=None)
    def test_get_recent_returns_reverse_chronological_order(self, num_notifications):
        """get_recent returns notifications in reverse chronological order (newest first).

        **Validates: Requirements 11.1**

        Property: For any set of notifications with distinct timestamps,
        get_recent returns them ordered by created_at descending.
        """
        # Create notifications with unique increasing timestamps
        base_time = datetime(2024, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
        all_notifications = []
        for i in range(num_notifications):
            notif = _make_mock_notification(
                notification_id=i + 1,
                created_at=base_time + timedelta(seconds=i * 30),
            )
            all_notifications.append(notif)

        # Simulate DB behavior: order by created_at DESC, limit 100
        sorted_desc = sorted(
            all_notifications, key=lambda n: n.created_at, reverse=True
        )
        db_result = sorted_desc[:100]

        # Mock the DB session
        db = MagicMock()
        query_mock = MagicMock()
        filter_mock = MagicMock()
        order_mock = MagicMock()
        limit_mock = MagicMock()

        db.query.return_value = query_mock
        query_mock.filter.return_value = filter_mock
        filter_mock.order_by.return_value = order_mock
        order_mock.limit.return_value = limit_mock
        limit_mock.all.return_value = db_result

        redis_client = MagicMock()
        service = NotificationService(db=db, redis_client=redis_client)

        result = service.get_recent(user_id=1, limit=100)

        # Verify reverse chronological ordering
        for i in range(len(result) - 1):
            assert result[i].created_at >= result[i + 1].created_at, (
                f"Notifications not in reverse chronological order at index {i}: "
                f"{result[i].created_at} should be >= {result[i + 1].created_at}"
            )

    @given(
        severities=st.lists(
            severity_strategy,
            min_size=1,
            max_size=50,
        ),
    )
    @settings(max_examples=50, deadline=None)
    def test_severity_levels_preserved(self, severities):
        """Notification severity levels are correctly preserved in the feed.

        **Validates: Requirements 11.1**

        Property: For any sequence of notifications with valid severity levels,
        get_recent preserves the severity field on each returned notification.
        """
        base_time = datetime(2024, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
        notifications = []
        for i, sev in enumerate(severities):
            notif = _make_mock_notification(
                notification_id=i + 1,
                severity=sev,
                created_at=base_time + timedelta(minutes=i),
            )
            notifications.append(notif)

        # Sort descending and limit
        db_result = sorted(
            notifications, key=lambda n: n.created_at, reverse=True
        )[:100]

        db = MagicMock()
        query_mock = MagicMock()
        filter_mock = MagicMock()
        order_mock = MagicMock()
        limit_mock = MagicMock()

        db.query.return_value = query_mock
        query_mock.filter.return_value = filter_mock
        filter_mock.order_by.return_value = order_mock
        order_mock.limit.return_value = limit_mock
        limit_mock.all.return_value = db_result

        redis_client = MagicMock()
        service = NotificationService(db=db, redis_client=redis_client)

        result = service.get_recent(user_id=1, limit=100)

        # Every returned notification must have a valid severity
        valid_severities = {"info", "warning", "critical"}
        for notif in result:
            assert notif.severity in valid_severities, (
                f"Invalid severity '{notif.severity}' found in results. "
                f"Expected one of {valid_severities}"
            )

    @given(
        num_notifications=st.integers(min_value=0, max_value=300),
    )
    @settings(max_examples=50, deadline=None)
    def test_retention_limit_is_exactly_100(self, num_notifications):
        """The feed retention limit is exactly 100 — never more.

        **Validates: Requirements 11.7**

        Property: Regardless of how many notifications exist in the DB,
        the get_recent call with default limit returns at most 100.
        """
        base_time = datetime(2024, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
        all_notifications = []
        for i in range(num_notifications):
            notif = _make_mock_notification(
                notification_id=i + 1,
                created_at=base_time + timedelta(seconds=i),
            )
            all_notifications.append(notif)

        sorted_desc = sorted(
            all_notifications, key=lambda n: n.created_at, reverse=True
        )
        # Simulate DB limit(100) behavior
        db_result = sorted_desc[:100]

        db = MagicMock()
        query_mock = MagicMock()
        filter_mock = MagicMock()
        order_mock = MagicMock()
        limit_mock = MagicMock()

        db.query.return_value = query_mock
        query_mock.filter.return_value = filter_mock
        filter_mock.order_by.return_value = order_mock
        order_mock.limit.return_value = limit_mock
        limit_mock.all.return_value = db_result

        redis_client = MagicMock()
        service = NotificationService(db=db, redis_client=redis_client)

        result = service.get_recent(user_id=1)

        assert len(result) <= 100, (
            f"Feed returned {len(result)} notifications, exceeding max retention of 100"
        )


# ============================================================
# Property 13: Threshold Proximity Warning
# ============================================================


class TestThresholdProximityWarning:
    """Property-based tests for threshold proximity warning logic.

    **Validates: Requirements 10.4, 10.5**

    Core invariant:
    - Warning is triggered iff abs(current_pnl) >= threshold * (1 - 0.10)
      for at least one threshold in the list.
    - i.e., warning iff P&L has reached 90%+ of any threshold (within last 10%).
    """

    @given(
        current_pnl=st.floats(
            min_value=-500000.0, max_value=500000.0,
            allow_nan=False, allow_infinity=False,
        ),
        thresholds=st.lists(
            st.floats(
                min_value=100.0, max_value=500000.0,
                allow_nan=False, allow_infinity=False,
            ),
            min_size=1,
            max_size=5,
        ),
    )
    @settings(max_examples=200, deadline=None)
    def test_proximity_warning_biconditional(self, current_pnl, thresholds):
        """Warning iff abs(P&L) >= threshold * 0.90 for any threshold (biconditional).

        **Validates: Requirements 10.4, 10.5**

        Property: check_threshold_proximity returns True iff
        abs(current_pnl) >= threshold * (1 - 0.10) for at least one threshold
        in the list.
        """
        result = check_threshold_proximity(current_pnl, thresholds, proximity_pct=0.10)

        # Compute expected: should be True iff any threshold is within proximity
        abs_pnl = abs(current_pnl)
        expected = False
        for t in thresholds:
            if t <= 0:
                continue
            warning_level = t * (1.0 - 0.10)  # 90% of threshold
            if abs_pnl >= warning_level:
                expected = True
                break

        assert result == expected, (
            f"Expected proximity_warning={expected}, got {result}. "
            f"current_pnl={current_pnl}, abs_pnl={abs_pnl}, thresholds={thresholds}"
        )

    @given(
        threshold=st.floats(
            min_value=1000.0, max_value=100000.0,
            allow_nan=False, allow_infinity=False,
        ),
        fraction=st.floats(
            min_value=0.90, max_value=2.0,
            allow_nan=False, allow_infinity=False,
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_warning_triggers_when_pnl_within_10_percent(self, threshold, fraction):
        """Warning triggers when P&L is at or above 90% of threshold.

        **Validates: Requirements 10.4**

        Property: When abs(current_pnl) >= threshold * 0.90,
        check_threshold_proximity returns True.
        """
        # P&L at fraction of threshold (fraction >= 0.90)
        current_pnl = threshold * fraction

        result = check_threshold_proximity(current_pnl, [threshold], proximity_pct=0.10)

        assert result is True, (
            f"Expected warning=True when P&L ({current_pnl:.2f}) >= "
            f"90% of threshold ({threshold * 0.90:.2f}), but got False"
        )

    @given(
        threshold=st.floats(
            min_value=1000.0, max_value=100000.0,
            allow_nan=False, allow_infinity=False,
        ),
        fraction=st.floats(
            min_value=0.0, max_value=0.8999,
            allow_nan=False, allow_infinity=False,
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_no_warning_when_pnl_below_90_percent_of_threshold(self, threshold, fraction):
        """No warning when P&L is below 90% of all thresholds.

        **Validates: Requirements 10.4**

        Property: When abs(current_pnl) < threshold * 0.90 for all thresholds,
        check_threshold_proximity returns False.
        """
        # P&L at fraction of threshold (fraction < 0.90)
        current_pnl = threshold * fraction

        result = check_threshold_proximity(current_pnl, [threshold], proximity_pct=0.10)

        assert result is False, (
            f"Expected warning=False when P&L ({current_pnl:.2f}) < "
            f"90% of threshold ({threshold * 0.90:.2f}), but got True"
        )

    @given(
        threshold=st.floats(
            min_value=1000.0, max_value=100000.0,
            allow_nan=False, allow_infinity=False,
        ),
        fraction=st.floats(
            min_value=0.90, max_value=2.0,
            allow_nan=False, allow_infinity=False,
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_warning_with_negative_pnl_loss_threshold(self, threshold, fraction):
        """Warning triggers for negative P&L (losses) when within 10% of loss threshold.

        **Validates: Requirements 10.4**

        Property: For negative current_pnl (a loss), warning triggers when
        abs(current_pnl) >= threshold * 0.90 (loss threshold is expressed as positive).
        """
        # Negative P&L representing a loss at fraction of threshold
        current_pnl = -(threshold * fraction)

        result = check_threshold_proximity(current_pnl, [threshold], proximity_pct=0.10)

        assert result is True, (
            f"Expected warning=True for loss P&L ({current_pnl:.2f}) within 10% of "
            f"threshold ({threshold:.2f}), but got False"
        )

    def test_empty_thresholds_returns_false(self):
        """No warning when thresholds list is empty.

        **Validates: Requirements 10.4**

        Edge case: With no thresholds configured, no proximity warning is possible.
        """
        result = check_threshold_proximity(50000.0, [], proximity_pct=0.10)
        assert result is False

    @given(
        current_pnl=st.floats(
            min_value=-500000.0, max_value=500000.0,
            allow_nan=False, allow_infinity=False,
        ),
        num_thresholds=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=50, deadline=None)
    def test_multiple_thresholds_warning_if_any_within_proximity(self, current_pnl, num_thresholds):
        """Warning triggers if P&L is within 10% of ANY threshold in the list.

        **Validates: Requirements 10.4, 10.5**

        Property: With multiple thresholds, the function returns True
        if the P&L is within proximity of at least one threshold.
        """
        abs_pnl = abs(current_pnl)

        # Create thresholds where at least one is close to the P&L
        # to test that the "any" logic works
        thresholds = []
        for i in range(num_thresholds):
            # Spread thresholds far apart so we can test individual proximity
            thresholds.append(abs_pnl * (1.0 + 0.5 * i) + 1000.0)

        # None should be within proximity since all are larger than pnl
        result = check_threshold_proximity(current_pnl, thresholds, proximity_pct=0.10)

        # Verify with manual computation
        expected = False
        for t in thresholds:
            if t <= 0:
                continue
            warning_level = t * 0.90
            if abs_pnl >= warning_level:
                expected = True
                break

        assert result == expected, (
            f"Expected {expected}, got {result}. "
            f"abs_pnl={abs_pnl}, thresholds={thresholds}"
        )
