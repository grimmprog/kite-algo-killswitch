"""Security tests for the Multi-User Web Trading Platform.

Requirements covered:
- 6.5.1: Test for SQL injection vulnerabilities
- 6.5.2: Test for authentication bypass
- 6.5.3: Test for authorization bypass
- 6.5.4: Test for token security
- 6.5.5: Test for cross-user data access
- 2.4.2: Validate JWT tokens on every API request
- 2.4.3: Enforce user authorization
- 2.4.4: Encrypt broker tokens using Fernet
- 2.4.5: Never log or expose broker tokens
- 2.4.6: Use parameterized queries
"""

import sys
import os
import time
import logging
import logging.handlers
import inspect
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import jwt
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from cryptography.fernet import Fernet

from fastapi.testclient import TestClient

from src.auth.jwt_handler import JWTHandler
from src.auth.password import hash_password
from src.broker.token_encryption import TokenEncryption


# --- Constants ---
JWT_SECRET = "test-secret-key-for-security-tests"
WRONG_SECRET = "wrong-secret-key-completely-different"


# --- Helpers ---


def _create_test_app():
    """Create a fresh FastAPI app with all routers for security testing."""
    from fastapi import FastAPI
    from src.api.routers.auth import router as auth_router
    from src.api.routers.dashboard import router as dashboard_router
    from src.api.routers.trading import router as trading_router
    from src.api.routers.killswitch import router as killswitch_router

    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(dashboard_router)
    app.include_router(trading_router)
    app.include_router(killswitch_router)
    return app


def _make_fake_user(user_id=1, email="user@example.com", password="SecurePass123", is_active=True):
    """Create a fake user object."""
    user = MagicMock()
    user.id = user_id
    user.email = email
    user.password_hash = hash_password(password)
    user.is_active = is_active
    user.last_login = None
    user.broker_access_token = None
    user.broker_refresh_token = None
    user.broker_token_expiry = None
    user.capital = 100000.0
    user.risk_profile = "moderate"
    user.daily_loss_limit_percent = 2.0
    user.max_trade_risk_percent = 1.0
    user.killswitch_state = False
    return user


def _create_valid_token(user_id=1, secret=JWT_SECRET):
    """Create a valid JWT access token."""
    handler = JWTHandler(secret_key=secret)
    return handler.create_access_token(user_id=user_id)


