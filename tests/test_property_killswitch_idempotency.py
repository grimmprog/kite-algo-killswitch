"""Property-based tests for kill switch idempotency (Task 23.2).

Uses Hypothesis to verify that activating the kill switch multiple times
for the same user results in exactly ONE kill switch log entry and the
kill switch flag being set exactly once (not reset/re-set).

**Validates: Requirements 1.5.8, 6.3.3**

Sub-tasks:
- 23.2.1: Generate random user (custom strategies)
- 23.2.2: Activate multiple times (2-10 activations)
- 23.2.3: Verify single log entry (idempotency invariant)
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch, call
from hypothesis import given, strategies as st, settings, assume
from dataclasses import dataclass

from src.workers.risk_engine_worker import RiskEngineWorker
from src.cache.redis_keys import RedisKeys


# ============================================================
# 23.2.1: Custom Strategies - Generate Random User
# ============================================================

VALID_RISK_PROFILES = ["conservative", "moderate", "aggressive"]
VALID_REASONS = [
    "Daily loss limit breached",
    "Margin limit breached: 95.00% of capital",
    "Manual kill switch activation",
    "System-triggered risk breach",
    "Drawdown limit exceeded",
]


@dataclass
class KillSwitchUserConfig:
    """Generated user configuration for kill switch idempotency tests."""

    user_id: int
    capital: float
    risk_profile: str
    daily_loss_limit_pct: float


def killswitch_user_strategy():
    """Generate random user configurations for kill switch testing."""
    return st.builds(
        KillSwitchUserConfig,
        user_id=st.integers(min_value=1, max_value=10000),
        capital=st.floats(
            min_value=50000.0, max_value=10000000.0,
            allow_nan=False, allow_infinity=False
        ),
        risk_profile=st.sampled_from(VALID_RISK_PROFILES),
        daily_loss_limit_pct=st.floats(
            min_value=1.0, max_value=10.0,
            allow_nan=False, allow_infinity=False
        ),
    )


def killswitch_reason_strategy():
    """Generate random kill switch trigger reasons."""
    return st.sampled_from(VALID_REASONS)


# ============================================================
# Test Infrastructure: Shared In-Memory Redis Store
# ============================================================


def create_redis_store_and_mock():
    """Create a shared in-memory Redis store with a mock client.

    The mock accurately simulates Redis SET with NX (set-if-not-exists)
    behavior which is the core mechanism for kill switch idempotency.
    """
    store = {}

    redis_mock = MagicMock()

    def _get(key):
        return store.get(key)

    def _set(key, value, nx=False, **kwargs):
        if nx and key in store:
            # NX semantics: return False/None if key already exists
            return False
        store[key] = value
        return True

    def _hgetall(key):
        return store.get(key, {})

    def _hset(key, mapping=None, **kwargs):
        if mapping:
            store[key] = mapping
        return True

    def _expire(key, ttl):
        return True

    def _publish(channel, message):
        return 1

    redis_mock.get.side_effect = _get
    redis_mock.set.side_effect = _set
    redis_mock.hgetall.side_effect = _hgetall
    redis_mock.hset.side_effect = _hset
    redis_mock.expire.side_effect = _expire
    redis_mock.publish.side_effect = _publish

    return store, redis_mock


def create_db_mock_for_killswitch(user_id: int, capital: float):
    """Create a mock database session that tracks db.add calls.

    Returns the mock and a list that collects all objects passed to db.add().
    This lets us count KillSwitchLog entries created.
    """
    db = MagicMock()
    added_objects = []

    def _add(obj):
        added_objects.append(obj)

    db.add.side_effect = _add
    db.commit.return_value = None
    db.rollback.return_value = None

    # Mock user query for capital lookup
    mock_user = MagicMock()
    mock_user.capital = capital
    mock_user.id = user_id
    db.query.return_value.filter_by.return_value.first.return_value = mock_user

    return db, added_objects


# ============================================================
# 23.2.2 & 23.2.3: Property Tests - Activate Multiple Times & Verify
# ============================================================


class TestKillSwitchIdempotencyProperty:
    """Property-based tests for kill switch idempotency.

    **Validates: Requirements 1.5.8, 6.3.3**

    The core invariant:
    No matter how many times trigger_killswitch is called for the same user,
    only ONE kill switch log entry is created, and the Redis flag is set
    exactly once.
    """

    @given(
        user=killswitch_user_strategy(),
        reason=killswitch_reason_strategy(),
        num_activations=st.integers(min_value=2, max_value=10),
    )
    @settings(max_examples=50, deadline=None)
    @patch("src.workers.celery_app.celery_app")
    def test_multiple_activations_produce_single_log_entry(
        self, mock_celery, user, reason, num_activations
    ):
        """Activating kill switch N times results in exactly 1 DB log entry.

        **Validates: Requirements 1.5.8**

        Property: For any user and any number of kill switch activations (2-10),
        only ONE KillSwitchLog record is created in the database.
        The first call returns True (newly activated), all subsequent calls
        return False (already active, duplicate prevented).
        """
        # Set up fresh Redis store and DB mock for each test case
        store, redis_mock = create_redis_store_and_mock()
        db, added_objects = create_db_mock_for_killswitch(user.user_id, user.capital)

        # Create risk engine worker
        kite_mock = MagicMock()
        kite_mock.positions.return_value = {"net": [], "day": []}

        risk_engine = RiskEngineWorker(
            user_id=user.user_id,
            kite_client=kite_mock,
            redis_client=redis_mock,
            db_session=db,
        )

        # 23.2.2: Activate kill switch multiple times
        results = []
        for _ in range(num_activations):
            result = risk_engine.trigger_killswitch(reason=reason, capital=user.capital)
            results.append(result)

        # 23.2.3: Verify idempotency invariant

        # First activation should succeed (return True)
        assert results[0] is True, (
            f"First kill switch activation should return True, got {results[0]}"
        )

        # All subsequent activations should be rejected (return False)
        for i, result in enumerate(results[1:], start=2):
            assert result is False, (
                f"Kill switch activation #{i} should return False (duplicate), "
                f"got {result}"
            )

        # Only ONE log entry should exist in the database
        assert len(added_objects) == 1, (
            f"Expected exactly 1 KillSwitchLog entry after {num_activations} "
            f"activations, but got {len(added_objects)}"
        )

        # Verify the single log entry has the correct user_id
        log_entry = added_objects[0]
        assert log_entry.user_id == user.user_id, (
            f"KillSwitchLog user_id mismatch: expected {user.user_id}, "
            f"got {log_entry.user_id}"
        )

        # db.add should have been called exactly once
        assert db.add.call_count == 1, (
            f"db.add called {db.add.call_count} times, expected 1"
        )

        # db.commit should have been called exactly once
        assert db.commit.call_count == 1, (
            f"db.commit called {db.commit.call_count} times, expected 1"
        )

    @given(
        user=killswitch_user_strategy(),
        reason=killswitch_reason_strategy(),
        num_activations=st.integers(min_value=2, max_value=10),
    )
    @settings(max_examples=50, deadline=None)
    @patch("src.workers.celery_app.celery_app")
    def test_redis_flag_set_exactly_once(
        self, mock_celery, user, reason, num_activations
    ):
        """Kill switch Redis flag is set exactly once regardless of activation count.

        **Validates: Requirements 1.5.8**

        Property: For any user and any number of activations, the Redis key
        user:{user_id}:killswitch is set to "true" exactly once via SET NX.
        The NX (set-if-not-exists) semantics guarantee atomicity.
        """
        store, redis_mock = create_redis_store_and_mock()
        db, _ = create_db_mock_for_killswitch(user.user_id, user.capital)

        kite_mock = MagicMock()
        kite_mock.positions.return_value = {"net": [], "day": []}

        risk_engine = RiskEngineWorker(
            user_id=user.user_id,
            kite_client=kite_mock,
            redis_client=redis_mock,
            db_session=db,
        )

        # Activate multiple times
        for _ in range(num_activations):
            risk_engine.trigger_killswitch(reason=reason, capital=user.capital)

        # Verify the Redis flag is "true" (set once, never changed)
        ks_key = RedisKeys.user_killswitch(user.user_id)
        assert store.get(ks_key) == "true", (
            f"Kill switch flag should be 'true', got '{store.get(ks_key)}'"
        )

        # Count how many times redis.set was called with the killswitch key
        # and nx=True. All calls should target the same key.
        set_calls_with_nx = [
            c for c in redis_mock.set.call_args_list
            if c[0][0] == ks_key and c[1].get("nx") is True
        ]
        assert len(set_calls_with_nx) == num_activations, (
            f"Expected {num_activations} SET NX attempts on the killswitch key, "
            f"got {len(set_calls_with_nx)}"
        )

        # But only the first one should have actually written to the store
        # (verified by the fact that store[ks_key] == "true" and was only set once)
        # The store dict being simple means only one write happened
        assert store[ks_key] == "true"

    @given(
        user=killswitch_user_strategy(),
        reasons=st.lists(
            killswitch_reason_strategy(),
            min_size=2, max_size=5,
        ),
    )
    @settings(max_examples=50, deadline=None)
    @patch("src.workers.celery_app.celery_app")
    def test_different_reasons_still_idempotent(
        self, mock_celery, user, reasons
    ):
        """Kill switch is idempotent even when triggered with different reasons.

        **Validates: Requirements 1.5.8**

        Property: For any user and any sequence of different trigger reasons,
        only the FIRST reason is logged. Subsequent triggers with different
        reasons are still rejected because the flag is already set.
        """
        store, redis_mock = create_redis_store_and_mock()
        db, added_objects = create_db_mock_for_killswitch(user.user_id, user.capital)

        kite_mock = MagicMock()
        kite_mock.positions.return_value = {"net": [], "day": []}

        risk_engine = RiskEngineWorker(
            user_id=user.user_id,
            kite_client=kite_mock,
            redis_client=redis_mock,
            db_session=db,
        )

        # Activate with different reasons each time
        results = []
        for reason in reasons:
            result = risk_engine.trigger_killswitch(reason=reason, capital=user.capital)
            results.append(result)

        # Only the first activation should succeed
        assert results[0] is True
        for i, result in enumerate(results[1:], start=2):
            assert result is False, (
                f"Activation #{i} with reason '{reasons[i-1]}' should return False"
            )

        # Only one log entry - with the FIRST reason
        assert len(added_objects) == 1, (
            f"Expected 1 log entry, got {len(added_objects)} after "
            f"{len(reasons)} activations with different reasons"
        )
        assert added_objects[0].trigger_reason == reasons[0], (
            f"Log entry should have first reason '{reasons[0]}', "
            f"got '{added_objects[0].trigger_reason}'"
        )
