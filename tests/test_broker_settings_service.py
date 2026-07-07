"""Unit tests for BrokerSettingsService.

Tests the Kite connection status derivation, OAuth reconnection initiation,
OAuth callback handling, and time-remaining formatting.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet

from src.services.broker_settings_service import (
    BrokerSettingsService,
    KiteStatusResponse,
    DhanStatusResponse,
    derive_kite_status,
    format_time_remaining,
)
from src.broker.token_encryption import TokenEncryption
from src.database.models.broker_connection import BrokerConnection


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def encryption_key():
    """Generate a valid Fernet key for testing."""
    return Fernet.generate_key().decode()


@pytest.fixture
def encryptor(encryption_key):
    """Create a TokenEncryption instance with a valid key."""
    return TokenEncryption(encryption_key)


@pytest.fixture
def service(encryptor):
    """Create a BrokerSettingsService with test encryptor."""
    return BrokerSettingsService(token_encryption=encryptor)


@pytest.fixture
def mock_db():
    """Create a mock SQLAlchemy session."""
    return MagicMock()


# ---------------------------------------------------------------------------
# Tests for derive_kite_status
# ---------------------------------------------------------------------------


class TestDeriveKiteStatus:
    """Tests for the status derivation pure function."""

    def test_no_token_returns_disconnected(self):
        """No token → Disconnected."""
        assert derive_kite_status(None, None) == "Disconnected"

    def test_empty_string_token_returns_disconnected(self):
        """Empty string token → Disconnected."""
        assert derive_kite_status("", None) == "Disconnected"

    def test_token_no_expiry_returns_disconnected(self):
        """Token exists but no expiry → Disconnected."""
        assert derive_kite_status("encrypted_token_data", None) == "Disconnected"

    def test_token_with_future_expiry_returns_connected(self):
        """Token + future expiry → Connected."""
        future = datetime.now(timezone.utc) + timedelta(hours=5)
        assert derive_kite_status("encrypted_token_data", future) == "Connected"

    def test_token_with_past_expiry_returns_token_expired(self):
        """Token + past expiry → Token Expired."""
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        assert derive_kite_status("encrypted_token_data", past) == "Token Expired"

    def test_token_expiry_exactly_now_returns_token_expired(self):
        """Token + expiry at current moment → Token Expired (not strictly future)."""
        # Use a time slightly in the past to account for execution time
        now = datetime.now(timezone.utc) - timedelta(seconds=1)
        assert derive_kite_status("encrypted_token_data", now) == "Token Expired"


# ---------------------------------------------------------------------------
# Tests for format_time_remaining
# ---------------------------------------------------------------------------


class TestFormatTimeRemaining:
    """Tests for the time remaining formatting function."""

    def test_expired_returns_expired(self):
        """Past datetime returns 'Expired'."""
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        assert format_time_remaining(past) == "Expired"

    def test_hours_and_minutes(self):
        """Future datetime with hours shows 'Xh Ym remaining'."""
        future = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30, seconds=10)
        result = format_time_remaining(future)
        assert "5h" in result
        assert "30m" in result
        assert "remaining" in result

    def test_only_minutes(self):
        """Future datetime under 1 hour shows 'Xm remaining'."""
        future = datetime.now(timezone.utc) + timedelta(minutes=45, seconds=10)
        result = format_time_remaining(future)
        assert "h" not in result
        assert "45m remaining" == result

    def test_zero_minutes_remaining(self):
        """Future datetime with seconds only shows '0m remaining'."""
        future = datetime.now(timezone.utc) + timedelta(seconds=30)
        result = format_time_remaining(future)
        assert result == "0m remaining"

    def test_large_hours(self):
        """Future datetime with many hours formats correctly."""
        future = datetime.now(timezone.utc) + timedelta(hours=23, minutes=59)
        result = format_time_remaining(future)
        assert "23h" in result
        assert "remaining" in result


# ---------------------------------------------------------------------------
# Tests for BrokerSettingsService.get_kite_status
# ---------------------------------------------------------------------------


class TestGetKiteStatus:
    """Tests for get_kite_status method."""

    def test_no_connection_record_returns_disconnected(self, service, mock_db):
        """When no BrokerConnection exists, returns Disconnected status."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = service.get_kite_status(mock_db, user_id=1)

        assert result.status == "Disconnected"
        assert result.token_expiry is None
        assert result.time_remaining is None
        assert result.auto_login_enabled is False

    def test_connected_status_with_valid_token(self, service, mock_db, encryptor):
        """When token is valid and not expired, returns Connected."""
        future_expiry = datetime.now(timezone.utc) + timedelta(hours=10)
        connection = BrokerConnection(
            user_id=1,
            broker_type="kite",
            access_token_encrypted=encryptor.encrypt("test_token"),
            token_expiry=future_expiry,
            auto_login_enabled=True,
            last_auto_login_at=None,
            last_auto_login_success=None,
            status="connected",
        )
        mock_db.query.return_value.filter.return_value.first.return_value = connection

        result = service.get_kite_status(mock_db, user_id=1)

        assert result.status == "Connected"
        assert result.token_expiry is not None
        assert "remaining" in result.time_remaining
        assert result.auto_login_enabled is True

    def test_expired_token_returns_token_expired(self, service, mock_db, encryptor):
        """When token exists but is expired, returns Token Expired."""
        past_expiry = datetime.now(timezone.utc) - timedelta(hours=2)
        connection = BrokerConnection(
            user_id=1,
            broker_type="kite",
            access_token_encrypted=encryptor.encrypt("old_token"),
            token_expiry=past_expiry,
            auto_login_enabled=False,
            last_auto_login_at=None,
            last_auto_login_success=None,
            status="connected",
        )
        mock_db.query.return_value.filter.return_value.first.return_value = connection

        result = service.get_kite_status(mock_db, user_id=1)

        assert result.status == "Token Expired"
        assert result.time_remaining == "Expired"


