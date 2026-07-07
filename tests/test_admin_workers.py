"""Tests for Admin Workers API (src/admin/api/workers.py).

Tests cover:
- GET /admin/api/workers: querying Celery workers and beat schedule
- Handling broker unavailability
- Handling timedelta and numeric schedules
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.admin.api.workers import router


# ============================================================
# Fixtures
# ============================================================


def _create_test_app():
    """Create a fresh FastAPI app with the workers router."""
    app = FastAPI()
    app.include_router(router)
    return app


# ============================================================
# Tests for GET /admin/api/workers
# ============================================================


class TestGetWorkers:
    """Tests for the workers endpoint."""

    @patch("src.admin.api.workers.celery_app")
    def test_returns_online_workers(self, mock_celery):
        """Returns workers with online status when they respond to ping."""
        mock_inspect = MagicMock()
        mock_inspect.ping.return_value = {
            "celery@worker1": {"ok": "pong"},
            "celery@worker2": {"ok": "pong"},
        }
        mock_celery.control.inspect.return_value = mock_inspect
        mock_celery.conf.beat_schedule = {}

        app = _create_test_app()
        client = TestClient(app)
        response = client.get("/api/workers")

        assert response.status_code == 200
        data = response.json()
        assert len(data["workers"]) == 2
        assert data["workers"][0]["status"] == "online"
        assert data["workers"][1]["status"] == "online"

    @patch("src.admin.api.workers.celery_app")
    def test_returns_empty_workers_on_broker_down(self, mock_celery):
        """Returns empty workers list when Celery broker is unavailable."""
        mock_celery.control.inspect.side_effect = Exception("Connection refused")
        mock_celery.conf.beat_schedule = {}

        app = _create_test_app()
        client = TestClient(app)
        response = client.get("/api/workers")

        assert response.status_code == 200
        data = response.json()
        assert data["workers"] == []

    @patch("src.admin.api.workers.celery_app")
    def test_returns_beat_schedule_tasks(self, mock_celery):
        """Returns beat schedule tasks with schedule interval."""
        mock_inspect = MagicMock()
        mock_inspect.ping.return_value = {}
        mock_celery.control.inspect.return_value = mock_inspect
        mock_celery.conf.beat_schedule = {
            "fetch-market-data": {
                "task": "src.workers.market_data_task.fetch_market_data",
                "schedule": 5.0,
            },
            "compute-risk": {
                "task": "src.workers.risk_engine_task.compute_risk",
                "schedule": timedelta(seconds=3),
            },
        }

        app = _create_test_app()
        client = TestClient(app)
        response = client.get("/api/workers")

        assert response.status_code == 200
        data = response.json()
        assert len(data["tasks"]) == 2
        assert data["tasks"][0]["name"] == "fetch-market-data"
        assert data["tasks"][0]["schedule_seconds"] == 5.0
        assert data["tasks"][1]["name"] == "compute-risk"
        assert data["tasks"][1]["schedule_seconds"] == 3.0

    @patch("src.admin.api.workers.celery_app")
    def test_handles_none_ping_response(self, mock_celery):
        """Handles None ping response gracefully."""
        mock_inspect = MagicMock()
        mock_inspect.ping.return_value = None
        mock_celery.control.inspect.return_value = mock_inspect
        mock_celery.conf.beat_schedule = {}

        app = _create_test_app()
        client = TestClient(app)
        response = client.get("/api/workers")

        assert response.status_code == 200
        data = response.json()
        assert data["workers"] == []

    @patch("src.admin.api.workers.celery_app")
    def test_handles_empty_beat_schedule(self, mock_celery):
        """Handles empty or None beat schedule."""
        mock_inspect = MagicMock()
        mock_inspect.ping.return_value = {}
        mock_celery.control.inspect.return_value = mock_inspect
        mock_celery.conf.beat_schedule = None

        app = _create_test_app()
        client = TestClient(app)
        response = client.get("/api/workers")

        assert response.status_code == 200
        data = response.json()
        assert data["tasks"] == []
