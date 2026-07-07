"""Tests for Authentication API Endpoints (Tasks 9.1–9.4).

Tests the FastAPI router at /api/v1/auth/* using TestClient
with mocked dependencies (database, broker OAuth).

Requirements covered:
- 1.1.4: JWT-based authentication with 24-hour access token expiry
- 1.1.5: Refresh tokens with 30-day expiry
- 1.1.10: Support user logout and token invalidation
- 1.2.2: Support OAuth-based broker authentication
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.auth.jwt_handler import JWTHandler
from src.auth.password import hash_password


# --- Test Setup ---

JWT_SECRET = "test-secret-key-for-endpoints"


def _create_test_app():
    """Create a fresh FastAPI app with the auth router for testing."""
    from fastapi import FastAPI
    from src.api.routers.auth import router

    app = FastAPI()
    app.include_router(router)
    return app


def _make_fake_user(user_id=1, email="test@example.com", password="SecurePass123", is_active=True):
    """Create a fake user object with the given properties."""
    user = MagicMock()
    user.id = user_id
    user.email = email
    user.password_hash = hash_password(password)
    user.is_active = is_active
    user.last_login = None
    user.broker_access_token = None
    user.broker_refresh_token = None
    user.broker_token_expiry = None
    return user


def _get_auth_header(user_id=1):
    """Generate a valid Bearer token header for the given user."""
    handler = JWTHandler(secret_key=JWT_SECRET)
    token = handler.create_access_token(user_id=user_id)
    return {"Authorization": f"Bearer {token}"}


# --- 9.1: POST /api/v1/auth/login Tests ---


class TestLoginEndpoint:
    """Test POST /api/v1/auth/login."""

    @patch.dict(os.environ, {"JWT_SECRET_KEY": JWT_SECRET})
    def test_successful_login(self):
        """9.1.1-9.1.3: Valid credentials return access and refresh tokens."""
        fake_user = _make_fake_user()

        app = _create_test_app()

        # Override get_db dependency
        from src.api.dependencies import get_db

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = fake_user

        app.dependency_overrides[get_db] = lambda: mock_db

        client = TestClient(app)
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "test@example.com", "password": "SecurePass123"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert data["user_id"] == 1

        # Verify the access token is a valid JWT
        handler = JWTHandler(secret_key=JWT_SECRET)
        payload = handler.verify_token(data["access_token"])
        assert payload["sub"] == "1"
        assert payload["type"] == "access"

        app.dependency_overrides.clear()

    @patch.dict(os.environ, {"JWT_SECRET_KEY": JWT_SECRET})
    def test_invalid_credentials_returns_401(self):
        """9.1.4: Invalid password returns 401 Unauthorized."""
        fake_user = _make_fake_user(password="SecurePass123")

        app = _create_test_app()

        from src.api.dependencies import get_db

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = fake_user

        app.dependency_overrides[get_db] = lambda: mock_db

        client = TestClient(app)
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "test@example.com", "password": "WrongPassword1"},
        )

        assert response.status_code == 401
        assert "Invalid email or password" in response.json()["detail"]

        app.dependency_overrides.clear()

    @patch.dict(os.environ, {"JWT_SECRET_KEY": JWT_SECRET})
    def test_nonexistent_user_returns_401(self):
        """9.1.4: Non-existent email returns 401."""
        app = _create_test_app()

        from src.api.dependencies import get_db

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None  # User not found

        app.dependency_overrides[get_db] = lambda: mock_db

        client = TestClient(app)
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "SomePassword1"},
        )

        assert response.status_code == 401

        app.dependency_overrides.clear()

    @patch.dict(os.environ, {"JWT_SECRET_KEY": JWT_SECRET})
    def test_missing_email_returns_422(self):
        """Validation: missing email field returns 422."""
        app = _create_test_app()

        from src.api.dependencies import get_db

        mock_db = MagicMock()
        app.dependency_overrides[get_db] = lambda: mock_db

        client = TestClient(app)
        response = client.post(
            "/api/v1/auth/login",
            json={"password": "SecurePass123"},
        )

        assert response.status_code == 422

        app.dependency_overrides.clear()

    @patch.dict(os.environ, {"JWT_SECRET_KEY": JWT_SECRET})
    def test_short_password_returns_422(self):
        """Validation: password shorter than 8 chars returns 422."""
        app = _create_test_app()

        from src.api.dependencies import get_db

        mock_db = MagicMock()
        app.dependency_overrides[get_db] = lambda: mock_db

        client = TestClient(app)
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "test@example.com", "password": "short"},
        )

        assert response.status_code == 422

        app.dependency_overrides.clear()


# --- 9.2: POST /api/v1/auth/refresh Tests ---


class TestRefreshEndpoint:
    """Test POST /api/v1/auth/refresh."""

    @patch.dict(os.environ, {"JWT_SECRET_KEY": JWT_SECRET})
    def test_valid_refresh_returns_new_access_token(self):
        """9.2.1-9.2.3: Valid refresh token generates new access token."""
        fake_user = _make_fake_user()

        app = _create_test_app()

        from src.api.dependencies import get_db

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = fake_user

        app.dependency_overrides[get_db] = lambda: mock_db

        # Create a valid refresh token
        handler = JWTHandler(secret_key=JWT_SECRET)
        refresh_token = handler.create_refresh_token(user_id=1)

        client = TestClient(app)
        response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

        # Verify new access token
        payload = handler.verify_token(data["access_token"])
        assert payload["sub"] == "1"
        assert payload["type"] == "access"

        app.dependency_overrides.clear()

    @patch.dict(os.environ, {"JWT_SECRET_KEY": JWT_SECRET})
    def test_invalid_refresh_token_returns_401(self):
        """9.2.1: Invalid refresh token returns 401."""
        app = _create_test_app()

        from src.api.dependencies import get_db

        mock_db = MagicMock()
        app.dependency_overrides[get_db] = lambda: mock_db

        client = TestClient(app)
        response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "invalid.token.here"},
        )

        assert response.status_code == 401

        app.dependency_overrides.clear()

    @patch.dict(os.environ, {"JWT_SECRET_KEY": JWT_SECRET})
    def test_access_token_as_refresh_returns_401(self):
        """9.2.1: Using access token as refresh token returns 401."""
        fake_user = _make_fake_user()

        app = _create_test_app()

        from src.api.dependencies import get_db

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = fake_user

        app.dependency_overrides[get_db] = lambda: mock_db

        # Create access token (not refresh)
        handler = JWTHandler(secret_key=JWT_SECRET)
        access_token = handler.create_access_token(user_id=1)

        client = TestClient(app)
        response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": access_token},
        )

        assert response.status_code == 401
        assert "Invalid refresh token" in response.json()["detail"]

        app.dependency_overrides.clear()


# --- 9.3: POST /api/v1/auth/logout Tests ---


class TestLogoutEndpoint:
    """Test POST /api/v1/auth/logout."""

    @patch.dict(os.environ, {"JWT_SECRET_KEY": JWT_SECRET})
    def test_successful_logout(self):
        """9.3.1-9.3.2: Authenticated user can logout successfully."""
        fake_user = _make_fake_user()

        app = _create_test_app()

        from src.api.dependencies import get_db, get_current_user

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = fake_user

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_current_user] = lambda: 1

        client = TestClient(app)
        response = client.post("/api/v1/auth/logout")

        assert response.status_code == 200
        assert response.json()["message"] == "Logged out successfully"

        app.dependency_overrides.clear()

    @patch.dict(os.environ, {"JWT_SECRET_KEY": JWT_SECRET})
    def test_logout_requires_auth(self):
        """9.3.1: Logout without authentication returns 401/403."""
        app = _create_test_app()

        from src.api.dependencies import get_db

        mock_db = MagicMock()
        app.dependency_overrides[get_db] = lambda: mock_db

        client = TestClient(app)
        # No Authorization header
        response = client.post("/api/v1/auth/logout")

        # Should return 401 or 403 depending on HTTPBearer config
        assert response.status_code in (401, 403)

        app.dependency_overrides.clear()


# --- 9.4: POST /api/v1/auth/broker-connect Tests ---


class TestBrokerConnectEndpoint:
    """Test POST /api/v1/auth/broker-connect."""

    @patch.dict(os.environ, {
        "JWT_SECRET_KEY": JWT_SECRET,
        "KITE_API_KEY": "test_api_key",
        "KITE_API_SECRET": "test_api_secret",
        "KITE_REDIRECT_URL": "http://localhost:8000/callback",
        "ENCRYPTION_KEY": "dGVzdC1lbmNyeXB0aW9uLWtleS0xMjM0NTY3ODk=",  # placeholder
    })
    @patch("src.broker.oauth.ZerodhaOAuth")
    @patch("src.broker.token_encryption.TokenEncryption")
    def test_successful_broker_connect(self, mock_encryption_cls, mock_oauth_cls):
        """9.4.1-9.4.3: Successful broker connection flow."""
        fake_user = _make_fake_user()

        app = _create_test_app()

        from src.api.dependencies import get_db, get_current_user

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.filter_by.return_value = mock_query
        mock_query.first.return_value = fake_user

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_current_user] = lambda: 1

        # Mock OAuth flow
        mock_oauth = MagicMock()
        mock_oauth.handle_callback.return_value = {
            "access_token": "broker_access_token_123",
            "public_token": "public_token_456",
        }
        mock_oauth_cls.return_value = mock_oauth

        # Mock encryption
        mock_encryptor = MagicMock()
        mock_encryption_cls.return_value = mock_encryptor

        client = TestClient(app)
        response = client.post(
            "/api/v1/auth/broker-connect",
            json={"request_token": "valid_request_token"},
        )

        assert response.status_code == 200
        assert response.json()["message"] == "Broker connected successfully"

        # Verify OAuth was called with correct token
        mock_oauth.handle_callback.assert_called_once_with("valid_request_token")

        # Verify tokens were stored
        mock_oauth.store_tokens.assert_called_once()

        app.dependency_overrides.clear()

    @patch.dict(os.environ, {"JWT_SECRET_KEY": JWT_SECRET})
    def test_broker_connect_requires_auth(self):
        """9.4.1: Broker connect without auth returns 401/403."""
        app = _create_test_app()

        from src.api.dependencies import get_db

        mock_db = MagicMock()
        app.dependency_overrides[get_db] = lambda: mock_db

        client = TestClient(app)
        response = client.post(
            "/api/v1/auth/broker-connect",
            json={"request_token": "some_token"},
        )

        assert response.status_code in (401, 403)

        app.dependency_overrides.clear()

    @patch.dict(os.environ, {
        "JWT_SECRET_KEY": JWT_SECRET,
        "KITE_API_KEY": "test_api_key",
        "KITE_API_SECRET": "test_api_secret",
        "KITE_REDIRECT_URL": "http://localhost:8000/callback",
        "ENCRYPTION_KEY": "dGVzdC1lbmNyeXB0aW9uLWtleS0xMjM0NTY3ODk=",
    })
    @patch("src.broker.oauth.ZerodhaOAuth")
    @patch("src.broker.token_encryption.TokenEncryption")
    def test_broker_connect_oauth_failure_returns_400(self, mock_encryption_cls, mock_oauth_cls):
        """9.4.1: OAuth failure returns 400."""
        from src.broker.oauth import OAuthError

        app = _create_test_app()

        from src.api.dependencies import get_db, get_current_user

        mock_db = MagicMock()
        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_current_user] = lambda: 1

        # Mock OAuth to raise error
        mock_oauth = MagicMock()
        mock_oauth.handle_callback.side_effect = OAuthError("Token exchange failed")
        mock_oauth_cls.return_value = mock_oauth

        mock_encryptor = MagicMock()
        mock_encryption_cls.return_value = mock_encryptor

        client = TestClient(app)
        response = client.post(
            "/api/v1/auth/broker-connect",
            json={"request_token": "invalid_request_token"},
        )

        assert response.status_code == 400
        assert "Broker connection failed" in response.json()["detail"]

        app.dependency_overrides.clear()

    @patch.dict(os.environ, {
        "JWT_SECRET_KEY": JWT_SECRET,
        "KITE_API_KEY": "",
        "KITE_API_SECRET": "",
    })
    def test_broker_connect_missing_config_returns_500(self):
        """9.4.1: Missing broker API config returns 500."""
        app = _create_test_app()

        from src.api.dependencies import get_db, get_current_user

        mock_db = MagicMock()
        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_current_user] = lambda: 1

        client = TestClient(app)
        response = client.post(
            "/api/v1/auth/broker-connect",
            json={"request_token": "some_token"},
        )

        assert response.status_code == 500
        assert "Broker API credentials not configured" in response.json()["detail"]

        app.dependency_overrides.clear()