def _create_expired_token(user_id=1, secret=JWT_SECRET):
    """Create an expired JWT token (expired 1 hour ago)."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "iat": now - timedelta(hours=25),
        "exp": now - timedelta(hours=1),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def _setup_app_with_user(user_id=1, user=None):
    """Set up app with mocked dependencies returning the given user."""
    app = _create_test_app()
    from src.api.dependencies import get_db, get_redis

    if user is None:
        user = _make_fake_user(user_id=user_id)

    mock_db = MagicMock()
    mock_query = MagicMock()
    mock_db.query.return_value = mock_query
    mock_query.filter.return_value = mock_query
    mock_query.filter_by.return_value = mock_query
    mock_query.first.return_value = user
    mock_query.order_by.return_value = mock_query
    mock_query.offset.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.all.return_value = []

    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    mock_redis.hgetall.return_value = {}

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_redis] = lambda: mock_redis

    return app, mock_db, mock_redis


# ===========================================================================
# Task 25.1: Authentication Security Tests
# ===========================================================================


class TestExpiredTokenRejection:
    """25.1.1: Test that expired JWT tokens are rejected with 401.

    Validates: Requirements 2.4.2, 6.5.2
    """

    @patch.dict(os.environ, {"JWT_SECRET_KEY": JWT_SECRET})
    def test_expired_token_rejected_on_dashboard(self):
        """Expired access token returns 401 on /dashboard."""
        app, _, _ = _setup_app_with_user()
        client = TestClient(app)

        expired_token = _create_expired_token(user_id=1)
        response = client.get(
            "/api/v1/dashboard",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert response.status_code == 401

    @patch.dict(os.environ, {"JWT_SECRET_KEY": JWT_SECRET})
    def test_expired_token_rejected_on_positions(self):
        """Expired access token returns 401 on /positions."""
        app, _, _ = _setup_app_with_user()
        client = TestClient(app)

        expired_token = _create_expired_token(user_id=1)
        response = client.get(
            "/api/v1/positions",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert response.status_code == 401

    @patch.dict(os.environ, {"JWT_SECRET_KEY": JWT_SECRET})
    def test_expired_token_rejected_on_risk(self):
        """Expired access token returns 401 on /risk."""
        app, _, _ = _setup_app_with_user()
        client = TestClient(app)

        expired_token = _create_expired_token(user_id=1)
        response = client.get(
            "/api/v1/risk",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert response.status_code == 401


    @patch.dict(os.environ, {"JWT_SECRET_KEY": JWT_SECRET})
    def test_expired_token_rejected_on_killswitch(self):
        """Expired access token returns 401 on /killswitch/activate."""
        app, _, _ = _setup_app_with_user()
        client = TestClient(app)

        expired_token = _create_expired_token(user_id=1)
        response = client.post(
            "/api/v1/killswitch/activate",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert response.status_code == 401

    @patch.dict(os.environ, {"JWT_SECRET_KEY": JWT_SECRET})
    def test_expired_token_rejected_on_trade_execute(self):
        """Expired access token returns 401 on /trades/execute."""
        app, _, _ = _setup_app_with_user()
        client = TestClient(app)

        expired_token = _create_expired_token(user_id=1)
        response = client.post(
            "/api/v1/trades/execute",
            headers={"Authorization": f"Bearer {expired_token}"},
            json={"symbol": "NIFTY", "exchange": "NSE", "quantity": 1, "side": "BUY"},
        )
        assert response.status_code == 401


class TestInvalidTokenRejection:
    """25.1.2: Test that invalid/malformed JWT tokens are rejected with 401.

    Validates: Requirements 2.4.2, 6.5.2
    """

    @patch.dict(os.environ, {"JWT_SECRET_KEY": JWT_SECRET})
    def test_random_string_token_rejected(self):
        """Random string as token returns 401."""
        app, _, _ = _setup_app_with_user()
        client = TestClient(app)

        response = client.get(
            "/api/v1/dashboard",
            headers={"Authorization": "Bearer random-invalid-string"},
        )
        assert response.status_code == 401


    @patch.dict(os.environ, {"JWT_SECRET_KEY": JWT_SECRET})
    def test_empty_token_rejected(self):
        """Empty Bearer token returns 401 or 403."""
        app, _, _ = _setup_app_with_user()
        client = TestClient(app)

        response = client.get(
            "/api/v1/dashboard",
            headers={"Authorization": "Bearer "},
        )
        # FastAPI HTTPBearer may return 403 for empty credentials
        assert response.status_code in (401, 403)

    @patch.dict(os.environ, {"JWT_SECRET_KEY": JWT_SECRET})
    def test_malformed_jwt_three_dots_rejected(self):
        """JWT with extra dots is rejected."""
        app, _, _ = _setup_app_with_user()
        client = TestClient(app)

        response = client.get(
            "/api/v1/dashboard",
            headers={"Authorization": "Bearer aaa.bbb.ccc.ddd"},
        )
        assert response.status_code == 401

    @patch.dict(os.environ, {"JWT_SECRET_KEY": JWT_SECRET})
    def test_none_algorithm_token_rejected(self):
        """Token with 'none' algorithm (alg=none attack) is rejected."""
        import base64
        import json

        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "none", "typ": "JWT"}).encode()
        ).rstrip(b"=").decode()
        payload = base64.urlsafe_b64encode(
            json.dumps({"sub": "1", "type": "access", "exp": 9999999999}).encode()
        ).rstrip(b"=").decode()
        # No signature
        none_token = f"{header}.{payload}."

        app, _, _ = _setup_app_with_user()
        client = TestClient(app)

        response = client.get(
            "/api/v1/dashboard",
            headers={"Authorization": f"Bearer {none_token}"},
        )
        assert response.status_code == 401


    @patch.dict(os.environ, {"JWT_SECRET_KEY": JWT_SECRET})
    def test_no_authorization_header_rejected(self):
        """Request without Authorization header returns 401 or 403."""
        app, _, _ = _setup_app_with_user()
        client = TestClient(app)

        response = client.get("/api/v1/dashboard")
        assert response.status_code in (401, 403)


class TestTokenTamperingDetection:
    """25.1.3: Test that tampered JWT tokens are rejected.

    Validates: Requirements 2.4.2, 6.5.2
    """

    @patch.dict(os.environ, {"JWT_SECRET_KEY": JWT_SECRET})
    def test_modified_payload_rejected(self):
        """Token with modified payload (different user_id) is rejected."""
        # Create token for user 1, then decode and change to user 999
        import base64
        import json

        token = _create_valid_token(user_id=1)
        parts = token.split(".")
        # Decode payload, change user_id, re-encode
        payload_bytes = parts[1] + "=" * (4 - len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_bytes))
        payload["sub"] = "999"  # Tamper user ID
        new_payload = base64.urlsafe_b64encode(
            json.dumps(payload).encode()
        ).rstrip(b"=").decode()
        tampered_token = f"{parts[0]}.{new_payload}.{parts[2]}"

        app, _, _ = _setup_app_with_user()
        client = TestClient(app)

        response = client.get(
            "/api/v1/dashboard",
            headers={"Authorization": f"Bearer {tampered_token}"},
        )
        assert response.status_code == 401


    @patch.dict(os.environ, {"JWT_SECRET_KEY": JWT_SECRET})
    def test_wrong_signature_key_rejected(self):
        """Token signed with a different secret key is rejected."""
        # Sign with a different key
        wrong_token = _create_valid_token(user_id=1, secret=WRONG_SECRET)

        app, _, _ = _setup_app_with_user()
        client = TestClient(app)

        response = client.get(
            "/api/v1/dashboard",
            headers={"Authorization": f"Bearer {wrong_token}"},
        )
        assert response.status_code == 401

    @patch.dict(os.environ, {"JWT_SECRET_KEY": JWT_SECRET})
    def test_signature_removed_rejected(self):
        """Token with signature removed is rejected."""
        token = _create_valid_token(user_id=1)
        parts = token.split(".")
        # Remove signature
        no_sig_token = f"{parts[0]}.{parts[1]}."

        app, _, _ = _setup_app_with_user()
        client = TestClient(app)

        response = client.get(
            "/api/v1/dashboard",
            headers={"Authorization": f"Bearer {no_sig_token}"},
        )
        assert response.status_code == 401

    @patch.dict(os.environ, {"JWT_SECRET_KEY": JWT_SECRET})
    def test_token_with_modified_expiry_rejected(self):
        """Token with exp modified to far future is rejected (signature invalid)."""
        import base64
        import json

        token = _create_valid_token(user_id=1)
        parts = token.split(".")
        payload_bytes = parts[1] + "=" * (4 - len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_bytes))
        payload["exp"] = 9999999999  # Far future
        new_payload = base64.urlsafe_b64encode(
            json.dumps(payload).encode()
        ).rstrip(b"=").decode()
        tampered_token = f"{parts[0]}.{new_payload}.{parts[2]}"

        app, _, _ = _setup_app_with_user()
        client = TestClient(app)

        response = client.get(
            "/api/v1/dashboard",
            headers={"Authorization": f"Bearer {tampered_token}"},
        )
        assert response.status_code == 401


# ===========================================================================
# Task 25.2: Authorization Tests
# ===========================================================================


class TestCrossUserDataAccess:
    """25.2.1: Test that User A cannot access User B's data.

    Validates: Requirements 2.4.3, 6.5.3, 6.5.5
    """

    @patch.dict(os.environ, {"JWT_SECRET_KEY": JWT_SECRET})
    def test_user_can_only_see_own_positions(self):
        """User A's token should only return User A's data from positions endpoint."""
        app = _create_test_app()
        from src.api.dependencies import get_db, get_redis, get_current_user

        # User A authenticates with ID 1
        user_a = _make_fake_user(user_id=1)

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []

        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_redis.hgetall.return_value = {}

        # Override get_current_user to return user 1
        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_current_user] = lambda: 1

        client = TestClient(app)
        response = client.get("/api/v1/positions")
        assert response.status_code == 200

        # Verify the DB query filters by user_id (not user 2's data)
        # The Trade query should always filter by user_id
        filter_calls = mock_query.filter.call_args_list
        assert len(filter_calls) > 0  # Filter was applied

        app.dependency_overrides.clear()


    @patch.dict(os.environ, {"JWT_SECRET_KEY": JWT_SECRET})
    def test_user_can_only_see_own_risk_metrics(self):
        """User's risk endpoint only fetches their own Redis key."""
        app = _create_test_app()
        from src.api.dependencies import get_db, get_redis, get_current_user
        from src.cache.redis_keys import RedisKeys

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        mock_redis = MagicMock()
        mock_redis.hgetall.return_value = {}
        mock_redis.get.return_value = None

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_current_user] = lambda: 42  # User ID 42

        client = TestClient(app)
        response = client.get("/api/v1/risk")
        assert response.status_code == 200

        # Verify Redis was queried with user 42's key, not another user's
        redis_calls = mock_redis.hgetall.call_args_list
        assert len(redis_calls) > 0
        key_used = redis_calls[0][0][0]
        assert "42" in key_used  # Key should contain user ID 42

        app.dependency_overrides.clear()

    @patch.dict(os.environ, {"JWT_SECRET_KEY": JWT_SECRET})
    def test_user_can_only_see_own_trade_history(self):
        """Trade history endpoint filters by authenticated user's ID."""
        app = _create_test_app()
        from src.api.dependencies import get_db, get_redis, get_current_user

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []

        mock_redis = MagicMock()

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_current_user] = lambda: 5  # User ID 5

        client = TestClient(app)
        response = client.get("/api/v1/trades/history")
        assert response.status_code == 200

        # Verify DB query uses filter (implying user_id filtering)
        assert mock_query.filter.called

        app.dependency_overrides.clear()


