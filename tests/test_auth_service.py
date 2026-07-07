"""Tests for Authentication Service, Rate Limiter, and Exceptions.

Tests Requirements:
- 1.1.10: Support user logout and token invalidation
- 2.4.8: Rate limit login attempts (5 attempts per 15 minutes)
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, PropertyMock

from src.auth.exceptions import AuthenticationError
from src.auth.jwt_handler import JWTHandler
from src.auth.password import hash_password
from src.auth.rate_limiter import LoginRateLimiter
from src.auth.service import AuthService


# --- Fixtures ---


class FakeRedis:
    """In-memory fake Redis client for testing."""

    def __init__(self):
        self.store = {}
        self.ttls = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value):
        self.store[key] = value

    def incr(self, key):
        if key not in self.store:
            self.store[key] = 0
        self.store[key] = int(self.store[key]) + 1
        return self.store[key]

    def expire(self, key, seconds):
        self.ttls[key] = seconds

    def delete(self, key):
        self.store.pop(key, None)
        self.ttls.pop(key, None)

    def ttl(self, key):
        return self.ttls.get(key, -2)

    def pipeline(self):
        return FakePipeline(self)


class FakePipeline:
    """Fake Redis pipeline for testing."""

    def __init__(self, redis_client):
        self.redis_client = redis_client
        self.commands = []

    def incr(self, key):
        self.commands.append(("incr", key))
        return self

    def expire(self, key, seconds):
        self.commands.append(("expire", key, seconds))
        return self

    def execute(self):
        results = []
        for cmd in self.commands:
            if cmd[0] == "incr":
                results.append(self.redis_client.incr(cmd[1]))
            elif cmd[0] == "expire":
                self.redis_client.expire(cmd[1], cmd[2])
                results.append(True)
        self.commands = []
        return results


class FakeUser:
    """Fake User object for testing without database."""

    def __init__(self, id, email, password_hash, is_active=True, last_login=None):
        self.id = id
        self.email = email
        self.password_hash = password_hash
        self.is_active = is_active
        self.last_login = last_login


class FakeQuery:
    """Fake SQLAlchemy query for testing."""

    def __init__(self, users):
        self._users = users
        self._filters = []

    def filter(self, *args):
        # Simple filter simulation - stores the condition
        self._filters.append(args)
        return self

    def first(self):
        # Simple matching based on stored filters
        if not self._users:
            return None
        # Return first user that hasn't been filtered out
        return self._users[0] if self._users else None


class FakeSession:
    """Fake SQLAlchemy session for testing."""

    def __init__(self, users=None):
        self._users = users or []
        self._committed = False

    def query(self, model_class):
        return FakeQueryBuilder(self._users)

    def commit(self):
        self._committed = True

    def add(self, obj):
        pass


class FakeQueryBuilder:
    """Simulates SQLAlchemy's query builder with filter support."""

    def __init__(self, users):
        self._users = users
        self._email_filter = None
        self._id_filter = None

    def filter(self, condition):
        """Extract filter condition value from SQLAlchemy expression."""
        # Store the condition for later filtering
        self._last_condition = condition
        return self

    def first(self):
        """Return the first matching user."""
        # Check if we have a filter condition
        if hasattr(self, "_last_condition"):
            condition = self._last_condition
            # Try to extract the filter from SQLAlchemy BinaryExpression
            try:
                # For User.email == value
                right_value = condition.right.value
                left_key = condition.left.key
                for user in self._users:
                    if getattr(user, left_key, None) == right_value:
                        return user
                return None
            except (AttributeError, TypeError):
                pass
        # Fallback: return first user
        return self._users[0] if self._users else None


@pytest.fixture
def jwt_handler():
    return JWTHandler(secret_key="test-secret-for-auth-service")


@pytest.fixture
def fake_redis():
    return FakeRedis()


@pytest.fixture
def rate_limiter(fake_redis):
    return LoginRateLimiter(redis_client=fake_redis)


@pytest.fixture
def sample_password():
    return "SecurePass123"


@pytest.fixture
def sample_password_hash(sample_password):
    return hash_password(sample_password)


# --- AuthenticationError Tests ---


