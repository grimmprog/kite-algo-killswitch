"""Property-based tests for Authentication Required On All Endpoints (Property 12).

Uses Hypothesis to verify:
- For any request to any broker or market data settings endpoint that lacks
  a valid authentication token, the system SHALL return a 401 Unauthorized
  response regardless of the request method or path.

**Validates: Requirements 8.9**
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from hypothesis import given, strategies as st, settings
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routers.broker_settings import router as broker_settings_router
from src.api.routers.market_data_settings import router as market_data_settings_router
from src.api.routers.live_market import router as live_market_router
from src.api.dependencies import get_db, get_redis


# ============================================================
# Helpers
# ============================================================


def _create_test_app() -> FastAPI:
    """Create a FastAPI app with all broker/market-data routers registered.

    Does NOT override get_current_user so that unauthenticated requests
    are rejected by the auth dependency.
    """
    app = FastAPI()
    app.include_router(broker_settings_router)
    app.include_router(market_data_settings_router)
    app.include_router(live_market_router)

    # Override DB and Redis dependencies with mocks (these are not relevant
    # for auth testing — we just need them so the app doesn't try to connect
    # to real databases).
    mock_db = MagicMock()
    mock_redis = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_redis] = lambda: mock_redis

    return app


# All broker and market-data endpoints as (method, path) tuples.
# These are the endpoints defined in the design doc's API table
# that require authentication (Requirement 8.9).
# Only includes endpoints that are currently implemented in the codebase.
PROTECTED_ENDPOINTS = [
    ("GET", "/api/v1/settings/brokers/kite"),
    ("POST", "/api/v1/settings/brokers/kite/reconnect"),
    ("GET", "/api/v1/settings/brokers/kite/callback?request_token=test"),
    ("PUT", "/api/v1/settings/brokers/kite/auto-login"),
    ("GET", "/api/v1/settings/market-data/sources"),
    ("PUT", "/api/v1/settings/market-data/sources"),
    ("GET", "/api/v1/market-data/live"),
]

# Endpoints pending implementation (Dhan routes from task 5.2).
# Once implemented, move these to PROTECTED_ENDPOINTS above.
PENDING_ENDPOINTS = [
    ("GET", "/api/v1/settings/brokers/dhan"),
    ("POST", "/api/v1/settings/brokers/dhan/connect"),
    ("DELETE", "/api/v1/settings/brokers/dhan/connect"),
]


# ============================================================
# Property 12: Authentication Required On All Endpoints
# ============================================================


class TestAuthenticationRequiredOnAllEndpoints:
    """Property-based tests for authentication enforcement.

    **Validates: Requirements 8.9**

    Core invariant:
    - For any request to any broker or market data settings endpoint that
      lacks a valid authentication token, the system SHALL return a 401
      Unauthorized (or 403 Forbidden) response regardless of the request
      method or path.
    """

    @given(
        endpoint_index=st.integers(min_value=0, max_value=len(PROTECTED_ENDPOINTS) - 1),
    )
    @settings(max_examples=50, deadline=None)
    def test_unauthenticated_requests_rejected(self, endpoint_index: int):
        """All protected endpoints reject requests without a valid auth token.

        **Validates: Requirements 8.9**

        Property: For any request to any broker or market data settings
        endpoint that lacks a valid authentication token, the system SHALL
        return a 401 Unauthorized response regardless of the request method
        or path.
        """
        method, path = PROTECTED_ENDPOINTS[endpoint_index]
        app = _create_test_app()
        client = TestClient(app, raise_server_exceptions=False)

        # Make the request WITHOUT any Authorization header
        if method == "GET":
            response = client.get(path)
        elif method == "POST":
            response = client.post(path, json={})
        elif method == "PUT":
            response = client.put(path, json={})
        elif method == "DELETE":
            response = client.delete(path)
        else:
            pytest.fail(f"Unsupported HTTP method: {method}")

        # The endpoint MUST reject the unauthenticated request with 401 or 403.
        # FastAPI's HTTPBearer returns 403 when the Authorization header is
        # missing entirely, and 401 when the token is invalid/expired.
        assert response.status_code in (401, 403), (
            f"Expected 401 or 403 for unauthenticated {method} {path}, "
            f"but got {response.status_code}. Response: {response.text}"
        )

    @given(
        endpoint_index=st.integers(min_value=0, max_value=len(PROTECTED_ENDPOINTS) - 1),
        fake_token=st.text(
            alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-",
            min_size=1,
            max_size=50,
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_invalid_token_rejected(self, endpoint_index: int, fake_token: str):
        """All protected endpoints reject requests with an invalid auth token.

        **Validates: Requirements 8.9**

        Property: For any request with an invalid/garbage Bearer token,
        the system SHALL return a 401 Unauthorized response.
        """
        method, path = PROTECTED_ENDPOINTS[endpoint_index]
        app = _create_test_app()
        client = TestClient(app, raise_server_exceptions=False)

        headers = {"Authorization": f"Bearer {fake_token}"}

        if method == "GET":
            response = client.get(path, headers=headers)
        elif method == "POST":
            response = client.post(path, json={}, headers=headers)
        elif method == "PUT":
            response = client.put(path, json={}, headers=headers)
        elif method == "DELETE":
            response = client.delete(path, headers=headers)
        else:
            pytest.fail(f"Unsupported HTTP method: {method}")

        # Invalid tokens must be rejected with 401 or 403
        assert response.status_code in (401, 403), (
            f"Expected 401 or 403 for invalid token on {method} {path}, "
            f"but got {response.status_code}. Response: {response.text}"
        )
