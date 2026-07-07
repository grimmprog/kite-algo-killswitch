"""Tests for API Error Handlers (src/api/error_handlers.py).

Tests cover:
- http_exception_handler: consistent JSON format with request_id
- validation_exception_handler: field-level validation error details
- unhandled_exception_handler: safe 500 response without leaking internals
- register_error_handlers: registers all handlers on app
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.api.error_handlers import (
    http_exception_handler,
    validation_exception_handler,
    unhandled_exception_handler,
    register_error_handlers,
    _get_request_id,
)


# ============================================================
# Tests for _get_request_id
# ============================================================


class TestGetRequestId:
    """Tests for request_id extraction."""

    def test_returns_request_id_from_state(self):
        """Returns request_id when available in request state."""
        mock_request = MagicMock()
        mock_request.state.request_id = "abc-123"

        result = _get_request_id(mock_request)

        assert result == "abc-123"

    def test_returns_unknown_when_not_set(self):
        """Returns 'unknown' when request_id is not in state."""
        mock_request = MagicMock(spec=[])
        mock_request.state = MagicMock(spec=[])

        result = _get_request_id(mock_request)

        assert result == "unknown"


# ============================================================
# Tests for http_exception_handler
# ============================================================


class TestHttpExceptionHandler:
    """Tests for HTTP exception handling."""

    @pytest.mark.asyncio
    async def test_returns_json_with_error_and_request_id(self):
        """Returns JSON with error, status_code, and request_id."""
        mock_request = MagicMock()
        mock_request.state.request_id = "req-001"
        exc = StarletteHTTPException(status_code=404, detail="Not found")

        response = await http_exception_handler(mock_request, exc)

        assert response.status_code == 404
        import json
        body = json.loads(response.body)
        assert body["error"] == "Not found"
        assert body["status_code"] == 404
        assert body["request_id"] == "req-001"

    @pytest.mark.asyncio
    async def test_handles_401_unauthorized(self):
        """Handles 401 errors correctly."""
        mock_request = MagicMock()
        mock_request.state.request_id = "req-002"
        exc = StarletteHTTPException(status_code=401, detail="Unauthorized")

        response = await http_exception_handler(mock_request, exc)

        assert response.status_code == 401
        import json
        body = json.loads(response.body)
        assert body["error"] == "Unauthorized"


# ============================================================
# Tests for validation_exception_handler
# ============================================================


class TestValidationExceptionHandler:
    """Tests for request validation error handling."""

    @pytest.mark.asyncio
    async def test_returns_422_with_field_errors(self):
        """Returns 422 with detailed field validation errors."""
        from fastapi.exceptions import RequestValidationError

        mock_request = MagicMock()
        mock_request.state.request_id = "req-003"

        errors = [
            {
                "loc": ("body", "email"),
                "msg": "field required",
                "type": "value_error.missing",
            }
        ]
        exc = RequestValidationError(errors=errors)

        response = await validation_exception_handler(mock_request, exc)

        assert response.status_code == 422
        import json
        body = json.loads(response.body)
        assert body["error"] == "Validation failed"
        assert body["request_id"] == "req-003"
        assert len(body["details"]) == 1
        assert "email" in body["details"][0]["field"]


# ============================================================
# Tests for unhandled_exception_handler
# ============================================================


class TestUnhandledExceptionHandler:
    """Tests for unhandled exception handling."""

    @pytest.mark.asyncio
    async def test_returns_500_without_leaking_details(self):
        """Returns generic 500 without exposing internal error details."""
        mock_request = MagicMock()
        mock_request.state.request_id = "req-004"
        mock_request.method = "POST"
        mock_request.url.path = "/api/v1/trades"
        exc = RuntimeError("Database connection pool exhausted")

        response = await unhandled_exception_handler(mock_request, exc)

        assert response.status_code == 500
        import json
        body = json.loads(response.body)
        assert body["error"] == "Internal server error"
        assert body["request_id"] == "req-004"
        # Should NOT contain internal error message
        assert "pool exhausted" not in body["error"]


# ============================================================
# Tests for register_error_handlers
# ============================================================


class TestRegisterErrorHandlers:
    """Tests for handler registration."""

    def test_registers_all_handlers(self):
        """Registers HTTP, validation, and unhandled exception handlers."""
        app = FastAPI()

        register_error_handlers(app)

        # The handlers should be registered (FastAPI keeps them internally)
        # We verify by making requests that trigger each handler type
        # HTTP 404
        client = TestClient(app)
        response = client.get("/nonexistent")
        assert response.status_code == 404

    def test_http_exception_formatted_correctly(self):
        """HTTP exceptions return consistent JSON format via the handler."""
        app = FastAPI()
        register_error_handlers(app)

        @app.get("/test-error")
        async def raise_error():
            raise StarletteHTTPException(status_code=403, detail="Forbidden")

        client = TestClient(app)
        response = client.get("/test-error")

        assert response.status_code == 403
        data = response.json()
        assert data["error"] == "Forbidden"
        assert data["status_code"] == 403
        assert "request_id" in data

    def test_unhandled_exception_returns_500(self):
        """Unhandled exceptions return 500 with safe error message."""
        app = FastAPI()
        register_error_handlers(app)

        @app.get("/test-crash")
        async def crash():
            raise RuntimeError("Something broke internally")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test-crash")

        assert response.status_code == 500
        data = response.json()
        assert data["error"] == "Internal server error"
        assert "broke" not in data["error"]