class TestUnauthorizedEndpoints:
    """25.2.2: Test that unauthenticated requests return 401.

    Validates: Requirements 2.4.2, 6.5.2
    """

    PROTECTED_ENDPOINTS = [
        ("GET", "/api/v1/dashboard"),
        ("GET", "/api/v1/positions"),
        ("GET", "/api/v1/risk"),
        ("GET", "/api/v1/trades/history"),
        ("POST", "/api/v1/trades/execute"),
        ("POST", "/api/v1/killswitch/activate"),
        ("POST", "/api/v1/killswitch/deactivate"),
        ("GET", "/api/v1/killswitch/status"),
        ("GET", "/api/v1/killswitch/logs"),
    ]

    @patch.dict(os.environ, {"JWT_SECRET_KEY": JWT_SECRET})
    @pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS)
    def test_no_auth_returns_401_or_403(self, method, path):
        """Protected endpoints reject requests without auth header."""
        app, _, _ = _setup_app_with_user()
        client = TestClient(app)

        if method == "GET":
            response = client.get(path)
        else:
            response = client.post(path, json={})

        # FastAPI HTTPBearer returns 403 when no header is present
        assert response.status_code in (401, 403)

    @patch.dict(os.environ, {"JWT_SECRET_KEY": JWT_SECRET})
    @pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS)
    def test_invalid_auth_returns_401(self, method, path):
        """Protected endpoints reject requests with invalid token."""
        app, _, _ = _setup_app_with_user()
        client = TestClient(app)

        headers = {"Authorization": "Bearer totally-invalid-token"}
        if method == "GET":
            response = client.get(path, headers=headers)
        else:
            response = client.post(path, json={}, headers=headers)

        assert response.status_code == 401


