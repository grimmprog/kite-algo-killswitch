"""Integration tests for multi-user isolation (Task 22.3).

Tests that multiple users operate independently:
1. Create two user worker instances
2. Execute trades for both users
3. Verify data isolation (different Redis keys, separate DB queries)
4. Trigger kill switch for one user
5. Verify the other user is unaffected

Requirements covered:
- 6.2.3: Integration tests for multi-user isolation
- 1.8: Multi-user support with per-user isolation
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch, call

from src.workers.risk_engine_worker import RiskEngineWorker
from src.workers.execution_worker import ExecutionWorker
from src.cache.redis_keys import RedisKeys


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def mock_kite_user1():
    """Create a mock KiteConnect client for user 1."""
    kite = MagicMock()
    kite.VARIETY_REGULAR = "regular"
    kite.positions.return_value = {
        "net": [
            {
                "tradingsymbol": "NIFTY23DEC21000CE",
                "exchange": "NFO",
                "product": "NRML",
                "quantity": 50,
                "average_price": 150.0,
                "last_price": 120.0,
                "pnl": -1500.0,
                "unrealised": -1500.0,
                "realised": 0.0,
                "buy_quantity": 50,
                "sell_quantity": 0,
            },
        ],
        "day": [],
    }
    kite.place_order.return_value = "ORDER_U1_001"
    return kite


@pytest.fixture
def mock_kite_user2():
    """Create a mock KiteConnect client for user 2."""
    kite = MagicMock()
    kite.VARIETY_REGULAR = "regular"
    kite.positions.return_value = {
        "net": [
            {
                "tradingsymbol": "BANKNIFTY23DEC45000PE",
                "exchange": "NFO",
                "product": "NRML",
                "quantity": -25,
                "average_price": 200.0,
                "last_price": 180.0,
                "pnl": 500.0,
                "unrealised": 500.0,
                "realised": 0.0,
                "buy_quantity": 0,
                "sell_quantity": 25,
            },
        ],
        "day": [],
    }
    kite.place_order.return_value = "ORDER_U2_001"
    return kite


@pytest.fixture
def redis_store():
    """Shared dict simulating Redis key-value store for isolation testing."""
    return {}


@pytest.fixture
def mock_redis_user1(redis_store):
    """Create a mock Redis client for user 1 backed by shared store."""
    redis = MagicMock()

    def _get(key):
        return redis_store.get(key)

    def _set(key, value, nx=False, **kwargs):
        if nx and key in redis_store:
            return False
        redis_store[key] = value
        return True

    def _hgetall(key):
        return redis_store.get(key, {})

    def _hset(key, mapping=None, **kwargs):
        if mapping:
            redis_store[key] = mapping
        return True

    def _lrange(key, start, end):
        return redis_store.get(key, [])

    def _lpush(key, *values):
        if key not in redis_store:
            redis_store[key] = []
        for v in values:
            redis_store[key].insert(0, v)
        return len(redis_store[key])

    redis.get.side_effect = _get
    redis.set.side_effect = _set
    redis.hgetall.side_effect = _hgetall
    redis.hset.side_effect = _hset
    redis.lrange.side_effect = _lrange
    redis.lpush.side_effect = _lpush
    redis.publish.return_value = 1
    return redis


@pytest.fixture
def mock_redis_user2(redis_store):
    """Create a mock Redis client for user 2 backed by same shared store."""
    redis = MagicMock()

    def _get(key):
        return redis_store.get(key)

    def _set(key, value, nx=False, **kwargs):
        if nx and key in redis_store:
            return False
        redis_store[key] = value
        return True

    def _hgetall(key):
        return redis_store.get(key, {})

    def _hset(key, mapping=None, **kwargs):
        if mapping:
            redis_store[key] = mapping
        return True

    def _lrange(key, start, end):
        return redis_store.get(key, [])

    def _lpush(key, *values):
        if key not in redis_store:
            redis_store[key] = []
        for v in values:
            redis_store[key].insert(0, v)
        return len(redis_store[key])

    redis.get.side_effect = _get
    redis.set.side_effect = _set
    redis.hgetall.side_effect = _hgetall
    redis.hset.side_effect = _hset
    redis.lrange.side_effect = _lrange
    redis.lpush.side_effect = _lpush
    redis.publish.return_value = 1
    return redis


@pytest.fixture
def mock_db_user1():
    """Create a mock database session for user 1."""
    db = MagicMock()
    mock_user = MagicMock()
    mock_user.capital = 500000.0
    mock_user.id = 1
    db.query.return_value.filter_by.return_value.first.return_value = mock_user
    db.add.return_value = None
    db.commit.return_value = None
    return db


@pytest.fixture
def mock_db_user2():
    """Create a mock database session for user 2."""
    db = MagicMock()
    mock_user = MagicMock()
    mock_user.capital = 300000.0
    mock_user.id = 2
    db.query.return_value.filter_by.return_value.first.return_value = mock_user
    db.add.return_value = None
    db.commit.return_value = None
    return db


# ============================================================
# 22.3.1: Create Two Users
# ============================================================


class TestCreateTwoUsers:
    """Test that two independent user worker instances can be created."""

    def test_create_risk_workers_for_two_users(
        self, mock_kite_user1, mock_kite_user2, mock_redis_user1, mock_redis_user2,
        mock_db_user1, mock_db_user2,
    ):
        """Two RiskEngineWorker instances can be created with different user_ids."""
        worker1 = RiskEngineWorker(
            user_id=1,
            kite_client=mock_kite_user1,
            redis_client=mock_redis_user1,
            db_session=mock_db_user1,
        )
        worker2 = RiskEngineWorker(
            user_id=2,
            kite_client=mock_kite_user2,
            redis_client=mock_redis_user2,
            db_session=mock_db_user2,
        )

        assert worker1.user_id == 1
        assert worker2.user_id == 2
        assert worker1.user_id != worker2.user_id

    def test_create_execution_workers_for_two_users(
        self, mock_kite_user1, mock_kite_user2, mock_redis_user1, mock_redis_user2,
        mock_db_user1, mock_db_user2,
    ):
        """Two ExecutionWorker instances can be created with different user_ids."""
        exec1 = ExecutionWorker(
            user_id=1,
            kite_client=mock_kite_user1,
            redis_client=mock_redis_user1,
            db_session=mock_db_user1,
        )
        exec2 = ExecutionWorker(
            user_id=2,
            kite_client=mock_kite_user2,
            redis_client=mock_redis_user2,
            db_session=mock_db_user2,
        )

        assert exec1.user_id == 1
        assert exec2.user_id == 2
        assert exec1.user_id != exec2.user_id


# ============================================================
# 22.3.2: Execute Trades for Both
# ============================================================


class TestExecuteTradesForBoth:
    """Test that both users can execute trades independently."""

    def test_user1_can_place_order(
        self, mock_kite_user1, mock_redis_user1, mock_db_user1,
    ):
        """User 1 can place an order successfully."""
        exec1 = ExecutionWorker(
            user_id=1,
            kite_client=mock_kite_user1,
            redis_client=mock_redis_user1,
            db_session=mock_db_user1,
        )
        order = {
            "exchange": "NFO",
            "symbol": "NIFTY23DEC21000CE",
            "side": "BUY",
            "quantity": 50,
            "order_type": "MARKET",
        }
        result = exec1.place_order(order)

        assert result["success"] is True
        assert result["order_id"] == "ORDER_U1_001"

    def test_user2_can_place_order(
        self, mock_kite_user2, mock_redis_user2, mock_db_user2,
    ):
        """User 2 can place an order successfully."""
        exec2 = ExecutionWorker(
            user_id=2,
            kite_client=mock_kite_user2,
            redis_client=mock_redis_user2,
            db_session=mock_db_user2,
        )
        order = {
            "exchange": "NFO",
            "symbol": "BANKNIFTY23DEC45000PE",
            "side": "SELL",
            "quantity": 25,
            "order_type": "MARKET",
        }
        result = exec2.place_order(order)

        assert result["success"] is True
        assert result["order_id"] == "ORDER_U2_001"

    def test_both_users_trade_independently(
        self, mock_kite_user1, mock_kite_user2,
        mock_redis_user1, mock_redis_user2,
        mock_db_user1, mock_db_user2,
    ):
        """Both users can trade simultaneously without interference."""
        exec1 = ExecutionWorker(
            user_id=1,
            kite_client=mock_kite_user1,
            redis_client=mock_redis_user1,
            db_session=mock_db_user1,
        )
        exec2 = ExecutionWorker(
            user_id=2,
            kite_client=mock_kite_user2,
            redis_client=mock_redis_user2,
            db_session=mock_db_user2,
        )

        order1 = {
            "exchange": "NFO",
            "symbol": "NIFTY23DEC21000CE",
            "side": "BUY",
            "quantity": 50,
            "order_type": "MARKET",
        }
        order2 = {
            "exchange": "NFO",
            "symbol": "BANKNIFTY23DEC45000PE",
            "side": "SELL",
            "quantity": 25,
            "order_type": "MARKET",
        }

        result1 = exec1.place_order(order1)
        result2 = exec2.place_order(order2)

        assert result1["success"] is True
        assert result2["success"] is True
        assert result1["order_id"] != result2["order_id"]


# ============================================================
# 22.3.3: Verify Isolation
# ============================================================


class TestVerifyIsolation:
    """Test that user data is isolated via different Redis keys and DB queries."""

    def test_redis_keys_are_user_scoped(self):
        """RedisKeys generates unique keys per user_id."""
        risk_key_1 = RedisKeys.user_risk(1)
        risk_key_2 = RedisKeys.user_risk(2)
        assert risk_key_1 == "user:1:risk"
        assert risk_key_2 == "user:2:risk"
        assert risk_key_1 != risk_key_2

        ks_key_1 = RedisKeys.user_killswitch(1)
        ks_key_2 = RedisKeys.user_killswitch(2)
        assert ks_key_1 == "user:1:killswitch"
        assert ks_key_2 == "user:2:killswitch"
        assert ks_key_1 != ks_key_2

        orders_key_1 = RedisKeys.user_recent_orders(1)
        orders_key_2 = RedisKeys.user_recent_orders(2)
        assert orders_key_1 == "user:1:recent_orders"
        assert orders_key_2 == "user:2:recent_orders"
        assert orders_key_1 != orders_key_2

    def test_risk_cache_isolation(
        self, redis_store, mock_kite_user1, mock_kite_user2,
        mock_redis_user1, mock_redis_user2,
        mock_db_user1, mock_db_user2,
    ):
        """Risk metrics for one user do not appear in the other user's cache."""
        worker1 = RiskEngineWorker(
            user_id=1,
            kite_client=mock_kite_user1,
            redis_client=mock_redis_user1,
            db_session=mock_db_user1,
        )
        worker2 = RiskEngineWorker(
            user_id=2,
            kite_client=mock_kite_user2,
            redis_client=mock_redis_user2,
            db_session=mock_db_user2,
        )

        # Update risk cache for user 1
        worker1.update_redis_cache(
            pnl=-1500.0,
            greeks={"net_delta": 0.5, "net_gamma": 0.01, "net_vega": 100.0},
            margin_used=50000.0,
        )

        # User 2's risk key should not have user 1's data
        user2_risk_key = RedisKeys.user_risk(2)
        user1_risk_key = RedisKeys.user_risk(1)

        # The shared store should show user 1's key was set
        # but user 2's key should be empty/missing
        assert user1_risk_key != user2_risk_key

        # Verify redis was called with the correct user-scoped key for user 1
        mock_redis_user1.hset.assert_called()
        call_args = mock_redis_user1.hset.call_args
        # The key passed to hset should contain user_id=1
        assert "user:1:risk" in str(call_args)

    def test_execution_uses_user_specific_keys(
        self, redis_store, mock_kite_user1, mock_kite_user2,
        mock_redis_user1, mock_redis_user2,
        mock_db_user1, mock_db_user2,
    ):
        """ExecutionWorker check_killswitch reads user-specific Redis keys."""
        exec1 = ExecutionWorker(
            user_id=1,
            kite_client=mock_kite_user1,
            redis_client=mock_redis_user1,
            db_session=mock_db_user1,
        )
        exec2 = ExecutionWorker(
            user_id=2,
            kite_client=mock_kite_user2,
            redis_client=mock_redis_user2,
            db_session=mock_db_user2,
        )

        # Check killswitch for both - both should be inactive
        ks1 = exec1.check_killswitch()
        ks2 = exec2.check_killswitch()

        assert ks1 is False
        assert ks2 is False

        # Verify each worker read from its own key
        mock_redis_user1.get.assert_called_with("user:1:killswitch")
        mock_redis_user2.get.assert_called_with("user:2:killswitch")