# ---------------------------------------------------------------------------
# Tests for BrokerSettingsService.initiate_reconnect
# ---------------------------------------------------------------------------


class TestInitiateReconnect:
    """Tests for initiate_reconnect method."""

    @patch.dict(os.environ, {
        "KITE_API_KEY": "test_key",
        "KITE_API_SECRET": "test_secret",
        "KITE_REDIRECT_URL": "http://localhost:8000/callback",
    })
    @patch("src.services.broker_settings_service.ZerodhaOAuth")
    def test_returns_login_url(self, mock_oauth_cls, service):
        """Returns the OAuth login URL from ZerodhaOAuth."""
        mock_oauth = MagicMock()
        mock_oauth.get_login_url.return_value = "https://kite.zerodha.com/connect/login?v=3&api_key=test_key"
        mock_oauth_cls.return_value = mock_oauth

        url = service.initiate_reconnect(user_id=1)

        assert "kite.zerodha.com" in url
        mock_oauth_cls.assert_called_once_with(
            api_key="test_key",
            api_secret="test_secret",
            redirect_url="http://localhost:8000/callback",
        )

    @patch.dict(os.environ, {"KITE_API_KEY": "", "KITE_API_SECRET": ""})
    def test_raises_when_credentials_missing(self, service):
        """Raises RuntimeError when API credentials are not configured."""
        with pytest.raises(RuntimeError, match="Broker API credentials not configured"):
            service.initiate_reconnect(user_id=1)


# ---------------------------------------------------------------------------
# Tests for BrokerSettingsService.handle_oauth_callback
# ---------------------------------------------------------------------------