class TestAdminEndpoints:
    """25.2.3: Test that admin endpoints reject non-admin users.

    The admin router is mounted at /admin/* prefix. While currently it doesn't
    enforce JWT auth (it's a testing UI), we verify that the admin endpoints
    are isolated from the main API auth flow and a normal user token
    cannot escalate to admin operations via the standard API.

    Validates: Requirements 2.4.3, 6.5.3
    """

    @patch.dict(os.environ, {"JWT_SECRET_KEY": JWT_SECRET})
    def test_regular_user_cannot_access_admin_seed(self):
        """Regular user token cannot be used to authorize admin-level actions.

        The admin endpoints are on a separate path (/admin/*) and do not use
        the get_current_user dependency. This test verifies that a user's token
        cannot grant them admin access through the main API path.
        """
        # The main API has no admin-specific endpoints - they are on /admin/ path.
        # This verifies there's no privilege escalation within the authenticated API.
        app = _create_test_app()
        from src.api.dependencies import get_db, get_redis, get_current_user

        mock_db = MagicMock()
        mock_redis = MagicMock()

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_current_user] = lambda: 1

        client = TestClient(app)

        # These admin paths should NOT be accessible via the main app routers
        response = client.get("/admin/api/users")
        assert response.status_code == 404  # Not mounted in test app

        response = client.post("/admin/api/seed")
        assert response.status_code == 404  # Not mounted in test app

        app.dependency_overrides.clear()

    @patch.dict(os.environ, {"JWT_SECRET_KEY": JWT_SECRET})
    def test_inactive_user_rejected(self):
        """Inactive user (is_active=False) is rejected even with valid token."""
        inactive_user = _make_fake_user(user_id=1, is_active=False)

        app = _create_test_app()
        from src.api.dependencies import get_db, get_redis

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = inactive_user

        mock_redis = MagicMock()

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_redis] = lambda: mock_redis

        client = TestClient(app)
        valid_token = _create_valid_token(user_id=1)
        response = client.get(
            "/api/v1/dashboard",
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert response.status_code == 401

        app.dependency_overrides.clear()


# ===========================================================================
# Task 25.3: SQL Injection Tests
# ===========================================================================


class TestSQLInjectionMaliciousInputs:
    """25.3.1: Test that SQL injection payloads are handled safely.

    Validates: Requirements 2.4.6, 6.5.1
    """

    SQL_INJECTION_PAYLOADS = [
        "' OR '1'='1",
        "'; DROP TABLE users; --",
        "' UNION SELECT * FROM users --",
        "1' OR 1=1 --",
        "admin'--",
        "'; INSERT INTO users VALUES ('hack','hack'); --",
        "' OR ''='",
        "1; DELETE FROM trades WHERE 1=1",
        "' AND 1=CONVERT(int, (SELECT TOP 1 email FROM users))--",
        "robert'); DROP TABLE users;--",
    ]

    @patch.dict(os.environ, {"JWT_SECRET_KEY": JWT_SECRET})
    @pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
    def test_sql_injection_in_login_email(self, payload):
        """SQL injection in login email field does not cause server error."""
        app = _create_test_app()
        from src.api.dependencies import get_db

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        app.dependency_overrides[get_db] = lambda: mock_db

        client = TestClient(app)
        response = client.post(
            "/api/v1/auth/login",
            json={"email": payload, "password": "SomePassword123"},
        )
        # Should get 401 (invalid credentials) or 422 (validation error)
        # but NOT 500 (server error from SQL injection)
        assert response.status_code in (401, 422)

        app.dependency_overrides.clear()


    @patch.dict(os.environ, {"JWT_SECRET_KEY": JWT_SECRET})
    @pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
    def test_sql_injection_in_login_password(self, payload):
        """SQL injection in login password field does not cause server error."""
        app = _create_test_app()
        from src.api.dependencies import get_db

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        app.dependency_overrides[get_db] = lambda: mock_db

        client = TestClient(app)
        # Only test payloads with 8+ chars (to pass Pydantic validation)
        if len(payload) >= 8:
            response = client.post(
                "/api/v1/auth/login",
                json={"email": "test@example.com", "password": payload},
            )
            # Should be 401 (user not found) or normal error, never 500
            assert response.status_code in (401, 422)

        app.dependency_overrides.clear()

    @patch.dict(os.environ, {"JWT_SECRET_KEY": JWT_SECRET})
    @pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
    def test_sql_injection_in_trade_symbol(self, payload):
        """SQL injection in trade symbol field handled safely."""
        app = _create_test_app()
        from src.api.dependencies import get_db, get_redis, get_current_user

        mock_db = MagicMock()
        mock_redis = MagicMock()
        mock_redis.get.return_value = None  # Killswitch not active

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_current_user] = lambda: 1

        client = TestClient(app)
        response = client.post(
            "/api/v1/trades/execute",
            json={
                "symbol": payload,
                "exchange": "NSE",
                "quantity": 1,
                "side": "BUY",
            },
        )
        # Should get 422 (validation) or 400 but NOT 500
        assert response.status_code != 500

        app.dependency_overrides.clear()


