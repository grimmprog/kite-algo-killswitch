"""Tests for Admin SSE module (src/admin/sse.py).

Tests cover:
- _get_market_data: reading market data from Redis
- _get_all_risk_metrics: reading risk metrics for all users
- _get_all_killswitch_status: reading kill switch state
- _get_worker_status: querying Celery worker state
- sse_event_generator: SSE event stream with change detection
- sse_stream endpoint: returns StreamingResponse
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import json
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from src.admin.sse import (
    _get_market_data,
    _get_all_risk_metrics,
    _get_all_killswitch_status,
    _get_worker_status,
    sse_event_generator,
    router,
)


# ============================================================
# Tests for _get_market_data
# ============================================================


class TestGetMarketData:
    """Tests for _get_market_data helper."""

    @patch("src.admin.sse.get_redis_client")
    def test_returns_parsed_json_for_available_instruments(self, mock_get_redis):
        """Returns parsed dict when Redis has data for instruments."""
        mock_redis = MagicMock()

        def mock_get(key):
            if "BANKNIFTY" in key:
                return json.dumps({"spot": 47000.0})
            if "NIFTY" in key:
                return json.dumps({"spot": 22500.0})
            return None

        mock_redis.get.side_effect = mock_get
        mock_get_redis.return_value = mock_redis

        result = _get_market_data()

        assert result["NIFTY"] == {"spot": 22500.0}
        assert result["BANKNIFTY"] == {"spot": 47000.0}

    @patch("src.admin.sse.get_redis_client")
    def test_returns_none_for_missing_instruments(self, mock_get_redis):
        """Returns None for instruments with no cached data."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        result = _get_market_data()

        assert result["NIFTY"] is None
        assert result["BANKNIFTY"] is None

    @patch("src.admin.sse.get_redis_client")
    def test_returns_none_on_redis_error(self, mock_get_redis):
        """Returns None for instruments where Redis raises an exception."""
        mock_redis = MagicMock()
        mock_redis.get.side_effect = Exception("Connection refused")
        mock_get_redis.return_value = mock_redis

        result = _get_market_data()

        assert result["NIFTY"] is None
        assert result["BANKNIFTY"] is None


# ============================================================
# Tests for _get_all_risk_metrics
# ============================================================


class TestGetAllRiskMetrics:
    """Tests for _get_all_risk_metrics helper."""

    @patch("src.admin.sse.get_redis_client")
    def test_returns_metrics_for_users_with_data(self, mock_get_redis):
        """Returns parsed risk metrics for users that have data."""
        mock_redis = MagicMock()

        def mock_hgetall(key):
            if "user:1:risk" in key:
                return {
                    "pnl": "1500.0",
                    "net_delta": "0.5",
                    "net_gamma": "0.02",
                    "net_vega": "50.0",
                    "margin_used": "25000.0",
                    "updated_at": "2024-01-15T10:00:00",
                }
            return {}

        mock_redis.hgetall.side_effect = mock_hgetall
        mock_get_redis.return_value = mock_redis

        result = _get_all_risk_metrics()

        assert "1" in result
        assert result["1"]["pnl"] == 1500.0
        assert result["1"]["net_delta"] == 0.5

    @patch("src.admin.sse.get_redis_client")
    def test_returns_empty_when_no_users_have_data(self, mock_get_redis):
        """Returns empty dict when no users have risk data."""
        mock_redis = MagicMock()
        mock_redis.hgetall.return_value = {}
        mock_get_redis.return_value = mock_redis

        result = _get_all_risk_metrics()

        assert result == {}

    @patch("src.admin.sse.get_redis_client")
    def test_handles_redis_error_gracefully(self, mock_get_redis):
        """Continues processing other users on Redis error."""
        mock_redis = MagicMock()
        mock_redis.hgetall.side_effect = Exception("Redis timeout")
        mock_get_redis.return_value = mock_redis

        result = _get_all_risk_metrics()

        assert result == {}


# ============================================================
# Tests for _get_all_killswitch_status
# ============================================================


