"""Tests for API middleware and error handlers.

Validates:
- Request ID middleware (4.2.10)
- CORS configuration (2.4.11)
- Exception handlers (4.2.3)
- Request logging middleware (2.3.7)
"""

import uuid

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.api.error_handlers import register_error_handlers
from src.api.middleware import RequestIDMiddleware, RequestLoggingMiddleware


@pytest.fixture
def test_app():
    """Create a minimal FastAPI app with middleware and error handlers for testing."""
    app = FastAPI()

    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RequestIDMiddleware)
    register_error_handlers(app)

    @app.get("/ok")
    async def ok_endpoint():
        return {"status": "ok"}

    @app.get("/error")
    async def error_endpoint():
        raise HTTPException(status_code=403, detail="Forbidden")

    @app.get("/crash")
    async def crash_endpoint():
        raise RuntimeError("Something went wrong")

    return app


@pytest.fixture
def client(test_app):
    return TestClient(test_app)


class TestRequestIDMiddleware:
    """Tests for X-Request-ID header generation and preservation."""

    def test_generates_request_id_when_not_provided(self, client):
        response = client.get("/ok")
        assert "X-Request-ID" in response.headers
        # Should be a valid UUID4
        request_id = response.headers["X-Request-ID"]
        uuid.UUID(request_id, version=4)

    def test_preserves_client_request_id(self, client):
        custom_id = "my-trace-id-123"
        response = client.get("/ok", headers={"X-Request-ID": custom_id})
        assert response.headers["X-Request-ID"] == custom_id

    def test_request_id_present_in_error_responses(self, client):
        response = client.get("/error")
        assert "X-Request-ID" in response.headers
        data = response.json()
        assert data["request_id"] == response.headers["X-Request-ID"]


class TestErrorHandlers:
    """Tests for exception handler JSON responses."""

    def test_http_exception_returns_json(self, client):
        response = client.get("/error")
        assert response.status_code == 403
        data = response.json()
        assert data["error"] == "Forbidden"
        assert data["status_code"] == 403
        assert "request_id" in data

    def test_unhandled_exception_returns_500(self, client):
        response = client.get("/crash")
        assert response.status_code == 500
        data = response.json()
        assert data["error"] == "Internal server error"
        assert data["status_code"] == 500
        assert "request_id" in data

    def test_404_returns_json_with_request_id(self, client):
        response = client.get("/nonexistent")
        assert response.status_code == 404
        data = response.json()
        assert "request_id" in data
        assert data["status_code"] == 404


class TestMainApp:
    """Integration tests against the main application."""

    def test_app_imports_cleanly(self):
        from src.main import app
        assert app.title == "Multi-User Web Trading Platform"
        assert app.docs_url == "/docs"
        assert app.redoc_url == "/redoc"

    def test_admin_router_still_works(self):
        from src.main import app
        client = TestClient(app)
        response = client.get("/admin/")
        assert response.status_code == 200

    def test_cors_allows_configured_origin(self):
        from src.main import app
        client = TestClient(app)
        response = client.options(
            "/docs",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert "access-control-allow-origin" in response.headers
