"""Tests for the broker integration module.

Tests cover:
- TokenEncryption: Fernet-based encryption/decryption
- ZerodhaOAuth: OAuth flow (login URL, callback, token storage)
- KiteClientFactory: Client creation, token validity, auth error handling
- TokenRefreshService: Token expiry checking, refresh logic, failure handling
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet

from src.broker.token_encryption import TokenEncryption, TokenEncryptionError
from src.broker.oauth import ZerodhaOAuth, OAuthError
from src.broker.kite_client_factory import (
    KiteClientFactory,
    BrokerAuthError,
    TokenExpiredError,
)
from src.broker.token_refresh import TokenRefreshService, TokenRefreshError


# ============================================================
# TokenEncryption Tests
# ============================================================


class TestTokenEncryption:
    """Tests for Fernet-based token encryption."""

    @pytest.fixture
    def valid_key(self):
        """Generate a valid Fernet key for testing."""
        return Fernet.generate_key().decode()

    @pytest.fixture
    def encryptor(self, valid_key):
        """Create a TokenEncryption instance with a valid key."""
        return TokenEncryption(valid_key)

    def test_init_with_valid_key(self, valid_key):
        """Test initialization with a valid Fernet key."""
        enc = TokenEncryption(valid_key)
        assert enc is not None

    def test_init_with_empty_key_raises(self):
        """Test that empty key raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            TokenEncryption("")

    def test_init_with_none_key_raises(self):
        """Test that None key raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            TokenEncryption(None)

    def test_init_with_invalid_key_raises(self):
        """Test that invalid key format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid Fernet encryption key"):
            TokenEncryption("not-a-valid-fernet-key")

    def test_encrypt_returns_string(self, encryptor):
        """Test that encrypt returns a non-empty string."""
        result = encryptor.encrypt("my_secret_token")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_encrypt_different_from_plaintext(self, encryptor):
        """Test that encrypted value differs from plaintext."""
        plaintext = "my_secret_token"
        encrypted = encryptor.encrypt(plaintext)
        assert encrypted != plaintext

    def test_encrypt_empty_string_raises(self, encryptor):
        """Test that encrypting empty string raises ValueError."""
        with pytest.raises(ValueError, match="Cannot encrypt empty"):
            encryptor.encrypt("")

    def test_decrypt_roundtrip(self, encryptor):
        """Test that encrypt then decrypt returns original value."""
        plaintext = "access_token_abc123"
        encrypted = encryptor.encrypt(plaintext)
        decrypted = encryptor.decrypt(encrypted)
        assert decrypted == plaintext

    def test_decrypt_with_wrong_key_raises(self, encryptor):
        """Test that decrypting with wrong key raises error."""
        encrypted = encryptor.encrypt("secret")
        other_key = Fernet.generate_key().decode()
        other_encryptor = TokenEncryption(other_key)

        with pytest.raises(TokenEncryptionError):
            other_encryptor.decrypt(encrypted)

    def test_decrypt_empty_string_raises(self, encryptor):
        """Test that decrypting empty string raises ValueError."""
        with pytest.raises(ValueError, match="Cannot decrypt empty"):
            encryptor.decrypt("")

    def test_decrypt_corrupted_data_raises(self, encryptor):
        """Test that decrypting corrupted data raises error."""
        with pytest.raises(TokenEncryptionError):
            encryptor.decrypt("not-valid-encrypted-data")

    def test_generate_key_returns_valid_key(self):
        """Test that generate_key produces a usable key."""
        key = TokenEncryption.generate_key()
        assert isinstance(key, str)
        # Should be able to create an encryptor with it
        enc = TokenEncryption(key)
        assert enc.decrypt(enc.encrypt("test")) == "test"

    def test_encrypt_different_values_produce_different_ciphertexts(self, encryptor):
        """Test that different plaintexts produce different ciphertexts."""
        enc1 = encryptor.encrypt("token_a")
        enc2 = encryptor.encrypt("token_b")
        assert enc1 != enc2

    def test_encrypt_same_value_produces_different_ciphertexts(self, encryptor):
        """Fernet uses random IV so same plaintext gives different ciphertexts."""
        enc1 = encryptor.encrypt("same_token")
        enc2 = encryptor.encrypt("same_token")
        assert enc1 != enc2  # Different due to random IV

    def test_roundtrip_with_special_characters(self, encryptor):
        """Test encryption/decryption with special characters in token."""
        token = "abc!@#$%^&*()_+-=[]{}|;':\",./<>?"
        assert encryptor.decrypt(encryptor.encrypt(token)) == token

    def test_roundtrip_with_long_token(self, encryptor):
        """Test encryption/decryption with a long token string."""
        token = "x" * 1000
        assert encryptor.decrypt(encryptor.encrypt(token)) == token