# ============================================================
# 22.3.4: Trigger Kill Switch for One
# ============================================================


class TestTriggerKillSwitchForOne:
    """Test that kill switch can be triggered for a single user."""

    def test_trigger_killswitch_for_user1_only(
        self, redis_store, mock_kite_user1, mock_redis_user1, mock_db_user1,
    ):
        """Triggering kill switch for user 1 sets only user 1's flag."""
        worker1 = RiskEngineWorker(
            user_id=1,
            kite_client=mock_kite_user1,
            redis_client=mock_redis_user1,
            db_session=mock_db_user1,
        )

        result = worker1.trigger_killswitch(reason="Daily loss limit breached")

        assert result is True
        # Verify the Redis set was called with user 1's killswitch key
        mock_redis_user1.set.assert_called_with(
            "user:1:killswitch", "true", nx=True
        )

    def test_killswitch_flag_set_in_redis_store(
        self, redis_store, mock_kite_user1, mock_redis_user1, mock_db_user1,
    ):
        """Kill switch flag is stored with user-scoped key in Redis."""
        worker1 = RiskEngineWorker(
            user_id=1,
            kite_client=mock_kite_user1,
            redis_client=mock_redis_user1,
            db_session=mock_db_user1,
        )

        worker1.trigger_killswitch(reason="Daily loss limit breached")

        # The shared Redis store should have user:1:killswitch = "true"
        assert redis_store.get("user:1:killswitch") == "true"
        # User 2's key should NOT be set
        assert redis_store.get("user:2:killswitch") is None


