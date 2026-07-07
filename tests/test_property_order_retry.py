"""Property-based tests for order retry convergence (Task 23.3).

Uses Hypothesis to verify that the execution worker's retry logic
converges correctly: if at least one attempt succeeds within the retry
window, the order eventually completes successfully; if all attempts fail,
the order reports failure gracefully with the correct attempt count.

**Validates: Requirements 1.3.5, 6.3.4**

Sub-tasks:
- 23.3.1: Generate random orders (custom strategies)
- 23.3.2: Simulate failures (mock kite_client.place_order to fail N times)
- 23.3.3: Verify eventual success (convergence invariant)
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch, call
from hypothesis import given, strategies as st, settings, assume
from dataclasses import dataclass
from typing import List

from kiteconnect import exceptions as kite_exceptions

from src.workers.execution_worker import ExecutionWorker
from src.cache.redis_keys import RedisKeys


# ============================================================
# 23.3.1: Custom Strategies - Generate Random Orders
# ============================================================

VALID_SYMBOLS = [
    "NIFTY23DEC21000CE",
    "NIFTY23DEC21000PE",
    "BANKNIFTY23DEC45000CE",
    "BANKNIFTY23DEC45000PE",
    "RELIANCE",
    "TCS",
    "INFY",
    "HDFCBANK",
    "SBIN",
    "ICICIBANK",
]

VALID_EXCHANGES = ["NSE", "NFO", "BSE", "BFO"]
VALID_SIDES = ["BUY", "SELL"]


@dataclass
class RandomOrder:
    """Generated order for retry convergence tests."""

    symbol: str
    exchange: str
    side: str
    quantity: int


def random_order_strategy():
    """Generate random orders with valid parameters."""
    return st.builds(
        RandomOrder,
        symbol=st.sampled_from(VALID_SYMBOLS),
        exchange=st.sampled_from(VALID_EXCHANGES),
        side=st.sampled_from(VALID_SIDES),
        quantity=st.integers(min_value=1, max_value=500),
    )


def to_order_dict(order: RandomOrder) -> dict:
    """Convert a RandomOrder dataclass to the dict format expected by ExecutionWorker."""
    return {
        "symbol": order.symbol,
        "exchange": order.exchange,
        "side": order.side,
        "quantity": order.quantity,
        "order_type": "MARKET",
    }


# ============================================================
# Test Infrastructure
# ============================================================


def create_redis_mock_for_retry():
    """Create a Redis mock that allows trades (no kill switch, low margin)."""
    store = {}
    redis_mock = MagicMock()

    def _get(key):
        return store.get(key)

    def _set(key, value, nx=False, **kwargs):
        if nx and key in store:
            return False
        store[key] = value
        return True

    def _hgetall(key):
        return store.get(key, {})

    def _hset(key, mapping=None, **kwargs):
        if mapping:
            store[key] = mapping
        return True

    def _lrange(key, start, end):
        return store.get(key, [])

    def _lpush(key, *values):
        if key not in store:
            store[key] = []
        for v in values:
            store[key].insert(0, v)
        return len(store[key])

    def _ltrim(key, start, end):
        if key in store:
            store[key] = store[key][start:end + 1]
        return True

    def _expire(key, ttl):
        return True

    redis_mock.get.side_effect = _get
    redis_mock.set.side_effect = _set
    redis_mock.hgetall.side_effect = _hgetall
    redis_mock.hset.side_effect = _hset
    redis_mock.lrange.side_effect = _lrange
    redis_mock.lpush.side_effect = _lpush
    redis_mock.ltrim.side_effect = _ltrim
    redis_mock.expire.side_effect = _expire

    return redis_mock


def create_db_mock_for_retry(user_id: int, capital: float = 1000000.0):
    """Create a DB mock with a user that has plenty of margin."""
    db = MagicMock()
    mock_user = MagicMock()
    mock_user.capital = capital
    mock_user.id = user_id
    db.query.return_value.filter_by.return_value.first.return_value = mock_user
    db.add.return_value = None
    db.commit.return_value = None
    return db


def create_kite_mock_with_failures(num_failures: int, order_id: str = "ORDER_123"):
    """Create a Kite mock that fails num_failures times then succeeds.

    Each failure raises a NetworkException (retryable).
    After num_failures, it returns a successful order_id.
    """
    kite = MagicMock()
    kite.VARIETY_REGULAR = "regular"

    call_count = [0]

    def _place_order(**kwargs):
        call_count[0] += 1
        if call_count[0] <= num_failures:
            raise kite_exceptions.NetworkException("Connection timeout")
        return order_id

    kite.place_order.side_effect = _place_order
    return kite


def create_kite_mock_all_failures():
    """Create a Kite mock that always fails with retryable NetworkException."""
    kite = MagicMock()
    kite.VARIETY_REGULAR = "regular"
    kite.place_order.side_effect = kite_exceptions.NetworkException("Connection timeout")
    return kite


def create_kite_mock_non_retryable_failure():
    """Create a Kite mock that fails with a non-retryable OrderException."""
    kite = MagicMock()
    kite.VARIETY_REGULAR = "regular"
    kite.place_order.side_effect = kite_exceptions.OrderException("Insufficient funds")
    return kite


# ============================================================
# 23.3.2 & 23.3.3: Property Tests - Simulate Failures & Verify Convergence
# ============================================================


class TestOrderRetryConvergenceProperty:
    """Property-based tests for order retry convergence.

    **Validates: Requirements 1.3.5, 6.3.4**

    Core invariant:
    If the number of transient failures before success is less than max_retries,
    then execute_with_retry converges to success. If failures >= max_retries + 1,
    the order reports failure gracefully.
    """

    @given(
        order=random_order_strategy(),
        num_failures=st.integers(min_value=0, max_value=2),
    )
    @settings(max_examples=50, deadline=None)
    @patch("time.sleep")
    def test_order_succeeds_when_failures_within_retry_window(
        self, mock_sleep, order, num_failures
    ):
        """Order eventually succeeds if failures < max_retries.

        **Validates: Requirements 1.3.5**

        Property: For any random order and any number of transient failures (0-2),
        since max_retries=3, at least one attempt succeeds, so execute_with_retry
        returns success=True.
        """
        user_id = 1
        order_dict = to_order_dict(order)

        redis_mock = create_redis_mock_for_retry()
        db_mock = create_db_mock_for_retry(user_id)
        kite_mock = create_kite_mock_with_failures(
            num_failures=num_failures,
            order_id=f"ORDER_{order.symbol}_{order.quantity}",
        )

        worker = ExecutionWorker(
            user_id=user_id,
            kite_client=kite_mock,
            redis_client=redis_mock,
            db_session=db_mock,
        )

        result = worker.execute_with_retry(order_dict)

        # Core convergence invariant: order succeeds
        assert result['success'] is True, (
            f"Order should succeed with {num_failures} failures "
            f"(max_retries=3), but got: {result}"
        )

        # The order_id should be returned
        assert result['order_id'] is not None, (
            f"Successful order should have an order_id, got: {result}"
        )

        # Total attempts should be num_failures + 1 (the successful attempt)
        assert result['attempts'] == num_failures + 1, (
            f"Expected {num_failures + 1} attempts, got {result['attempts']}"
        )

    @given(
        order=random_order_strategy(),
    )
    @settings(max_examples=50, deadline=None)
    @patch("time.sleep")
    def test_order_fails_gracefully_when_all_retries_exhausted(
        self, mock_sleep, order
    ):
        """Order reports failure when all retry attempts are exhausted.

        **Validates: Requirements 1.3.5**

        Property: For any random order where ALL attempts fail (retryable),
        execute_with_retry returns success=False after max_retries+1 total attempts.
        """
        user_id = 2
        order_dict = to_order_dict(order)

        redis_mock = create_redis_mock_for_retry()
        db_mock = create_db_mock_for_retry(user_id)
        kite_mock = create_kite_mock_all_failures()

        worker = ExecutionWorker(
            user_id=user_id,
            kite_client=kite_mock,
            redis_client=redis_mock,
            db_session=db_mock,
        )

        result = worker.execute_with_retry(order_dict)

        # Order should fail
        assert result['success'] is False, (
            f"Order should fail after exhausting retries, but got: {result}"
        )

        # Total attempts should be max_retries + 1 = 4
        assert result['attempts'] == worker.max_retries + 1, (
            f"Expected {worker.max_retries + 1} attempts after exhausting retries, "
            f"got {result['attempts']}"
        )

        # Message should indicate retries exhausted
        assert "Max retries" in result['message'] or "exhausted" in result['message'], (
            f"Failure message should mention max retries, got: {result['message']}"
        )

    @given(
        order=random_order_strategy(),
        num_failures=st.integers(min_value=0, max_value=2),
    )
    @settings(max_examples=50, deadline=None)
    @patch("time.sleep")
    def test_exponential_backoff_applied_between_retries(
        self, mock_sleep, order, num_failures
    ):
        """Exponential backoff is applied between retry attempts.

        **Validates: Requirements 1.3.5**

        Property: For any order with N transient failures before success,
        time.sleep is called with exponential backoff values:
        sleep(1*1), sleep(1*2), sleep(1*3), etc. (retry_backoff * attempt_number)
        """
        # Only test when there are actual retries
        assume(num_failures > 0)

        user_id = 3
        order_dict = to_order_dict(order)

        redis_mock = create_redis_mock_for_retry()
        db_mock = create_db_mock_for_retry(user_id)
        kite_mock = create_kite_mock_with_failures(
            num_failures=num_failures,
            order_id=f"ORDER_{order.symbol}",
        )

        worker = ExecutionWorker(
            user_id=user_id,
            kite_client=kite_mock,
            redis_client=redis_mock,
            db_session=db_mock,
        )

        result = worker.execute_with_retry(order_dict)

        # Order should still succeed
        assert result['success'] is True

        # Verify exponential backoff: sleep should be called num_failures times
        # with values retry_backoff * 1, retry_backoff * 2, ... retry_backoff * num_failures
        assert mock_sleep.call_count == num_failures, (
            f"Expected {num_failures} sleep calls for backoff, "
            f"got {mock_sleep.call_count}"
        )

        # Verify actual backoff values
        expected_backoff_calls = [
            call(worker.retry_backoff * attempt)
            for attempt in range(1, num_failures + 1)
        ]
        assert mock_sleep.call_args_list == expected_backoff_calls, (
            f"Expected exponential backoff calls {expected_backoff_calls}, "
            f"got {mock_sleep.call_args_list}"
        )

    @given(
        order=random_order_strategy(),
    )
    @settings(max_examples=50, deadline=None)
    @patch("time.sleep")
    def test_non_retryable_failure_does_not_retry(
        self, mock_sleep, order
    ):
        """Non-retryable failures are not retried.

        **Validates: Requirements 1.3.5**

        Property: For any order that fails with a non-retryable error
        (e.g., OrderException), execute_with_retry returns immediately
        without any retries (attempts=1, no sleep calls).
        """
        user_id = 4
        order_dict = to_order_dict(order)

        redis_mock = create_redis_mock_for_retry()
        db_mock = create_db_mock_for_retry(user_id)
        kite_mock = create_kite_mock_non_retryable_failure()

        worker = ExecutionWorker(
            user_id=user_id,
            kite_client=kite_mock,
            redis_client=redis_mock,
            db_session=db_mock,
        )

        result = worker.execute_with_retry(order_dict)

        # Order should fail
        assert result['success'] is False, (
            f"Non-retryable order should fail, got: {result}"
        )

        # Only 1 attempt — no retries
        assert result['attempts'] == 1, (
            f"Non-retryable failure should have 1 attempt, got {result['attempts']}"
        )

        # No sleep calls (no backoff applied)
        assert mock_sleep.call_count == 0, (
            f"No sleep should be called for non-retryable failures, "
            f"got {mock_sleep.call_count} calls"
        )

    @given(
        order=random_order_strategy(),
        failure_at_boundary=st.just(3),
    )
    @settings(max_examples=50, deadline=None)
    @patch("time.sleep")
    def test_order_succeeds_at_exact_retry_boundary(
        self, mock_sleep, order, failure_at_boundary
    ):
        """Order succeeds when it fails exactly max_retries times then succeeds.

        **Validates: Requirements 1.3.5**

        Property: For any order with exactly 3 failures (== max_retries),
        the 4th attempt (max_retries + 1) succeeds. This is the boundary
        case for retry convergence.
        """
        user_id = 5
        order_dict = to_order_dict(order)

        redis_mock = create_redis_mock_for_retry()
        db_mock = create_db_mock_for_retry(user_id)
        kite_mock = create_kite_mock_with_failures(
            num_failures=failure_at_boundary,
            order_id=f"ORDER_BOUNDARY_{order.symbol}",
        )

        worker = ExecutionWorker(
            user_id=user_id,
            kite_client=kite_mock,
            redis_client=redis_mock,
            db_session=db_mock,
        )

        result = worker.execute_with_retry(order_dict)

        # At the exact boundary (3 failures with max_retries=3), the 4th attempt
        # is the last retry — it should succeed since our mock succeeds on attempt 4
        assert result['success'] is True, (
            f"Order should succeed at retry boundary (3 failures, 4th attempt succeeds), "
            f"but got: {result}"
        )

        # Total attempts = 4 (1 initial + 3 retries)
        assert result['attempts'] == 4, (
            f"Expected 4 total attempts at retry boundary, got {result['attempts']}"
        )

    @given(
        order=random_order_strategy(),
    )
    @settings(max_examples=50, deadline=None)
    @patch("time.sleep")
    def test_immediate_success_has_no_retries(
        self, mock_sleep, order
    ):
        """Orders that succeed on first attempt have no retries or backoff.

        **Validates: Requirements 1.3.5**

        Property: For any order that succeeds immediately (0 failures),
        execute_with_retry returns with attempts=1 and no sleep calls.
        """
        user_id = 6
        order_dict = to_order_dict(order)

        redis_mock = create_redis_mock_for_retry()
        db_mock = create_db_mock_for_retry(user_id)
        kite_mock = create_kite_mock_with_failures(
            num_failures=0,
            order_id=f"ORDER_INSTANT_{order.symbol}",
        )

        worker = ExecutionWorker(
            user_id=user_id,
            kite_client=kite_mock,
            redis_client=redis_mock,
            db_session=db_mock,
        )

        result = worker.execute_with_retry(order_dict)

        # Immediate success
        assert result['success'] is True
        assert result['attempts'] == 1
        assert mock_sleep.call_count == 0