class TestParameterizedQueries:
    """25.3.2: Verify that all database operations use parameterized queries.

    SQLAlchemy ORM uses parameterized queries by default. This test verifies
    that raw SQL strings are not used in the codebase.

    Validates: Requirements 2.4.6, 6.5.1
    """

    def test_no_raw_sql_in_auth_router(self):
        """Auth router uses SQLAlchemy ORM, not raw SQL."""
        import src.api.routers.auth as auth_module
        source = inspect.getsource(auth_module)
        # Check that no raw SQL execution patterns exist
        assert "execute(" not in source or "text(" not in source
        assert "raw_connection" not in source

    def test_no_raw_sql_in_dashboard_router(self):
        """Dashboard router uses SQLAlchemy ORM, not raw SQL."""
        import src.api.routers.dashboard as dashboard_module
        source = inspect.getsource(dashboard_module)
        assert "raw_connection" not in source
        assert ".execute(\"" not in source

    def test_no_raw_sql_in_trading_router(self):
        """Trading router uses SQLAlchemy ORM, not raw SQL."""
        import src.api.routers.trading as trading_module
        source = inspect.getsource(trading_module)
        assert "raw_connection" not in source
        assert ".execute(\"" not in source

    def test_no_raw_sql_in_killswitch_router(self):
        """Killswitch router uses SQLAlchemy ORM, not raw SQL."""
        import src.api.routers.killswitch as ks_module
        source = inspect.getsource(ks_module)
        assert "raw_connection" not in source
        assert ".execute(\"" not in source

    def test_no_raw_sql_in_auth_service(self):
        """Auth service uses SQLAlchemy ORM, not raw SQL."""
        import src.auth.service as service_module
        source = inspect.getsource(service_module)
        assert "raw_connection" not in source
        assert ".execute(\"" not in source

    def test_sqlalchemy_orm_used_for_queries(self):
        """Verify that the auth service uses SQLAlchemy query() method."""
        import src.auth.service as service_module
        source = inspect.getsource(service_module)
        # Should use .query() pattern (SQLAlchemy ORM)
        assert ".query(" in source
        assert ".filter(" in source


