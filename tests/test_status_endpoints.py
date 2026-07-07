"""Tests for System Status and Capital API Endpoints (Task 9.8).

Tests the FastAPI router at /api/v1/status/* using TestClient
with mocked dependencies (Redis).

Requirements covered:
- 13.1-13.4: Capital display, margin data, segment breakdown
- 16.1-16.5: Market hours countdown, session status, worker status
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import time
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


# --- Test Setup ---


def _create_test_app():
    """Create a fresh FastAPI app with the status router for testing."""
    from fastapi import FastAPI
    from src.api.routers.status import router

    app = FastAPI()
    app.include_router(router)
    return app


def _mock_redis_client(
    session_data=None,
    session_ttl=-1,
    heartbeats=None,
    margins_data=None,
):
    """Create a mock RedisClient with configurable responses.

    Args:
        session_data: Value for kite:session:{user_id} key.
        session_ttl: TTL for session key (-2=missing, -1=no expiry, >0=valid).
        heartbeats: Dict mapping worker name to heartbeat timestamp.
        margins_data: Dict with margin data to store as JSON.
    """
    mock = MagicMock()

    def _get_side_effect(key):
        if "kite:session:" in key:
            return session_data
        if "worker:" in key and ":heartbeat" in key:
            if heartbeats:
                # Extract worker name from key like "worker:scanner_worker:heartbeat"
                parts = key.split(":")
                if len(parts) >= 3:
                    worker_name = parts[1]
                    if worker_name in heartbeats:
                        return str(heartbeats[worker_name])
            return None
        if "kite:margins:" in key:
            if margins_data:
                return json.dumps(margins_data)
            return None
        return None

    mock.get.side_effect = _get_side_effect
    mock.ttl.return_value = session_ttl
    return mock


def _override_dependencies(app, redis_mock, user_id=1):
    """Override FastAPI dependencies for testing."""
    from src.api.dependencies import get_redis, get_current_user

    app.dependency_overrides[get_redis] = lambda: redis_mock
    app.dependency_overrides[get_current_user] = lambda: user_id


# --- System Status Tests ---


class TestGetSystemStatus:
    """Tests for GET /api/v1/status/system."""

    def test_returns_system_status_with_all_fields(self):
        """Test that system status returns all expected fields."""
        app = _create_test_app()
        redis_mock = _mock_redis_client(
            session_data="active",
            session_ttl=-1,
            heartbeats={
                "scanner_worker": time.time(),
                "position_monitor_worker": time.time(),
                "killswitch_monitor": time.time(),
            },
        )
        _override_dependencies(app, redis_mock)

        client = TestClient(app)
        response = client.get("/api/v1/status/system")

        assert response.status_code == 200
        data = response.json()
        assert "market_status" in data
        assert "countdown_seconds" in data
        assert "session_status" in data
        assert "workers" in data
        assert data["market_status"] in ["pre_market", "open", "closed"]
        assert data["countdown_seconds"] >= 0
        assert data["session_status"] in ["connected", "disconnected", "expired"]
        assert len(data["workers"]) == 3

    def test_session_connected_when_key_exists(self):
        """Test session shows connected when Redis key has data."""
        app = _create_test_app()
        redis_mock = _mock_redis_client(session_data="active", session_ttl=-1)
        _override_dependencies(app, redis_mock)

        client = TestClient(app)
        response = client.get("/api/v1/status/system")

        assert response.status_code == 200
        assert response.json()["session_status"] == "connected"

    def test_session_disconnected_when_key_missing(self):
        """Test session shows disconnected when Redis key is absent."""
        app = _create_test_app()
        redis_mock = _mock_redis_client(session_data=None, session_ttl=-2)
        _override_dependencies(app, redis_mock)

        client = TestClient(app)
        response = client.get("/api/v1/status/system")

        assert response.status_code == 200
        assert response.json()["session_status"] == "disconnected"

    def test_workers_running_with_recent_heartbeats(self):
        """Test workers show running when heartbeat is within 60 seconds."""
        app = _create_test_app()
        recent = time.time() - 30  # 30 seconds ago
        redis_mock = _mock_redis_client(
            heartbeats={
                "scanner_worker": recent,
                "position_monitor_worker": recent,
                "killswitch_monitor": recent,
            },
        )
        _override_dependencies(app, redis_mock)

        client = TestClient(app)
        response = client.get("/api/v1/status/system")

        assert response.status_code == 200
        workers = response.json()["workers"]
        for worker in workers:
            assert worker["status"] == "running"

    def test_workers_stopped_with_stale_heartbeats(self):
        """Test workers show stopped when heartbeat is older than 60 seconds."""
        app = _create_test_app()
        stale = time.time() - 120  # 120 seconds ago
        redis_mock = _mock_redis_client(
            heartbeats={
                "scanner_worker": stale,
                "position_monitor_worker": stale,
                "killswitch_monitor": stale,
            },
        )
        _override_dependencies(app, redis_mock)

        client = TestClient(app)
        response = client.get("/api/v1/status/system")

        assert response.status_code == 200
        workers = response.json()["workers"]
        for worker in workers:
            assert worker["status"] == "stopped"

    def test_workers_stopped_when_no_heartbeat(self):
        """Test workers show stopped when heartbeat key is missing."""
        app = _create_test_app()
        redis_mock = _mock_redis_client(heartbeats=None)
        _override_dependencies(app, redis_mock)

        client = TestClient(app)
        response = client.get("/api/v1/status/system")

        assert response.status_code == 200
        workers = response.json()["workers"]
        for worker in workers:
            assert worker["status"] == "stopped"

    @patch("src.api.routers.status._get_current_ist_time")
    def test_market_pre_market_before_915(self, mock_time):
        """Test market status is pre_market before 9:15 IST."""
        # 8:00 AM IST
        mock_time.return_value = datetime(2024, 1, 15, 8, 0, 0)
        app = _create_test_app()
        redis_mock = _mock_redis_client()
        _override_dependencies(app, redis_mock)

        client = TestClient(app)
        response = client.get("/api/v1/status/system")

        assert response.status_code == 200
        data = response.json()
        assert data["market_status"] == "pre_market"
        # 75 minutes = 4500 seconds (8:00 to 9:15)
        assert data["countdown_seconds"] == 4500

    @patch("src.api.routers.status._get_current_ist_time")
    def test_market_open_between_915_and_1530(self, mock_time):
        """Test market status is open between 9:15 and 15:30 IST."""
        # 10:00 AM IST
        mock_time.return_value = datetime(2024, 1, 15, 10, 0, 0)
        app = _create_test_app()
        redis_mock = _mock_redis_client()
        _override_dependencies(app, redis_mock)

        client = TestClient(app)
        response = client.get("/api/v1/status/system")

        assert response.status_code == 200
        data = response.json()
        assert data["market_status"] == "open"
        # 5.5 hours = 330 minutes = 19800 seconds (10:00 to 15:30)
        assert data["countdown_seconds"] == 19800

    @patch("src.api.routers.status._get_current_ist_time")
    def test_market_closed_after_1530(self, mock_time):
        """Test market status is closed after 15:30 IST."""
        # 16:00 IST
        mock_time.return_value = datetime(2024, 1, 15, 16, 0, 0)
        app = _create_test_app()
        redis_mock = _mock_redis_client()
        _override_dependencies(app, redis_mock)

        client = TestClient(app)
        response = client.get("/api/v1/status/system")

        assert response.status_code == 200
        data = response.json()
        assert data["market_status"] == "closed"
        assert data["countdown_seconds"] > 0


# --- Capital Tests ---


class TestGetCapitalStatus:
    """Tests for GET /api/v1/status/capital."""

    def test_returns_capital_data_from_redis(self):
        """Test capital endpoint returns data from Redis cache."""
        margins_data = {
            "available_balance": 150000.0,
            "configured_capital": 200000.0,
            "used_margin": 50000.0,
            "available_margin": 100000.0,
            "segment_breakdown": {
                "equity": 30000.0,
                "commodity": 5000.0,
                "fno": 15000.0,
            },
        }
        app = _create_test_app()
        redis_mock = _mock_redis_client(margins_data=margins_data)
        _override_dependencies(app, redis_mock)

        client = TestClient(app)
        response = client.get("/api/v1/status/capital")

        assert response.status_code == 200
        data = response.json()
        assert data["available_balance"] == 150000.0
        assert data["configured_capital"] == 200000.0
        assert data["used_margin"] == 50000.0
        assert data["available_margin"] == 100000.0
        assert data["segment_breakdown"]["equity"] == 30000.0
        assert data["segment_breakdown"]["commodity"] == 5000.0
        assert data["segment_breakdown"]["fno"] == 15000.0

    def test_returns_defaults_when_no_redis_data(self):
        """Test capital endpoint returns zero defaults when no cached data."""
        app = _create_test_app()
        redis_mock = _mock_redis_client(margins_data=None)
        _override_dependencies(app, redis_mock)

        client = TestClient(app)
        response = client.get("/api/v1/status/capital")

        assert response.status_code == 200
        data = response.json()
        assert data["available_balance"] == 0.0
        assert data["configured_capital"] == 0.0
        assert data["used_margin"] == 0.0
        assert data["available_margin"] == 0.0
        assert data["segment_breakdown"] == {
            "equity": 0.0,
            "commodity": 0.0,
            "fno": 0.0,
        }

    def test_returns_defaults_on_malformed_redis_data(self):
        """Test capital endpoint handles malformed JSON gracefully."""
        app = _create_test_app()
        redis_mock = MagicMock()
        # Return invalid JSON
        redis_mock.get.return_value = "not-valid-json{{"
        _override_dependencies(app, redis_mock)

        client = TestClient(app)
        response = client.get("/api/v1/status/capital")

        assert response.status_code == 200
        data = response.json()
        assert data["available_balance"] == 0.0
        assert data["configured_capital"] == 0.0

    def test_handles_partial_margin_data(self):
        """Test capital endpoint handles partial data (missing fields)."""
        margins_data = {
            "available_balance": 100000.0,
            # Missing other fields
        }
        app = _create_test_app()
        redis_mock = _mock_redis_client(margins_data=margins_data)
        _override_dependencies(app, redis_mock)

        client = TestClient(app)
        response = client.get("/api/v1/status/capital")

        assert response.status_code == 200
        data = response.json()
        assert data["available_balance"] == 100000.0
        assert data["configured_capital"] == 0.0
        assert data["used_margin"] == 0.0
