"""Tests for Admin Market Data API (src/admin/api/market_data.py).

Tests cover:
- GET /admin/api/market-data: successful retrieval
- Missing data returns null for instruments
- Redis errors handled gracefully
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.admin.api.market_data import router
from src.admin.dependencies import get_redis


# ============================================================
# Fixtures
# ============================================================


def _create_test_app():
    """Create a fresh FastAPI app with the market_data router."""
    app = FastAPI()
    app.include_router(router)
    return app


# ============================================================
# Tests for GET /admin/api/market-data
# ============================================================


class TestGetMarketData:
    """Tests for the market data endpoint."""

    def test_returns_market_data_for_all_instruments(self):
        """Returns parsed market data for NIFTY and BANKNIFTY."""
        app = _create_test_app()
        mock_redis = MagicMock()
        nifty_data = {"spot": 22500.0, "vwap": 22480.0, "timestamp": "2024-01-15T10:00:00"}
        banknifty_data = {"spot": 47000.0, "vwap": 46950.0, "timestamp": "2024-01-15T10:00:00"}

        def mock_get(key):
            if "NIFTY" in key and "BANK" not in key:
                return json.dumps(nifty_data)
            if "BANKNIFTY" in key:
                return json.dumps(banknifty_data)
            return None

        mock_redis.get.side_effect = mock_get
        app.dependency_overrides[get_redis] = lambda: mock_redis
        client = TestClient(app)

        response = client.get("/api/market-data")

        assert response.status_code == 200
        data = response.json()
        assert data["NIFTY"]["spot"] == 22500.0
        assert data["BANKNIFTY"]["spot"] == 47000.0
        app.dependency_overrides.clear()

    def test_returns_null_for_missing_instruments(self):
        """Returns null for instruments with no cached data."""
        app = _create_test_app()
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        app.dependency_overrides[get_redis] = lambda: mock_redis
        client = TestClient(app)

        response = client.get("/api/market-data")

        assert response.status_code == 200
        data = response.json()
        assert data["NIFTY"] is None
        assert data["BANKNIFTY"] is None
        app.dependency_overrides.clear()

    def test_returns_null_on_redis_error(self):
        """Returns null for instruments where Redis raises an exception."""
        app = _create_test_app()
        mock_redis = MagicMock()
        mock_redis.get.side_effect = Exception("Connection refused")
        app.dependency_overrides[get_redis] = lambda: mock_redis
        client = TestClient(app)

        response = client.get("/api/market-data")

        assert response.status_code == 200
        data = response.json()
        assert data["NIFTY"] is None
        assert data["BANKNIFTY"] is None
        app.dependency_overrides.clear()

    def test_partial_data_available(self):
        """Returns data for available instruments, null for others."""
        app = _create_test_app()
        mock_redis = MagicMock()
        nifty_data = {"spot": 22500.0}

        def mock_get(key):
            if "NIFTY" in key and "BANK" not in key:
                return json.dumps(nifty_data)
            return None

        mock_redis.get.side_effect = mock_get
        app.dependency_overrides[get_redis] = lambda: mock_redis
        client = TestClient(app)

        response = client.get("/api/market-data")

        assert response.status_code == 200
        data = response.json()
        assert data["NIFTY"] == {"spot": 22500.0}
        assert data["BANKNIFTY"] is None
        app.dependency_overrides.clear()