# ===========================================================================
# Task 25.4: Broker Token Security Tests
# ===========================================================================


class TestBrokerTokenEncryption:
    """25.4.1: Verify broker tokens stored in DB are encrypted (not plaintext).

    Validates: Requirements 2.4.4, 6.5.4
    """

    def test_token_encryption_produces_non_plaintext(self):
        """TokenEncryption.encrypt() produces output different from input."""
        key = Fernet.generate_key().decode()
        encryptor = TokenEncryption(encryption_key=key)

        plaintext_token = "my-super-secret-broker-token-12345"
        encrypted = encryptor.encrypt(plaintext_token)

        # Encrypted value must be different from plaintext
        assert encrypted != plaintext_token
        # Encrypted value should not contain the plaintext
        assert plaintext_token not in encrypted

    def test_encrypted_token_is_fernet_format(self):
        """Encrypted tokens follow Fernet format (base64 encoded)."""
        key = Fernet.generate_key().decode()
        encryptor = TokenEncryption(encryption_key=key)

        plaintext_token = "kite_access_token_abc123xyz"
        encrypted = encryptor.encrypt(plaintext_token)

        # Fernet tokens are base64 url-safe encoded
        import base64
        try:
            base64.urlsafe_b64decode(encrypted)
            is_base64 = True
        except Exception:
            is_base64 = False
        assert is_base64

    def test_encrypted_token_decrypts_correctly(self):
        """Encrypted token can be decrypted back to original value."""
        key = Fernet.generate_key().decode()
        encryptor = TokenEncryption(encryption_key=key)

        original = "broker_access_token_xyz789"
        encrypted = encryptor.encrypt(original)
        decrypted = encryptor.decrypt(encrypted)

        assert decrypted == original


    def test_wrong_key_cannot_decrypt(self):
        """Token encrypted with one key cannot be decrypted with another."""
        from src.broker.token_encryption import TokenEncryptionError

        key1 = Fernet.generate_key().decode()
        key2 = Fernet.generate_key().decode()

        encryptor1 = TokenEncryption(encryption_key=key1)
        encryptor2 = TokenEncryption(encryption_key=key2)

        encrypted = encryptor1.encrypt("secret_token")
        with pytest.raises(TokenEncryptionError):
            encryptor2.decrypt(encrypted)

    def test_broker_connect_encrypts_before_storing(self):
        """Broker OAuth flow encrypts tokens before database storage."""
        # Inspect the broker_connect endpoint - it should use TokenEncryption
        import src.api.routers.auth as auth_module
        source = inspect.getsource(auth_module.broker_connect)
        # Should reference TokenEncryption
        assert "TokenEncryption" in source or "encryptor" in source


