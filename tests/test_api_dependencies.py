"""Tests for src/api/dependencies.py

Tests:
- get_db yields a session and closes it after use
- get_redis returns a RedisClient instance
- get_current_user extracts user_id from a valid token
- get_current_user raises 401 on invalid token
- get_current_user raises 401 on inactive user
"""

from unittest.mock import MagicMock, patch
import pytest

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from src.auth.jwt_handler import JWTHandler


# --------------------------------------------------------------------------
# 8.2.1: get_db tests
# --------------------------------------------------------------------------


class TestGetDb:
    """Tests for the database session dependency."""

    @patch("src.api.dependencies._get_session_factory")
    def test_get_db_yields_session_and_closes(self, mock_factory_fn):
        """get_db should yield a session and call close() on it after use."""
        from src.api.dependencies import get_db

        mock_session = MagicMock()
        mock_factory = MagicMock(return_value=mock_session)
        mock_factory_fn.return_value = mock_factory

        gen = get_db()
        session = next(gen)

        assert session is mock_session
        mock_session.close.assert_not_called()

        # Exhaust the generator (simulates request completion)
        with pytest.raises(StopIteration):
            next(gen)

        mock_session.close.assert_called_once()

    @patch("src.api.dependencies._get_session_factory")
    def test_get_db_closes_session_on_exception(self, mock_factory_fn):
        """get_db should close the session even if an exception occurs."""
        from src.api.dependencies import get_db

        mock_session = MagicMock()
        mock_factory = MagicMock(return_value=mock_session)
        mock_factory_fn.return_value = mock_factory

        gen = get_db()
        next(gen)

        # Simulate an exception during request processing
        with pytest.raises(RuntimeError):
            gen.throw(RuntimeError("simulated error"))

        mock_session.close.assert_called_once()


# --------------------------------------------------------------------------
# 8.2.2: get_redis tests
# --------------------------------------------------------------------------


class TestGetRedis:
    """Tests for the Redis client dependency."""

    @patch("src.api.dependencies.get_redis_client")
    def test_get_redis_returns_client(self, mock_get_redis):
        """get_redis should return the shared RedisClient instance."""
        from src.api.dependencies import get_redis

        mock_client = MagicMock()
        mock_get_redis.return_value = mock_client

        result = get_redis()

        assert result is mock_client
        mock_get_redis.assert_called_once()


# --------------------------------------------------------------------------
# 8.2.3: get_current_user tests
# --------------------------------------------------------------------------


class TestGetCurrentUser:
    """Tests for the current user dependency."""

    @pytest.fixture
    def jwt_handler(self):
        """Create a JWTHandler with a known secret."""
        return JWTHandler(secret_key="test-secret-key")

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return MagicMock()

    @pytest.mark.asyncio
    @patch("src.api.dependencies.JWT_SECRET_KEY", "test-secret-key")
    async def test_get_current_user_valid_token(self, jwt_handler, mock_db):
        """get_current_user should return user_id for a valid token."""
        from src.api.dependencies import get_current_user

        # Create a valid token
        token = jwt_handler.create_access_token(user_id=42)
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=token
        )

        # Mock user in database
        mock_user = MagicMock()
        mock_user.id = 42
        mock_user.is_active = True
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        result = await get_current_user(credentials=credentials, db=mock_db)

        assert result == 42

    @pytest.mark.asyncio
    @patch("src.api.dependencies.JWT_SECRET_KEY", "test-secret-key")
    async def test_get_current_user_invalid_token(self, mock_db):
        """get_current_user should raise 401 for an invalid token."""
        from src.api.dependencies import get_current_user

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="invalid.token.here"
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=credentials, db=mock_db)

        assert exc_info.value.status_code == 401
        assert "Invalid or expired token" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("src.api.dependencies.JWT_SECRET_KEY", "test-secret-key")
    async def test_get_current_user_expired_token(self, mock_db):
        """get_current_user should raise 401 for an expired token."""
        from src.api.dependencies import get_current_user
        import jwt as pyjwt
        from datetime import datetime, timedelta, timezone

        # Create an already-expired token
        payload = {
            "sub": "42",
            "type": "access",
            "iat": datetime.now(timezone.utc) - timedelta(hours=48),
            "exp": datetime.now(timezone.utc) - timedelta(hours=24),
        }
        token = pyjwt.encode(payload, "test-secret-key", algorithm="HS256")
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=token
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=credentials, db=mock_db)

        assert exc_info.value.status_code == 401
        assert "Invalid or expired token" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("src.api.dependencies.JWT_SECRET_KEY", "test-secret-key")
    async def test_get_current_user_user_not_found(self, jwt_handler, mock_db):
        """get_current_user should raise 401 if user not in database."""
        from src.api.dependencies import get_current_user

        token = jwt_handler.create_access_token(user_id=999)
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=token
        )

        # No user found
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=credentials, db=mock_db)

        assert exc_info.value.status_code == 401
        assert "User not found or inactive" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("src.api.dependencies.JWT_SECRET_KEY", "test-secret-key")
    async def test_get_current_user_inactive_user(self, jwt_handler, mock_db):
        """get_current_user should raise 401 for inactive users."""
        from src.api.dependencies import get_current_user

        token = jwt_handler.create_access_token(user_id=7)
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=token
        )

        # User exists but is inactive
        mock_user = MagicMock()
        mock_user.id = 7
        mock_user.is_active = False
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=credentials, db=mock_db)

        assert exc_info.value.status_code == 401
        assert "User not found or inactive" in exc_info.value.detail