class TestHandleOauthCallback:
    """Tests for handle_oauth_callback method."""

    @patch.dict(os.environ, {
        "KITE_API_KEY": "test_key",
        "KITE_API_SECRET": "test_secret",
        "KITE_REDIRECT_URL": "http://localhost:8000/callback",
    })
    @patch("src.services.broker_settings_service.ZerodhaOAuth")
    def test_successful_callback_stores_encrypted_token(
        self, mock_oauth_cls, service, mock_db, encryptor
    ):
        """Successful OAuth callback stores encrypted token and sets expiry."""
        mock_oauth = MagicMock()
        mock_oauth.handle_callback.return_value = {
            "access_token": "new_access_token_123",
            "public_token": "public_token_456",
        }
        mock_oauth_cls.return_value = mock_oauth

        # Mock no existing connection → will create one
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.flush = MagicMock()

        service.handle_oauth_callback(mock_db, user_id=1, request_token="req_token_abc")

        # Verify commit was called
        mock_db.commit.assert_called_once()
        # Verify a new BrokerConnection was added
        mock_db.add.assert_called_once()
        added_connection = mock_db.add.call_args[0][0]
        assert added_connection.broker_type == "kite"
        assert added_connection.access_token_encrypted is not None
        assert added_connection.token_expiry is not None
        assert added_connection.status == "connected"

        # Verify the stored token can be decrypted back
        decrypted = encryptor.decrypt(added_connection.access_token_encrypted)
        assert decrypted == "new_access_token_123"

    def test_empty_request_token_raises(self, service, mock_db):
        """Empty request token raises ValueError."""
        with pytest.raises(ValueError, match="Request token cannot be empty"):
            service.handle_oauth_callback(mock_db, user_id=1, request_token="")

    @patch.dict(os.environ, {
        "KITE_API_KEY": "test_key",
        "KITE_API_SECRET": "test_secret",
        "KITE_REDIRECT_URL": "http://localhost:8000/callback",
    })
    @patch("src.services.broker_settings_service.ZerodhaOAuth")
    def test_updates_existing_connection(self, mock_oauth_cls, service, mock_db, encryptor):
        """When connection record exists, updates it instead of creating new."""
        mock_oauth = MagicMock()
        mock_oauth.handle_callback.return_value = {
            "access_token": "updated_token",
            "public_token": "",
        }
        mock_oauth_cls.return_value = mock_oauth

        # Mock existing connection
        existing = BrokerConnection(
            user_id=1,
            broker_type="kite",
            access_token_encrypted="old_encrypted",
            token_expiry=datetime.now(timezone.utc) - timedelta(hours=5),
            status="disconnected",
        )
        mock_db.query.return_value.filter.return_value.first.return_value = existing

        service.handle_oauth_callback(mock_db, user_id=1, request_token="req_token")

        # Verify the existing record was updated
        assert existing.access_token_encrypted != "old_encrypted"
        assert existing.status == "connected"
        assert existing.error_message is None
        mock_db.commit.assert_called_once()
        # Should NOT create a new record
        mock_db.add.assert_not_called()


# ---------------------------------------------------------------------------
# Tests for BrokerSettingsService.validate_totp_key
# ---------------------------------------------------------------------------


class TestValidateTotpKey:
    """Tests for the TOTP key validation method."""

    def test_valid_base32_key_returns_true(self, service):
        """A valid Base32-encoded key produces a 6-digit code and returns True."""
        # Standard Base32 key used in TOTP (e.g., from Google Authenticator)
        valid_key = "JBSWY3DPEHPK3PXP"
        assert service.validate_totp_key(valid_key) is True

    def test_another_valid_key_returns_true(self, service):
        """Another valid Base32 key also returns True."""
        valid_key = "L62UZQR2RNJNUKWONZPHMGSW7CZHGH22"
        assert service.validate_totp_key(valid_key) is True

    def test_empty_string_returns_false(self, service):
        """Empty string key returns False."""
        assert service.validate_totp_key("") is False

    def test_whitespace_only_returns_false(self, service):
        """Whitespace-only key returns False."""
        assert service.validate_totp_key("   ") is False

    def test_invalid_base32_returns_false(self, service):
        """Non-Base32 string returns False."""
        assert service.validate_totp_key("not-a-valid-base32!!!") is False

    def test_key_with_whitespace_trimmed(self, service):
        """Key with leading/trailing whitespace is trimmed and validated."""
        valid_key = "  JBSWY3DPEHPK3PXP  "
        assert service.validate_totp_key(valid_key) is True


# ---------------------------------------------------------------------------
# Tests for BrokerSettingsService.update_auto_login
# ---------------------------------------------------------------------------


