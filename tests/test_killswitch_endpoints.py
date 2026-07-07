"""Tests for Kill Switch API Endpoints (Tasks 12.1–12.4).

Tests the FastAPI router at /api/v1/killswitch/* using TestClient
with mocked dependencies (Redis, database).

Requirements covered:
- 1.5.1: Atomically set kill switch flag in Redis
- 1.5.6: Log kill switch activations with timestamp and reason
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routers.killswitch import router as killswitch_router
from src.api.dependencies import get_current_user, get_redis, get_db


# --- Test Setup ---


def _create_test_app():
    """Create a fresh FastAPI app with the killswitch router for testing."""
    app = FastAPI()
    app.include_router(killswitch_router)
    return app


# --- 12.1: POST /api/v1/killswitch/activate Tests ---


class TestActivateKillswitch:
    """Test POST /api/v1/killswitch/activate."""

    def test_successful_activation(self):
        """12.1.2-12.1.4: Kill switch is activated and logged."""
        app = _create_test_app()

        mock_redis = MagicMock()
        mock_db = MagicMock()

        app.dependency_overrides[get_current_user] = lambda: 1
        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_db] = lambda: mock_db

        client = TestClient(app)
        response = client.post("/api/v1/killswitch/activate")

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Kill switch activated"
        assert data["active"] is True

        # Verify Redis was called to set the flag
        mock_redis.set.assert_called_once_with("user:1:killswitch", "true")

        # Verify a log was created
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

        # Verify the log object has correct attributes
        log_obj = mock_db.add.call_args[0][0]
        assert log_obj.user_id == 1
        assert log_obj.trigger_reason == "Manual activation"

        app.dependency_overrides.clear()

    def test_activation_requires_auth(self):
        """12.1.1: Activation requires authentication."""
        app = _create_test_app()

        mock_redis = MagicMock()
        mock_db = MagicMock()
        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_db] = lambda: mock_db

        client = TestClient(app)
        response = client.post("/api/v1/killswitch/activate")

        assert response.status_code in (401, 403)

        app.dependency_overrides.clear()


# --- 12.2: POST /api/v1/killswitch/deactivate Tests ---


class TestDeactivateKillswitch:
    """Test POST /api/v1/killswitch/deactivate."""

    def test_successful_deactivation(self):
        """12.2.2-12.2.3: Kill switch is deactivated (Redis key deleted)."""
        app = _create_test_app()

        mock_redis = MagicMock()

        app.dependency_overrides[get_current_user] = lambda: 1
        app.dependency_overrides[get_redis] = lambda: mock_redis

        client = TestClient(app)
        response = client.post("/api/v1/killswitch/deactivate")

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Kill switch deactivated"
        assert data["active"] is False

        # Verify Redis delete was called
        mock_redis.delete.assert_called_once_with("user:1:killswitch")

        app.dependency_overrides.clear()

    def test_deactivation_requires_auth(self):
        """12.2.1: Deactivation requires authentication."""
        app = _create_test_app()

        mock_redis = MagicMock()
        app.dependency_overrides[get_redis] = lambda: mock_redis

        client = TestClient(app)
        response = client.post("/api/v1/killswitch/deactivate")

        assert response.status_code in (401, 403)

        app.dependency_overrides.clear()


# --- 12.3: GET /api/v1/killswitch/status Tests ---


class TestKillswitchStatus:
    """Test GET /api/v1/killswitch/status."""

    def test_status_active(self):
        """12.3.1-12.3.2: Returns active=True when flag is set."""
        app = _create_test_app()

        mock_redis = MagicMock()
        mock_redis.get.return_value = "true"

        app.dependency_overrides[get_current_user] = lambda: 1
        app.dependency_overrides[get_redis] = lambda: mock_redis

        client = TestClient(app)
        response = client.get("/api/v1/killswitch/status")

        assert response.status_code == 200
        data = response.json()
        assert data["active"] is True
        assert data["user_id"] == 1

        app.dependency_overrides.clear()

    def test_status_inactive_when_none(self):
        """12.3.1: Returns active=False when key doesn't exist."""
        app = _create_test_app()

        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        app.dependency_overrides[get_current_user] = lambda: 1
        app.dependency_overrides[get_redis] = lambda: mock_redis

        client = TestClient(app)
        response = client.get("/api/v1/killswitch/status")

        assert response.status_code == 200
        data = response.json()
        assert data["active"] is False

        app.dependency_overrides.clear()

    def test_status_inactive_when_false(self):
        """12.3.1: Returns active=False when flag is 'false'."""
        app = _create_test_app()

        mock_redis = MagicMock()
        mock_redis.get.return_value = "false"

        app.dependency_overrides[get_current_user] = lambda: 1
        app.dependency_overrides[get_redis] = lambda: mock_redis

        client = TestClient(app)
        response = client.get("/api/v1/killswitch/status")

        assert response.status_code == 200
        data = response.json()
        assert data["active"] is False

        app.dependency_overrides.clear()

    def test_status_requires_auth(self):
        """12.3: Status check requires authentication."""
        app = _create_test_app()

        mock_redis = MagicMock()
        app.dependency_overrides[get_redis] = lambda: mock_redis

        client = TestClient(app)
        response = client.get("/api/v1/killswitch/status")

        assert response.status_code in (401, 403)

        app.dependency_overrides.clear()


# --- 12.4: GET /api/v1/killswitch/logs Tests ---


class TestKillswitchLogs:
    """Test GET /api/v1/killswitch/logs."""

    def test_logs_returns_history(self):
        """12.4.1-12.4.2: Returns log history sorted by timestamp desc."""
        app = _create_test_app()

        # Create mock log entries
        mock_log_1 = MagicMock()
        mock_log_1.id = 1
        mock_log_1.trigger_reason = "Manual activation"
        mock_log_1.timestamp = datetime(2024, 1, 15, 10, 30, 0)
        mock_log_1.positions_closed_count = 0

        mock_log_2 = MagicMock()
        mock_log_2.id = 2
        mock_log_2.trigger_reason = "Daily loss limit exceeded"
        mock_log_2.timestamp = datetime(2024, 1, 16, 14, 0, 0)
        mock_log_2.positions_closed_count = 5

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [mock_log_2, mock_log_1]

        app.dependency_overrides[get_current_user] = lambda: 1
        app.dependency_overrides[get_db] = lambda: mock_db

        client = TestClient(app)
        response = client.get("/api/v1/killswitch/logs")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["id"] == 2
        assert data[0]["reason"] == "Daily loss limit exceeded"
        assert data[0]["positions_closed"] == 5
        assert data[1]["id"] == 1
        assert data[1]["reason"] == "Manual activation"

        app.dependency_overrides.clear()

    def test_logs_empty(self):
        """12.4.1: Returns empty list when no logs exist."""
        app = _create_test_app()

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []

        app.dependency_overrides[get_current_user] = lambda: 1
        app.dependency_overrides[get_db] = lambda: mock_db

        client = TestClient(app)
        response = client.get("/api/v1/killswitch/logs")

        assert response.status_code == 200
        assert response.json() == []

        app.dependency_overrides.clear()

    def test_logs_requires_auth(self):
        """12.4: Logs endpoint requires authentication."""
        app = _create_test_app()

        mock_db = MagicMock()
        app.dependency_overrides[get_db] = lambda: mock_db

        client = TestClient(app)
        response = client.get("/api/v1/killswitch/logs")

        assert response.status_code in (401, 403)

        app.dependency_overrides.clear()
