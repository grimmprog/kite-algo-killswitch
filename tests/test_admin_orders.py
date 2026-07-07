"""Tests for Admin Orders API (src/admin/api/orders.py).

Tests cover:
- POST /admin/api/validate-order: order validation via ExecutionWorker
- Validation result parsing (kill_switch, margin, duplicate)
- Error handling for invalid requests
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.admin.api.orders import router, _parse_failed_check
from src.admin.dependencies import get_db, get_redis


# ============================================================
# Fixtures
# ============================================================


def _create_test_app():
    """Create a fresh FastAPI app with the orders router."""
    app = FastAPI()
    app.include_router(router)
    return app


# ============================================================
# Tests for _parse_failed_check
# ============================================================


class TestParseFailedCheck:
    """Tests for the failure message parser."""

    def test_detects_kill_switch_failure(self):
        """Identifies 'kill_switch' from failure message."""
        assert _parse_failed_check("Kill switch is active for this user") == "kill_switch"

    def test_detects_margin_failure(self):
        """Identifies 'margin' from failure message."""
        assert _parse_failed_check("Insufficient margin available") == "margin"

    def test_detects_duplicate_failure(self):
        """Identifies 'duplicate' from failure message."""
        assert _parse_failed_check("Duplicate order detected") == "duplicate"

    def test_returns_none_for_unknown_failure(self):
        """Returns None for unrecognized failure messages."""
        assert _parse_failed_check("Some unknown error") is None

    def test_case_insensitive(self):
        """Matching is case insensitive."""
        assert _parse_failed_check("KILL SWITCH is active") == "kill_switch"
        assert _parse_failed_check("MARGIN insufficient") == "margin"
        assert _parse_failed_check("DUPLICATE detected") == "duplicate"


# ============================================================
# Tests for POST /admin/api/validate-order
# ============================================================


class TestValidateOrder:
    """Tests for the order validation endpoint."""

    @patch("src.admin.api.orders.ExecutionWorker")
    def test_valid_order_returns_valid(self, mock_worker_cls):
        """Returns valid=True when order passes all checks."""
        mock_worker = MagicMock()
        mock_worker.validate_order.return_value = (True, "Order is valid")
        mock_worker_cls.return_value = mock_worker

        app = _create_test_app()
        mock_redis = MagicMock()
        mock_db = MagicMock()
        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_db] = lambda: mock_db
        client = TestClient(app)

        response = client.post("/api/validate-order", json={
            "user_id": 1,
            "symbol": "NIFTY22500CE",
            "side": "BUY",
            "quantity": 50,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["message"] == "Order is valid"
        assert data["failed_check"] is None
        app.dependency_overrides.clear()

    @patch("src.admin.api.orders.ExecutionWorker")
    def test_killswitch_failure(self, mock_worker_cls):
        """Returns valid=False with failed_check='kill_switch'."""
        mock_worker = MagicMock()
        mock_worker.validate_order.return_value = (False, "Kill switch is active")
        mock_worker_cls.return_value = mock_worker

        app = _create_test_app()
        mock_redis = MagicMock()
        mock_db = MagicMock()
        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_db] = lambda: mock_db
        client = TestClient(app)

        response = client.post("/api/validate-order", json={
            "user_id": 1,
            "symbol": "NIFTY22500CE",
            "side": "BUY",
            "quantity": 50,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert data["failed_check"] == "kill_switch"
        app.dependency_overrides.clear()

    @patch("src.admin.api.orders.ExecutionWorker")
    def test_duplicate_failure(self, mock_worker_cls):
        """Returns valid=False with failed_check='duplicate'."""
        mock_worker = MagicMock()
        mock_worker.validate_order.return_value = (False, "Duplicate order detected")
        mock_worker_cls.return_value = mock_worker

        app = _create_test_app()
        mock_redis = MagicMock()
        mock_db = MagicMock()
        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_db] = lambda: mock_db
        client = TestClient(app)

        response = client.post("/api/validate-order", json={
            "user_id": 1,
            "symbol": "NIFTY22500CE",
            "side": "BUY",
            "quantity": 50,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert data["failed_check"] == "duplicate"
        app.dependency_overrides.clear()

    @patch("src.admin.api.orders.ExecutionWorker")
    def test_margin_failure(self, mock_worker_cls):
        """Returns valid=False with failed_check='margin'."""
        mock_worker = MagicMock()
        mock_worker.validate_order.return_value = (False, "Insufficient margin")
        mock_worker_cls.return_value = mock_worker

        app = _create_test_app()
        mock_redis = MagicMock()
        mock_db = MagicMock()
        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_db] = lambda: mock_db
        client = TestClient(app)

        response = client.post("/api/validate-order", json={
            "user_id": 1,
            "symbol": "NIFTY22500CE",
            "side": "BUY",
            "quantity": 50,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert data["failed_check"] == "margin"
        app.dependency_overrides.clear()

    @patch("src.admin.api.orders.ExecutionWorker")
    def test_worker_value_error_returns_422(self, mock_worker_cls):
        """Returns 422 when ExecutionWorker raises ValueError."""
        mock_worker_cls.side_effect = ValueError("user_id must be positive")

        app = _create_test_app()
        mock_redis = MagicMock()
        mock_db = MagicMock()
        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_db] = lambda: mock_db
        client = TestClient(app)

        response = client.post("/api/validate-order", json={
            "user_id": -1,
            "symbol": "NIFTY22500CE",
            "side": "BUY",
            "quantity": 50,
        })

        assert response.status_code == 422
        app.dependency_overrides.clear()

    @patch("src.admin.api.orders.ExecutionWorker")
    def test_unexpected_error_returns_500(self, mock_worker_cls):
        """Returns 500 on unexpected exception."""
        mock_worker_cls.side_effect = RuntimeError("Unexpected error")

        app = _create_test_app()
        mock_redis = MagicMock()
        mock_db = MagicMock()
        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_db] = lambda: mock_db
        client = TestClient(app)

        response = client.post("/api/validate-order", json={
            "user_id": 1,
            "symbol": "NIFTY22500CE",
            "side": "BUY",
            "quantity": 50,
        })

        assert response.status_code == 500
        app.dependency_overrides.clear()

    def test_missing_required_fields_returns_422(self):
        """Returns 422 when required fields are missing."""
        app = _create_test_app()
        mock_redis = MagicMock()
        mock_db = MagicMock()
        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_db] = lambda: mock_db
        client = TestClient(app)

        response = client.post("/api/validate-order", json={
            "user_id": 1,
            # missing symbol, side, quantity
        })

        assert response.status_code == 422
        app.dependency_overrides.clear()