class TestUpdateAutoLogin:
    """Tests for the update_auto_login method."""

    def test_enable_with_valid_key(self, service, mock_db, encryptor):
        """Enabling auto-login with a valid TOTP key encrypts and stores it."""
        # Mock no existing connection → creates one
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.flush = MagicMock()

        valid_key = "JBSWY3DPEHPK3PXP"
        service.update_auto_login(db=mock_db, user_id=1, totp_key=valid_key, enabled=True)

        mock_db.commit.assert_called_once()
        added_connection = mock_db.add.call_args[0][0]
        assert added_connection.auto_login_enabled is True
        assert added_connection.totp_key_encrypted is not None
        # Verify the stored key can be decrypted back
        decrypted = encryptor.decrypt(added_connection.totp_key_encrypted)
        assert decrypted == valid_key

    def test_enable_without_key_uses_existing(self, service, mock_db, encryptor):
        """Enabling auto-login without providing a key leaves existing key unchanged."""
        existing = BrokerConnection(
            user_id=1,
            broker_type="kite",
            totp_key_encrypted=encryptor.encrypt("EXISTING_KEY_123456"),
            auto_login_enabled=False,
            status="connected",
        )
        mock_db.query.return_value.filter.return_value.first.return_value = existing

        service.update_auto_login(db=mock_db, user_id=1, totp_key=None, enabled=True)

        assert existing.auto_login_enabled is True
        # Key should remain unchanged
        decrypted = encryptor.decrypt(existing.totp_key_encrypted)
        assert decrypted == "EXISTING_KEY_123456"
        mock_db.commit.assert_called_once()

    def test_disable_auto_login(self, service, mock_db, encryptor):
        """Disabling auto-login sets the flag to False."""
        existing = BrokerConnection(
            user_id=1,
            broker_type="kite",
            totp_key_encrypted=encryptor.encrypt("SOME_KEY_VALUE_123"),
            auto_login_enabled=True,
            status="connected",
        )
        mock_db.query.return_value.filter.return_value.first.return_value = existing

        service.update_auto_login(db=mock_db, user_id=1, totp_key=None, enabled=False)

        assert existing.auto_login_enabled is False
        mock_db.commit.assert_called_once()

    def test_invalid_key_raises_value_error(self, service, mock_db):
        """Providing an invalid TOTP key raises ValueError."""
        with pytest.raises(ValueError, match="Invalid TOTP key format"):
            service.update_auto_login(
                db=mock_db, user_id=1, totp_key="not-valid!!!", enabled=True
            )
        # Should not commit if validation fails
        mock_db.commit.assert_not_called()

    def test_empty_key_raises_value_error(self, service, mock_db):
        """Providing an empty TOTP key raises ValueError."""
        with pytest.raises(ValueError, match="Invalid TOTP key format"):
            service.update_auto_login(
                db=mock_db, user_id=1, totp_key="", enabled=True
            )
        mock_db.commit.assert_not_called()


# ---------------------------------------------------------------------------
# Tests for BrokerSettingsService.get_auto_login_config
# ---------------------------------------------------------------------------


