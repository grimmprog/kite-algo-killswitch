"""Tests for JWT Authentication Module.

Tests Requirements: 1.1.2, 1.1.3, 1.1.4, 1.1.5, 2.4.2
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import jwt
from datetime import datetime, timedelta, timezone
from hypothesis import given, strategies as st, settings

from src.auth.jwt_handler import JWTHandler
from src.auth.password import hash_password, verify_password


# --- JWT Handler Tests ---


class TestJWTHandlerInit:
    """Test JWTHandler initialization."""

    def test_valid_initialization(self):
        handler = JWTHandler(secret_key="test-secret-key")
        assert handler.secret_key == "test-secret-key"
        assert handler.algorithm == "HS256"

    def test_custom_algorithm(self):
        handler = JWTHandler(secret_key="test-secret", algorithm="HS384")
        assert handler.algorithm == "HS384"

    def test_empty_secret_raises(self):
        with pytest.raises(ValueError, match="Secret key cannot be empty"):
            JWTHandler(secret_key="")

    def test_none_secret_raises(self):
        with pytest.raises(ValueError, match="Secret key cannot be empty"):
            JWTHandler(secret_key=None)


class TestAccessTokenGeneration:
    """Test access token creation (Requirement 1.1.4)."""

    def setup_method(self):
        self.handler = JWTHandler(secret_key="test-secret-key-for-access-tokens")

    def test_creates_valid_token(self):
        token = self.handler.create_access_token(user_id=1)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_token_contains_user_id(self):
        token = self.handler.create_access_token(user_id=42)
        payload = jwt.decode(token, "test-secret-key-for-access-tokens", algorithms=["HS256"])
        assert payload["sub"] == "42"

    def test_token_type_is_access(self):
        token = self.handler.create_access_token(user_id=1)
        payload = jwt.decode(token, "test-secret-key-for-access-tokens", algorithms=["HS256"])
        assert payload["type"] == "access"

    def test_token_has_24h_expiry(self):
        token = self.handler.create_access_token(user_id=1)
        payload = jwt.decode(token, "test-secret-key-for-access-tokens", algorithms=["HS256"])
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        iat = datetime.fromtimestamp(payload["iat"], tz=timezone.utc)
        delta = exp - iat
        assert delta == timedelta(hours=24)

    def test_extra_claims_included(self):
        token = self.handler.create_access_token(
            user_id=1, extra_claims={"role": "admin", "tenant": "acme"}
        )
        payload = jwt.decode(token, "test-secret-key-for-access-tokens", algorithms=["HS256"])
        assert payload["role"] == "admin"
        assert payload["tenant"] == "acme"

    def test_invalid_user_id_zero(self):
        with pytest.raises(ValueError, match="user_id must be a positive integer"):
            self.handler.create_access_token(user_id=0)

    def test_invalid_user_id_negative(self):
        with pytest.raises(ValueError, match="user_id must be a positive integer"):
            self.handler.create_access_token(user_id=-1)

    def test_invalid_user_id_string(self):
        with pytest.raises(ValueError, match="user_id must be a positive integer"):
            self.handler.create_access_token(user_id="abc")


class TestRefreshTokenGeneration:
    """Test refresh token creation (Requirement 1.1.5)."""

    def setup_method(self):
        self.handler = JWTHandler(secret_key="test-secret-key-for-refresh-tokens")

    def test_creates_valid_token(self):
        token = self.handler.create_refresh_token(user_id=1)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_token_contains_user_id(self):
        token = self.handler.create_refresh_token(user_id=99)
        payload = jwt.decode(token, "test-secret-key-for-refresh-tokens", algorithms=["HS256"])
        assert payload["sub"] == "99"

    def test_token_type_is_refresh(self):
        token = self.handler.create_refresh_token(user_id=1)
        payload = jwt.decode(token, "test-secret-key-for-refresh-tokens", algorithms=["HS256"])
        assert payload["type"] == "refresh"

    def test_token_has_30_day_expiry(self):
        token = self.handler.create_refresh_token(user_id=1)
        payload = jwt.decode(token, "test-secret-key-for-refresh-tokens", algorithms=["HS256"])
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        iat = datetime.fromtimestamp(payload["iat"], tz=timezone.utc)
        delta = exp - iat
        assert delta == timedelta(days=30)

    def test_invalid_user_id_zero(self):
        with pytest.raises(ValueError, match="user_id must be a positive integer"):
            self.handler.create_refresh_token(user_id=0)

    def test_invalid_user_id_negative(self):
        with pytest.raises(ValueError, match="user_id must be a positive integer"):
            self.handler.create_refresh_token(user_id=-5)


class TestTokenVerification:
    """Test token verification (Requirement 2.4.2)."""

    def setup_method(self):
        self.handler = JWTHandler(secret_key="verify-test-secret")

    def test_verify_valid_access_token(self):
        token = self.handler.create_access_token(user_id=1)
        payload = self.handler.verify_token(token)
        assert payload["sub"] == "1"
        assert payload["type"] == "access"

    def test_verify_valid_refresh_token(self):
        token = self.handler.create_refresh_token(user_id=5)
        payload = self.handler.verify_token(token)
        assert payload["sub"] == "5"
        assert payload["type"] == "refresh"

    def test_expired_token_raises(self):
        # Manually create an expired token
        now = datetime.now(timezone.utc)
        payload = {
            "sub": 1,
            "type": "access",
            "iat": now - timedelta(hours=25),
            "exp": now - timedelta(hours=1),
        }
        expired_token = jwt.encode(payload, "verify-test-secret", algorithm="HS256")

        with pytest.raises(jwt.ExpiredSignatureError):
            self.handler.verify_token(expired_token)

    def test_tampered_token_raises(self):
        token = self.handler.create_access_token(user_id=1)
        # Tamper with the token by changing a character
        tampered = token[:-1] + ("A" if token[-1] != "A" else "B")

        with pytest.raises(jwt.InvalidTokenError):
            self.handler.verify_token(tampered)

    def test_wrong_secret_raises(self):
        token = self.handler.create_access_token(user_id=1)
        other_handler = JWTHandler(secret_key="different-secret")

        with pytest.raises(jwt.InvalidTokenError):
            other_handler.verify_token(token)

    def test_empty_token_raises(self):
        with pytest.raises(ValueError, match="Token cannot be empty"):
            self.handler.verify_token("")

    def test_malformed_token_raises(self):
        with pytest.raises(jwt.InvalidTokenError):
            self.handler.verify_token("not.a.valid.jwt.token")


class TestExtractUserId:
    """Test user_id extraction from token."""

    def setup_method(self):
        self.handler = JWTHandler(secret_key="extract-test-secret")

    def test_extract_from_access_token(self):
        token = self.handler.create_access_token(user_id=42)
        assert self.handler.extract_user_id(token) == 42

    def test_extract_from_refresh_token(self):
        token = self.handler.create_refresh_token(user_id=7)
        assert self.handler.extract_user_id(token) == 7

    def test_expired_token_raises(self):
        now = datetime.now(timezone.utc)
        payload = {
            "sub": 1,
            "type": "access",
            "iat": now - timedelta(hours=25),
            "exp": now - timedelta(hours=1),
        }
        expired_token = jwt.encode(payload, "extract-test-secret", algorithm="HS256")

        with pytest.raises(jwt.ExpiredSignatureError):
            self.handler.extract_user_id(expired_token)

    def test_missing_sub_raises(self):
        now = datetime.now(timezone.utc)
        payload = {
            "type": "access",
            "iat": now,
            "exp": now + timedelta(hours=1),
        }
        token = jwt.encode(payload, "extract-test-secret", algorithm="HS256")

        with pytest.raises(ValueError, match="Token does not contain user_id"):
            self.handler.extract_user_id(token)


# --- Password Hashing Tests ---


class TestPasswordHashing:
    """Test password hashing (Requirements 1.1.2, 1.1.3)."""

    def test_hash_valid_password(self):
        hashed = hash_password("SecurePass123")
        assert isinstance(hashed, str)
        assert hashed.startswith("$2b$12$")

    def test_hash_uses_cost_factor_12(self):
        hashed = hash_password("ValidPassword1")
        # bcrypt format: $2b$12$<salt+hash>
        assert "$2b$12$" in hashed

    def test_hash_different_for_same_password(self):
        hash1 = hash_password("SamePassword1")
        hash2 = hash_password("SamePassword1")
        # Different salts produce different hashes
        assert hash1 != hash2

    def test_minimum_length_exactly_8(self):
        # Exactly 8 characters should work
        hashed = hash_password("12345678")
        assert hashed.startswith("$2b$12$")

    def test_short_password_raises(self):
        with pytest.raises(ValueError, match="Password must be at least 8 characters"):
            hash_password("short")

    def test_7_char_password_raises(self):
        with pytest.raises(ValueError, match="Password must be at least 8 characters"):
            hash_password("1234567")

    def test_empty_password_raises(self):
        with pytest.raises(ValueError, match="Password must be at least 8 characters"):
            hash_password("")

    def test_none_password_raises(self):
        with pytest.raises(ValueError, match="Password must be at least 8 characters"):
            hash_password(None)


class TestPasswordVerification:
    """Test password verification (Requirement 1.1.2)."""

    def test_correct_password_verifies(self):
        password = "CorrectHorse42"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_wrong_password_fails(self):
        hashed = hash_password("CorrectPassword1")
        assert verify_password("WrongPassword1", hashed) is False

    def test_empty_password_returns_false(self):
        hashed = hash_password("ValidPassword1")
        assert verify_password("", hashed) is False

    def test_empty_hash_returns_false(self):
        assert verify_password("SomePassword1", "") is False

    def test_none_password_returns_false(self):
        hashed = hash_password("ValidPassword1")
        assert verify_password(None, hashed) is False

    def test_none_hash_returns_false(self):
        assert verify_password("SomePassword1", None) is False


# --- Property-Based Tests ---


class TestJWTProperties:
    """Property-based tests for JWT tokens.

    **Validates: Requirements 1.1.4, 1.1.5**
    """

    @given(user_id=st.integers(min_value=1, max_value=1_000_000))
    @settings(max_examples=50)
    def test_access_token_roundtrip(self, user_id):
        """Any valid user_id can be encoded and decoded from an access token."""
        handler = JWTHandler(secret_key="property-test-secret")
        token = handler.create_access_token(user_id=user_id)
        extracted = handler.extract_user_id(token)
        assert extracted == user_id

    @given(user_id=st.integers(min_value=1, max_value=1_000_000))
    @settings(max_examples=50)
    def test_refresh_token_roundtrip(self, user_id):
        """Any valid user_id can be encoded and decoded from a refresh token."""
        handler = JWTHandler(secret_key="property-test-secret")
        token = handler.create_refresh_token(user_id=user_id)
        extracted = handler.extract_user_id(token)
        assert extracted == user_id

    @given(user_id=st.integers(min_value=1, max_value=1_000_000))
    @settings(max_examples=50)
    def test_access_token_type_is_access(self, user_id):
        """Access tokens always have type 'access'."""
        handler = JWTHandler(secret_key="property-test-secret")
        token = handler.create_access_token(user_id=user_id)
        payload = handler.verify_token(token)
        assert payload["type"] == "access"

    @given(user_id=st.integers(min_value=1, max_value=1_000_000))
    @settings(max_examples=50)
    def test_refresh_token_type_is_refresh(self, user_id):
        """Refresh tokens always have type 'refresh'."""
        handler = JWTHandler(secret_key="property-test-secret")
        token = handler.create_refresh_token(user_id=user_id)
        payload = handler.verify_token(token)
        assert payload["type"] == "refresh"


class TestPasswordProperties:
    """Property-based tests for password hashing.

    **Validates: Requirements 1.1.2, 1.1.3**
    """

    @given(
        password=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N")),
            min_size=8,
            max_size=30,
        )
    )
    @settings(max_examples=20, deadline=None)
    def test_hash_verify_roundtrip(self, password):
        """Any valid password (>=8 chars, <=72 bytes) can be hashed and then verified."""
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    @given(
        password=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N")),
            min_size=8,
            max_size=30,
        )
    )
    @settings(max_examples=20, deadline=None)
    def test_hash_always_uses_cost_12(self, password):
        """All hashes use bcrypt cost factor 12."""
        hashed = hash_password(password)
        assert "$2b$12$" in hashed

    @given(
        password=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N")),
            min_size=1,
            max_size=7,
        )
    )
    @settings(max_examples=30)
    def test_short_passwords_rejected(self, password):
        """Passwords shorter than 8 characters are always rejected."""
        with pytest.raises(ValueError):
            hash_password(password)