# ============================================================
# ZerodhaOAuth Tests
# ============================================================


class TestZerodhaOAuth:
    """Tests for Zerodha OAuth flow."""

    @pytest.fixture
    def oauth(self):
        """Create a ZerodhaOAuth instance with mock KiteConnect."""
        with patch("src.broker.oauth.KiteConnect") as MockKite:
            mock_instance = MagicMock()
            MockKite.return_value = mock_instance
            mock_instance.login_url.return_value = "https://kite.zerodha.com/connect/login?v=3&api_key=test_key"

            oauth_service = ZerodhaOAuth(
                api_key="test_key",
                api_secret="test_secret",
                redirect_url="http://localhost:8000/callback",
            )
            oauth_service._kite = mock_instance
            return oauth_service

    def test_init_with_valid_params(self):
        """Test initialization with valid parameters."""
        with patch("src.broker.oauth.KiteConnect"):
            oauth = ZerodhaOAuth(
                api_key="key",
                api_secret="secret",
                redirect_url="http://example.com/callback",
            )
            assert oauth.api_key == "key"
            assert oauth.api_secret == "secret"
            assert oauth.redirect_url == "http://example.com/callback"

    def test_init_empty_api_key_raises(self):
        """Test that empty api_key raises ValueError."""
        with pytest.raises(ValueError, match="API key cannot be empty"):
            ZerodhaOAuth(api_key="", api_secret="secret", redirect_url="http://x.com")

    def test_init_empty_api_secret_raises(self):
        """Test that empty api_secret raises ValueError."""
        with pytest.raises(ValueError, match="API secret cannot be empty"):
            ZerodhaOAuth(api_key="key", api_secret="", redirect_url="http://x.com")

    def test_init_empty_redirect_url_raises(self):
        """Test that empty redirect_url raises ValueError."""
        with pytest.raises(ValueError, match="Redirect URL cannot be empty"):
            ZerodhaOAuth(api_key="key", api_secret="secret", redirect_url="")

    def test_get_login_url(self, oauth):
        """Test login URL generation."""
        url = oauth.get_login_url()
        assert "kite.zerodha.com" in url
        assert "test_key" in url

    def test_handle_callback_success(self, oauth):
        """Test successful token exchange."""
        oauth._kite.generate_session.return_value = {
            "access_token": "access_123",
            "public_token": "public_456",
        }

        result = oauth.handle_callback("request_token_abc")
        assert result["access_token"] == "access_123"
        assert result["public_token"] == "public_456"

        oauth._kite.generate_session.assert_called_once_with(
            request_token="request_token_abc",
            api_secret="test_secret",
        )

    def test_handle_callback_empty_request_token_raises(self, oauth):
        """Test that empty request_token raises ValueError."""
        with pytest.raises(ValueError, match="Request token cannot be empty"):
            oauth.handle_callback("")

    def test_handle_callback_no_access_token_in_response(self, oauth):
        """Test that missing access_token in response raises OAuthError."""
        oauth._kite.generate_session.return_value = {
            "public_token": "public_456",
        }

        with pytest.raises(OAuthError, match="No access token"):
            oauth.handle_callback("request_token")

    def test_handle_callback_api_error(self, oauth):
        """Test that API error raises OAuthError."""
        oauth._kite.generate_session.side_effect = Exception("Network error")

        with pytest.raises(OAuthError, match="Failed to exchange"):
            oauth.handle_callback("request_token")

    def test_store_tokens_success(self, oauth):
        """Test successful token storage with encryption."""
        key = Fernet.generate_key().decode()
        encryptor = TokenEncryption(key)

        mock_user = MagicMock()
        mock_user.broker_access_token = None
        mock_user.broker_refresh_token = None
        mock_user.broker_token_expiry = None

        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = mock_user

        oauth.store_tokens(
            user_id=1,
            access_token="access_token_value",
            db_session=mock_session,
            encryptor=encryptor,
            public_token="public_token_value",
        )

        # Verify tokens are encrypted (not plaintext)
        assert mock_user.broker_access_token != "access_token_value"
        assert mock_user.broker_refresh_token != "public_token_value"

        # Verify encrypted values can be decrypted
        assert encryptor.decrypt(mock_user.broker_access_token) == "access_token_value"
        assert encryptor.decrypt(mock_user.broker_refresh_token) == "public_token_value"

        # Verify expiry is set
        assert mock_user.broker_token_expiry is not None
        mock_session.commit.assert_called_once()

    def test_store_tokens_invalid_user_id_raises(self, oauth):
        """Test that invalid user_id raises ValueError."""
        encryptor = MagicMock()
        mock_session = MagicMock()

        with pytest.raises(ValueError, match="user_id must be a positive"):
            oauth.store_tokens(
                user_id=0,
                access_token="token",
                db_session=mock_session,
                encryptor=encryptor,
            )

    def test_store_tokens_empty_access_token_raises(self, oauth):
        """Test that empty access_token raises ValueError."""
        encryptor = MagicMock()
        mock_session = MagicMock()

        with pytest.raises(ValueError, match="Access token cannot be empty"):
            oauth.store_tokens(
                user_id=1,
                access_token="",
                db_session=mock_session,
                encryptor=encryptor,
            )

    def test_store_tokens_user_not_found(self, oauth):
        """Test that missing user raises OAuthError."""
        encryptor = MagicMock()
        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = None

        with pytest.raises(OAuthError, match="not found"):
            oauth.store_tokens(
                user_id=999,
                access_token="token",
                db_session=mock_session,
                encryptor=encryptor,
            )