class TestAuthenticationError:
    """Test custom AuthenticationError exception."""

    def test_default_message(self):
        error = AuthenticationError()
        assert str(error) == "Authentication failed"
        assert error.message == "Authentication failed"

    def test_custom_message(self):
        error = AuthenticationError("Invalid credentials")
        assert str(error) == "Invalid credentials"
        assert error.message == "Invalid credentials"

    def test_is_exception(self):
        error = AuthenticationError("test")
        assert isinstance(error, Exception)

    def test_can_be_raised_and_caught(self):
        with pytest.raises(AuthenticationError, match="test error"):
            raise AuthenticationError("test error")


# --- LoginRateLimiter Tests ---


class TestLoginRateLimiterInit:
    """Test LoginRateLimiter initialization."""

    def test_valid_init(self, fake_redis):
        limiter = LoginRateLimiter(fake_redis, max_attempts=5, window_seconds=900)
        assert limiter.max_attempts == 5
        assert limiter.window_seconds == 900

    def test_default_values(self, fake_redis):
        limiter = LoginRateLimiter(fake_redis)
        assert limiter.max_attempts == 5
        assert limiter.window_seconds == 900

    def test_custom_values(self, fake_redis):
        limiter = LoginRateLimiter(fake_redis, max_attempts=3, window_seconds=60)
        assert limiter.max_attempts == 3
        assert limiter.window_seconds == 60

    def test_invalid_max_attempts_zero(self, fake_redis):
        with pytest.raises(ValueError, match="max_attempts must be a positive integer"):
            LoginRateLimiter(fake_redis, max_attempts=0)

    def test_invalid_max_attempts_negative(self, fake_redis):
        with pytest.raises(ValueError, match="max_attempts must be a positive integer"):
            LoginRateLimiter(fake_redis, max_attempts=-1)

    def test_invalid_window_seconds_zero(self, fake_redis):
        with pytest.raises(ValueError, match="window_seconds must be a positive integer"):
            LoginRateLimiter(fake_redis, window_seconds=0)

    def test_invalid_window_seconds_negative(self, fake_redis):
        with pytest.raises(ValueError, match="window_seconds must be a positive integer"):
            LoginRateLimiter(fake_redis, window_seconds=-100)


class TestLoginRateLimiterCheckLimit:
    """Test rate limit checking (Requirement 2.4.8)."""

    def test_first_attempt_allowed(self, rate_limiter):
        assert rate_limiter.check_rate_limit("user@example.com") is True

    def test_under_limit_allowed(self, rate_limiter, fake_redis):
        fake_redis.store["login_attempts:user@example.com"] = 4
        assert rate_limiter.check_rate_limit("user@example.com") is True

    def test_at_limit_blocked(self, rate_limiter, fake_redis):
        fake_redis.store["login_attempts:user@example.com"] = 5
        assert rate_limiter.check_rate_limit("user@example.com") is False

    def test_over_limit_blocked(self, rate_limiter, fake_redis):
        fake_redis.store["login_attempts:user@example.com"] = 10
        assert rate_limiter.check_rate_limit("user@example.com") is False

    def test_different_emails_isolated(self, rate_limiter, fake_redis):
        fake_redis.store["login_attempts:user1@example.com"] = 5
        assert rate_limiter.check_rate_limit("user1@example.com") is False
        assert rate_limiter.check_rate_limit("user2@example.com") is True


class TestLoginRateLimiterRecordAttempt:
    """Test recording login attempts."""

    def test_first_attempt_sets_counter(self, rate_limiter, fake_redis):
        rate_limiter.record_attempt("user@example.com")
        assert fake_redis.store["login_attempts:user@example.com"] == 1

    def test_subsequent_attempts_increment(self, rate_limiter, fake_redis):
        rate_limiter.record_attempt("user@example.com")
        rate_limiter.record_attempt("user@example.com")
        rate_limiter.record_attempt("user@example.com")
        assert fake_redis.store["login_attempts:user@example.com"] == 3

    def test_sets_ttl(self, rate_limiter, fake_redis):
        rate_limiter.record_attempt("user@example.com")
        assert fake_redis.ttls["login_attempts:user@example.com"] == 900


class TestLoginRateLimiterReset:
    """Test rate limit reset after successful login."""

    def test_reset_removes_counter(self, rate_limiter, fake_redis):
        fake_redis.store["login_attempts:user@example.com"] = 3
        rate_limiter.reset("user@example.com")
        assert "login_attempts:user@example.com" not in fake_redis.store

    def test_reset_nonexistent_key(self, rate_limiter):
        # Should not raise
        rate_limiter.reset("nonexistent@example.com")


