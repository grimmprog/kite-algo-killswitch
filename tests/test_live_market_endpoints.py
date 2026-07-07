"""Tests for Live Market Data API Endpoint (Task 5.4).

Tests the FastAPI router at /api/v1/market-data/live using TestClient
with mocked dependencies (database, Redis).

Requirements covered:
- 8.9: Authentication required on all endpoints
- 8.10: Live market data accessible via REST
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routers.live_market import router as live_market_router
from src.api.dependencies import get_current_user, get_db, get_redis


def _create_test_app():
    """Create a fresh FastAPI app with the live market router for testing."""
    app = FastAPI()
    app.include_router(live_market_router)
    return app


class TestGetLiveMarketData:
    """Tests for GET /api/v1/market-data/live."""

    def test_returns_live_data_on_success(self):
        """Successful fetch returns LiveMarketResponse with indices."""
        app = _create_test_app()
        mock_db = MagicMock()
        mock_redis = MagicMock()
        mock_redis.get.return_value = None  # No cache

        app.dependency_overrides[get_current_user] = lambda: 1
        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_redis] = lambda: mock_redis

        fake_response = {
            "indices": [
                {
                    "symbol": "NIFTY 50",
                    "value": 22500.0,
                    "change_points": 150.0,
                    "change_percent": 0.67,
                    "last_updated": "2024-01-15T10:30:00+05:30",
                }
            ],
            "market_open": True,
            "data_source": "nsepy",
            "last_successful_fetch": "2024-01-15T10:30:00+05:30",
        }

        with patch(
            "src.api.routers.live_market.MarketDataService"
        ) as MockService:
            mock_service_instance = MagicMock()
            from src.services.market_data_service import LiveMarketResponse, IndexData

            mock_service_instance.fetch_live_indices.return_value = (
                LiveMarketResponse(**fake_response)
            )
            MockService.return_value = mock_service_instance

            client = TestClient(app)
            response = client.get("/api/v1/market-data/live")

        assert response.status_code == 200
        data = response.json()
        assert data["market_open"] is True
        assert data["data_source"] == "nsepy"
        assert len(data["indices"]) == 1
        assert data["indices"][0]["symbol"] == "NIFTY 50"
        assert data["indices"][0]["value"] == 22500.0

    def test_returns_503_when_all_sources_fail(self):
        """Returns 503 with detail when DataUnavailableError is raised."""
        app = _create_test_app()
        mock_db = MagicMock()
        mock_redis = MagicMock()

        app.dependency_overrides[get_current_user] = lambda: 1
        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_redis] = lambda: mock_redis

        with patch(
            "src.api.routers.live_market.MarketDataService"
        ) as MockService:
            from src.services.market_data_service import DataUnavailableError

            mock_service_instance = MagicMock()
            mock_service_instance.fetch_live_indices.side_effect = (
                DataUnavailableError("All 2 sources failed")
            )
            MockService.return_value = mock_service_instance

            client = TestClient(app)
            response = client.get("/api/v1/market-data/live")

        assert response.status_code == 503
        data = response.json()
        assert data["detail"]["detail"] == "Data unavailable"

    def test_requires_authentication(self):
        """Returns 401 when no auth token is provided."""
        app = _create_test_app()
        # Do NOT override get_current_user — no auth
        mock_db = MagicMock()
        mock_redis = MagicMock()

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_redis] = lambda: mock_redis

        client = TestClient(app)
        response = client.get("/api/v1/market-data/live")

        # Without auth token, endpoint rejects the request
        assert response.status_code in (401, 403)

    def test_passes_user_id_to_service(self):
        """Ensures the authenticated user_id is passed to the service."""
        app = _create_test_app()
        mock_db = MagicMock()
        mock_redis = MagicMock()

        test_user_id = 42
        app.dependency_overrides[get_current_user] = lambda: test_user_id
        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_redis] = lambda: mock_redis

        with patch(
            "src.api.routers.live_market.MarketDataService"
        ) as MockService:
            from src.services.market_data_service import LiveMarketResponse

            mock_service_instance = MagicMock()
            mock_service_instance.fetch_live_indices.return_value = (
                LiveMarketResponse(
                    indices=[],
                    market_open=False,
                    data_source="nsepy",
                    last_successful_fetch=None,
                )
            )
            MockService.return_value = mock_service_instance

            client = TestClient(app)
            client.get("/api/v1/market-data/live")

            mock_service_instance.fetch_live_indices.assert_called_once_with(
                test_user_id
            )