# ============================================================
# KiteClientFactory Tests
# ============================================================


class TestKiteClientFactory:
    """Tests for Kite client factory with connection pooling."""

    @pytest.fixture
    def encryption_key(self):
        """Generate a valid Fernet key."""
        return Fernet.generate_key().decode()

    @pytest.fixture
    def encryptor(self, encryption_key):
        """Create a TokenEncryption instance."""
        return TokenEncryption(encryption_key)

    @pytest.fixture
    def mock_user(self, encryptor):
        """Create a mock user with valid encrypted token."""
        user = MagicMock()
        user.id = 1
        user.broker_access_token = encryptor.encrypt("test_access_token")
        user.broker_refresh_token = encryptor.encrypt("test_refresh_token")
        user.broker_token_expiry = datetime.now(timezone.utc) + timedelta(hours=12)
        return user

    @pytest.fixture
    def mock_session_factory(self, mock_user):
        """Create a mock session factory that returns user."""
        def factory():
            session = MagicMock()
            session.query.return_value.filter_by.return_value.first.return_value = mock_user
            return session
        return factory

    @pytest.fixture
    def factory(self, encryptor, mock_session_factory):
        """Create a KiteClientFactory instance."""
        return KiteClientFactory(
            api_key="test_api_key",
            token_encryption=encryptor,
            db_session_factory=mock_session_factory,
        )

    def test_init_with_valid_params(self, encryptor, mock_session_factory):
        """Test factory initialization."""
        factory = KiteClientFactory(
            api_key="key",
            token_encryption=encryptor,
            db_session_factory=mock_session_factory,
        )
        assert factory.api_key == "key"
        assert factory.get_pool_size() == 0

    def test_init_empty_api_key_raises(self, encryptor, mock_session_factory):
        """Test that empty api_key raises ValueError."""
        with pytest.raises(ValueError, match="API key cannot be empty"):
            KiteClientFactory(
                api_key="",
                token_encryption=encryptor,
                db_session_factory=mock_session_factory,
            )

    def test_init_no_encryption_raises(self, mock_session_factory):
        """Test that missing token_encryption raises ValueError."""
        with pytest.raises(ValueError, match="Token encryption instance"):
            KiteClientFactory(
                api_key="key",
                token_encryption=None,
                db_session_factory=mock_session_factory,
            )

    def test_init_no_session_factory_raises(self, encryptor):
        """Test that missing db_session_factory raises ValueError."""
        with pytest.raises(ValueError, match="Database session factory"):
            KiteClientFactory(
                api_key="key",
                token_encryption=encryptor,
                db_session_factory=None,
            )

    @patch("src.broker.kite_client_factory.KiteConnect")
    def test_get_client_creates_instance(self, MockKite, factory):
        """Test that get_client creates and returns a KiteConnect instance."""
        mock_kite = MagicMock()
        MockKite.return_value = mock_kite

        client = factory.get_client(user_id=1)
        assert client == mock_kite
        mock_kite.set_access_token.assert_called_once_with("test_access_token")

    @patch("src.broker.kite_client_factory.KiteConnect")
    def test_get_client_caches_instance(self, MockKite, factory):
        """Test that subsequent calls return cached client."""
        mock_kite = MagicMock()
        MockKite.return_value = mock_kite

        client1 = factory.get_client(user_id=1)
        client2 = factory.get_client(user_id=1)
        assert client1 is client2
        # KiteConnect should only be instantiated once
        assert MockKite.call_count == 1

    def test_get_client_invalid_user_id_raises(self, factory):
        """Test that invalid user_id raises ValueError."""
        with pytest.raises(ValueError, match="user_id must be a positive"):
            factory.get_client(user_id=0)

    def test_get_client_expired_token_raises(self, factory, mock_user):
        """Test that expired token raises TokenExpiredError."""
        # Set token expiry to past
        mock_user.broker_token_expiry = datetime.now(timezone.utc) - timedelta(hours=1)

        with pytest.raises(TokenExpiredError):
            factory.get_client(user_id=1)

    def test_check_token_validity_valid(self, factory):
        """Test token validity check with valid token."""
        assert factory.check_token_validity(user_id=1) is True

    def test_check_token_validity_expired(self, factory, mock_user):
        """Test token validity check with expired token."""
        mock_user.broker_token_expiry = datetime.now(timezone.utc) - timedelta(hours=1)
        assert factory.check_token_validity(user_id=1) is False

    def test_check_token_validity_no_token(self, factory, mock_user):
        """Test token validity check when no token stored."""
        mock_user.broker_access_token = None
        assert factory.check_token_validity(user_id=1) is False

    def test_check_token_validity_no_expiry(self, factory, mock_user):
        """Test token validity check when no expiry set."""
        mock_user.broker_token_expiry = None
        assert factory.check_token_validity(user_id=1) is False

    def test_check_token_validity_invalid_user_id(self, factory):
        """Test token validity returns False for invalid user_id."""
        assert factory.check_token_validity(user_id=0) is False
        assert factory.check_token_validity(user_id=-1) is False

    def test_check_token_validity_within_buffer(self, factory, mock_user):
        """Test that token within refresh buffer is considered invalid."""
        # Set expiry to 20 minutes from now (within 30-min buffer)
        mock_user.broker_token_expiry = datetime.now(timezone.utc) + timedelta(minutes=20)
        assert factory.check_token_validity(user_id=1) is False

    @patch("src.broker.kite_client_factory.KiteConnect")
    def test_handle_auth_error_removes_cached_client(self, MockKite, factory):
        """Test that auth error removes client from pool."""
        mock_kite = MagicMock()
        MockKite.return_value = mock_kite

        # First get a client so it's in the pool
        factory.get_client(user_id=1)
        assert factory.get_pool_size() == 1

        # Handle auth error
        factory.handle_auth_error(user_id=1, error=Exception("Token invalid"))
        assert factory.get_pool_size() == 0

    @patch("src.broker.kite_client_factory.KiteConnect")
    def test_invalidate_user_removes_client(self, MockKite, factory):
        """Test that invalidate_user removes client from pool."""
        mock_kite = MagicMock()
        MockKite.return_value = mock_kite

        factory.get_client(user_id=1)
        assert factory.get_pool_size() == 1

        factory.invalidate_user(user_id=1)
        assert factory.get_pool_size() == 0

    def test_get_client_no_broker_token(self, factory, mock_user):
        """Test that missing broker token raises BrokerAuthError."""
        mock_user.broker_access_token = None
        # Token validity check will fail, raising TokenExpiredError
        with pytest.raises((BrokerAuthError, TokenExpiredError)):
            factory.get_client(user_id=1)

    def test_needs_refresh_within_buffer(self, factory, mock_user):
        """Test needs_refresh returns True when within buffer period."""
        # Set expiry to 20 minutes from now (within 30-min buffer)
        mock_user.broker_token_expiry = datetime.now(timezone.utc) + timedelta(minutes=20)
        assert factory.needs_refresh(user_id=1) is True

    def test_needs_refresh_outside_buffer(self, factory, mock_user):
        """Test needs_refresh returns False when well before buffer."""
        # Set expiry to 12 hours from now (well outside buffer)
        mock_user.broker_token_expiry = datetime.now(timezone.utc) + timedelta(hours=12)
        assert factory.needs_refresh(user_id=1) is False

    def test_needs_refresh_already_expired(self, factory, mock_user):
        """Test needs_refresh returns False when already expired."""
        mock_user.broker_token_expiry = datetime.now(timezone.utc) - timedelta(hours=1)
        assert factory.needs_refresh(user_id=1) is False

    def test_get_pool_size_empty(self, factory):
        """Test pool size is 0 initially."""
        assert factory.get_pool_size() == 0