class TestLoginRateLimiterRemainingAttempts:
    """Test remaining attempts calculation."""

    def test_no_attempts_returns_max(self, rate_limiter):
        remaining = rate_limiter.get_remaining_attempts("user@example.com")
        assert remaining == 5

    def test_some_attempts_returns_correct(self, rate_limiter, fake_redis):
        fake_redis.store["login_attempts:user@example.com"] = 3
        remaining = rate_limiter.get_remaining_attempts("user@example.com")
        assert remaining == 2

    def test_at_limit_returns_zero(self, rate_limiter, fake_redis):
        fake_redis.store["login_attempts:user@example.com"] = 5
        remaining = rate_limiter.get_remaining_attempts("user@example.com")
        assert remaining == 0

    def test_over_limit_returns_zero(self, rate_limiter, fake_redis):
        fake_redis.store["login_attempts:user@example.com"] = 10
        remaining = rate_limiter.get_remaining_attempts("user@example.com")
        assert remaining == 0


class TestLoginRateLimiterTTL:
    """Test TTL retrieval."""

    def test_no_active_limit_returns_none(self, rate_limiter):
        ttl = rate_limiter.get_ttl("user@example.com")
        assert ttl is None

    def test_active_limit_returns_ttl(self, rate_limiter, fake_redis):
        fake_redis.store["login_attempts:user@example.com"] = 3
        fake_redis.ttls["login_attempts:user@example.com"] = 450
        ttl = rate_limiter.get_ttl("user@example.com")
        assert ttl == 450


# --- AuthService Tests ---


class TestAuthServiceAuthenticate:
    """Test AuthService.authenticate_user (Tasks 3.4.1, 3.4.2, 3.4.3)."""

    def _make_service(self, users, jwt_handler, rate_limiter=None):
        """Create AuthService with fake dependencies."""
        session = MagicMock()
        # Setup query chain mock
        query_mock = MagicMock()
        filter_mock = MagicMock()
        session.query.return_value = query_mock
        query_mock.filter.return_value = filter_mock

        if users:
            filter_mock.first.return_value = users[0]
        else:
            filter_mock.first.return_value = None

        return AuthService(
            jwt_handler=jwt_handler,
            db_session=session,
            rate_limiter=rate_limiter,
        )

    def test_successful_login(self, jwt_handler, sample_password, sample_password_hash):
        user = FakeUser(id=1, email="user@example.com", password_hash=sample_password_hash)
        service = self._make_service([user], jwt_handler)

        result = service.authenticate_user("user@example.com", sample_password)

        assert "access_token" in result
        assert "refresh_token" in result
        assert result["token_type"] == "bearer"
        assert result["user_id"] == 1

    def test_access_token_valid(self, jwt_handler, sample_password, sample_password_hash):
        user = FakeUser(id=42, email="user@example.com", password_hash=sample_password_hash)
        service = self._make_service([user], jwt_handler)

        result = service.authenticate_user("user@example.com", sample_password)

        # Verify the access token is valid
        payload = jwt_handler.verify_token(result["access_token"])
        assert payload["sub"] == "42"
        assert payload["type"] == "access"

    def test_refresh_token_valid(self, jwt_handler, sample_password, sample_password_hash):
        user = FakeUser(id=42, email="user@example.com", password_hash=sample_password_hash)
        service = self._make_service([user], jwt_handler)

        result = service.authenticate_user("user@example.com", sample_password)

        # Verify the refresh token is valid
        payload = jwt_handler.verify_token(result["refresh_token"])
        assert payload["sub"] == "42"
        assert payload["type"] == "refresh"

    def test_invalid_email_raises(self, jwt_handler, sample_password):
        service = self._make_service([], jwt_handler)

        with pytest.raises(AuthenticationError, match="Invalid email or password"):
            service.authenticate_user("unknown@example.com", sample_password)

    def test_invalid_password_raises(self, jwt_handler, sample_password_hash):
        user = FakeUser(id=1, email="user@example.com", password_hash=sample_password_hash)
        service = self._make_service([user], jwt_handler)

        with pytest.raises(AuthenticationError, match="Invalid email or password"):
            service.authenticate_user("user@example.com", "WrongPassword123")

    def test_inactive_user_raises(self, jwt_handler, sample_password, sample_password_hash):
        user = FakeUser(
            id=1, email="user@example.com",
            password_hash=sample_password_hash, is_active=False
        )
        service = self._make_service([user], jwt_handler)

        with pytest.raises(AuthenticationError, match="Account is deactivated"):
            service.authenticate_user("user@example.com", sample_password)

    def test_empty_email_raises(self, jwt_handler):
        service = self._make_service([], jwt_handler)

        with pytest.raises(AuthenticationError, match="Email and password are required"):
            service.authenticate_user("", "password123")

    def test_empty_password_raises(self, jwt_handler):
        service = self._make_service([], jwt_handler)

        with pytest.raises(AuthenticationError, match="Email and password are required"):
            service.authenticate_user("user@example.com", "")

    def test_updates_last_login(self, jwt_handler, sample_password, sample_password_hash):
        user = FakeUser(id=1, email="user@example.com", password_hash=sample_password_hash)
        service = self._make_service([user], jwt_handler)

        service.authenticate_user("user@example.com", sample_password)

        # Verify commit was called (last_login update)
        service.db_session.commit.assert_called()

    def test_rate_limited_raises(self, jwt_handler, fake_redis, sample_password):
        rate_limiter = LoginRateLimiter(fake_redis)
        # Set attempts to max
        fake_redis.store["login_attempts:user@example.com"] = 5

        service = self._make_service([], jwt_handler, rate_limiter=rate_limiter)

        with pytest.raises(AuthenticationError, match="Too many login attempts"):
            service.authenticate_user("user@example.com", sample_password)

    def test_rate_limit_records_attempt(
        self, jwt_handler, fake_redis, sample_password, sample_password_hash
    ):
        rate_limiter = LoginRateLimiter(fake_redis)
        user = FakeUser(id=1, email="user@example.com", password_hash=sample_password_hash)
        service = self._make_service([user], jwt_handler, rate_limiter=rate_limiter)

        service.authenticate_user("user@example.com", sample_password)

        # After successful login, rate limit should be reset
        assert fake_redis.store.get("login_attempts:user@example.com") is None

    def test_works_without_rate_limiter(self, jwt_handler, sample_password, sample_password_hash):
        user = FakeUser(id=1, email="user@example.com", password_hash=sample_password_hash)
        service = self._make_service([user], jwt_handler, rate_limiter=None)

        result = service.authenticate_user("user@example.com", sample_password)
        assert result["user_id"] == 1