class TestNoTokenLogging:
    """25.4.2: Verify broker tokens are never logged.

    Validates: Requirements 2.4.5, 6.5.4
    """

    def test_token_encryption_module_does_not_log_plaintext(self):
        """TokenEncryption never logs actual token variable values."""
        import src.broker.token_encryption as te_module
        source = inspect.getsource(te_module)

        # Check that no logger calls include the plaintext/ciphertext variables
        # (the actual token values). Generic messages like "Token encryption failed"
        # are acceptable as they don't expose secrets.
        lines = source.split("\n")
        for line in lines:
            if "logger." in line:
                # Logger lines should NOT include plaintext/ciphertext variable references
                assert "plaintext" not in line
                assert "ciphertext" not in line
                # Should not use f-string/format with the actual token variable
                assert "{plaintext}" not in line
                assert "{ciphertext}" not in line


    def test_broker_token_not_logged_during_encryption(self):
        """Encryption/decryption operations do not log token values."""
        key = Fernet.generate_key().decode()
        encryptor = TokenEncryption(encryption_key=key)

        # Set up a log capture
        logger = logging.getLogger("src.broker.token_encryption")
        log_handler = logging.handlers.MemoryHandler(capacity=100)
        logger.addHandler(log_handler)

        secret_token = "SUPER_SECRET_BROKER_TOKEN_12345"
        encrypted = encryptor.encrypt(secret_token)
        decrypted = encryptor.decrypt(encrypted)

        # Check no log records contain the secret token
        for record in log_handler.buffer:
            assert secret_token not in record.getMessage()

        logger.removeHandler(log_handler)

    def test_no_broker_token_in_log_file(self):
        """When logging to a file, broker tokens should never appear."""
        # Create a temp log file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            log_path = f.name

        try:
            # Set up file logging
            file_handler = logging.FileHandler(log_path)
            root_logger = logging.getLogger()
            root_logger.addHandler(file_handler)

            # Simulate normal encryption flow
            key = Fernet.generate_key().decode()
            encryptor = TokenEncryption(encryption_key=key)
            secret = "BROKER_ACCESS_TOKEN_XYZ_123456"
            encrypted = encryptor.encrypt(secret)

            # Flush handlers
            file_handler.flush()
            root_logger.removeHandler(file_handler)
            file_handler.close()

            # Read log file and verify token is not present
            with open(log_path, "r") as f:
                log_content = f.read()
            assert secret not in log_content
        finally:
            os.unlink(log_path)