# ============================================================
# 22.3.5: Verify Other Unaffected
# ============================================================


class TestVerifyOtherUnaffected:
    """Test that triggering kill switch for user 1 does not affect user 2."""

    def test_user2_killswitch_not_set_after_user1_trigger(
        self, redis_store, mock_kite_user1, mock_kite_user2,
        mock_redis_user1, mock_redis_user2,
        mock_db_user1, mock_db_user2,
    ):
        """User 2's kill switch flag remains inactive after user 1's trigger."""
        worker1 = RiskEngineWorker(
            user_id=1,
            kite_client=mock_kite_user1,
            redis_client=mock_redis_user1,
            db_session=mock_db_user1,
        )
        exec2 = ExecutionWorker(
            user_id=2,
            kite_client=mock_kite_user2,
            redis_client=mock_redis_user2,
            db_session=mock_db_user2,
        )

        # Trigger kill switch for user 1
        worker1.trigger_killswitch(reason="Daily loss limit breached")

        # User 2's kill switch should remain inactive
        ks2 = exec2.check_killswitch()
        assert ks2 is False

    def test_user2_can_still_trade_after_user1_killswitch(
        self, redis_store, mock_kite_user1, mock_kite_user2,
        mock_redis_user1, mock_redis_user2,
        mock_db_user1, mock_db_user2,
    ):
        """User 2 can still place orders after user 1's kill switch triggers."""
        worker1 = RiskEngineWorker(
            user_id=1,
            kite_client=mock_kite_user1,
            redis_client=mock_redis_user1,
            db_session=mock_db_user1,
        )
        exec2 = ExecutionWorker(
            user_id=2,
            kite_client=mock_kite_user2,
            redis_client=mock_redis_user2,
            db_session=mock_db_user2,
        )

        # Trigger kill switch for user 1
        worker1.trigger_killswitch(reason="Daily loss limit breached")

        # User 2 can still trade
        order = {
            "exchange": "NFO",
            "symbol": "BANKNIFTY23DEC45000PE",
            "side": "SELL",
            "quantity": 25,
            "order_type": "MARKET",
        }
        result = exec2.place_order(order)

        assert result["success"] is True
        assert result["order_id"] == "ORDER_U2_001"

    def test_user1_blocked_user2_unblocked(
        self, redis_store, mock_kite_user1, mock_kite_user2,
        mock_redis_user1, mock_redis_user2,
        mock_db_user1, mock_db_user2,
    ):
        """User 1 is blocked from trading while user 2 remains free."""
        worker1 = RiskEngineWorker(
            user_id=1,
            kite_client=mock_kite_user1,
            redis_client=mock_redis_user1,
            db_session=mock_db_user1,
        )
        exec1 = ExecutionWorker(
            user_id=1,
            kite_client=mock_kite_user1,
            redis_client=mock_redis_user1,
            db_session=mock_db_user1,
        )
        exec2 = ExecutionWorker(
            user_id=2,
            kite_client=mock_kite_user2,
            redis_client=mock_redis_user2,
            db_session=mock_db_user2,
        )

        # Trigger kill switch for user 1
        worker1.trigger_killswitch(reason="Daily loss limit breached")

        # User 1's kill switch is active
        assert exec1.check_killswitch() is True

        # User 2's kill switch is NOT active
        assert exec2.check_killswitch() is False

    def test_user2_validate_order_passes_after_user1_killswitch(
        self, redis_store, mock_kite_user1, mock_kite_user2,
        mock_redis_user1, mock_redis_user2,
        mock_db_user1, mock_db_user2,
    ):
        """User 2's validate_order passes all checks after user 1's kill switch."""
        worker1 = RiskEngineWorker(
            user_id=1,
            kite_client=mock_kite_user1,
            redis_client=mock_redis_user1,
            db_session=mock_db_user1,
        )
        exec2 = ExecutionWorker(
            user_id=2,
            kite_client=mock_kite_user2,
            redis_client=mock_redis_user2,
            db_session=mock_db_user2,
        )

        # Trigger kill switch for user 1
        worker1.trigger_killswitch(reason="Daily loss limit breached")

        # User 2 can validate orders normally
        order = {
            "exchange": "NFO",
            "symbol": "BANKNIFTY23DEC45000PE",
            "side": "SELL",
            "quantity": 25,
            "order_type": "MARKET",
        }
        is_valid, message = exec2.validate_order(order)

        assert is_valid is True
        assert message == "Valid"
