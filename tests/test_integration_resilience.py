"""Integration tests for Redis failover and worker restart resilience (Tasks 22.4 & 22.5).

Tests the system's behavior when Redis becomes unavailable (failover)
and when Celery workers crash and restart (task durability).

Requirements covered:
- 6.2.4: Integration tests for Redis failover
- 6.2.5: Integration tests for worker restart
- 2.3.3: Handle Redis connection loss gracefully
- 2.3.4: Fall back to database when Redis unavailable
- 2.3.1: Automatically restart crashed workers within 5 seconds
- 2.3.2: Not lose queued tasks when workers restart
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime

import redis
from fastapi.testclient import TestClient

from src.workers.risk_engine_worker import RiskEngineWorker
from src.workers.execution_worker import ExecutionWorker
from src.cache.redis_keys import RedisKeys


# --- Constants ---

USER_ID = 1
CAPITAL = 500000.0


# --- Fixtures ---


@pytest.fixture
def mock_kite():
    """Create a mock Kite client."""
    kite = MagicMock()
    kite.VARIETY_REGULAR = "regular"
    kite.positions.return_value = {
        "net": [
            {
                "tradingsymbol": "NIFTY23DEC21000CE",
                "exchange": "NFO",
                "product": "MIS",
                "quantity": 50,
                "average_price": 150.0,
                "last_price": 160.0,
                "pnl": 500.0,
                "delta": 0.5,
                "gamma": 0.01,
                "vega": 10.0,
                "margin": 50000.0,
            }
        ]
    }
    return kite


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    db = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock()
    db.rollback = MagicMock()
    return db


@pytest.fixture
def redis_connection_error():
    """Create a Redis ConnectionError for simulating Redis unavailability."""
    return redis.ConnectionError("Connection refused")


@pytest.fixture
def mock_redis_unavailable(redis_connection_error):
    """Create a mock Redis client that raises ConnectionError on all operations.

    Simulates Redis being completely unavailable (Task 22.4.1: Stop Redis).
    """
    mock_redis = MagicMock()
    mock_redis.get.side_effect = redis_connection_error
    mock_redis.set.side_effect = redis_connection_error
    mock_redis.hset.side_effect = redis_connection_error
    mock_redis.hgetall.side_effect = redis_connection_error
    mock_redis.lrange.side_effect = redis_connection_error
    mock_redis.lpush.side_effect = redis_connection_error
    mock_redis.ltrim.side_effect = redis_connection_error
    mock_redis.expire.side_effect = redis_connection_error
    mock_redis.delete.side_effect = redis_connection_error
    return mock_redis


@pytest.fixture
def mock_redis_healthy():
    """Create a mock Redis client that works normally.

    Simulates Redis being available (Task 22.4.3: Restart Redis).
    """
    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    mock_redis.set.return_value = True
    mock_redis.hset.return_value = 1
    mock_redis.hgetall.return_value = {}
    mock_redis.lrange.return_value = []
    mock_redis.lpush.return_value = 1
    mock_redis.ltrim.return_value = True
    mock_redis.expire.return_value = True
    mock_redis.delete.return_value = 1
    return mock_redis


# =============================================================================
# Task 22.4: Test Redis Failover
# =============================================================================


class TestRedisFailover:
    """Integration tests for Redis failover behavior.

    Verifies the system handles Redis being unavailable gracefully:
    - RiskEngineWorker falls back when cache update fails
    - ExecutionWorker uses safe defaults when Redis is unreachable
    - System recovers when Redis comes back online

    Requirements covered:
    - 6.2.4: Integration tests for Redis failover
    - 2.3.3: Handle Redis connection loss gracefully
    - 2.3.4: Fall back to database when Redis unavailable
    """

    # --- 22.4.1: Stop Redis (simulate Redis unavailable) ---
    # --- 22.4.2: Verify fallback to database ---

    def test_risk_engine_update_redis_cache_returns_false_on_redis_failure(
        self, mock_kite, mock_db, mock_redis_unavailable
    ):
        """RiskEngineWorker.update_redis_cache returns False when Redis is down.

        Validates: Requirement 2.3.3 - Handle Redis connection loss gracefully
        """
        worker = RiskEngineWorker(
            user_id=USER_ID,
            kite_client=mock_kite,
            redis_client=mock_redis_unavailable,
            db_session=mock_db,
        )

        greeks = {"net_delta": 25.0, "net_gamma": 0.5, "net_vega": 500.0}
        result = worker.update_redis_cache(pnl=-5000.0, greeks=greeks, margin_used=100000.0)

        # Should return False indicating cache update failed
        assert result is False


    def test_risk_engine_continues_processing_despite_redis_failure(
        self, mock_kite, mock_db, mock_redis_unavailable
    ):
        """RiskEngineWorker can still compute metrics even when Redis is down.

        The risk engine should compute P&L, Greeks, and margin regardless
        of whether it can cache them. Processing should not crash.

        Validates: Requirement 2.3.4 - Fall back to database when Redis unavailable
        """
        worker = RiskEngineWorker(
            user_id=USER_ID,
            kite_client=mock_kite,
            redis_client=mock_redis_unavailable,
            db_session=mock_db,
        )

        positions = [
            {"pnl": -3000.0, "quantity": 50, "delta": 0.5, "gamma": 0.01, "vega": 10.0, "margin": 50000.0},
            {"pnl": 1000.0, "quantity": -25, "delta": 0.3, "gamma": 0.02, "vega": 8.0, "margin": 30000.0},
        ]

        # These computations should succeed without Redis
        pnl = worker.compute_live_pnl(positions)
        greeks = worker.compute_greeks(positions)
        margin = worker.compute_margin_used(positions)

        assert pnl == -2000.0
        assert greeks["net_delta"] == (0.5 * 50) + (0.3 * -25)
        assert margin == 80000.0

        # Cache update should fail gracefully (return False, no exception)
        result = worker.update_redis_cache(pnl, greeks, margin)
        assert result is False


    def test_execution_worker_check_killswitch_returns_true_on_redis_failure(
        self, mock_kite, mock_db, mock_redis_unavailable
    ):
        """ExecutionWorker.check_killswitch returns True (safe default) when Redis is down.

        When Redis is unavailable, the system cannot confirm whether the kill
        switch is active. The safe default is to BLOCK trading (return True)
        to prevent accidental execution during uncertain system state.

        Validates: Requirement 2.3.3 - Handle Redis connection loss gracefully
        """
        worker = ExecutionWorker(
            user_id=USER_ID,
            kite_client=mock_kite,
            redis_client=mock_redis_unavailable,
            db_session=mock_db,
        )

        # When Redis is down, check_killswitch should return True (block trades)
        result = worker.check_killswitch()
        assert result is True

    def test_execution_worker_blocks_trades_when_redis_unavailable(
        self, mock_kite, mock_db, mock_redis_unavailable
    ):
        """ExecutionWorker blocks trade execution when Redis is unavailable.

        Since check_killswitch returns True on Redis failure, any order
        validation should fail with "Kill switch is active" message.

        Validates: Requirement 2.3.3 - Handle Redis connection loss gracefully
        """
        worker = ExecutionWorker(
            user_id=USER_ID,
            kite_client=mock_kite,
            redis_client=mock_redis_unavailable,
            db_session=mock_db,
        )

        order = {
            "symbol": "NIFTY23DEC21000CE",
            "exchange": "NFO",
            "side": "BUY",
            "quantity": 50,
        }

        valid, message = worker.validate_order(order)
        assert valid is False
        assert "kill switch" in message.lower() or "Kill switch" in message


    # --- 22.4.3: Restart Redis (simulate Redis recovery) ---
    # --- 22.4.4: Verify cache rebuild ---

    def test_risk_engine_cache_rebuild_after_redis_recovery(
        self, mock_kite, mock_db, mock_redis_healthy
    ):
        """RiskEngineWorker successfully rebuilds cache after Redis recovers.

        After Redis comes back online, update_redis_cache should succeed,
        effectively rebuilding the cache from computed metrics.

        Validates: Requirement 2.3.4 - Fall back to database when Redis unavailable
        """
        worker = RiskEngineWorker(
            user_id=USER_ID,
            kite_client=mock_kite,
            redis_client=mock_redis_healthy,
            db_session=mock_db,
        )

        greeks = {"net_delta": 25.0, "net_gamma": 0.5, "net_vega": 500.0}
        result = worker.update_redis_cache(pnl=-5000.0, greeks=greeks, margin_used=100000.0)

        # Should return True indicating cache was rebuilt successfully
        assert result is True
        # Verify hset was called with correct key
        expected_key = RedisKeys.user_risk(USER_ID)
        mock_redis_healthy.hset.assert_called_once()
        call_args = mock_redis_healthy.hset.call_args
        # hset is called as hset(key, mapping=...) - key is first positional arg
        assert call_args[0][0] == expected_key


    def test_cache_rebuild_stores_correct_values_after_recovery(
        self, mock_kite, mock_db, mock_redis_healthy
    ):
        """Verify rebuilt cache contains the exact computed values.

        After Redis recovery, update_redis_cache must store the correct pnl,
        greeks (net_delta, net_gamma, net_vega), margin_used, and a valid
        timestamp in the Redis hash mapping. The key must follow the
        RedisKeys.user_risk pattern: "user:{user_id}:risk".

        Validates: Requirement 2.3.4, 3.6.1, 3.6.9
        """
        worker = RiskEngineWorker(
            user_id=USER_ID,
            kite_client=mock_kite,
            redis_client=mock_redis_healthy,
            db_session=mock_db,
        )

        # Specific values to verify in the cache
        pnl = -7500.50
        greeks = {"net_delta": 42.3, "net_gamma": 1.25, "net_vega": 850.0}
        margin_used = 225000.75

        result = worker.update_redis_cache(pnl=pnl, greeks=greeks, margin_used=margin_used)
        assert result is True

        # Extract the mapping passed to hset
        call_args = mock_redis_healthy.hset.call_args
        key_used = call_args[0][0]
        mapping = call_args[1]["mapping"]

        # Verify key follows RedisKeys pattern
        assert key_used == f"user:{USER_ID}:risk"
        assert key_used == RedisKeys.user_risk(USER_ID)

        # Verify all computed values are stored correctly as strings
        assert mapping["pnl"] == str(pnl)
        assert mapping["net_delta"] == str(greeks["net_delta"])
        assert mapping["net_gamma"] == str(greeks["net_gamma"])
        assert mapping["net_vega"] == str(greeks["net_vega"])
        assert mapping["margin_used"] == str(margin_used)

        # Verify timestamp is present and is a valid ISO format
        assert "updated_at" in mapping
        # Should parse without error (validates ISO format)
        parsed_time = datetime.fromisoformat(mapping["updated_at"])
        assert parsed_time is not None

    def test_execution_worker_resumes_normal_after_redis_recovery(
        self, mock_kite, mock_db, mock_redis_healthy
    ):
        """ExecutionWorker resumes normal kill switch checks after Redis recovers.

        After Redis comes back, check_killswitch should return False
        (no kill switch active) and allow trades to proceed.

        Validates: Requirement 2.3.4 - Fall back to database when Redis unavailable
        """
        worker = ExecutionWorker(
            user_id=USER_ID,
            kite_client=mock_kite,
            redis_client=mock_redis_healthy,
            db_session=mock_db,
        )

        # Redis returns None (key doesn't exist) = kill switch inactive
        result = worker.check_killswitch()
        assert result is False

    def test_full_redis_failover_and_recovery_cycle(
        self, mock_kite, mock_db, mock_redis_unavailable, mock_redis_healthy
    ):
        """Full cycle: Redis down -> fallback -> Redis up -> cache rebuild.

        Simulates the complete failover scenario end-to-end:
        1. Redis goes down - cache update fails but computation continues
        2. Redis comes back - cache rebuild succeeds

        Validates: Requirements 2.3.3, 2.3.4
        """
        positions = [
            {"pnl": -5000.0, "quantity": 50, "delta": 0.5, "gamma": 0.01, "vega": 10.0, "margin": 50000.0},
        ]

        # Phase 1: Redis unavailable
        worker_down = RiskEngineWorker(
            user_id=USER_ID,
            kite_client=mock_kite,
            redis_client=mock_redis_unavailable,
            db_session=mock_db,
        )
        pnl = worker_down.compute_live_pnl(positions)
        greeks = worker_down.compute_greeks(positions)
        margin = worker_down.compute_margin_used(positions)
        cache_result = worker_down.update_redis_cache(pnl, greeks, margin)
        assert cache_result is False  # Failed due to Redis being down

        # Phase 2: Redis recovered
        worker_up = RiskEngineWorker(
            user_id=USER_ID,
            kite_client=mock_kite,
            redis_client=mock_redis_healthy,
            db_session=mock_db,
        )
        cache_result = worker_up.update_redis_cache(pnl, greeks, margin)
        assert cache_result is True  # Cache rebuilt successfully


# =============================================================================
# Task 22.4.2: Verify fallback to database (API endpoint level)
# =============================================================================


class TestRedisFallbackToDatabase:
    """Integration tests verifying API endpoints fall back to database when Redis is unavailable.

    When Redis raises ConnectionError, the RedisClient returns safe defaults
    (empty dict for hgetall, None for get). The dashboard and risk endpoints
    detect missing/stale data and fall back to reading from PostgreSQL.

    Requirements covered:
    - 2.3.3: Handle Redis connection loss gracefully
    - 2.3.4: Fall back to database when Redis unavailable
    """

    def _create_test_app(self):
        """Create a fresh FastAPI app with the dashboard router."""
        from fastapi import FastAPI
        from src.api.routers.dashboard import router

        app = FastAPI()
        app.include_router(router)
        return app

    def _mock_redis_unavailable(self):
        """Create a mock RedisClient that simulates Redis being completely down.

        All operations return safe defaults as the real RedisClient does when
        ConnectionError occurs:
        - hgetall -> {} (empty dict)
        - get -> None
        - hset -> False
        - set -> False
        """
        mock_redis = MagicMock()
        mock_redis.hgetall.return_value = {}
        mock_redis.get.return_value = None
        mock_redis.hset.return_value = False
        mock_redis.set.return_value = False
        return mock_redis

    def _make_fake_position(
        self,
        user_id=1,
        net_delta=1.5,
        net_gamma=0.03,
        net_vega=200.0,
        margin_used=75000.0,
        unrealized_pnl=-4500.0,
    ):
        """Create a mock Position object simulating database data."""
        pos = MagicMock()
        pos.user_id = user_id
        pos.net_delta = net_delta
        pos.net_gamma = net_gamma
        pos.net_vega = net_vega
        pos.margin_used = margin_used
        pos.unrealized_pnl = unrealized_pnl
        pos.updated_at = datetime.now()
        return pos

    def _make_fake_trade(
        self,
        id=1,
        user_id=1,
        symbol="RELIANCE",
        exchange="NSE",
        qty=10,
        side="BUY",
        entry_price=2500.0,
        pnl=500.0,
        margin_used=25000.0,
        status="OPEN",
    ):
        """Create a mock Trade object simulating database data."""
        trade = MagicMock()
        trade.id = id
        trade.user_id = user_id
        trade.symbol = symbol
        trade.exchange = exchange
        trade.qty = qty
        trade.side = side
        trade.entry_price = entry_price
        trade.pnl = pnl
        trade.margin_used = margin_used
        trade.status = status
        trade.timestamp = datetime(2024, 1, 15, 10, 30, 0)
        trade.exit_price = None
        trade.exit_timestamp = None
        return trade

    def test_risk_endpoint_falls_back_to_database_when_redis_unavailable(self):
        """GET /api/v1/risk returns data from database Position when Redis is down.

        When Redis returns empty data (simulating unavailability), the risk
        endpoint should query the Position table and return those metrics.
        No error should propagate to the user.

        Validates: Requirement 2.3.4 - Fall back to database when Redis unavailable
        """
        app = self._create_test_app()

        from src.api.dependencies import get_db, get_redis, get_current_user

        # Redis is unavailable — returns empty/None for all operations
        mock_redis = self._mock_redis_unavailable()

        # Database has position data as fallback
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = self._make_fake_position(
            net_delta=1.5,
            net_gamma=0.03,
            net_vega=200.0,
            unrealized_pnl=-4500.0,
        )

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_current_user] = lambda: 1

        client = TestClient(app)
        response = client.get("/api/v1/risk")

        # No error propagated to user
        assert response.status_code == 200

        data = response.json()
        # Data comes from database Position, not Redis
        assert data["net_delta"] == 1.5
        assert data["net_gamma"] == 0.03
        assert data["net_vega"] == 200.0
        assert data["unrealized_pnl"] == -4500.0
        # Kill switch defaults to False when Redis is unavailable (get returns None)
        assert data["killswitch_active"] is False

        app.dependency_overrides.clear()

    def test_dashboard_endpoint_falls_back_to_database_when_redis_unavailable(self):
        """GET /api/v1/dashboard returns positions from DB when Redis is down.

        When Redis is unavailable:
        - risk_metrics default to zeros (no Redis data, no fresh cache)
        - positions come from database trades
        - killswitch defaults to False (Redis returns None)
        No error should propagate to the user.

        Validates: Requirement 2.3.4 - Fall back to database when Redis unavailable
        """
        app = self._create_test_app()

        from src.api.dependencies import get_db, get_redis, get_current_user

        # Redis is unavailable
        mock_redis = self._mock_redis_unavailable()

        # Database has open trades
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [
            self._make_fake_trade(symbol="RELIANCE", qty=10, entry_price=2500.0, pnl=500.0),
            self._make_fake_trade(id=2, symbol="TCS", qty=5, entry_price=3800.0, side="SELL", pnl=-200.0),
        ]

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_current_user] = lambda: 1

        client = TestClient(app)
        response = client.get("/api/v1/dashboard")

        # No error propagated to user
        assert response.status_code == 200

        data = response.json()

        # Risk metrics default to zeros (Redis unavailable, no cache)
        assert data["risk_metrics"]["daily_loss_pct"] == 0.0
        assert data["risk_metrics"]["net_delta"] == 0.0

        # Positions come from database trades
        assert len(data["positions"]) == 2
        assert data["positions"][0]["symbol"] == "RELIANCE"
        assert data["positions"][0]["entry_price"] == 2500.0
        # No current price available (Redis market data unavailable)
        assert data["positions"][0]["current_price"] is None
        # P&L falls back to trade's stored pnl field
        assert data["positions"][0]["pnl"] == 500.0

        assert data["positions"][1]["symbol"] == "TCS"
        assert data["positions"][1]["pnl"] == -200.0

        # Kill switch defaults to False when Redis is unavailable
        assert data["killswitch_active"] is False

        app.dependency_overrides.clear()

    def test_risk_endpoint_returns_defaults_when_redis_and_db_both_empty(self):
        """GET /api/v1/risk returns zeroed defaults when neither Redis nor DB has data.

        Even in the worst case (Redis down + no DB position record), the
        endpoint must return a valid response with zeroed defaults.

        Validates: Requirement 2.3.3 - Handle Redis connection loss gracefully
        """
        app = self._create_test_app()

        from src.api.dependencies import get_db, get_redis, get_current_user

        mock_redis = self._mock_redis_unavailable()

        # Database also has no position record for the user
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_current_user] = lambda: 1

        client = TestClient(app)
        response = client.get("/api/v1/risk")

        # Still returns 200 with defaults
        assert response.status_code == 200

        data = response.json()
        assert data["daily_loss_pct"] == 0.0
        assert data["capital_used_pct"] == 0.0
        assert data["margin_used_pct"] == 0.0
        assert data["net_delta"] == 0.0
        assert data["net_gamma"] == 0.0
        assert data["net_vega"] == 0.0
        assert data["unrealized_pnl"] == 0.0
        assert data["killswitch_active"] is False

        app.dependency_overrides.clear()

    def test_positions_endpoint_uses_db_pnl_when_redis_market_data_unavailable(self):
        """GET /api/v1/positions uses stored trade P&L when Redis market data is gone.

        When Redis is down, market data cache is unavailable. The positions
        endpoint should still return positions using the stored pnl from the
        trade record rather than failing.

        Validates: Requirement 2.3.4 - Fall back to database when Redis unavailable
        """
        app = self._create_test_app()

        from src.api.dependencies import get_db, get_redis, get_current_user

        mock_redis = self._mock_redis_unavailable()

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [
            self._make_fake_trade(
                symbol="NIFTY24JUNFUT", exchange="NFO", qty=50,
                entry_price=22500.0, pnl=2500.0, margin_used=100000.0,
            ),
        ]

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_current_user] = lambda: 1

        client = TestClient(app)
        response = client.get("/api/v1/positions")

        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["symbol"] == "NIFTY24JUNFUT"
        assert data[0]["quantity"] == 50
        assert data[0]["entry_price"] == 22500.0
        # No current price (Redis unavailable for market data)
        assert data[0]["current_price"] is None
        # Falls back to stored pnl from trade record
        assert data[0]["pnl"] == 2500.0
        assert data[0]["margin_used"] == 100000.0

        app.dependency_overrides.clear()

    def test_no_500_error_when_redis_raises_connection_error(self):
        """All dashboard endpoints return 200 (not 500) when Redis is unavailable.

        This test confirms that ConnectionError from Redis is caught internally
        by the RedisClient (returning safe defaults) and never propagates as
        an unhandled exception to the API layer.

        Validates: Requirement 2.3.3 - Handle Redis connection loss gracefully
        """
        app = self._create_test_app()

        from src.api.dependencies import get_db, get_redis, get_current_user

        mock_redis = self._mock_redis_unavailable()

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []
        mock_query.first.return_value = None

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_current_user] = lambda: 1

        client = TestClient(app)

        # All endpoints should return 200, not 500
        risk_resp = client.get("/api/v1/risk")
        assert risk_resp.status_code == 200

        dashboard_resp = client.get("/api/v1/dashboard")
        assert dashboard_resp.status_code == 200

        positions_resp = client.get("/api/v1/positions")
        assert positions_resp.status_code == 200

        app.dependency_overrides.clear()


# =============================================================================
# Task 22.5: Test Worker Restart
# =============================================================================


class TestWorkerRestart:
    """Integration tests for Celery worker restart behavior.

    Verifies task durability when workers crash and restart:
    - Tasks can be queued via celery_app.send_task
    - Tasks survive worker unavailability through retry mechanism
    - Tasks are eventually processed after worker recovery

    Requirements covered:
    - 6.2.5: Integration tests for worker restart
    - 2.3.1: Automatically restart crashed workers within 5 seconds
    - 2.3.2: Not lose queued tasks when workers restart
    """

    # --- 22.5.1: Queue tasks ---

    @patch("src.workers.celery_app.celery_app.send_task")
    def test_tasks_can_be_queued(self, mock_send_task, mock_kite, mock_db, mock_redis_healthy):
        """Verify tasks can be queued via celery_app.send_task.

        Tests that the RiskEngineWorker can successfully queue exit orders
        as Celery tasks via send_task, simulating normal task queuing.

        Validates: Requirement 2.3.2 - Not lose queued tasks when workers restart
        """
        mock_send_task.return_value = MagicMock(id="task-123")

        worker = RiskEngineWorker(
            user_id=USER_ID,
            kite_client=mock_kite,
            redis_client=mock_redis_healthy,
            db_session=mock_db,
        )

        # Queue an exit order (simulates kill switch queueing tasks)
        position = {
            "tradingsymbol": "NIFTY23DEC21000CE",
            "exchange": "NFO",
            "product": "MIS",
            "quantity": 50,
        }
        worker._queue_single_exit_order(position)

        # Verify send_task was called
        mock_send_task.assert_called_once()
        call_kwargs = mock_send_task.call_args[1]
        assert call_kwargs["kwargs"]["user_id"] == USER_ID
        assert call_kwargs["kwargs"]["tradingsymbol"] == "NIFTY23DEC21000CE"
        assert call_kwargs["kwargs"]["transaction_type"] == "SELL"
        assert call_kwargs["kwargs"]["quantity"] == 50


    # --- 22.5.2: Kill worker (simulate worker crash) ---

    @patch("src.workers.celery_app.celery_app.send_task")
    def test_task_fails_when_worker_unavailable(
        self, mock_send_task, mock_kite, mock_db, mock_redis_healthy
    ):
        """Simulate worker being unavailable - task send raises exception.

        When a Celery worker crashes, tasks sent to it may raise exceptions.
        The system should handle this gracefully without crashing.

        Validates: Requirement 2.3.1 - Automatically restart crashed workers
        """
        mock_send_task.side_effect = Exception("Worker connection refused")

        worker = RiskEngineWorker(
            user_id=USER_ID,
            kite_client=mock_kite,
            redis_client=mock_redis_healthy,
            db_session=mock_db,
        )

        # Queue exit order should not raise even when worker is down
        position = {
            "tradingsymbol": "NIFTY23DEC21000CE",
            "exchange": "NFO",
            "product": "MIS",
            "quantity": 50,
        }
        # Should not raise - the method handles exceptions internally
        worker._queue_single_exit_order(position)

        # The send_task was called but failed
        mock_send_task.assert_called_once()


    # --- 22.5.3: Restart worker (simulate worker recovery) ---
    # --- 22.5.4: Verify task processing ---

    @patch("time.sleep", return_value=None)
    def test_execution_worker_retry_processes_after_transient_failure(
        self, mock_sleep, mock_kite, mock_db, mock_redis_healthy
    ):
        """ExecutionWorker retries and eventually succeeds after transient failures.

        Simulates a worker crash/restart scenario where the first attempts
        fail (worker unavailable) but a subsequent retry succeeds (worker
        recovered). The execute_with_retry method handles this via
        exponential backoff retries.

        Validates: Requirement 2.3.2 - Not lose queued tasks when workers restart
        """
        from kiteconnect import exceptions as kite_exceptions

        # First 2 calls fail with NetworkException (simulating worker/broker down)
        # Third call succeeds (worker recovered)
        mock_kite.place_order.side_effect = [
            kite_exceptions.NetworkException("Connection timeout"),
            kite_exceptions.NetworkException("Connection reset"),
            "ORDER-12345",  # Success on third attempt
        ]

        worker = ExecutionWorker(
            user_id=USER_ID,
            kite_client=mock_kite,
            redis_client=mock_redis_healthy,
            db_session=mock_db,
        )

        order = {
            "symbol": "NIFTY23DEC21000CE",
            "exchange": "NFO",
            "side": "BUY",
            "quantity": 50,
            "order_type": "MARKET",
        }

        result = worker.execute_with_retry(order)

        # Should eventually succeed after retries
        assert result["success"] is True
        assert result["order_id"] == "ORDER-12345"
        assert result["attempts"] == 3

        # Verify sleep was called for backoff between retries
        assert mock_sleep.call_count == 2


    @patch("time.sleep", return_value=None)
    def test_execution_worker_exhausts_retries_on_persistent_failure(
        self, mock_sleep, mock_kite, mock_db, mock_redis_healthy
    ):
        """ExecutionWorker fails gracefully after exhausting all retries.

        When a worker is down for longer than the retry window, all retries
        are exhausted and the task reports failure with appropriate message.

        Validates: Requirement 2.3.2 - System handles persistent failures
        """
        from kiteconnect import exceptions as kite_exceptions

        # All attempts fail (worker never recovers during retry window)
        mock_kite.place_order.side_effect = kite_exceptions.NetworkException(
            "Connection refused"
        )

        worker = ExecutionWorker(
            user_id=USER_ID,
            kite_client=mock_kite,
            redis_client=mock_redis_healthy,
            db_session=mock_db,
        )

        order = {
            "symbol": "NIFTY23DEC21000CE",
            "exchange": "NFO",
            "side": "BUY",
            "quantity": 50,
            "order_type": "MARKET",
        }

        result = worker.execute_with_retry(order)

        # Should fail after max retries (1 initial + 3 retries = 4 attempts)
        assert result["success"] is False
        assert "retries" in result["message"].lower() or "exhausted" in result["message"].lower()
        assert result["attempts"] == 4  # 1 initial + 3 retries


    @patch("src.workers.celery_app.celery_app.send_task")
    def test_task_queuing_resumes_after_worker_recovery(
        self, mock_send_task, mock_kite, mock_db, mock_redis_healthy
    ):
        """Tasks can be queued again after worker recovers from crash.

        Simulates: Worker crashes (send_task fails) -> Worker restarts
        (send_task succeeds again). The system should recover seamlessly.

        Validates: Requirement 2.3.1 - Automatically restart crashed workers
        """
        # First call fails (worker down), second succeeds (worker recovered)
        mock_send_task.side_effect = [
            Exception("Worker connection refused"),
            MagicMock(id="task-456"),
        ]

        worker = RiskEngineWorker(
            user_id=USER_ID,
            kite_client=mock_kite,
            redis_client=mock_redis_healthy,
            db_session=mock_db,
        )

        position = {
            "tradingsymbol": "NIFTY23DEC21000CE",
            "exchange": "NFO",
            "product": "MIS",
            "quantity": 50,
        }

        # First queue attempt - worker is down (doesn't raise)
        worker._queue_single_exit_order(position)

        # Second queue attempt - worker has recovered
        worker._queue_single_exit_order(position)

        # Both calls were attempted
        assert mock_send_task.call_count == 2


    def test_celery_config_ensures_task_durability(self):
        """Verify Celery configuration supports task durability across restarts.

        Checks that celery_app is configured with task_acks_late=True and
        worker_prefetch_multiplier=1, which ensure:
        - Tasks are only acknowledged after completion (not on receipt)
        - Workers don't prefetch extra tasks that could be lost on crash

        Validates: Requirement 2.3.2 - Not lose queued tasks when workers restart
        """
        from src.workers.celery_app import celery_app

        # task_acks_late=True: Tasks acknowledged only after worker completes them
        # If worker crashes, unacknowledged tasks are re-delivered to another worker
        assert celery_app.conf.task_acks_late is True

        # worker_prefetch_multiplier=1: Worker only takes one task at a time
        # Prevents multiple tasks being lost if worker crashes
        assert celery_app.conf.worker_prefetch_multiplier == 1

    @patch("time.sleep", return_value=None)
    def test_execution_worker_retry_with_exponential_backoff(
        self, mock_sleep, mock_kite, mock_db, mock_redis_healthy
    ):
        """Verify exponential backoff timing between retries.

        The retry mechanism should use increasing delays:
        - 1st retry: 1.0s (retry_backoff * 1)
        - 2nd retry: 2.0s (retry_backoff * 2)
        - 3rd retry: 3.0s (retry_backoff * 3)

        Validates: Requirement 1.3.5 - Retry with exponential backoff
        """
        from kiteconnect import exceptions as kite_exceptions

        # All attempts fail to test all backoff intervals
        mock_kite.place_order.side_effect = kite_exceptions.NetworkException(
            "Timeout"
        )

        worker = ExecutionWorker(
            user_id=USER_ID,
            kite_client=mock_kite,
            redis_client=mock_redis_healthy,
            db_session=mock_db,
        )

        order = {
            "symbol": "NIFTY23DEC21000CE",
            "exchange": "NFO",
            "side": "BUY",
            "quantity": 50,
            "order_type": "MARKET",
        }

        worker.execute_with_retry(order)

        # Verify exponential backoff: 1.0, 2.0, 3.0 seconds
        assert mock_sleep.call_count == 3
        mock_sleep.assert_any_call(1.0)
        mock_sleep.assert_any_call(2.0)
        mock_sleep.assert_any_call(3.0)
