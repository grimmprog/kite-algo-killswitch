"""Tests for Admin Seed API (src/admin/api/seed.py).

Tests cover:
- POST /admin/api/seed: Seeding test data into Redis
- POST /admin/api/seed/clear: Clearing seeded data from Redis
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.admin.api.seed import router
from src.admin.dependencies import get_redis


# ============================================================
# Fixtures
# ============================================================


def _create_test_app():
    """Create a fresh FastAPI app with the seed router for testing."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    return MagicMock()


@pytest.fixture
def client(mock_redis):
    """Create a test client with mocked Redis."""
    app = _create_test_app()
    app.dependency_overrides[get_redis] = lambda: mock_redis
    yield TestClient(app)
    app.dependency_overrides.clear()


# ============================================================
# Tests for POST /admin/api/seed
# ============================================================


class TestSeedTestData:
    """Tests for the seed endpoint."""

    def test_seed_returns_success(self, client, mock_redis):
        """POST /admin/api/seed returns success with seeded data summary."""
        response = client.post("/api/seed")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "seeded" in data
        assert "market_data" in data["seeded"]
        assert "risk_metrics" in data["seeded"]

    def test_seed_sets_market_data_in_redis(self, client, mock_redis):
        """Seed sets market data for NIFTY and BANKNIFTY in Redis."""
        response = client.post("/api/seed")

        assert response.status_code == 200
        # setex should be called for NIFTY and BANKNIFTY market data
        setex_calls = mock_redis.setex.call_args_list
        assert len(setex_calls) >= 2

    def test_seed_sets_risk_metrics_for_test_users(self, client, mock_redis):
        """Seed sets risk metrics hashes for users 1, 2, 3."""
        response = client.post("/api/seed")

        assert response.status_code == 200
        # hset should be called for each test user
        hset_calls = mock_redis.hset.call_args_list
        assert len(hset_calls) == 3

    def test_seed_creates_market_ticks(self, client, mock_redis):
        """Seed creates market ticks for VWAP calculation."""
        response = client.post("/api/seed")

        assert response.status_code == 200
        # lpush should be called for tick data (20 ticks per symbol = 40)
        # plus 2 for recent orders
        lpush_calls = mock_redis.lpush.call_args_list
        assert len(lpush_calls) >= 40

    def test_seed_creates_recent_orders(self, client, mock_redis):
        """Seed creates recent orders for user 1."""
        response = client.post("/api/seed")

        assert response.status_code == 200
        data = response.json()
        assert "recent_orders_user_1" in data["seeded"]
        assert len(data["seeded"]["recent_orders_user_1"]) == 2

    def test_seed_sets_ttl_on_ticks(self, client, mock_redis):
        """Seed sets TTL on market tick keys."""
        response = client.post("/api/seed")

        assert response.status_code == 200
        expire_calls = mock_redis.expire.call_args_list
        assert len(expire_calls) >= 2


# ============================================================
# Tests for POST /admin/api/seed/clear
# ============================================================


class TestClearTestData:
    """Tests for the clear endpoint."""

    def test_clear_returns_success(self, client, mock_redis):
        """POST /admin/api/seed/clear returns success with cleared keys."""
        response = client.post("/api/seed/clear")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "cleared" in data
        assert len(data["cleared"]) > 0

    def test_clear_deletes_market_data(self, client, mock_redis):
        """Clear deletes market data for all instruments."""
        response = client.post("/api/seed/clear")

        assert response.status_code == 200
        delete_calls = mock_redis.delete.call_args_list
        deleted_keys = [call[0][0] for call in delete_calls]
        # Should delete market data and ticks for NIFTY and BANKNIFTY
        assert any("NIFTY" in k for k in deleted_keys)
        assert any("BANKNIFTY" in k for k in deleted_keys)

    def test_clear_deletes_user_risk_and_killswitch(self, client, mock_redis):
        """Clear deletes risk, killswitch, and recent_orders for users 1-3."""
        response = client.post("/api/seed/clear")

        assert response.status_code == 200
        delete_calls = mock_redis.delete.call_args_list
        # Should have multiple delete calls for user data
        assert len(delete_calls) >= 10  # 2 instruments * 2 + 3 users * 3
