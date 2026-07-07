"""Tests for Trading API Endpoints (Tasks 11.1–11.2).

Tests the FastAPI router at /api/v1/trades/* using TestClient
with mocked dependencies (Redis, Celery).

Requirements covered:
- 1.3.3: Validate trades before execution (kill switch check)
- 1.5.2: Block all new trades immediately when kill switch is active
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routers.trading import router as trading_router
from src.api.dependencies import get_current_user, get_redis


# --- Test Setup ---


def _create_test_app():
    """Create a fresh FastAPI app with the trading router for testing."""
    app = FastAPI()
    app.include_router(trading_router)
    return app


def _valid_trade_request():
    """Return a valid trade request payload."""
    return {
        "symbol": "RELIANCE",
        "exchange": "NSE",
        "quantity": 10,
        "side": "BUY",
        "order_type": "MARKET",
    }


# --- 11.1: POST /api/v1/trades/execute Tests ---


class TestExecuteTradeEndpoint:
    """Test POST /api/v1/trades/execute."""

    @patch("src.workers.celery_app.celery_app")
    def test_successful_trade_queued(self, mock_celery):
        """11.1.3-11.1.4: Valid trade is queued and returns task ID."""
        app = _create_test_app()

        # Mock dependencies
        mock_redis = MagicMock()
        mock_redis.get.return_value = None  # Kill switch not active

        mock_task = MagicMock()
        mock_task.id = "test-task-id-123"
        mock_celery.send_task.return_value = mock_task

        app.dependency_overrides[get_current_user] = lambda: 1
        app.dependency_overrides[get_redis] = lambda: mock_redis

        client = TestClient(app)
        response = client.post(
            "/api/v1/trades/execute",
            json=_valid_trade_request(),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "test-task-id-123"
        assert data["message"] == "Order queued for execution"

        # Verify Celery was called with correct data
        mock_celery.send_task.assert_called_once()
        call_args = mock_celery.send_task.call_args
        assert call_args[0][0] == "execute_order"
        # send_task("execute_order", args=[order_data]) -> kwargs["args"][0]
        order_data = call_args[1]["args"][0]
        assert order_data["user_id"] == 1
        assert order_data["symbol"] == "RELIANCE"
        assert order_data["exchange"] == "NSE"
        assert order_data["quantity"] == 10
        assert order_data["side"] == "BUY"

        app.dependency_overrides.clear()

    def test_trade_blocked_when_killswitch_active(self):
        """11.1.2: Trade is blocked when kill switch is active."""
        app = _create_test_app()

        # Mock Redis returning kill switch as active
        mock_redis = MagicMock()
        mock_redis.get.return_value = "true"

        app.dependency_overrides[get_current_user] = lambda: 1
        app.dependency_overrides[get_redis] = lambda: mock_redis

        client = TestClient(app)
        response = client.post(
            "/api/v1/trades/execute",
            json=_valid_trade_request(),
        )

        assert response.status_code == 400
        assert "kill switch is active" in response.json()["detail"]

        app.dependency_overrides.clear()

    def test_trade_blocked_killswitch_case_insensitive(self):
        """11.1.2: Kill switch check is case-insensitive."""
        app = _create_test_app()

        mock_redis = MagicMock()
        mock_redis.get.return_value = "True"  # Capital T

        app.dependency_overrides[get_current_user] = lambda: 1
        app.dependency_overrides[get_redis] = lambda: mock_redis

        client = TestClient(app)
        response = client.post(
            "/api/v1/trades/execute",
            json=_valid_trade_request(),
        )

        assert response.status_code == 400
        assert "kill switch is active" in response.json()["detail"]

        app.dependency_overrides.clear()

    @patch("src.workers.celery_app.celery_app")
    def test_trade_allowed_when_killswitch_false(self, mock_celery):
        """11.1.2: Trade proceeds when kill switch is explicitly false."""
        app = _create_test_app()

        mock_redis = MagicMock()
        mock_redis.get.return_value = "false"

        mock_task = MagicMock()
        mock_task.id = "task-456"
        mock_celery.send_task.return_value = mock_task

        app.dependency_overrides[get_current_user] = lambda: 1
        app.dependency_overrides[get_redis] = lambda: mock_redis

        client = TestClient(app)
        response = client.post(
            "/api/v1/trades/execute",
            json=_valid_trade_request(),
        )

        assert response.status_code == 200

        app.dependency_overrides.clear()

    def test_trade_requires_auth(self):
        """11.1.1: Trade execution requires authentication."""
        app = _create_test_app()

        mock_redis = MagicMock()
        app.dependency_overrides[get_redis] = lambda: mock_redis

        client = TestClient(app)
        # No auth header — get_current_user not overridden
        response = client.post(
            "/api/v1/trades/execute",
            json=_valid_trade_request(),
        )

        assert response.status_code in (401, 403)

        app.dependency_overrides.clear()

    def test_invalid_exchange_returns_422(self):
        """11.1.1: Invalid exchange value returns 422."""
        app = _create_test_app()

        mock_redis = MagicMock()
        app.dependency_overrides[get_current_user] = lambda: 1
        app.dependency_overrides[get_redis] = lambda: mock_redis

        client = TestClient(app)
        payload = _valid_trade_request()
        payload["exchange"] = "INVALID"

        response = client.post("/api/v1/trades/execute", json=payload)

        assert response.status_code == 422

        app.dependency_overrides.clear()

    def test_invalid_side_returns_422(self):
        """11.1.1: Invalid side value returns 422."""
        app = _create_test_app()

        mock_redis = MagicMock()
        app.dependency_overrides[get_current_user] = lambda: 1
        app.dependency_overrides[get_redis] = lambda: mock_redis

        client = TestClient(app)
        payload = _valid_trade_request()
        payload["side"] = "SHORT"

        response = client.post("/api/v1/trades/execute", json=payload)

        assert response.status_code == 422

        app.dependency_overrides.clear()

    def test_zero_quantity_returns_422(self):
        """11.1.1: Zero quantity returns 422."""
        app = _create_test_app()

        mock_redis = MagicMock()
        app.dependency_overrides[get_current_user] = lambda: 1
        app.dependency_overrides[get_redis] = lambda: mock_redis

        client = TestClient(app)
        payload = _valid_trade_request()
        payload["quantity"] = 0

        response = client.post("/api/v1/trades/execute", json=payload)

        assert response.status_code == 422

        app.dependency_overrides.clear()

    @patch("src.workers.celery_app.celery_app")
    def test_limit_order_with_price(self, mock_celery):
        """11.1.3: LIMIT order with price is queued correctly."""
        app = _create_test_app()

        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        mock_task = MagicMock()
        mock_task.id = "limit-task-789"
        mock_celery.send_task.return_value = mock_task

        app.dependency_overrides[get_current_user] = lambda: 1
        app.dependency_overrides[get_redis] = lambda: mock_redis

        client = TestClient(app)
        payload = {
            "symbol": "NIFTY24JUNFUT",
            "exchange": "NFO",
            "quantity": 50,
            "side": "SELL",
            "order_type": "LIMIT",
            "price": 22500.50,
        }

        response = client.post("/api/v1/trades/execute", json=payload)

        assert response.status_code == 200
        assert response.json()["task_id"] == "limit-task-789"

        app.dependency_overrides.clear()


# --- 11.2: GET /api/v1/trades/status/{task_id} Tests ---


class TestTradeStatusEndpoint:
    """Test GET /api/v1/trades/status/{task_id}."""

    @patch("src.workers.celery_app.celery_app")
    def test_pending_task_status(self, mock_celery):
        """11.2.2: Pending task returns status 'pending'."""
        app = _create_test_app()

        mock_result = MagicMock()
        mock_result.ready.return_value = False
        mock_celery.AsyncResult.return_value = mock_result

        app.dependency_overrides[get_current_user] = lambda: 1

        client = TestClient(app)
        response = client.get("/api/v1/trades/status/task-123")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"
        assert data["result"] is None

        app.dependency_overrides.clear()

    @patch("src.workers.celery_app.celery_app")
    def test_completed_task_status(self, mock_celery):
        """11.2.2: Completed task returns status 'completed' with result."""
        app = _create_test_app()

        execution_result = {
            "success": True,
            "order_id": "ORD123",
            "message": "Order executed successfully",
            "filled": True,
            "fill_price": 2500.0,
            "fill_quantity": 10,
        }

        mock_result = MagicMock()
        mock_result.ready.return_value = True
        mock_result.get.return_value = execution_result
        mock_celery.AsyncResult.return_value = mock_result

        app.dependency_overrides[get_current_user] = lambda: 1

        client = TestClient(app)
        response = client.get("/api/v1/trades/status/task-456")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["result"]["success"] is True
        assert data["result"]["order_id"] == "ORD123"

        app.dependency_overrides.clear()

    def test_status_requires_auth(self):
        """11.2.1: Trade status check requires authentication."""
        app = _create_test_app()

        client = TestClient(app)
        response = client.get("/api/v1/trades/status/task-123")

        assert response.status_code in (401, 403)

        app.dependency_overrides.clear()