class TestAuthServiceRefreshToken:
    """Test AuthService.refresh_access_token (Task 3.5)."""

    def _make_service(self, users, jwt_handler):
        """Create AuthService with fake dependencies."""
        session = MagicMock()
        query_mock = MagicMock()
        filter_mock = MagicMock()
        session.query.return_value = query_mock
        query_mock.filter.return_value = filter_mock

        if users:
            filter_mock.first.return_value = users[0]
        else:
            filter_mock.first.return_value = None

        return AuthService(jwt_handler=jwt_handler, db_session=session)

    def test_valid_refresh_returns_new_access_token(self, jwt_handler):
        user = FakeUser(id=5, email="user@example.com", password_hash="hash")
        service = self._make_service([user], jwt_handler)

        refresh_token = jwt_handler.create_refresh_token(user_id=5)
        result = service.refresh_access_token(refresh_token)

        assert "access_token" in result
        assert result["token_type"] == "bearer"

        # Verify new access token is valid
        payload = jwt_handler.verify_token(result["access_token"])
        assert payload["sub"] == "5"
        assert payload["type"] == "access"

    def test_empty_token_raises(self, jwt_handler):
        service = self._make_service([], jwt_handler)

        with pytest.raises(AuthenticationError, match="Refresh token is required"):
            service.refresh_access_token("")

    def test_invalid_token_raises(self, jwt_handler):
        service = self._make_service([], jwt_handler)

        with pytest.raises(AuthenticationError, match="Invalid refresh token"):
            service.refresh_access_token("not.a.valid.token")

    def test_access_token_as_refresh_raises(self, jwt_handler):
        user = FakeUser(id=1, email="user@example.com", password_hash="hash")
        service = self._make_service([user], jwt_handler)

        # Use an access token instead of a refresh token
        access_token = jwt_handler.create_access_token(user_id=1)

        with pytest.raises(AuthenticationError, match="Invalid refresh token"):
            service.refresh_access_token(access_token)

    def test_user_not_found_raises(self, jwt_handler):
        service = self._make_service([], jwt_handler)

        refresh_token = jwt_handler.create_refresh_token(user_id=999)

        with pytest.raises(AuthenticationError, match="User not found"):
            service.refresh_access_token(refresh_token)

    def test_inactive_user_raises(self, jwt_handler):
        user = FakeUser(id=1, email="user@example.com", password_hash="hash", is_active=False)
        service = self._make_service([user], jwt_handler)

        refresh_token = jwt_handler.create_refresh_token(user_id=1)

        with pytest.raises(AuthenticationError, match="Account is deactivated"):
            service.refresh_access_token(refresh_token)

    def test_wrong_secret_raises(self, jwt_handler):
        user = FakeUser(id=1, email="user@example.com", password_hash="hash")
        service = self._make_service([user], jwt_handler)

        # Create token with different secret
        other_handler = JWTHandler(secret_key="different-secret")
        refresh_token = other_handler.create_refresh_token(user_id=1)

        with pytest.raises(AuthenticationError, match="Invalid refresh token"):
            service.refresh_access_token(refresh_token)


