"""Tests for Admin Risk API (src/admin/api/risk.py).

Tests cover:
- GET /admin/api/risk/{user_id}: successful retrieval
- No risk data returns 404
- User not found returns 404
- Redis error returns 500
- Database error returns 500
- Margin percentage calculation
- Threshold warning calculation
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.admin.api.risk import router
from src.admin.dependencies import get_db, get_redis


# ============================================================
# Fixtures
# ============================================================


def _create_test_app():
    """Create a fresh FastAPI app with the risk router."""
    app = FastAPI()
    app.include_router(router)
    return app


def _mock_user(capital=100000.0, daily_loss_limit_percent=2.0):
    """Create a mock user with specified capital and loss limit."""
    user = MagicMock()
    user.id = 1
    user.capital = capital
    user.daily_loss_limit_percent = daily_loss_limit_percent
    return user


# ============================================================
# Tests for GET /admin/api/risk/{user_id}
# ============================================================


class TestGetRisk:
    """Tests for the risk metrics endpoint."""

    def test_returns_risk_metrics_success(self):
        """Returns risk metrics with margin_percent and threshold_warning."""
        app = _create_test_app()
        mock_redis = MagicMock()
        mock_redis.hgetall.return_value = {
            "pnl": "-500.0",
            "net_delta": "0.5",
            "net_gamma": "0.02",
            "net_vega": "50.0",
            "margin_used": "30000.0",
            "updated_at": "2024-01-15T10:00:00",
        }
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = _mock_user(
            capital=100000.0, daily_loss_limit_percent=2.0
        )

        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_db] = lambda: mock_db
        client = TestClient(app)

        response = client.get("/api/risk/1")

        assert response.status_code == 200
        data = response.json()
        assert data["pnl"] == -500.0
        assert data["net_delta"] == 0.5
        assert data["net_gamma"] == 0.02
        assert data["net_vega"] == 50.0
        assert data["margin_used"] == 30000.0
        assert data["margin_percent"] == 30.0  # 30000/100000 * 100
        assert data["updated_at"] == "2024-01-15T10:00:00"
        app.dependency_overrides.clear()

    def test_threshold_warning_true_when_loss_exceeds_half_limit(self):
        """threshold_warning is True when loss > 0.5 * daily_loss_limit_percent."""
        app = _create_test_app()
        mock_redis = MagicMock()
        # PnL = -1500, capital = 100000, so loss % = 1.5%
        # daily_loss_limit = 2.0%, threshold = 0.5 * 2.0 = 1.0%
        # 1.5% > 1.0% → threshold_warning = True
        mock_redis.hgetall.return_value = {
            "pnl": "-1500.0",
            "net_delta": "0",
            "net_gamma": "0",
            "net_vega": "0",
            "margin_used": "0",
            "updated_at": "2024-01-15T10:00:00",
        }
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = _mock_user(
            capital=100000.0, daily_loss_limit_percent=2.0
        )

        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_db] = lambda: mock_db
        client = TestClient(app)

        response = client.get("/api/risk/1")

        assert response.status_code == 200
        assert response.json()["threshold_warning"] is True
        app.dependency_overrides.clear()

    def test_threshold_warning_false_when_loss_below_half_limit(self):
        """threshold_warning is False when loss < 0.5 * daily_loss_limit_percent."""
        app = _create_test_app()
        mock_redis = MagicMock()
        # PnL = -200, capital = 100000, so loss % = 0.2%
        # daily_loss_limit = 2.0%, threshold = 1.0%
        # 0.2% < 1.0% → threshold_warning = False
        mock_redis.hgetall.return_value = {
            "pnl": "-200.0",
            "net_delta": "0",
            "net_gamma": "0",
            "net_vega": "0",
            "margin_used": "0",
            "updated_at": "2024-01-15T10:00:00",
        }
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = _mock_user(
            capital=100000.0, daily_loss_limit_percent=2.0
        )

        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_db] = lambda: mock_db
        client = TestClient(app)

        response = client.get("/api/risk/1")

        assert response.status_code == 200
        assert response.json()["threshold_warning"] is False
        app.dependency_overrides.clear()

    def test_returns_404_when_no_risk_data(self):
        """Returns 404 when Redis has no risk data for the user."""
        app = _create_test_app()
        mock_redis = MagicMock()
        mock_redis.hgetall.return_value = {}
        mock_db = MagicMock()

        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_db] = lambda: mock_db
        client = TestClient(app)

        response = client.get("/api/risk/1")

        assert response.status_code == 404
        assert "No risk data" in response.json()["detail"]
        app.dependency_overrides.clear()

    def test_returns_404_when_user_not_found(self):
        """Returns 404 when user does not exist in database."""
        app = _create_test_app()
        mock_redis = MagicMock()
        mock_redis.hgetall.return_value = {
            "pnl": "0",
            "net_delta": "0",
            "net_gamma": "0",
            "net_vega": "0",
            "margin_used": "0",
            "updated_at": "2024-01-15T10:00:00",
        }
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_db] = lambda: mock_db
        client = TestClient(app)

        response = client.get("/api/risk/999")

        assert response.status_code == 404
        assert "User not found" in response.json()["detail"]
        app.dependency_overrides.clear()

    def test_returns_500_on_redis_error(self):
        """Returns 500 when Redis throws an exception."""
        app = _create_test_app()
        mock_redis = MagicMock()
        mock_redis.hgetall.side_effect = Exception("Redis connection lost")
        mock_db = MagicMock()

        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_db] = lambda: mock_db
        client = TestClient(app)

        response = client.get("/api/risk/1")

        assert response.status_code == 500
        app.dependency_overrides.clear()

    def test_returns_500_on_db_error(self):
        """Returns 500 when database throws an exception."""
        app = _create_test_app()
        mock_redis = MagicMock()
        mock_redis.hgetall.return_value = {
            "pnl": "0",
            "net_delta": "0",
            "net_gamma": "0",
            "net_vega": "0",
            "margin_used": "0",
            "updated_at": "2024-01-15T10:00:00",
        }
        mock_db = MagicMock()
        mock_db.query.side_effect = Exception("Database timeout")

        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_db] = lambda: mock_db
        client = TestClient(app)

        response = client.get("/api/risk/1")

        assert response.status_code == 500
        app.dependency_overrides.clear()

    def test_margin_percent_zero_when_capital_zero(self):
        """margin_percent is 0 when user capital is 0 (avoids division by zero)."""
        app = _create_test_app()
        mock_redis = MagicMock()
        mock_redis.hgetall.return_value = {
            "pnl": "0",
            "net_delta": "0",
            "net_gamma": "0",
            "net_vega": "0",
            "margin_used": "5000.0",
            "updated_at": "2024-01-15T10:00:00",
        }
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = _mock_user(
            capital=0.0, daily_loss_limit_percent=2.0
        )

        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_db] = lambda: mock_db
        client = TestClient(app)

        response = client.get("/api/risk/1")

        # capital=0 → margin_percent=0 (no division by zero)
        assert response.status_code == 200
        assert response.json()["margin_percent"] == 0.0
        app.dependency_overrides.clear()