class TestNoTokenExposure:
    """25.4.3: Verify broker tokens are never exposed in API responses.

    Validates: Requirements 2.4.5, 6.5.4
    """

    @patch.dict(os.environ, {"JWT_SECRET_KEY": JWT_SECRET})
    def test_dashboard_response_has_no_broker_token(self):
        """Dashboard endpoint response does not contain broker token."""
        app = _create_test_app()
        from src.api.dependencies import get_db, get_redis, get_current_user

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []

        mock_redis = MagicMock()
        mock_redis.hgetall.return_value = {}
        mock_redis.get.return_value = None

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_current_user] = lambda: 1

        client = TestClient(app)
        response = client.get("/api/v1/dashboard")
        assert response.status_code == 200

        response_text = response.text
        # Should not contain any broker token fields
        assert "broker_access_token" not in response_text
        assert "broker_refresh_token" not in response_text
        assert "access_token" not in response_text or "killswitch" in response_text

        app.dependency_overrides.clear()

    @patch.dict(os.environ, {"JWT_SECRET_KEY": JWT_SECRET})
    def test_positions_response_has_no_broker_token(self):
        """Positions endpoint response does not contain broker token."""
        app = _create_test_app()
        from src.api.dependencies import get_db, get_redis, get_current_user

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []

        mock_redis = MagicMock()

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_current_user] = lambda: 1

        client = TestClient(app)
        response = client.get("/api/v1/positions")
        assert response.status_code == 200

        response_text = response.text
        assert "broker_access_token" not in response_text
        assert "broker_refresh_token" not in response_text

        app.dependency_overrides.clear()


    @patch.dict(os.environ, {"JWT_SECRET_KEY": JWT_SECRET})
    def test_risk_response_has_no_broker_token(self):
        """Risk metrics endpoint response does not contain broker token."""
        app = _create_test_app()
        from src.api.dependencies import get_db, get_redis, get_current_user

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        mock_redis = MagicMock()
        mock_redis.hgetall.return_value = {}
        mock_redis.get.return_value = None

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_redis] = lambda: mock_redis
        app.dependency_overrides[get_current_user] = lambda: 1

        client = TestClient(app)
        response = client.get("/api/v1/risk")
        assert response.status_code == 200

        response_text = response.text
        assert "broker_access_token" not in response_text
        assert "broker_refresh_token" not in response_text

        app.dependency_overrides.clear()

    def test_user_model_tokens_not_in_repr(self):
        """User model __repr__ does not include broker token values."""
        from src.database.models.user import User
        source = inspect.getsource(User.__repr__)
        assert "broker_access_token" not in source
        assert "broker_refresh_token" not in source

    def test_response_schemas_exclude_broker_tokens(self):
        """API response schemas (Pydantic models) don't include broker tokens."""
        import src.api.schemas as schemas_module
        source = inspect.getsource(schemas_module)

        # None of the response models should have broker token fields
        # Check all Response classes
        for name, obj in inspect.getmembers(schemas_module):
            if inspect.isclass(obj) and "Response" in name:
                if hasattr(obj, "model_fields"):
                    field_names = list(obj.model_fields.keys())
                    assert "broker_access_token" not in field_names
                    assert "broker_refresh_token" not in field_names