class TestGetAutoLoginConfig:
    """Tests for the get_auto_login_config method."""

    def test_no_connection_returns_defaults(self, service, mock_db):
        """When no connection exists, returns all-disabled defaults."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        config = service.get_auto_login_config(mock_db, user_id=1)

        assert config == {
            "enabled": False,
            "key_configured": False,
            "last_auto_login_at": None,
            "last_auto_login_success": None,
        }

    def test_connection_with_key_configured(self, service, mock_db, encryptor):
        """Returns key_configured=True when TOTP key is stored."""
        connection = BrokerConnection(
            user_id=1,
            broker_type="kite",
            totp_key_encrypted=encryptor.encrypt("JBSWY3DPEHPK3PXP"),
            auto_login_enabled=True,
            last_auto_login_at=datetime(2024, 1, 15, 3, 15, tzinfo=timezone.utc),
            last_auto_login_success=True,
            status="connected",
        )
        mock_db.query.return_value.filter.return_value.first.return_value = connection

        config = service.get_auto_login_config(mock_db, user_id=1)

        assert config["enabled"] is True
        assert config["key_configured"] is True
        assert config["last_auto_login_at"] == "2024-01-15 03:15"
        assert config["last_auto_login_success"] is True

    def test_connection_without_key(self, service, mock_db):
        """Returns key_configured=False when no TOTP key is stored."""
        connection = BrokerConnection(
            user_id=1,
            broker_type="kite",
            totp_key_encrypted=None,
            auto_login_enabled=False,
            last_auto_login_at=None,
            last_auto_login_success=None,
            status="disconnected",
        )
        mock_db.query.return_value.filter.return_value.first.return_value = connection

        config = service.get_auto_login_config(mock_db, user_id=1)

        assert config["enabled"] is False
        assert config["key_configured"] is False
        assert config["last_auto_login_at"] is None
        assert config["last_auto_login_success"] is None

    def test_config_does_not_expose_raw_key(self, service, mock_db, encryptor):
        """The returned config never includes the raw TOTP key."""
        connection = BrokerConnection(
            user_id=1,
            broker_type="kite",
            totp_key_encrypted=encryptor.encrypt("SECRET_TOTP_KEY_HERE"),
            auto_login_enabled=True,
            last_auto_login_at=None,
            last_auto_login_success=None,
            status="connected",
        )
        mock_db.query.return_value.filter.return_value.first.return_value = connection

        config = service.get_auto_login_config(mock_db, user_id=1)

        # Should not contain any raw key values
        assert "totp_key" not in config
        assert "SECRET_TOTP_KEY_HERE" not in str(config)
        assert "key_configured" in config
        assert config["key_configured"] is True

    def test_failed_last_auto_login(self, service, mock_db, encryptor):
        """Returns last_auto_login_success=False when last attempt failed."""
        connection = BrokerConnection(
            user_id=1,
            broker_type="kite",
            totp_key_encrypted=encryptor.encrypt("JBSWY3DPEHPK3PXP"),
            auto_login_enabled=True,
            last_auto_login_at=datetime(2024, 3, 10, 3, 15, tzinfo=timezone.utc),
            last_auto_login_success=False,
            status="connected",
        )
        mock_db.query.return_value.filter.return_value.first.return_value = connection

        config = service.get_auto_login_config(mock_db, user_id=1)

        assert config["last_auto_login_at"] == "2024-03-10 03:15"
        assert config["last_auto_login_success"] is False


# ---------------------------------------------------------------------------
# Tests for DhanStatusResponse model
# ---------------------------------------------------------------------------


class TestDhanStatusResponse:
    """Tests for the DhanStatusResponse pydantic model."""

    def test_disconnected_status(self):
        """Creates a valid Disconnected response."""
        resp = DhanStatusResponse(status="Disconnected")
        assert resp.status == "Disconnected"
        assert resp.account_name is None
        assert resp.error_message is None

    def test_connected_status_with_account_name(self):
        """Creates a valid Connected response with account name."""
        resp = DhanStatusResponse(status="Connected", account_name="1000123")
        assert resp.status == "Connected"
        assert resp.account_name == "1000123"

    def test_error_status_with_message(self):
        """Creates a valid Error response with error message."""
        resp = DhanStatusResponse(status="Error", error_message="Invalid token")
        assert resp.status == "Error"
        assert resp.error_message == "Invalid token"


# ---------------------------------------------------------------------------
# Tests for BrokerSettingsService.get_dhan_status
# ---------------------------------------------------------------------------


class TestGetDhanStatus:
    """Tests for get_dhan_status method."""

    def test_no_connection_record_returns_disconnected(self, service, mock_db):
        """When no Dhan BrokerConnection exists, returns Disconnected status."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = service.get_dhan_status(mock_db, user_id=1)

        assert result.status == "Disconnected"
        assert result.account_name is None
        assert result.error_message is None

    def test_connected_with_valid_credentials(self, service, mock_db, encryptor):
        """When credentials are stored and status is connected, returns Connected."""
        connection = BrokerConnection(
            user_id=1,
            broker_type="dhan",
            access_token_encrypted=encryptor.encrypt("dhan_access_token"),
            client_id_encrypted=encryptor.encrypt("1000123"),
            account_name="1000123",
            status="connected",
            error_message=None,
        )
        mock_db.query.return_value.filter.return_value.first.return_value = connection

        result = service.get_dhan_status(mock_db, user_id=1)

        assert result.status == "Connected"
        assert result.account_name == "1000123"
        assert result.error_message is None

    def test_error_status_with_error_message(self, service, mock_db, encryptor):
        """When error_message is present, returns Error status."""
        connection = BrokerConnection(
            user_id=1,
            broker_type="dhan",
            access_token_encrypted=encryptor.encrypt("dhan_access_token"),
            client_id_encrypted=encryptor.encrypt("1000123"),
            account_name="1000123",
            status="connected",
            error_message="Token expired",
        )
        mock_db.query.return_value.filter.return_value.first.return_value = connection

        result = service.get_dhan_status(mock_db, user_id=1)

        assert result.status == "Error"
        assert result.account_name == "1000123"
        assert result.error_message == "Token expired"

    def test_missing_access_token_returns_disconnected(self, service, mock_db, encryptor):
        """When access_token is missing, returns Disconnected."""
        connection = BrokerConnection(
            user_id=1,
            broker_type="dhan",
            access_token_encrypted=None,
            client_id_encrypted=encryptor.encrypt("1000123"),
            account_name=None,
            status="disconnected",
            error_message=None,
        )
        mock_db.query.return_value.filter.return_value.first.return_value = connection

        result = service.get_dhan_status(mock_db, user_id=1)

        assert result.status == "Disconnected"
        assert result.account_name is None

    def test_missing_client_id_returns_disconnected(self, service, mock_db, encryptor):
        """When client_id is missing, returns Disconnected."""
        connection = BrokerConnection(
            user_id=1,
            broker_type="dhan",
            access_token_encrypted=encryptor.encrypt("token"),
            client_id_encrypted=None,
            account_name=None,
            status="disconnected",
            error_message=None,
        )
        mock_db.query.return_value.filter.return_value.first.return_value = connection

        result = service.get_dhan_status(mock_db, user_id=1)

        assert result.status == "Disconnected"
        assert result.account_name is None

    def test_credentials_present_but_status_not_connected(self, service, mock_db, encryptor):
        """When credentials exist but status is not 'connected', returns Disconnected."""
        connection = BrokerConnection(
            user_id=1,
            broker_type="dhan",
            access_token_encrypted=encryptor.encrypt("token"),
            client_id_encrypted=encryptor.encrypt("client"),
            account_name="client",
            status="disconnected",
            error_message=None,
        )
        mock_db.query.return_value.filter.return_value.first.return_value = connection

        result = service.get_dhan_status(mock_db, user_id=1)

        assert result.status == "Disconnected"


