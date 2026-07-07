"""Property-based tests for sensitive values excluded from API responses (Task 5.5).

Uses Hypothesis to verify:
- Property 11: Sensitive Values Excluded From API Responses — GET broker endpoints
  never return raw access token values, raw TOTP keys, or raw client secrets.

**Validates: Requirements 8.1, 8.4**
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hypothesis import given, strategies as st, settings, assume

from src.api.routers.broker_settings import router as broker_settings_router
from src.api.dependencies import get_current_user, get_db
from src.broker.token_encryption import TokenEncryption
from src.database.models.broker_connection import BrokerConnection


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate non-empty credential strings (simulating raw tokens, TOTP keys, secrets)
# Minimum length 4 to avoid trivially matching common substrings in JSON keys
credential_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P"),
        blacklist_characters='"\\',
    ),
    min_size=8,
    max_size=100,
).filter(lambda s: s.strip() and len(s.strip()) >= 8)

# Strategy for TOTP keys (Base32-like strings)
totp_key_strategy = st.text(
    alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ234567",
    min_size=16,
    max_size=32,
)

# Strategy for Dhan client IDs (alphanumeric)
client_id_strategy = st.text(
    alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
    min_size=8,
    max_size=20,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _create_test_app():
    """Create a fresh FastAPI app with the broker settings router."""
    app = FastAPI()
    app.include_router(broker_settings_router)
    return app


def _create_encryption():
    """Create an encryption instance for test use."""
    key = Fernet.generate_key().decode()
    return TokenEncryption(encryption_key=key), key


# ============================================================
# Property 11: Sensitive Values Excluded From API Responses
# ============================================================


class TestSensitiveValuesExcludedFromResponses:
    """Property-based tests verifying GET broker endpoints never leak sensitive data.

    **Validates: Requirements 8.1, 8.4**

    Core invariants:
    - GET /api/v1/settings/brokers/kite response JSON never contains raw access tokens
    - GET /api/v1/settings/brokers/kite response JSON never contains raw TOTP keys
    - Response only contains safe fields: status, token_expiry, time_remaining,
      auto_login_enabled, last_auto_login_at, last_auto_login_success
    """

    @given(
        raw_token=credential_strategy,
        raw_totp_key=totp_key_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_kite_get_never_returns_raw_token_or_totp_key(
        self, raw_token, raw_totp_key
    ):
        """GET /kite never includes raw access token or TOTP key in response.

        **Validates: Requirements 8.1**

        Property: For any stored encrypted access token and TOTP key,
        the GET /api/v1/settings/brokers/kite response body shall never
        contain the raw plaintext values.
        """
        encryptor, key = _create_encryption()

        # Encrypt the credentials as they would be stored in DB
        encrypted_token = encryptor.encrypt(raw_token)
        encrypted_totp = encryptor.encrypt(raw_totp_key)

        # Create a mock BrokerConnection with encrypted values
        mock_connection = MagicMock(spec=BrokerConnection)
        mock_connection.access_token_encrypted = encrypted_token
        mock_connection.token_expiry = datetime.now(timezone.utc) + timedelta(hours=5)
        mock_connection.totp_key_encrypted = encrypted_totp
        mock_connection.auto_login_enabled = True
        mock_connection.last_auto_login_at = datetime.now(timezone.utc)
        mock_connection.last_auto_login_success = True
        mock_connection.broker_type = "kite"
        mock_connection.status = "connected"

        app = _create_test_app()
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_connection
        )

        app.dependency_overrides[get_current_user] = lambda: 1
        app.dependency_overrides[get_db] = lambda: mock_db

        with patch.dict(os.environ, {"ENCRYPTION_KEY": key}):
            client = TestClient(app)
            response = client.get("/api/v1/settings/brokers/kite")

        assert response.status_code == 200
        response_text = response.text

        # The raw token must never appear in the response
        assert raw_token not in response_text, (
            f"Raw access token '{raw_token}' found in GET /kite response!"
        )

        # The raw TOTP key must never appear in the response
        assert raw_totp_key not in response_text, (
            f"Raw TOTP key '{raw_totp_key}' found in GET /kite response!"
        )

        # The encrypted versions should also not appear (defense in depth)
        assert encrypted_token not in response_text, (
            f"Encrypted access token found in GET /kite response!"
        )
        assert encrypted_totp not in response_text, (
            f"Encrypted TOTP key found in GET /kite response!"
        )

    @given(raw_token=credential_strategy)
    @settings(max_examples=50, deadline=None)
    def test_kite_get_never_returns_raw_token_when_disconnected(self, raw_token):
        """GET /kite with expired/no token still never leaks raw credentials.

        **Validates: Requirements 8.1**

        Property: Even when a connection has stored credentials but is disconnected,
        the response shall not contain raw token values.
        """
        encryptor, key = _create_encryption()
        encrypted_token = encryptor.encrypt(raw_token)

        # Connection with expired token
        mock_connection = MagicMock(spec=BrokerConnection)
        mock_connection.access_token_encrypted = encrypted_token
        mock_connection.token_expiry = datetime.now(timezone.utc) - timedelta(hours=1)
        mock_connection.totp_key_encrypted = None
        mock_connection.auto_login_enabled = False
        mock_connection.last_auto_login_at = None
        mock_connection.last_auto_login_success = None
        mock_connection.broker_type = "kite"
        mock_connection.status = "disconnected"

        app = _create_test_app()
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_connection
        )

        app.dependency_overrides[get_current_user] = lambda: 1
        app.dependency_overrides[get_db] = lambda: mock_db

        with patch.dict(os.environ, {"ENCRYPTION_KEY": key}):
            client = TestClient(app)
            response = client.get("/api/v1/settings/brokers/kite")

        assert response.status_code == 200
        response_text = response.text

        assert raw_token not in response_text, (
            f"Raw access token '{raw_token}' leaked in GET /kite response "
            f"for disconnected state!"
        )
        assert encrypted_token not in response_text, (
            f"Encrypted access token leaked in GET /kite response!"
        )

    @given(
        raw_token=credential_strategy,
        raw_totp_key=totp_key_strategy,
        raw_client_id=client_id_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_kite_response_only_contains_safe_fields(
        self, raw_token, raw_totp_key, raw_client_id
    ):
        """GET /kite response only contains the expected safe field set.

        **Validates: Requirements 8.1**

        Property: The response JSON keys shall only be from the allowed set:
        status, token_expiry, time_remaining, auto_login_enabled,
        last_auto_login_at, last_auto_login_success.
        """
        encryptor, key = _create_encryption()
        encrypted_token = encryptor.encrypt(raw_token)
        encrypted_totp = encryptor.encrypt(raw_totp_key)
        encrypted_client_id = encryptor.encrypt(raw_client_id)

        mock_connection = MagicMock(spec=BrokerConnection)
        mock_connection.access_token_encrypted = encrypted_token
        mock_connection.token_expiry = datetime.now(timezone.utc) + timedelta(hours=3)
        mock_connection.totp_key_encrypted = encrypted_totp
        mock_connection.client_id_encrypted = encrypted_client_id
        mock_connection.auto_login_enabled = True
        mock_connection.last_auto_login_at = datetime.now(timezone.utc)
        mock_connection.last_auto_login_success = True
        mock_connection.broker_type = "kite"
        mock_connection.status = "connected"

        app = _create_test_app()
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_connection
        )

        app.dependency_overrides[get_current_user] = lambda: 1
        app.dependency_overrides[get_db] = lambda: mock_db

        with patch.dict(os.environ, {"ENCRYPTION_KEY": key}):
            client = TestClient(app)
            response = client.get("/api/v1/settings/brokers/kite")

        assert response.status_code == 200
        data = response.json()

        # Only these fields are allowed in the Kite status response
        allowed_fields = {
            "status",
            "token_expiry",
            "time_remaining",
            "auto_login_enabled",
            "key_configured",
            "last_auto_login_at",
            "last_auto_login_success",
        }

        actual_fields = set(data.keys())
        assert actual_fields.issubset(allowed_fields), (
            f"Unexpected fields in response: {actual_fields - allowed_fields}. "
            f"Allowed: {allowed_fields}"
        )

        # Verify no sensitive values leaked into field values
        all_values_str = str(data.values())
        assert raw_token not in all_values_str
        assert raw_totp_key not in all_values_str
        assert raw_client_id not in all_values_str

    @given(
        raw_token=credential_strategy,
        raw_client_id=client_id_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_dhan_status_service_never_returns_raw_credentials(
        self, raw_token, raw_client_id
    ):
        """DhanStatusResponse from service never contains raw tokens or client secrets.

        **Validates: Requirements 8.4**

        Property: For any stored Dhan credentials, the get_dhan_status service
        method (which backs the GET /dhan endpoint) shall never include raw
        access token or client ID values in the response.
        """
        from src.services.broker_settings_service import BrokerSettingsService

        encryptor, key = _create_encryption()
        encrypted_token = encryptor.encrypt(raw_token)
        encrypted_client_id = encryptor.encrypt(raw_client_id)

        mock_connection = MagicMock(spec=BrokerConnection)
        mock_connection.access_token_encrypted = encrypted_token
        mock_connection.client_id_encrypted = encrypted_client_id
        mock_connection.account_name = "TestAccount"
        mock_connection.status = "connected"
        mock_connection.error_message = None
        mock_connection.broker_type = "dhan"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_connection
        )

        service = BrokerSettingsService(token_encryption=encryptor)
        result = service.get_dhan_status(mock_db, user_id=1)

        # Convert to dict for inspection
        result_dict = result.model_dump()
        result_str = str(result_dict)

        # Raw token must never appear
        assert raw_token not in result_str, (
            f"Raw access token '{raw_token}' found in Dhan status response!"
        )

        # Raw client ID must never appear
        assert raw_client_id not in result_str, (
            f"Raw client ID '{raw_client_id}' found in Dhan status response!"
        )

        # Encrypted values must not appear either
        assert encrypted_token not in result_str, (
            f"Encrypted access token found in Dhan status response!"
        )
        assert encrypted_client_id not in result_str, (
            f"Encrypted client ID found in Dhan status response!"
        )

        # Only allowed fields in the response
        allowed_fields = {"status", "account_name", "error_message"}
        actual_fields = set(result_dict.keys())
        assert actual_fields.issubset(allowed_fields), (
            f"Unexpected fields in Dhan response: {actual_fields - allowed_fields}"
        )

    @given(raw_token=credential_strategy)
    @settings(max_examples=30, deadline=None)
    def test_kite_get_no_connection_does_not_leak(self, raw_token):
        """GET /kite with no stored connection returns safe defaults.

        **Validates: Requirements 8.1**

        Property: When no broker connection exists for the user,
        the response shall contain only safe default values and no sensitive data.
        """
        _, key = _create_encryption()

        app = _create_test_app()
        mock_db = MagicMock()
        # No connection found
        mock_db.query.return_value.filter.return_value.first.return_value = None

        app.dependency_overrides[get_current_user] = lambda: 1
        app.dependency_overrides[get_db] = lambda: mock_db

        with patch.dict(os.environ, {"ENCRYPTION_KEY": key}):
            client = TestClient(app)
            response = client.get("/api/v1/settings/brokers/kite")

        assert response.status_code == 200
        data = response.json()

        # Should return disconnected status with no sensitive data
        assert data["status"] == "Disconnected"
        assert data["token_expiry"] is None
        assert data["time_remaining"] is None

        # The raw_token (which was never stored) should not appear
        response_text = response.text
        assert raw_token not in response_text
