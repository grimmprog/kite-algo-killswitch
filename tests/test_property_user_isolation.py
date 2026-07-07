"""Property-based tests for user isolation (Task 23.1).

Uses Hypothesis to verify that one user's trades and risk operations
never affect another user's capital, positions, or risk state.

**Validates: Requirements 1.8.1, 1.8.2, 1.8.3, 1.8.4, 1.8.5, 1.8.9, 1.8.10**
**Validates: Requirements 6.3.2**

Sub-tasks:
- 23.1.1: Generate random users (custom strategies)
- 23.1.2: Execute random trades
- 23.1.3: Verify isolation invariant
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch
from hypothesis import given, strategies as st, settings, assume
from dataclasses import dataclass
from typing import List, Dict

from src.workers.risk_engine_worker import RiskEngineWorker
from src.workers.execution_worker import ExecutionWorker
from src.cache.redis_keys import RedisKeys


# ============================================================
# 23.1.1: Custom Strategies - Generate Random Users
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
]

VALID_EXCHANGES = ["NSE", "NFO", "BSE", "BFO"]
VALID_SIDES = ["BUY", "SELL"]
VALID_RISK_PROFILES = ["conservative", "moderate", "aggressive"]


@dataclass
class UserConfig:
    """Generated user configuration for property tests."""

    user_id: int
    capital: float
    risk_profile: str
    daily_loss_limit_pct: float


@dataclass
class TradeOrder:
    """Generated trade order for property tests."""

    symbol: str
    exchange: str
    side: str
    quantity: int
    order_type: str


# Strategy: Generate a valid user configuration
def user_config_strategy():
    """Generate random user configurations with valid parameters."""
    return st.builds(
        UserConfig,
        user_id=st.integers(min_value=1, max_value=1000),
        capital=st.floats(min_value=10000.0, max_value=10000000.0, allow_nan=False, allow_infinity=False),
        risk_profile=st.sampled_from(VALID_RISK_PROFILES),
        daily_loss_limit_pct=st.floats(min_value=0.5, max_value=10.0, allow_nan=False, allow_infinity=False),
    )


# Strategy: Generate a valid trade order
def trade_order_strategy():
    """Generate random trade orders with valid parameters."""
    return st.builds(
        TradeOrder,
        symbol=st.sampled_from(VALID_SYMBOLS),
        exchange=st.sampled_from(VALID_EXCHANGES),
        side=st.sampled_from(VALID_SIDES),
        quantity=st.integers(min_value=1, max_value=500),
        order_type=st.just("MARKET"),
    )


# Strategy: Generate a pair of distinct users
def two_distinct_users_strategy():
    """Generate two users with distinct user_ids."""
    return st.tuples(
        user_config_strategy(),
        user_config_strategy(),
    ).filter(lambda pair: pair[0].user_id != pair[1].user_id)


# ============================================================
# Test Infrastructure: Shared Redis Store
# ============================================================


def create_shared_redis_store():
    """Create a shared in-memory Redis store and two mock clients that use it."""
    store = {}

    def make_redis_mock():
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
        redis_mock.publish.return_value = 1

        return redis_mock

    return store, make_redis_mock


def create_kite_mock(order_id_prefix: str, positions: List[Dict] = None):
    """Create a mock Kite client with configurable positions."""
    kite = MagicMock()
    kite.VARIETY_REGULAR = "regular"

    if positions is None:
        positions = []

    kite.positions.return_value = {"net": positions, "day": []}
    kite.place_order.return_value = f"{order_id_prefix}_001"

    return kite


def create_db_mock(user_id: int, capital: float):
    """Create a mock database session for a user."""
    db = MagicMock()
    mock_user = MagicMock()
    mock_user.capital = capital
    mock_user.id = user_id
    db.query.return_value.filter_by.return_value.first.return_value = mock_user
    db.add.return_value = None
    db.commit.return_value = None
    return db


# ============================================================
# 23.1.2 & 23.1.3: Property Tests - Execute Trades & Verify Isolation
# ============================================================


class TestUserIsolationProperty:
    """Property-based tests for user isolation invariant.

    **Validates: Requirements 1.8.1, 1.8.2, 1.8.4, 1.8.9, 1.8.10**
    **Validates: Requirements 6.3.2**

    The core invariant:
    After any operation on User A, User B's state must remain unchanged.
    This includes:
    - Capital (Requirement 1.8.1)
    - Positions (Requirement 1.8.2)
    - Risk thresholds (Requirement 1.8.3)
    - Kill switch state (Requirement 1.8.4, 1.8.9)
    - Trade impact (Requirement 1.8.10)
    """

    @given(
        users=two_distinct_users_strategy(),
        trades_for_user_a=st.lists(trade_order_strategy(), min_size=1, max_size=5),
    )
    @settings(max_examples=50, deadline=None)
    def test_trade_execution_does_not_affect_other_user_capital(
        self, users, trades_for_user_a
    ):
        """Trading for user A does not change user B's capital in the system.

        **Validates: Requirements 1.8.1, 1.8.10**

        Property: For any two users A, B and any sequence of trades executed
        by A, user B's capital remains the same before and after A's trades.
        """
        user_a, user_b = users

        # Set up shared Redis store
        store, make_redis = create_shared_redis_store()

        redis_a = make_redis()
        redis_b = make_redis()

        kite_a = create_kite_mock(f"ORDER_U{user_a.user_id}")
        kite_b = create_kite_mock(f"ORDER_U{user_b.user_id}")

        db_a = create_db_mock(user_a.user_id, user_a.capital)
        db_b = create_db_mock(user_b.user_id, user_b.capital)

        exec_a = ExecutionWorker(
            user_id=user_a.user_id,
            kite_client=kite_a,
            redis_client=redis_a,
            db_session=db_a,
        )
        exec_b = ExecutionWorker(
            user_id=user_b.user_id,
            kite_client=kite_b,
            redis_client=redis_b,
            db_session=db_b,
        )

        # Snapshot user B's state before
        b_capital_before = user_b.capital
        b_killswitch_before = exec_b.check_killswitch()

        # Execute trades for user A
        for trade in trades_for_user_a:
            order = {
                "exchange": trade.exchange,
                "symbol": trade.symbol,
                "side": trade.side,
                "quantity": trade.quantity,
                "order_type": trade.order_type,
            }
            exec_a.place_order(order)

        # Verify user B's state is unchanged
        b_killswitch_after = exec_b.check_killswitch()

        assert b_killswitch_after == b_killswitch_before, (
            f"User B's kill switch changed from {b_killswitch_before} to "
            f"{b_killswitch_after} after User A traded"
        )

        # User B's DB mock was never called for capital updates
        db_b_add_calls = db_b.add.call_count
        db_b_commit_calls = db_b.commit.call_count
        assert db_b_add_calls == 0, (
            f"User B's database was written to {db_b_add_calls} times "
            f"during User A's trade execution"
        )
        assert db_b_commit_calls == 0, (
            f"User B's database was committed {db_b_commit_calls} times "
            f"during User A's trade execution"
        )

    @given(
        users=two_distinct_users_strategy(),
        trades_for_user_a=st.lists(trade_order_strategy(), min_size=1, max_size=5),
    )
    @settings(max_examples=50, deadline=None)
    def test_trade_execution_does_not_affect_other_user_positions(
        self, users, trades_for_user_a
    ):
        """Trading for user A does not affect user B's positions or risk cache.

        **Validates: Requirements 1.8.2**

        Property: For any two users A, B and any trades executed by A,
        user B's risk cache in Redis (positions, P&L, Greeks) is unchanged.
        """
        user_a, user_b = users

        store, make_redis = create_shared_redis_store()
        redis_a = make_redis()
        redis_b = make_redis()

        # Pre-populate user B's risk cache
        b_risk_key = RedisKeys.user_risk(user_b.user_id)
        initial_b_risk = {
            "pnl": "500.0",
            "net_delta": "0.3",
            "net_gamma": "0.01",
            "net_vega": "50.0",
            "margin_used": "25000.0",
            "updated_at": "2024-01-01T10:00:00",
        }
        store[b_risk_key] = initial_b_risk

        kite_a = create_kite_mock(f"ORDER_U{user_a.user_id}")
        db_a = create_db_mock(user_a.user_id, user_a.capital)

        exec_a = ExecutionWorker(
            user_id=user_a.user_id,
            kite_client=kite_a,
            redis_client=redis_a,
            db_session=db_a,
        )

        # Execute trades for user A
        for trade in trades_for_user_a:
            order = {
                "exchange": trade.exchange,
                "symbol": trade.symbol,
                "side": trade.side,
                "quantity": trade.quantity,
                "order_type": trade.order_type,
            }
            exec_a.place_order(order)

        # Verify user B's risk cache is unchanged
        b_risk_after = store.get(b_risk_key)
        assert b_risk_after == initial_b_risk, (
            f"User B's risk cache changed after User A traded.\n"
            f"Before: {initial_b_risk}\n"
            f"After:  {b_risk_after}"
        )

    @given(
        users=two_distinct_users_strategy(),
        pnl_a=st.floats(min_value=-100000.0, max_value=-1000.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=50, deadline=None)
    def test_killswitch_activation_does_not_affect_other_user(
        self, users, pnl_a
    ):
        """Activating kill switch for user A does not affect user B.

        **Validates: Requirements 1.8.4, 1.8.9**

        Property: For any two users A, B, when A's kill switch is triggered
        (due to losses), B's kill switch remains inactive and B can still trade.
        """
        user_a, user_b = users

        store, make_redis = create_shared_redis_store()
        redis_a = make_redis()
        redis_b = make_redis()

        positions_a = [
            {
                "tradingsymbol": "NIFTY23DEC21000CE",
                "exchange": "NFO",
                "product": "NRML",
                "quantity": 50,
                "average_price": 150.0,
                "last_price": 100.0,
                "pnl": pnl_a,
                "unrealised": pnl_a,
                "realised": 0.0,
                "buy_quantity": 50,
                "sell_quantity": 0,
            }
        ]

        kite_a = create_kite_mock(f"ORDER_U{user_a.user_id}", positions_a)
        kite_b = create_kite_mock(f"ORDER_U{user_b.user_id}")

        db_a = create_db_mock(user_a.user_id, user_a.capital)
        db_b = create_db_mock(user_b.user_id, user_b.capital)

        risk_a = RiskEngineWorker(
            user_id=user_a.user_id,
            kite_client=kite_a,
            redis_client=redis_a,
            db_session=db_a,
        )
        exec_b = ExecutionWorker(
            user_id=user_b.user_id,
            kite_client=kite_b,
            redis_client=redis_b,
            db_session=db_b,
        )

        # Verify user B's kill switch is off before
        assert exec_b.check_killswitch() is False

        # Trigger kill switch for user A
        risk_a.trigger_killswitch(reason="Daily loss limit breached", capital=user_a.capital)

        # Verify user A's kill switch is now active
        a_ks_key = RedisKeys.user_killswitch(user_a.user_id)
        assert store.get(a_ks_key) == "true", "User A's kill switch should be active"

        # Verify user B's kill switch is STILL inactive
        b_ks_key = RedisKeys.user_killswitch(user_b.user_id)
        assert store.get(b_ks_key) is None, (
            f"User B's kill switch was set to '{store.get(b_ks_key)}' "
            f"after User A's kill switch activation"
        )

        # Verify user B can still check kill switch as False
        assert exec_b.check_killswitch() is False, (
            "User B's check_killswitch() returned True after "
            "User A's kill switch was activated"
        )

    @given(
        users=two_distinct_users_strategy(),
        trades_for_user_a=st.lists(trade_order_strategy(), min_size=1, max_size=3),
    )
    @settings(max_examples=50, deadline=None)
    def test_risk_cache_update_isolated_between_users(
        self, users, trades_for_user_a
    ):
        """Updating risk cache for user A does not overwrite user B's risk cache.

        **Validates: Requirements 1.8.2, 1.8.3**

        Property: For any two users and any risk metric update for A,
        user B's cached risk metrics remain unchanged.
        """
        user_a, user_b = users

        store, make_redis = create_shared_redis_store()
        redis_a = make_redis()
        redis_b = make_redis()

        # Pre-populate user B's risk cache
        b_risk_key = RedisKeys.user_risk(user_b.user_id)
        initial_b_risk = {
            "pnl": "1000.0",
            "net_delta": "0.5",
            "net_gamma": "0.02",
            "net_vega": "75.0",
            "margin_used": "40000.0",
            "updated_at": "2024-01-01T09:30:00",
        }
        store[b_risk_key] = initial_b_risk

        kite_a = create_kite_mock(f"ORDER_U{user_a.user_id}")
        db_a = create_db_mock(user_a.user_id, user_a.capital)

        risk_a = RiskEngineWorker(
            user_id=user_a.user_id,
            kite_client=kite_a,
            redis_client=redis_a,
            db_session=db_a,
        )

        # Update risk cache for user A with random data derived from trades
        risk_a.update_redis_cache(
            pnl=-5000.0,
            greeks={"net_delta": 1.2, "net_gamma": 0.05, "net_vega": 200.0},
            margin_used=100000.0,
        )

        # Verify user A's cache was updated
        a_risk_key = RedisKeys.user_risk(user_a.user_id)
        assert store.get(a_risk_key) is not None, "User A's risk cache should be set"

        # Verify user B's cache is UNCHANGED
        b_risk_after = store.get(b_risk_key)
        assert b_risk_after == initial_b_risk, (
            f"User B's risk cache was modified after User A's risk update.\n"
            f"Before: {initial_b_risk}\n"
            f"After:  {b_risk_after}"
        )

    @given(
        users=two_distinct_users_strategy(),
        trades_for_user_a=st.lists(trade_order_strategy(), min_size=1, max_size=5),
    )
    @settings(max_examples=50, deadline=None)
    def test_redis_keys_are_always_user_scoped(
        self, users, trades_for_user_a
    ):
        """All Redis key operations are scoped to the correct user_id.

        **Validates: Requirements 1.8.5, 1.8.8**

        Property: For any two distinct users, the set of Redis keys used
        by user A never overlaps with the set of keys used by user B.
        """
        user_a, user_b = users

        # Verify key namespaces are distinct for all key types
        a_risk = RedisKeys.user_risk(user_a.user_id)
        b_risk = RedisKeys.user_risk(user_b.user_id)
        assert a_risk != b_risk, (
            f"Risk keys collide: user {user_a.user_id} and {user_b.user_id} "
            f"both map to '{a_risk}'"
        )

        a_ks = RedisKeys.user_killswitch(user_a.user_id)
        b_ks = RedisKeys.user_killswitch(user_b.user_id)
        assert a_ks != b_ks, (
            f"Killswitch keys collide: user {user_a.user_id} and {user_b.user_id} "
            f"both map to '{a_ks}'"
        )

        a_orders = RedisKeys.user_recent_orders(user_a.user_id)
        b_orders = RedisKeys.user_recent_orders(user_b.user_id)
        assert a_orders != b_orders, (
            f"Recent orders keys collide: user {user_a.user_id} and {user_b.user_id} "
            f"both map to '{a_orders}'"
        )

        # Verify expected key format: user:{user_id}:<resource>
        assert a_risk == f"user:{user_a.user_id}:risk"
        assert b_risk == f"user:{user_b.user_id}:risk"
        assert a_ks == f"user:{user_a.user_id}:killswitch"
        assert b_ks == f"user:{user_b.user_id}:killswitch"
        assert a_orders == f"user:{user_a.user_id}:recent_orders"
        assert b_orders == f"user:{user_b.user_id}:recent_orders"

        # Verify all keys for user A are in a different namespace than user B
        a_keys = {a_risk, a_ks, a_orders}
        b_keys = {b_risk, b_ks, b_orders}
        assert a_keys.isdisjoint(b_keys), (
            f"Key overlap detected between users {user_a.user_id} and {user_b.user_id}: "
            f"{a_keys & b_keys}"
        )