# ---------------------------------------------------------------------------
# Tests for BrokerSettingsService.connect_dhan
# ---------------------------------------------------------------------------


class TestConnectDhan:
    """Tests for connect_dhan method."""

    @patch("src.services.broker_settings_service.DhanHQ")
    def test_successful_connection(self, mock_dhan_cls, service, mock_db, encryptor):
        """Successful Dhan connection stores encrypted credentials."""
        # Mock DhanHQ client
        mock_dhan = MagicMock()
        mock_dhan.get_fund_limits.return_value = {
            "status": "success",
            "data": {"availabelBalance": 50000},
        }
        mock_dhan_cls.return_value = mock_dhan

        # No existing connection → will create
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.flush = MagicMock()

        result = service.connect_dhan(
            db=mock_db,
            user_id=1,
            client_id="1000123",
            access_token="dhan_token_abc",
        )

        assert result == "1000123"
        mock_db.commit.assert_called_once()
        mock_db.add.assert_called_once()

        # Verify stored connection
        added_connection = mock_db.add.call_args[0][0]
        assert added_connection.broker_type == "dhan"
        assert added_connection.status == "connected"
        assert added_connection.account_name == "1000123"
        assert added_connection.error_message is None

        # Verify encrypted credentials can be decrypted
        decrypted_client = encryptor.decrypt(added_connection.client_id_encrypted)
        decrypted_token = encryptor.decrypt(added_connection.access_token_encrypted)
        assert decrypted_client == "1000123"
        assert decrypted_token == "dhan_token_abc"

    @patch("src.services.broker_settings_service.DhanHQ")
    def test_failed_connection_raises_error(self, mock_dhan_cls, service, mock_db):
        """Failed Dhan API call raises ConnectionError."""
        mock_dhan = MagicMock()
        mock_dhan.get_fund_limits.return_value = {
            "status": "failure",
            "remarks": {"error_message": "Invalid access token"},
        }
        mock_dhan_cls.return_value = mock_dhan

        with pytest.raises(ConnectionError, match="Dhan connection failed: Invalid access token"):
            service.connect_dhan(
                db=mock_db,
                user_id=1,
                client_id="1000123",
                access_token="bad_token",
            )

        mock_db.commit.assert_not_called()

    @patch("src.services.broker_settings_service.DhanHQ")
    def test_exception_during_connection_raises_error(self, mock_dhan_cls, service, mock_db):
        """Exception during DhanHQ initialization raises ConnectionError."""
        mock_dhan_cls.side_effect = Exception("Network timeout")

        with pytest.raises(ConnectionError, match="Dhan connection failed: Network timeout"):
            service.connect_dhan(
                db=mock_db,
                user_id=1,
                client_id="1000123",
                access_token="some_token",
            )

        mock_db.commit.assert_not_called()

    def test_empty_client_id_raises_value_error(self, service, mock_db):
        """Empty client_id raises ValueError."""
        with pytest.raises(ValueError, match="Dhan Client ID cannot be empty"):
            service.connect_dhan(
                db=mock_db,
                user_id=1,
                client_id="",
                access_token="some_token",
            )

    def test_empty_access_token_raises_value_error(self, service, mock_db):
        """Empty access_token raises ValueError."""
        with pytest.raises(ValueError, match="Dhan Access Token cannot be empty"):
            service.connect_dhan(
                db=mock_db,
                user_id=1,
                client_id="1000123",
                access_token="",
            )

    def test_whitespace_only_client_id_raises_value_error(self, service, mock_db):
        """Whitespace-only client_id raises ValueError."""
        with pytest.raises(ValueError, match="Dhan Client ID cannot be empty"):
            service.connect_dhan(
                db=mock_db,
                user_id=1,
                client_id="   ",
                access_token="some_token",
            )

    @patch("src.services.broker_settings_service.DhanHQ")
    def test_updates_existing_connection(self, mock_dhan_cls, service, mock_db, encryptor):
        """When connection record exists, updates it."""
        mock_dhan = MagicMock()
        mock_dhan.get_fund_limits.return_value = {"status": "success", "data": {}}
        mock_dhan_cls.return_value = mock_dhan

        existing = BrokerConnection(
            user_id=1,
            broker_type="dhan",
            access_token_encrypted="old_encrypted",
            client_id_encrypted="old_client",
            account_name="old_name",
            status="disconnected",
            error_message="old error",
        )
        mock_db.query.return_value.filter.return_value.first.return_value = existing

        result = service.connect_dhan(
            db=mock_db,
            user_id=1,
            client_id="2000456",
            access_token="new_token",
        )

        assert result == "2000456"
        assert existing.status == "connected"
        assert existing.account_name == "2000456"
        assert existing.error_message is None
        assert existing.access_token_encrypted != "old_encrypted"
        assert existing.client_id_encrypted != "old_client"
        mock_db.commit.assert_called_once()
        mock_db.add.assert_not_called()


