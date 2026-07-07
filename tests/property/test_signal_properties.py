"""Property-based tests for SignalService — Signal Countdown and Expiry (Property 9).

Uses Hypothesis to verify:
- Remaining time calculation correctness
- Expiry state transition behavior
- State machine: only "pending" signals can be approved/rejected/expired

**Validates: Requirements 4.5, 4.6**
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, strategies as st, settings, assume

from src.services.signal_service import SignalService, _signal_expiry_key


# ============================================================
# Strategies
# ============================================================

# Generate random countdown durations (1-300 seconds)
countdown_strategy = st.integers(min_value=1, max_value=300)

# Generate valid signal data
signal_data_strategy = st.fixed_dictionaries(
    {
        "signal_type": st.sampled_from(["trend_pullback", "consolidation_breakout"]),
        "symbol": st.from_regex(r"[A-Z]{4,10}\d{5}(CE|PE)", fullmatch=True),
        "confidence_score": st.floats(min_value=50.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        "entry_price": st.floats(min_value=1.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
        "stop_loss": st.floats(min_value=1.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
        "target_price": st.floats(min_value=1.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
        "max_potential_loss": st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
    }
)

# Valid user IDs
user_id_strategy = st.integers(min_value=1, max_value=10000)

# Non-pending statuses for state machine tests
non_pending_status_strategy = st.sampled_from(["approved", "rejected", "expired"])


# ============================================================
# Test Infrastructure
# ============================================================


def create_mock_db():
    """Create a mock SQLAlchemy session that tracks added signals."""
    db = MagicMock()
    added_signals = []

    def _add(obj):
        added_signals.append(obj)

    def _refresh(obj):
        # Simulate DB assigning an auto-increment ID
        obj.id = len(added_signals)

    db.add.side_effect = _add
    db.refresh.side_effect = _refresh
    db.commit.return_value = None

    return db, added_signals


def create_mock_redis(ttl_value=45):
    """Create a mock RedisClient with configurable TTL response."""
    redis = MagicMock()
    redis.set.return_value = True
    redis.delete.return_value = 1
    redis.ttl.return_value = ttl_value
    return redis


def create_pending_signal_mock(db, signal_id=1, user_id=1, status="pending"):
    """Set up a mock signal in the DB query chain."""
    signal = MagicMock()
    signal.id = signal_id
    signal.user_id = user_id
    signal.status = status
    signal.symbol = "NIFTY24500CE"
    signal.entry_price = 250.0
    signal.stop_loss = 230.0
    signal.target_price = 290.0
    signal.signal_type = "trend_pullback"
    signal.confidence_score = 75.0
    db.query.return_value.filter.return_value.first.return_value = signal
    return signal


# ============================================================
# Property 9: Signal Countdown and Expiry
# ============================================================


class TestSignalCountdownAndExpiry:
    """Property-based tests for signal countdown and expiry.

    **Validates: Requirements 4.5, 4.6**

    Properties verified:
    1. After create_signal, expires_at ≈ created_at + countdown_seconds
    2. expire_signal transitions status to "expired"
    3. remaining_seconds in get_pending_signals is always >= 0
    4. State machine: only "pending" signals can be approved/rejected/expired
    """

    @given(
        countdown_seconds=countdown_strategy,
        signal_data=signal_data_strategy,
        user_id=user_id_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_expires_at_equals_created_at_plus_countdown(
        self, countdown_seconds, signal_data, user_id
    ):
        """Signal expires_at should equal created_at + countdown_seconds (within tolerance).

        **Validates: Requirements 4.5**

        Property: For any countdown_seconds in [1, 300], the created signal
        has expires_at = created_at + timedelta(seconds=countdown_seconds)
        with at most 2 seconds of tolerance for execution time.
        """
        db, added_signals = create_mock_db()
        redis = create_mock_redis()
        service = SignalService(db=db, redis_client=redis)

        service.create_signal(
            user_id=user_id,
            scan_signal_data=signal_data,
            countdown_seconds=countdown_seconds,
        )

        assert len(added_signals) == 1
        signal = added_signals[0]

        # Verify countdown_seconds stored correctly
        assert signal.countdown_seconds == countdown_seconds

        # Verify expires_at is approximately now + countdown_seconds
        # Allow 2 seconds tolerance for execution time
        expected_expires_at = datetime.now(timezone.utc) + timedelta(seconds=countdown_seconds)
        delta = abs((signal.expires_at - expected_expires_at).total_seconds())
        assert delta < 2.0, (
            f"expires_at off by {delta}s (expected within 2s). "
            f"expires_at={signal.expires_at}, expected≈{expected_expires_at}"
        )

    @given(
        countdown_seconds=countdown_strategy,
        signal_data=signal_data_strategy,
        user_id=user_id_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_redis_ttl_set_with_countdown_seconds(
        self, countdown_seconds, signal_data, user_id
    ):
        """Redis key should be set with TTL equal to countdown_seconds.

        **Validates: Requirements 4.5**

        Property: For any countdown_seconds in [1, 300], the Redis key is
        set with exactly that TTL value for server-side countdown tracking.
        """
        db, added_signals = create_mock_db()
        redis = create_mock_redis()
        service = SignalService(db=db, redis_client=redis)

        service.create_signal(
            user_id=user_id,
            scan_signal_data=signal_data,
            countdown_seconds=countdown_seconds,
        )

        signal = added_signals[0]
        expected_key = _signal_expiry_key(signal.id)

        redis.set.assert_called_once_with(
            expected_key, str(signal.id), ttl=countdown_seconds
        )

    @given(
        signal_id=st.integers(min_value=1, max_value=10000),
    )
    @settings(max_examples=50, deadline=None)
    def test_expire_signal_transitions_to_expired(self, signal_id):
        """expire_signal should transition a pending signal to "expired" status.

        **Validates: Requirements 4.6**

        Property: For any signal_id, calling expire_signal on a pending signal
        sets status to "expired" and returns confirmation.
        """
        db = MagicMock()
        redis = create_mock_redis()
        signal = create_pending_signal_mock(db, signal_id=signal_id, status="pending")

        service = SignalService(db=db, redis_client=redis)
        result = service.expire_signal(signal_id=signal_id)

        assert signal.status == "expired"
        assert result == {"signal_id": signal_id, "status": "expired"}
        db.commit.assert_called_once()
        # Redis key cleaned up defensively
        redis.delete.assert_called_once_with(_signal_expiry_key(signal_id))

    @given(
        ttl_value=st.integers(min_value=-2, max_value=300),
        user_id=user_id_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_remaining_seconds_always_non_negative(self, ttl_value, user_id):
        """remaining_seconds in get_pending_signals should always be >= 0.

        **Validates: Requirements 4.5**

        Property: For any Redis TTL value (including -2 for missing key,
        -1 for no expiry, 0 for expired, or positive values), the
        remaining_seconds returned is always >= 0.
        """
        db = MagicMock()
        redis = create_mock_redis(ttl_value=ttl_value)

        # Set up a mock signal in the query result
        mock_signal = MagicMock()
        mock_signal.id = 1
        mock_signal.symbol = "NIFTY24500CE"
        mock_signal.signal_type = "trend_pullback"
        mock_signal.confidence_score = 80.0
        mock_signal.entry_price = 250.0
        mock_signal.stop_loss = 230.0
        mock_signal.target_price = 290.0
        mock_signal.max_potential_loss = 2000.0
        mock_signal.status = "pending"
        mock_signal.countdown_seconds = 60
        mock_signal.expires_at = datetime(2024, 1, 1, 10, 1, 0, tzinfo=timezone.utc)
        mock_signal.created_at = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        mock_signal.ai_quality_rating = None
        mock_signal.ai_warnings = None
        mock_signal.ai_explanation = None

        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [mock_signal]

        service = SignalService(db=db, redis_client=redis)
        result = service.get_pending_signals(user_id=user_id)

        assert len(result) == 1
        assert result[0]["remaining_seconds"] >= 0, (
            f"remaining_seconds should be >= 0, got {result[0]['remaining_seconds']} "
            f"for TTL value {ttl_value}"
        )

    @given(
        non_pending_status=non_pending_status_strategy,
        signal_id=st.integers(min_value=1, max_value=10000),
        user_id=user_id_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_approve_rejects_non_pending_signals(
        self, non_pending_status, signal_id, user_id
    ):
        """Only pending signals can be approved — others raise ValueError.

        **Validates: Requirements 4.5, 4.6**

        Property: For any non-pending status (approved, rejected, expired),
        calling approve_signal raises ValueError with "not pending" message.
        """
        db = MagicMock()
        redis = create_mock_redis()
        create_pending_signal_mock(
            db, signal_id=signal_id, user_id=user_id, status=non_pending_status
        )

        service = SignalService(db=db, redis_client=redis)

        with pytest.raises(ValueError, match="not pending"):
            service.approve_signal(signal_id=signal_id, user_id=user_id)

    @given(
        non_pending_status=non_pending_status_strategy,
        signal_id=st.integers(min_value=1, max_value=10000),
        user_id=user_id_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_reject_rejects_non_pending_signals(
        self, non_pending_status, signal_id, user_id
    ):
        """Only pending signals can be rejected — others raise ValueError.

        **Validates: Requirements 4.5, 4.6**

        Property: For any non-pending status (approved, rejected, expired),
        calling reject_signal raises ValueError with "not pending" message.
        """
        db = MagicMock()
        redis = create_mock_redis()
        create_pending_signal_mock(
            db, signal_id=signal_id, user_id=user_id, status=non_pending_status
        )

        service = SignalService(db=db, redis_client=redis)

        with pytest.raises(ValueError, match="not pending"):
            service.reject_signal(signal_id=signal_id, user_id=user_id)

    @given(
        non_pending_status=non_pending_status_strategy,
        signal_id=st.integers(min_value=1, max_value=10000),
    )
    @settings(max_examples=50, deadline=None)
    def test_expire_rejects_non_pending_signals(
        self, non_pending_status, signal_id
    ):
        """Only pending signals can be expired — others raise ValueError.

        **Validates: Requirements 4.6**

        Property: For any non-pending status (approved, rejected, expired),
        calling expire_signal raises ValueError with "not pending" message.
        """
        db = MagicMock()
        redis = create_mock_redis()
        create_pending_signal_mock(
            db, signal_id=signal_id, status=non_pending_status
        )

        service = SignalService(db=db, redis_client=redis)

        with pytest.raises(ValueError, match="not pending"):
            service.expire_signal(signal_id=signal_id)
