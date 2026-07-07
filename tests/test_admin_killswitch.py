"""Tests for Admin Kill Switch API (src/admin/api/killswitch.py).

Tests cover:
- POST /admin/api/killswitch/{user_id}/activate
- POST /admin/api/killswitch/{user_id}/deactivate
- GET /admin/api/killswitch/{user_id}/status
- Error handling for Redis failures
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.admin.api.killswitch import router
from src.admin.dependencies import get_redis


# ============================================================
# Fixtures
# ============================================================


def _create_test_app():
    """Create a fresh FastAPI app with the killswitch router."""
    app = FastAPI()
    app.include_router(router)
    return app


# ============================================================
# Tests for POST /admin/api/killswitch/{user_id}/activate
# ============================================================


class TestActivateKillswitch:
    """Tests for kill switch activation."""

    def test_activate_success(self):
        """Activation sets Redis key and returns active status."""
        app = _create_test_app()
        mock_redis = MagicMock()
        app.dependency_overrides[get_redis] = lambda: mock_redis
        client = TestClient(app)

        response = client.post("/api/killswitch/1/activate")

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == 1
        assert data["status"] == "active"
        assert "activated_at" in data
        mock_redis.set.assert_called_once()
        app.dependency_overrides.clear()

    def test_activate_redis_error_returns_500(self):
        """Returns 500 when Redis set fails."""
        app = _create_test_app()
        mock_redis = MagicMock()
        mock_redis.set.side_effect = Exception("Redis timeout")
        app.dependency_overrides[get_redis] = lambda: mock_redis
        client = TestClient(app)

        response = client.post("/api/killswitch/1/activate")

        assert response.status_code == 500
        assert "Failed to activate" in response.json()["detail"]
        app.dependency_overrides.clear()


# ============================================================
# Tests for POST /admin/api/killswitch/{user_id}/deactivate
# ============================================================


class TestDeactivateKillswitch:
    """Tests for kill switch deactivation."""

    def test_deactivate_success(self):
        """Deactivation deletes Redis key and returns inactive status."""
        app = _create_test_app()
        mock_redis = MagicMock()
        app.dependency_overrides[get_redis] = lambda: mock_redis
        client = TestClient(app)

        response = client.post("/api/killswitch/1/deactivate")

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == 1
        assert data["status"] == "inactive"
        mock_redis.delete.assert_called_once()
        app.dependency_overrides.clear()

    def test_deactivate_redis_error_returns_500(self):
        """Returns 500 when Redis delete fails."""
        app = _create_test_app()
        mock_redis = MagicMock()
        mock_redis.delete.side_effect = Exception("Redis timeout")
        app.dependency_overrides[get_redis] = lambda: mock_redis
        client = TestClient(app)

        response = client.post("/api/killswitch/1/deactivate")

        assert response.status_code == 500
        assert "Failed to deactivate" in response.json()["detail"]
        app.dependency_overrides.clear()


# ============================================================
# Tests for GET /admin/api/killswitch/{user_id}/status
# ============================================================


class TestGetKillswitchStatus:
    """Tests for kill switch status check."""

    def test_status_active(self):
        """Returns active when Redis key is 'true'."""
        app = _create_test_app()
        mock_redis = MagicMock()
        mock_redis.get.return_value = "true"
        app.dependency_overrides[get_redis] = lambda: mock_redis
        client = TestClient(app)

        response = client.get("/api/killswitch/1/status")

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == 1
        assert data["status"] == "active"
        app.dependency_overrides.clear()

    def test_status_inactive_when_none(self):
        """Returns inactive when Redis key does not exist."""
        app = _create_test_app()
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        app.dependency_overrides[get_redis] = lambda: mock_redis
        client = TestClient(app)

        response = client.get("/api/killswitch/1/status")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "inactive"
        app.dependency_overrides.clear()

    def test_status_inactive_when_false(self):
        """Returns inactive when Redis key is 'false'."""
        app = _create_test_app()
        mock_redis = MagicMock()
        mock_redis.get.return_value = "false"
        app.dependency_overrides[get_redis] = lambda: mock_redis
        client = TestClient(app)

        response = client.get("/api/killswitch/1/status")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "inactive"
        app.dependency_overrides.clear()

    def test_status_redis_error_returns_500(self):
        """Returns 500 when Redis get fails."""
        app = _create_test_app()
        mock_redis = MagicMock()
        mock_redis.get.side_effect = Exception("Redis down")
        app.dependency_overrides[get_redis] = lambda: mock_redis
        client = TestClient(app)

        response = client.get("/api/killswitch/1/status")

        assert response.status_code == 500
        assert "Failed to read" in response.json()["detail"]
        app.dependency_overrides.clear()