# ---------------------------------------------------------------------------
# Tests for BrokerSettingsService.disconnect_dhan
# ---------------------------------------------------------------------------


class TestDisconnectDhan:
    """Tests for disconnect_dhan method."""

    def test_disconnect_clears_all_fields(self, service, mock_db, encryptor):
        """Disconnect clears all credential fields and sets status to disconnected."""
        connection = BrokerConnection(
            user_id=1,
            broker_type="dhan",
            access_token_encrypted=encryptor.encrypt("token"),
            client_id_encrypted=encryptor.encrypt("client"),
            account_name="1000123",
            status="connected",
            error_message=None,
        )
        mock_db.query.return_value.filter.return_value.first.return_value = connection

        service.disconnect_dhan(mock_db, user_id=1)

        assert connection.access_token_encrypted is None
        assert connection.client_id_encrypted is None
        assert connection.account_name is None
        assert connection.status == "disconnected"
        assert connection.error_message is None
        mock_db.commit.assert_called_once()

    def test_disconnect_with_error_state_clears_error(self, service, mock_db, encryptor):
        """Disconnect clears error_message along with credentials."""
        connection = BrokerConnection(
            user_id=1,
            broker_type="dhan",
            access_token_encrypted=encryptor.encrypt("token"),
            client_id_encrypted=encryptor.encrypt("client"),
            account_name="1000123",
            status="connected",
            error_message="Some previous error",
        )
        mock_db.query.return_value.filter.return_value.first.return_value = connection

        service.disconnect_dhan(mock_db, user_id=1)

        assert connection.access_token_encrypted is None
        assert connection.client_id_encrypted is None
        assert connection.account_name is None
        assert connection.status == "disconnected"
        assert connection.error_message is None

    def test_disconnect_when_no_connection_exists(self, service, mock_db):
        """Disconnect when no record exists does nothing (no error)."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        # Should not raise
        service.disconnect_dhan(mock_db, user_id=1)

        mock_db.commit.assert_not_called()
