"""Tests for Dashboard API Endpoints (Tasks 10.1–10.5).

Tests the FastAPI router at /api/v1/* using TestClient
with mocked dependencies (database, Redis).

Requirements covered:
- 1.4.5: Cache risk metrics in Redis with timestamp
- 1.7.1: Dashboard showing positions, P&L, Greeks, kill switch status
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


# --- Test Setup ---


def _create_test_app():
    """Create a fresh FastAPI app with the dashboard router for testing."""
    from fastapi import FastAPI
    from src.api.routers.dashboard import router

    app = FastAPI()
    app.include_router(router)
    return app


def _mock_redis_client(risk_data=None, killswitch="false", market_data=None):
    """Create a mock RedisClient with configurable responses.

    Args:
        risk_data: Dict to return from hgetall for user risk key.
        killswitch: Value to return from get for killswitch key.
        market_data: Dict mapping symbol to market data JSON.
    """
    mock = MagicMock()

    # hgetall returns risk data or empty dict
    mock.hgetall.return_value = risk_data or {}

    # get returns killswitch status or market data based on key
    def _get_side_effect(key):
        if "killswitch" in key:
            return killswitch
        if "market:" in key and market_data:
            # Extract symbol from key like "market:RELIANCE:data"
            parts = key.split(":")
            if len(parts) >= 2:
                symbol = parts[1]
                if symbol in market_data:
                    return json.dumps(market_data[symbol])
        return None

    mock.get.side_effect = _get_side_effect
    return mock


def _make_fake_trade(
    id=1,
    user_id=1,
    symbol="RELIANCE",
    exchange="NSE",
    qty=10,
    side="BUY",
    entry_price=2500.0,
    exit_price=None,
    pnl=0.0,
    margin_used=25000.0,
    status="OPEN",
    timestamp=None,
    exit_timestamp=None,
):
    """Create a mock Trade object."""
    trade = MagicMock()
    trade.id = id
    trade.user_id = user_id
    trade.symbol = symbol
    trade.exchange = exchange
    trade.qty = qty
    trade.side = side
    trade.entry_price = entry_price
    trade.exit_price = exit_price
    trade.pnl = pnl
    trade.margin_used = margin_used
    trade.status = status
    trade.timestamp = timestamp or datetime(2024, 1, 15, 10, 30, 0)
    trade.exit_timestamp = exit_timestamp
    return trade


def _make_fake_position(
    id=1,
    user_id=1,
    net_delta=0.5,
    net_gamma=0.02,
    net_vega=150.0,
    margin_used=50000.0,
    unrealized_pnl=-1200.0,
    updated_at=None,
):
    """Create a mock Position object."""
    pos = MagicMock()
    pos.id = id
    pos.user_id = user_id
    pos.net_delta = net_delta
    pos.net_gamma = net_gamma
    pos.net_vega = net_vega
    pos.margin_used = margin_used
    pos.unrealized_pnl = unrealized_pnl
    pos.updated_at = updated_at or datetime.now()
    return pos


# --------------------------------------------------------------------------
# 10.1: GET /api/v1/dashboard Tests
# --------------------------------------------------------------------------


class TestDashboardEndpoint:
    """Test GET /api/v1/dashboard."""

    def test_dashboard_with_risk_data_and_positions(self):
        """10.1: Returns composite dashboard with risk metrics and positions."""
        app = _create_test_app()

        from src.api.dependencies import get_db, get_redis, get_current_user

        # Mock DB with open trades
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [
            _make_fake_trade(symbol="RELIANCE", qty=10, entry_price=2500.0),
            _make_fake_trade(id=2, symbol="TCS", qty=5, entry_price=3800.0, side="SELL"),
        ]

        # Mock Redis with risk data
        risk_data = {
            "daily_loss_pct": "2.5",
            "capital_used_pct": "45.0",
            "margin_used_pct": "60.0",
            "killswitch_active": "false",
            "net_delta": "0.75",
            "net_gamma": "0.03",
            "net_vega": "200.0",
            "pnl": "-5000.0",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        mock_redis = _mock_redis_client(risk_data=risk_data, killswitch="false")

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_current_user] = lambda: 1

        client = TestClient(app)
        response = client.get("/api/v1/dashboard")

        assert response.status_code == 200
        data = response.json()

        # Verify structure
        assert "risk_metrics" in data
        assert "positions" in data
        assert "killswitch_active" in data

        # Verify risk metrics
        assert data["risk_metrics"]["daily_loss_pct"] == 2.5
        assert data["risk_metrics"]["net_delta"] == 0.75
        assert data["risk_metrics"]["unrealized_pnl"] == -5000.0

        # Verify positions list
        assert len(data["positions"]) == 2
        assert data["positions"][0]["symbol"] == "RELIANCE"
        assert data["positions"][1]["symbol"] == "TCS"

        # Kill switch
        assert data["killswitch_active"] is False

        app.dependency_overrides.clear()

    def test_dashboard_empty_risk_returns_defaults(self):
        """10.1: Empty Redis returns default zeroed risk metrics."""
        app = _create_test_app()

        from src.api.dependencies import get_db, get_redis, get_current_user

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []

        mock_redis = _mock_redis_client(risk_data={}, killswitch="false")

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_current_user] = lambda: 1

        client = TestClient(app)
        response = client.get("/api/v1/dashboard")

        assert response.status_code == 200
        data = response.json()
        assert data["risk_metrics"]["daily_loss_pct"] == 0.0
        assert data["risk_metrics"]["net_delta"] == 0.0
        assert data["positions"] == []

        app.dependency_overrides.clear()

    def test_dashboard_killswitch_active(self):
        """10.1: Kill switch status is correctly reflected."""
        app = _create_test_app()

        from src.api.dependencies import get_db, get_redis, get_current_user

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []

        mock_redis = _mock_redis_client(risk_data={}, killswitch="true")

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_current_user] = lambda: 1

        client = TestClient(app)
        response = client.get("/api/v1/dashboard")

        assert response.status_code == 200
        assert response.json()["killswitch_active"] is True

        app.dependency_overrides.clear()


# --------------------------------------------------------------------------
# 10.2: GET /api/v1/positions Tests
# --------------------------------------------------------------------------


class TestPositionsEndpoint:
    """Test GET /api/v1/positions."""

    def test_positions_with_open_trades(self):
        """10.2: Returns open positions with P&L computed from entry price."""
        app = _create_test_app()

        from src.api.dependencies import get_db, get_redis, get_current_user

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [
            _make_fake_trade(symbol="RELIANCE", qty=10, entry_price=2500.0, pnl=500.0),
        ]

        # No market data in Redis — will use trade's pnl
        mock_redis = _mock_redis_client()

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_current_user] = lambda: 1

        client = TestClient(app)
        response = client.get("/api/v1/positions")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["symbol"] == "RELIANCE"
        assert data[0]["quantity"] == 10
        assert data[0]["entry_price"] == 2500.0
        assert data[0]["current_price"] is None
        assert data[0]["pnl"] == 500.0
        assert data[0]["margin_used"] == 25000.0

        app.dependency_overrides.clear()

    def test_positions_with_market_data_enrichment(self):
        """10.2: Current price from Redis is used to compute live P&L."""
        app = _create_test_app()

        from src.api.dependencies import get_db, get_redis, get_current_user

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [
            _make_fake_trade(symbol="RELIANCE", qty=10, entry_price=2500.0, side="BUY"),
        ]

        # Market data in Redis: current price is 2550
        market_data = {"RELIANCE": {"spot": 2550.0, "timestamp": "2024-01-15T10:30:00"}}
        mock_redis = _mock_redis_client(market_data=market_data)

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_current_user] = lambda: 1

        client = TestClient(app)
        response = client.get("/api/v1/positions")

        assert response.status_code == 200
        data = response.json()
        assert data[0]["current_price"] == 2550.0
        # P&L for BUY: (2550 - 2500) * 10 = 500
        assert data[0]["pnl"] == 500.0

        app.dependency_overrides.clear()

    def test_positions_sell_side_pnl_computation(self):
        """10.2: SELL side P&L is computed correctly (entry - current) * qty."""
        app = _create_test_app()

        from src.api.dependencies import get_db, get_redis, get_current_user

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [
            _make_fake_trade(symbol="TCS", qty=5, entry_price=3800.0, side="SELL"),
        ]

        market_data = {"TCS": {"spot": 3750.0, "timestamp": "2024-01-15T10:30:00"}}
        mock_redis = _mock_redis_client(market_data=market_data)

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_current_user] = lambda: 1

        client = TestClient(app)
        response = client.get("/api/v1/positions")

        assert response.status_code == 200
        data = response.json()
        # P&L for SELL: (3800 - 3750) * 5 = 250
        assert data[0]["pnl"] == 250.0

        app.dependency_overrides.clear()

    def test_positions_empty(self):
        """10.2: No open trades returns empty list."""
        app = _create_test_app()

        from src.api.dependencies import get_db, get_redis, get_current_user

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []

        mock_redis = _mock_redis_client()

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_current_user] = lambda: 1

        client = TestClient(app)
        response = client.get("/api/v1/positions")

        assert response.status_code == 200
        assert response.json() == []

        app.dependency_overrides.clear()


# --------------------------------------------------------------------------
# 10.3: GET /api/v1/risk Tests
# --------------------------------------------------------------------------


class TestRiskEndpoint:
    """Test GET /api/v1/risk."""

    def test_risk_fresh_redis_data(self):
        """10.3: Fresh Redis data is returned directly."""
        app = _create_test_app()

        from src.api.dependencies import get_db, get_redis, get_current_user

        mock_db = MagicMock()

        risk_data = {
            "daily_loss_pct": "3.0",
            "capital_used_pct": "55.0",
            "margin_used_pct": "70.0",
            "killswitch_active": "false",
            "net_delta": "1.2",
            "net_gamma": "0.05",
            "net_vega": "300.0",
            "pnl": "-8000.0",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        mock_redis = _mock_redis_client(risk_data=risk_data)

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_current_user] = lambda: 1

        client = TestClient(app)
        response = client.get("/api/v1/risk")

        assert response.status_code == 200
        data = response.json()
        assert data["daily_loss_pct"] == 3.0
        assert data["net_delta"] == 1.2
        assert data["unrealized_pnl"] == -8000.0
        assert data["killswitch_active"] is False

        app.dependency_overrides.clear()

    def test_risk_stale_redis_falls_back_to_db(self):
        """10.3: Stale Redis data (>60s) triggers DB fallback."""
        app = _create_test_app()

        from src.api.dependencies import get_db, get_redis, get_current_user

        # Stale data — updated_at is 2 minutes ago
        stale_time = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
        risk_data = {
            "daily_loss_pct": "1.0",
            "net_delta": "0.5",
            "pnl": "-1000.0",
            "updated_at": stale_time,
        }
        mock_redis = _mock_redis_client(risk_data=risk_data, killswitch="true")

        # DB has position data
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = _make_fake_position(
            net_delta=0.8, net_gamma=0.04, net_vega=250.0, unrealized_pnl=-3000.0
        )

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_current_user] = lambda: 1

        client = TestClient(app)
        response = client.get("/api/v1/risk")

        assert response.status_code == 200
        data = response.json()
        # Should reflect DB position data, not stale Redis
        assert data["net_delta"] == 0.8
        assert data["net_gamma"] == 0.04
        assert data["net_vega"] == 250.0
        assert data["unrealized_pnl"] == -3000.0
        assert data["killswitch_active"] is True

        app.dependency_overrides.clear()

    def test_risk_empty_redis_falls_back_to_db(self):
        """10.3: Missing Redis data triggers DB fallback."""
        app = _create_test_app()

        from src.api.dependencies import get_db, get_redis, get_current_user

        mock_redis = _mock_redis_client(risk_data={}, killswitch="false")

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = _make_fake_position(
            net_delta=0.3, unrealized_pnl=-500.0
        )

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_current_user] = lambda: 1

        client = TestClient(app)
        response = client.get("/api/v1/risk")

        assert response.status_code == 200
        data = response.json()
        assert data["net_delta"] == 0.3
        assert data["unrealized_pnl"] == -500.0

        app.dependency_overrides.clear()

    def test_risk_no_data_anywhere_returns_defaults(self):
        """10.3: No Redis or DB data returns zeroed defaults."""
        app = _create_test_app()

        from src.api.dependencies import get_db, get_redis, get_current_user

        mock_redis = _mock_redis_client(risk_data={}, killswitch="false")

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None  # No position in DB

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_current_user] = lambda: 1

        client = TestClient(app)
        response = client.get("/api/v1/risk")

        assert response.status_code == 200
        data = response.json()
        assert data["daily_loss_pct"] == 0.0
        assert data["net_delta"] == 0.0
        assert data["unrealized_pnl"] == 0.0
        assert data["killswitch_active"] is False

        app.dependency_overrides.clear()


# --------------------------------------------------------------------------
# 10.4: GET /api/v1/trades/history Tests
# --------------------------------------------------------------------------


class TestTradeHistoryEndpoint:
    """Test GET /api/v1/trades/history."""

    def test_trade_history_returns_trades(self):
        """10.4: Returns paginated trade history sorted by timestamp desc."""
        app = _create_test_app()

        from src.api.dependencies import get_db, get_redis, get_current_user

        trades = [
            _make_fake_trade(
                id=3,
                symbol="NIFTY24JUNFUT",
                exchange="NFO",
                qty=50,
                side="BUY",
                entry_price=22500.0,
                exit_price=22600.0,
                pnl=5000.0,
                status="CLOSED",
                timestamp=datetime(2024, 1, 15, 14, 0, 0),
                exit_timestamp=datetime(2024, 1, 15, 15, 0, 0),
            ),
            _make_fake_trade(
                id=2,
                symbol="RELIANCE",
                exchange="NSE",
                qty=10,
                side="BUY",
                entry_price=2500.0,
                pnl=0.0,
                status="OPEN",
                timestamp=datetime(2024, 1, 15, 10, 30, 0),
            ),
        ]

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = trades

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_current_user] = lambda: 1

        client = TestClient(app)
        response = client.get("/api/v1/trades/history")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["id"] == 3
        assert data[0]["symbol"] == "NIFTY24JUNFUT"
        assert data[0]["exchange"] == "NFO"
        assert data[0]["exit_price"] == 22600.0
        assert data[0]["pnl"] == 5000.0
        assert data[0]["status"] == "CLOSED"

        assert data[1]["id"] == 2
        assert data[1]["symbol"] == "RELIANCE"
        assert data[1]["exit_price"] is None
        assert data[1]["status"] == "OPEN"

        app.dependency_overrides.clear()

    def test_trade_history_pagination(self):
        """10.4: Pagination parameters are applied correctly."""
        app = _create_test_app()

        from src.api.dependencies import get_db, get_redis, get_current_user

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_current_user] = lambda: 1

        client = TestClient(app)
        response = client.get("/api/v1/trades/history?page=3&page_size=10")

        assert response.status_code == 200

        # Verify offset was called with (3-1)*10 = 20
        mock_query.offset.assert_called_once_with(20)
        mock_query.limit.assert_called_once_with(10)

        app.dependency_overrides.clear()

    def test_trade_history_empty(self):
        """10.4: No trades returns empty list."""
        app = _create_test_app()

        from src.api.dependencies import get_db, get_redis, get_current_user

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_current_user] = lambda: 1

        client = TestClient(app)
        response = client.get("/api/v1/trades/history")

        assert response.status_code == 200
        assert response.json() == []

        app.dependency_overrides.clear()

    def test_trade_history_invalid_page_returns_422(self):
        """10.4: Page < 1 returns 422 validation error."""
        app = _create_test_app()

        from src.api.dependencies import get_db, get_current_user

        mock_db = MagicMock()
        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_current_user] = lambda: 1

        client = TestClient(app)
        response = client.get("/api/v1/trades/history?page=0")

        assert response.status_code == 422

        app.dependency_overrides.clear()

    def test_trade_history_page_size_exceeds_max_returns_422(self):
        """10.4: page_size > 100 returns 422 validation error."""
        app = _create_test_app()

        from src.api.dependencies import get_db, get_current_user

        mock_db = MagicMock()
        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_current_user] = lambda: 1

        client = TestClient(app)
        response = client.get("/api/v1/trades/history?page_size=150")

        assert response.status_code == 422

        app.dependency_overrides.clear()