class TestAuthServiceLogout:
    """Test AuthService.logout (Task 3.6, Requirement 1.1.10)."""

    def _make_service(self, users, jwt_handler):
        """Create AuthService with fake dependencies."""
        session = MagicMock()
        query_mock = MagicMock()
        filter_mock = MagicMock()
        session.query.return_value = query_mock
        query_mock.filter.return_value = filter_mock

        if users:
            filter_mock.first.return_value = users[0]
        else:
            filter_mock.first.return_value = None

        return AuthService(jwt_handler=jwt_handler, db_session=session)

    def test_successful_logout(self, jwt_handler):
        user = FakeUser(id=1, email="user@example.com", password_hash="hash")
        service = self._make_service([user], jwt_handler)

        result = service.logout(user_id=1)

        assert result is True
        service.db_session.commit.assert_called()

    def test_user_not_found_returns_false(self, jwt_handler):
        service = self._make_service([], jwt_handler)

        result = service.logout(user_id=999)

        assert result is False

    def test_updates_last_login(self, jwt_handler):
        user = FakeUser(id=1, email="user@example.com", password_hash="hash")
        service = self._make_service([user], jwt_handler)

        service.logout(user_id=1)

        # last_login should be updated
        assert user.last_login is not None


# --- Integration-style Tests ---


class TestRateLimitIntegration:
    """Test rate limiting integration with auth service (Requirement 2.4.8)."""

    def _make_service(self, users, jwt_handler, rate_limiter):
        """Create AuthService with fake dependencies."""
        session = MagicMock()
        query_mock = MagicMock()
        filter_mock = MagicMock()
        session.query.return_value = query_mock
        query_mock.filter.return_value = filter_mock

        if users:
            filter_mock.first.return_value = users[0]
        else:
            filter_mock.first.return_value = None

        return AuthService(
            jwt_handler=jwt_handler,
            db_session=session,
            rate_limiter=rate_limiter,
        )

    def test_five_failed_attempts_blocks(self, jwt_handler, fake_redis):
        rate_limiter = LoginRateLimiter(fake_redis)
        service = self._make_service([], jwt_handler, rate_limiter)

        # Simulate 5 failed login attempts
        for i in range(5):
            with pytest.raises(AuthenticationError):
                service.authenticate_user("user@example.com", "WrongPass123")

        # 6th attempt should be rate limited
        with pytest.raises(AuthenticationError, match="Too many login attempts"):
            service.authenticate_user("user@example.com", "AnyPassword123")

    def test_successful_login_resets_counter(
        self, jwt_handler, fake_redis, sample_password, sample_password_hash
    ):
        rate_limiter = LoginRateLimiter(fake_redis)
        user = FakeUser(id=1, email="user@example.com", password_hash=sample_password_hash)
        service = self._make_service([user], jwt_handler, rate_limiter)

        # Simulate 3 failed attempts
        for i in range(3):
            with pytest.raises(AuthenticationError):
                service.authenticate_user("user@example.com", "WrongPass123")

        # Successful login should reset
        result = service.authenticate_user("user@example.com", sample_password)
        assert result["user_id"] == 1

        # Counter should be reset
        assert rate_limiter.get_remaining_attempts("user@example.com") == 5