class TestGetAllKillswitchStatus:
    """Tests for _get_all_killswitch_status helper."""

    @patch("src.admin.sse.get_redis_client")
    def test_returns_active_status_for_users_with_flag(self, mock_get_redis):
        """Returns active=True for users with killswitch set to 'true'."""
        mock_redis = MagicMock()

        def mock_get(key):
            if "user:1:killswitch" in key:
                return "true"
            if "user:2:killswitch" in key:
                return "false"
            return None

        mock_redis.get.side_effect = mock_get
        mock_get_redis.return_value = mock_redis

        result = _get_all_killswitch_status()

        assert result["1"]["active"] is True
        assert result["2"]["active"] is False

    @patch("src.admin.sse.get_redis_client")
    def test_excludes_users_without_killswitch_data(self, mock_get_redis):
        """Users with no killswitch key are not included."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        result = _get_all_killswitch_status()

        assert result == {}

    @patch("src.admin.sse.get_redis_client")
    def test_handles_redis_error_gracefully(self, mock_get_redis):
        """Continues on Redis errors."""
        mock_redis = MagicMock()
        mock_redis.get.side_effect = Exception("Connection lost")
        mock_get_redis.return_value = mock_redis

        result = _get_all_killswitch_status()

        assert result == {}


# ============================================================
# Tests for _get_worker_status
# ============================================================


class TestGetWorkerStatus:
    """Tests for _get_worker_status helper."""

    @patch("src.workers.celery_app.celery_app")
    def test_returns_workers_and_tasks(self, mock_celery):
        """Returns workers list and beat schedule tasks."""
        mock_inspect = MagicMock()
        mock_inspect.ping.return_value = {"celery@worker1": {"ok": "pong"}}
        mock_celery.control.inspect.return_value = mock_inspect
        mock_celery.conf.beat_schedule = {
            "market-data": {
                "task": "fetch_market_data",
                "schedule": 5.0,
            }
        }

        result = _get_worker_status()

        assert len(result["workers"]) == 1
        assert result["workers"][0]["name"] == "celery@worker1"
        assert result["workers"][0]["status"] == "online"
        assert len(result["tasks"]) == 1
        assert result["tasks"][0]["name"] == "market-data"

    @patch("src.workers.celery_app.celery_app")
    def test_returns_empty_on_broker_unavailable(self, mock_celery):
        """Returns empty lists when Celery broker is down."""
        mock_celery.control.inspect.side_effect = Exception("Broker unreachable")
        mock_celery.conf.beat_schedule = {}

        result = _get_worker_status()

        assert result["workers"] == []
        assert result["tasks"] == []

    @patch("src.workers.celery_app.celery_app")
    def test_handles_timedelta_schedule(self, mock_celery):
        """Handles timedelta objects in beat schedule."""
        from datetime import timedelta

        mock_inspect = MagicMock()
        mock_inspect.ping.return_value = {}
        mock_celery.control.inspect.return_value = mock_inspect
        mock_celery.conf.beat_schedule = {
            "risk-engine": {
                "task": "compute_risk",
                "schedule": timedelta(seconds=3),
            }
        }

        result = _get_worker_status()

        assert result["tasks"][0]["schedule_seconds"] == 3.0


# ============================================================
# Tests for sse_event_generator
# ============================================================


class TestSseEventGenerator:
    """Tests for SSE event generator async function."""

    def test_generator_is_async_generator(self):
        """sse_event_generator returns an async generator."""
        import inspect
        gen = sse_event_generator()
        assert inspect.isasyncgen(gen)


# ============================================================
# Tests for SSE endpoint
# ============================================================


class TestSseEndpoint:
    """Tests for the /sse endpoint."""

    def test_endpoint_returns_streaming_response(self):
        """The /sse endpoint returns a StreamingResponse with correct headers."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(router)

        client = TestClient(app)

        with patch("src.admin.sse.sse_event_generator") as mock_gen:
            # Return a simple async generator that yields one event and stops
            async def mock_generator():
                yield "event: test\ndata: {}\n\n"

            mock_gen.return_value = mock_generator()

            response = client.get("/sse")

            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")