# ============================================================
# TokenRefreshService Tests
# ============================================================


class TestTokenRefreshService:
    """Tests for token refresh logic."""

    @pytest.fixture
    def mock_user_valid(self):
        """Create a mock user with valid token (expiry far in future)."""
        user = MagicMock()
        user.id = 1
        user.broker_access_token = "encrypted_token"
        user.broker_token_expiry = datetime.now(timezone.utc) + timedelta(hours=12)
        return user

    @pytest.fixture
    def mock_user_expiring_soon(self):
        """Create a mock user with token expiring within 30 minutes."""
        user = MagicMock()
        user.id = 2
        user.broker_access_token = "encrypted_token"
        user.broker_token_expiry = datetime.now(timezone.utc) + timedelta(minutes=15)
        return user

    @pytest.fixture
    def mock_user_expired(self):
        """Create a mock user with expired token."""
        user = MagicMock()
        user.id = 3
        user.broker_access_token = "encrypted_token"
        user.broker_token_expiry = datetime.now(timezone.utc) - timedelta(hours=1)
        return user

    @pytest.fixture
    def mock_user_no_token(self):
        """Create a mock user with no broker token."""
        user = MagicMock()
        user.id = 4
        user.broker_access_token = None
        user.broker_token_expiry = None
        return user

    def _make_session_factory(self, user):
        """Helper to create a mock session factory returning a specific user."""
        def factory():
            session = MagicMock()
            session.query.return_value.filter_by.return_value.first.return_value = user
            return session
        return factory

    @pytest.fixture
    def service_valid(self, mock_user_valid):
        """Create a TokenRefreshService with a valid-token user."""
        return TokenRefreshService(
            db_session_factory=self._make_session_factory(mock_user_valid)
        )

    @pytest.fixture
    def service_expiring(self, mock_user_expiring_soon):
        """Create a TokenRefreshService with an expiring-soon user."""
        return TokenRefreshService(
            db_session_factory=self._make_session_factory(mock_user_expiring_soon)
        )

    @pytest.fixture
    def service_expired(self, mock_user_expired):
        """Create a TokenRefreshService with an expired-token user."""
        return TokenRefreshService(
            db_session_factory=self._make_session_factory(mock_user_expired)
        )

    @pytest.fixture
    def service_no_token(self, mock_user_no_token):
        """Create a TokenRefreshService with a no-token user."""
        return TokenRefreshService(
            db_session_factory=self._make_session_factory(mock_user_no_token)
        )

    # --- Initialization Tests ---

    def test_init_with_valid_factory(self):
        """Test initialization with valid db_session_factory."""
        service = TokenRefreshService(db_session_factory=MagicMock())
        assert service is not None

    def test_init_no_factory_raises(self):
        """Test that None db_session_factory raises ValueError."""
        with pytest.raises(ValueError, match="Database session factory"):
            TokenRefreshService(db_session_factory=None)

    def test_init_with_notification_callback(self):
        """Test initialization with notification callback."""
        callback = MagicMock()
        service = TokenRefreshService(
            db_session_factory=MagicMock(),
            notification_callback=callback,
        )
        assert service.notification_callback is callback

    # --- check_expiry Tests ---

    def test_check_expiry_valid_token_returns_false(self, service_valid):
        """Token not expiring soon returns False."""
        assert service_valid.check_expiry(user_id=1) is False

    def test_check_expiry_expiring_soon_returns_true(self, service_expiring):
        """Token expiring within 30 minutes returns True."""
        assert service_expiring.check_expiry(user_id=2) is True

    def test_check_expiry_expired_token_returns_false(self, service_expired):
        """Already expired token returns False (not 'expiring soon')."""
        assert service_expired.check_expiry(user_id=3) is False

    def test_check_expiry_no_token_returns_false(self, service_no_token):
        """No token stored returns False."""
        assert service_no_token.check_expiry(user_id=4) is False

    def test_check_expiry_invalid_user_id_raises(self, service_valid):
        """Invalid user_id raises ValueError."""
        with pytest.raises(ValueError, match="user_id must be a positive"):
            service_valid.check_expiry(user_id=0)

    def test_check_expiry_user_not_found(self):
        """User not found returns False."""
        def factory():
            session = MagicMock()
            session.query.return_value.filter_by.return_value.first.return_value = None
            return session

        service = TokenRefreshService(db_session_factory=factory)
        assert service.check_expiry(user_id=999) is False

    # --- is_expired Tests ---

    def test_is_expired_valid_token_returns_false(self, service_valid):
        """Valid token returns False."""
        assert service_valid.is_expired(user_id=1) is False

    def test_is_expired_expired_token_returns_true(self, service_expired):
        """Expired token returns True."""
        assert service_expired.is_expired(user_id=3) is True

    def test_is_expired_no_token_returns_true(self, service_no_token):
        """No token returns True (treated as expired)."""
        assert service_no_token.is_expired(user_id=4) is True

    def test_is_expired_invalid_user_id_raises(self, service_valid):
        """Invalid user_id raises ValueError."""
        with pytest.raises(ValueError, match="user_id must be a positive"):
            service_valid.is_expired(user_id=-1)

    # --- refresh_token Tests ---

    def test_refresh_token_valid_returns_valid_status(self, service_valid):
        """Valid token returns status 'valid'."""
        result = service_valid.refresh_token(user_id=1)
        assert result["status"] == "valid"
        assert result["requires_reauth"] is False
        assert "hours" in result["message"].lower()

    def test_refresh_token_expiring_soon_returns_expiring(self, service_expiring):
        """Expiring soon returns status 'expiring_soon'."""
        result = service_expiring.refresh_token(user_id=2)
        assert result["status"] == "expiring_soon"
        assert result["requires_reauth"] is True

    def test_refresh_token_expired_returns_expired(self, service_expired):
        """Expired token returns status 'expired'."""
        result = service_expired.refresh_token(user_id=3)
        assert result["status"] == "expired"
        assert result["requires_reauth"] is True

    def test_refresh_token_no_token_returns_missing(self, service_no_token):
        """No token returns status 'missing'."""
        result = service_no_token.refresh_token(user_id=4)
        assert result["status"] == "missing"
        assert result["requires_reauth"] is True

    def test_refresh_token_user_not_found(self):
        """User not found returns status 'missing'."""
        def factory():
            session = MagicMock()
            session.query.return_value.filter_by.return_value.first.return_value = None
            return session

        service = TokenRefreshService(db_session_factory=factory)
        result = service.refresh_token(user_id=999)
        assert result["status"] == "missing"
        assert result["requires_reauth"] is True

    def test_refresh_token_invalid_user_id_raises(self, service_valid):
        """Invalid user_id raises ValueError."""
        with pytest.raises(ValueError, match="user_id must be a positive"):
            service_valid.refresh_token(user_id=0)

    def test_refresh_token_notifies_user_on_expiry(self, mock_user_expired):
        """Notification callback is called when token expired."""
        callback = MagicMock()
        service = TokenRefreshService(
            db_session_factory=self._make_session_factory(mock_user_expired),
            notification_callback=callback,
        )

        service.refresh_token(user_id=3)
        callback.assert_called_once()
        call_args = callback.call_args
        assert call_args[0][0] == 3  # user_id
        assert "expired" in call_args[0][1].lower() or "re-login" in call_args[0][1].lower()

    def test_refresh_token_notifies_user_on_expiring_soon(self, mock_user_expiring_soon):
        """Notification callback is called when token expiring soon."""
        callback = MagicMock()
        service = TokenRefreshService(
            db_session_factory=self._make_session_factory(mock_user_expiring_soon),
            notification_callback=callback,
        )

        service.refresh_token(user_id=2)
        callback.assert_called_once()

    def test_refresh_token_no_notification_when_valid(self, mock_user_valid):
        """Notification callback is NOT called when token is valid."""
        callback = MagicMock()
        service = TokenRefreshService(
            db_session_factory=self._make_session_factory(mock_user_valid),
            notification_callback=callback,
        )

        service.refresh_token(user_id=1)
        callback.assert_not_called()

    # --- handle_refresh_failure Tests ---

    def test_handle_refresh_failure_marks_token_expired(self, mock_user_valid):
        """handle_refresh_failure marks token as expired in database."""
        factory_fn = self._make_session_factory(mock_user_valid)
        service = TokenRefreshService(db_session_factory=factory_fn)

        error = Exception("Connection timeout")
        service.handle_refresh_failure(user_id=1, error=error)

        # Verify token expiry was set to now (approximately)
        assert mock_user_valid.broker_token_expiry is not None
        expiry = mock_user_valid.broker_token_expiry
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        assert (datetime.now(timezone.utc) - expiry).total_seconds() < 5

    def test_handle_refresh_failure_notifies_user(self, mock_user_valid):
        """handle_refresh_failure sends notification to user."""
        callback = MagicMock()
        service = TokenRefreshService(
            db_session_factory=self._make_session_factory(mock_user_valid),
            notification_callback=callback,
        )

        error = Exception("Auth failed")
        service.handle_refresh_failure(user_id=1, error=error)

        callback.assert_called_once()
        call_args = callback.call_args
        assert call_args[0][0] == 1  # user_id
        assert "expired" in call_args[0][1].lower() or "re-login" in call_args[0][1].lower()

    def test_handle_refresh_failure_invalid_user_id_raises(self, service_valid):
        """Invalid user_id raises ValueError."""
        with pytest.raises(ValueError, match="user_id must be a positive"):
            service_valid.handle_refresh_failure(user_id=0, error=Exception("err"))

    def test_handle_refresh_failure_commits_to_db(self, mock_user_valid):
        """handle_refresh_failure commits expiry change to database."""
        session = MagicMock()
        session.query.return_value.filter_by.return_value.first.return_value = mock_user_valid

        def factory():
            return session

        service = TokenRefreshService(db_session_factory=factory)
        service.handle_refresh_failure(user_id=1, error=Exception("err"))

        session.commit.assert_called_once()

    def test_handle_refresh_failure_handles_db_error_gracefully(self):
        """handle_refresh_failure handles database errors without crashing."""
        session = MagicMock()
        session.query.return_value.filter_by.return_value.first.side_effect = Exception("DB down")

        def factory():
            return session

        service = TokenRefreshService(db_session_factory=factory)
        # Should not raise - graceful error handling
        service.handle_refresh_failure(user_id=1, error=Exception("auth error"))
