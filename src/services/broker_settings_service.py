"""Broker settings service for Kite connection management.

Implements business logic for Kite API connection status derivation,
OAuth reconnection, token exchange/storage, and time-remaining formatting.

Requirements covered:
- 2.1: Connection status display (Connected/Disconnected/Token Expired)
- 2.2: Token expiry timestamp display
- 2.3: Connected status with valid token
- 2.4: Token Expired status with expired token
- 2.5: Disconnected status with no token
- 2.6: Human-readable time remaining
- 3.1: Reconnect button initiates OAuth
- 3.2: OAuth flow redirect to Zerodha login URL
- 3.3: Token exchange and encrypted storage
- 3.4: Status update after successful OAuth
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import pyotp
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from src.broker.oauth import ZerodhaOAuth, OAuthError
from src.broker.token_encryption import TokenEncryption
from src.database.models.broker_connection import BrokerConnection

try:
    from dhanhq import DhanHQ
except ImportError:
    DhanHQ = None  # type: ignore[misc, assignment]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class KiteStatusResponse(BaseModel):
    """Response model for Kite connection status."""

    model_config = ConfigDict(from_attributes=True)

    status: str  # "Connected" | "Disconnected" | "Token Expired"
    token_expiry: Optional[str] = None  # "YYYY-MM-DD HH:MM" UTC
    time_remaining: Optional[str] = None  # "5h 30m remaining" or "Expired"
    auto_login_enabled: bool = False
    key_configured: bool = False
    last_auto_login_at: Optional[str] = None
    last_auto_login_success: Optional[bool] = None


class DhanStatusResponse(BaseModel):
    """Response model for Dhan connection status."""

    model_config = ConfigDict(from_attributes=True)

    status: str  # "Connected" | "Disconnected" | "Error"
    account_name: Optional[str] = None
    error_message: Optional[str] = None


# ---------------------------------------------------------------------------
# Pure helper functions (testable without DB)
# ---------------------------------------------------------------------------


def derive_kite_status(
    token_encrypted: Optional[str], token_expiry: Optional[datetime]
) -> str:
    """Derive connection status from token state.

    Rules:
    - No token → "Disconnected"
    - Token exists + no expiry → "Disconnected"
    - Token exists + expiry in future → "Connected"
    - Token exists + expiry in past → "Token Expired"

    Args:
        token_encrypted: The encrypted access token (or None).
        token_expiry: The token expiry datetime (or None).

    Returns:
        One of: "Connected", "Disconnected", "Token Expired"
    """
    if not token_encrypted:
        return "Disconnected"
    if token_expiry is None:
        return "Disconnected"
    # Ensure timezone-aware comparison (DB may store naive datetimes)
    now = datetime.now(timezone.utc)
    expiry = token_expiry if token_expiry.tzinfo else token_expiry.replace(tzinfo=timezone.utc)
    if expiry > now:
        return "Connected"
    return "Token Expired"


def format_time_remaining(expiry: datetime) -> str:
    """Format time until expiry as human-readable string.

    Args:
        expiry: The token expiry datetime (should be timezone-aware UTC).

    Returns:
        String like "5h 30m remaining", "45m remaining", or "Expired".
    """
    now = datetime.now(timezone.utc)
    # Ensure timezone-aware comparison
    expiry_aware = expiry if expiry.tzinfo else expiry.replace(tzinfo=timezone.utc)
    if expiry_aware <= now:
        return "Expired"
    delta = expiry_aware - now
    hours = int(delta.total_seconds() // 3600)
    minutes = int((delta.total_seconds() % 3600) // 60)
    if hours > 0:
        return f"{hours}h {minutes}m remaining"
    return f"{minutes}m remaining"


# ---------------------------------------------------------------------------
# BrokerSettingsService
# ---------------------------------------------------------------------------


class BrokerSettingsService:
    """Manages Kite broker connection status, OAuth reconnection, and token storage.

    Uses synchronous SQLAlchemy Session for database operations,
    following the same pattern as SettingsService.
    """

    # Zerodha tokens are valid for approximately 24 hours
    TOKEN_VALIDITY_HOURS = 24

    def __init__(self, token_encryption: TokenEncryption):
        """Initialize the broker settings service.

        Args:
            token_encryption: TokenEncryption instance for encrypting/decrypting tokens.
        """
        self.token_encryption = token_encryption

    def get_kite_status(self, db: Session, user_id: int) -> KiteStatusResponse:
        """Derive Kite connection status from stored token state.

        Queries the broker_connections table for the user's Kite connection
        and derives the status based on token presence and expiry.

        Args:
            db: SQLAlchemy session.
            user_id: The user's ID.

        Returns:
            KiteStatusResponse with derived status and metadata.
        """
        connection = self._get_kite_connection(db, user_id)

        if connection is None:
            return KiteStatusResponse(
                status="Disconnected",
                token_expiry=None,
                time_remaining=None,
                auto_login_enabled=False,
                key_configured=False,
                last_auto_login_at=None,
                last_auto_login_success=None,
            )

        status = derive_kite_status(
            connection.access_token_encrypted, connection.token_expiry
        )

        # Format token expiry for display
        token_expiry_str = None
        time_remaining_str = None
        if connection.token_expiry is not None:
            token_expiry_str = connection.token_expiry.strftime("%Y-%m-%d %H:%M")
            time_remaining_str = format_time_remaining(connection.token_expiry)

        # Format last auto-login timestamp
        last_auto_login_str = None
        if connection.last_auto_login_at is not None:
            last_auto_login_str = connection.last_auto_login_at.strftime(
                "%Y-%m-%d %H:%M"
            )

        return KiteStatusResponse(
            status=status,
            token_expiry=token_expiry_str,
            time_remaining=time_remaining_str,
            auto_login_enabled=connection.auto_login_enabled,
            key_configured=connection.totp_key_encrypted is not None,
            last_auto_login_at=last_auto_login_str,
            last_auto_login_success=connection.last_auto_login_success,
        )

    def initiate_reconnect(self, user_id: int) -> str:
        """Return OAuth login URL for Kite reconnection.

        Constructs the Zerodha OAuth login URL using environment configuration.
        The user should be redirected to this URL to authenticate with Zerodha.

        Args:
            user_id: The user's ID (for logging purposes).

        Returns:
            The Zerodha OAuth login URL string.

        Raises:
            RuntimeError: If broker API credentials are not configured.
        """
        api_key = os.environ.get("KITE_API_KEY", "")
        api_secret = os.environ.get("KITE_API_SECRET", "")
        redirect_url = os.environ.get(
            "KITE_REDIRECT_URL", "http://localhost:8000/callback"
        )

        if not api_key or not api_secret:
            raise RuntimeError("Broker API credentials not configured")

        oauth = ZerodhaOAuth(
            api_key=api_key,
            api_secret=api_secret,
            redirect_url=redirect_url,
        )

        login_url = oauth.get_login_url()
        logger.info("Initiated Kite reconnect for user %d", user_id)
        return login_url

    def handle_oauth_callback(
        self, db: Session, user_id: int, request_token: str
    ) -> None:
        """Exchange request token for access token and store encrypted.

        Handles the OAuth callback by:
        1. Exchanging the request_token for an access_token via Zerodha API
        2. Encrypting the access_token
        3. Storing/updating in the broker_connections table
        4. Setting token expiry (24 hours from now)

        Args:
            db: SQLAlchemy session.
            user_id: The user's ID.
            request_token: The request token from Zerodha OAuth callback.

        Raises:
            OAuthError: If token exchange fails.
            ValueError: If request_token is empty.
        """
        if not request_token:
            raise ValueError("Request token cannot be empty")

        api_key = os.environ.get("KITE_API_KEY", "")
        api_secret = os.environ.get("KITE_API_SECRET", "")
        redirect_url = os.environ.get(
            "KITE_REDIRECT_URL", "http://localhost:8000/callback"
        )

        if not api_key or not api_secret:
            raise RuntimeError("Broker API credentials not configured")

        oauth = ZerodhaOAuth(
            api_key=api_key,
            api_secret=api_secret,
            redirect_url=redirect_url,
        )

        # Exchange request token for access token
        token_data = oauth.handle_callback(request_token)
        access_token = token_data["access_token"]

        # Encrypt and store
        encrypted_token = self.token_encryption.encrypt(access_token)
        token_expiry = datetime.now(timezone.utc) + timedelta(
            hours=self.TOKEN_VALIDITY_HOURS
        )

        connection = self._get_or_create_kite_connection(db, user_id)
        connection.access_token_encrypted = encrypted_token
        connection.token_expiry = token_expiry
        connection.status = "connected"
        connection.error_message = None

        db.commit()
        logger.info(
            "Stored encrypted Kite access token for user %d (expires %s)",
            user_id,
            token_expiry.isoformat(),
        )

    # ------------------------------------------------------------------
    # Auto-login configuration
    # ------------------------------------------------------------------

    def validate_totp_key(self, totp_key: str) -> bool:
        """Validate a TOTP key by generating a test code and verifying 6-digit format.

        Uses pyotp to create a TOTP object from the key and generates a test code.
        Returns True only if the generated code is a 6-digit numeric string.

        Args:
            totp_key: A Base32-encoded TOTP secret key.

        Returns:
            True if the key produces a valid 6-digit numeric code, False otherwise.
        """
        if not totp_key or not totp_key.strip():
            return False
        try:
            totp = pyotp.TOTP(totp_key.strip())
            code = totp.now()
            return len(code) == 6 and code.isdigit()
        except Exception:
            return False

    def update_auto_login(
        self, db: Session, user_id: int, totp_key: Optional[str], enabled: bool
    ) -> None:
        """Update auto-login configuration for a user's Kite connection.

        If a totp_key is provided, validates it first (raises ValueError if invalid),
        then encrypts and stores it. Updates the auto_login_enabled flag.

        Args:
            db: SQLAlchemy session.
            user_id: The user's ID.
            totp_key: The TOTP secret key to store (or None to keep existing key).
            enabled: Whether auto-login should be enabled.

        Raises:
            ValueError: If the provided totp_key is invalid.
        """
        # Validate TOTP key if provided
        if totp_key is not None:
            if not self.validate_totp_key(totp_key):
                raise ValueError("Invalid TOTP key format")

        connection = self._get_or_create_kite_connection(db, user_id)

        # Encrypt and store the TOTP key if provided
        if totp_key is not None:
            encrypted_key = self.token_encryption.encrypt(totp_key.strip())
            connection.totp_key_encrypted = encrypted_key

        # Update the enabled flag
        connection.auto_login_enabled = enabled

        db.commit()
        logger.info(
            "Updated auto-login config for user %d: enabled=%s, key_updated=%s",
            user_id,
            enabled,
            totp_key is not None,
        )

    def get_auto_login_config(self, db: Session, user_id: int) -> dict:
        """Get auto-login configuration without exposing the raw TOTP key.

        Returns a dictionary with:
        - enabled: Whether auto-login is enabled.
        - key_configured: Whether a TOTP key has been stored.
        - last_auto_login_at: Timestamp of last auto-login attempt (or None).
        - last_auto_login_success: Whether the last attempt succeeded (or None).

        Args:
            db: SQLAlchemy session.
            user_id: The user's ID.

        Returns:
            Dict with auto-login configuration (no raw key).
        """
        connection = self._get_kite_connection(db, user_id)

        if connection is None:
            return {
                "enabled": False,
                "key_configured": False,
                "last_auto_login_at": None,
                "last_auto_login_success": None,
            }

        last_auto_login_str = None
        if connection.last_auto_login_at is not None:
            last_auto_login_str = connection.last_auto_login_at.strftime(
                "%Y-%m-%d %H:%M"
            )

        return {
            "enabled": connection.auto_login_enabled,
            "key_configured": connection.totp_key_encrypted is not None,
            "last_auto_login_at": last_auto_login_str,
            "last_auto_login_success": connection.last_auto_login_success,
        }

    # ------------------------------------------------------------------
    # Dhan connection management
    # ------------------------------------------------------------------

    def get_dhan_status(self, db: Session, user_id: int) -> DhanStatusResponse:
        """Derive Dhan connection status from stored credentials.

        Queries the broker_connections table for the user's Dhan connection
        and derives the status based on stored credential presence and status field.

        Status derivation:
        - No record or no credentials stored → "Disconnected"
        - Credentials stored + status=="connected" → "Connected"
        - status contains "error" or error_message present → "Error"

        Args:
            db: SQLAlchemy session.
            user_id: The user's ID.

        Returns:
            DhanStatusResponse with derived status and metadata (no raw tokens).
        """
        connection = self._get_dhan_connection(db, user_id)

        if connection is None:
            return DhanStatusResponse(
                status="Disconnected",
                account_name=None,
                error_message=None,
            )

        # Derive status from stored state
        if connection.error_message:
            return DhanStatusResponse(
                status="Error",
                account_name=connection.account_name,
                error_message=connection.error_message,
            )

        if (
            connection.access_token_encrypted
            and connection.client_id_encrypted
            and connection.status == "connected"
        ):
            return DhanStatusResponse(
                status="Connected",
                account_name=connection.account_name,
                error_message=None,
            )

        return DhanStatusResponse(
            status="Disconnected",
            account_name=None,
            error_message=None,
        )

    def connect_dhan(
        self, db: Session, user_id: int, client_id: str, access_token: str
    ) -> str:
        """Validate Dhan credentials, store encrypted, return account name.

        Initializes a dhanhq.DhanHQ client with the provided credentials,
        verifies connectivity by calling get_fund_limits(), then encrypts
        and stores both credentials on success.

        Args:
            db: SQLAlchemy session.
            user_id: The user's ID.
            client_id: Dhan Client ID.
            access_token: Dhan Access Token.

        Returns:
            The account holder name (client_id used as account_name).

        Raises:
            ValueError: If credentials are empty.
            ConnectionError: If Dhan API verification fails.
        """
        if not client_id or not client_id.strip():
            raise ValueError("Dhan Client ID cannot be empty")
        if not access_token or not access_token.strip():
            raise ValueError("Dhan Access Token cannot be empty")

        client_id = client_id.strip()
        access_token = access_token.strip()

        # Verify credentials using Dhan profile API (simpler, no IP restriction)
        try:
            import requests as http_requests

            headers = {
                "access-token": access_token,
                "Content-Type": "application/json",
            }
            profile_response = http_requests.get(
                "https://api.dhan.co/v2/profile",
                headers=headers,
                timeout=10,
            )

            if profile_response.status_code == 401:
                raise ConnectionError("Dhan connection failed: Invalid access token")
            elif profile_response.status_code != 200:
                raise ConnectionError(
                    f"Dhan connection failed: API returned status {profile_response.status_code}"
                )

            profile_data = profile_response.json()
            # Verify client ID matches
            if profile_data.get("dhanClientId") and profile_data["dhanClientId"] != client_id:
                raise ConnectionError(
                    f"Dhan connection failed: Client ID mismatch. Token belongs to {profile_data['dhanClientId']}"
                )

        except ConnectionError:
            raise
        except Exception as e:
            raise ConnectionError(f"Dhan connection failed: {str(e)}")

        # Encrypt and store credentials
        encrypted_client_id = self.token_encryption.encrypt(client_id)
        encrypted_access_token = self.token_encryption.encrypt(access_token)

        connection = self._get_or_create_dhan_connection(db, user_id)
        connection.client_id_encrypted = encrypted_client_id
        connection.access_token_encrypted = encrypted_access_token
        connection.account_name = client_id
        connection.status = "connected"
        connection.error_message = None

        db.commit()
        logger.info("Stored encrypted Dhan credentials for user %d", user_id)
        return client_id

    def disconnect_dhan(self, db: Session, user_id: int) -> None:
        """Remove all stored Dhan credentials and set status to Disconnected.

        Clears access_token_encrypted, client_id_encrypted, account_name,
        error_message and sets status to "disconnected".

        Args:
            db: SQLAlchemy session.
            user_id: The user's ID.
        """
        connection = self._get_dhan_connection(db, user_id)

        if connection is not None:
            connection.access_token_encrypted = None
            connection.client_id_encrypted = None
            connection.account_name = None
            connection.status = "disconnected"
            connection.error_message = None
            db.commit()
            logger.info("Cleared Dhan credentials for user %d", user_id)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_kite_connection(
        self, db: Session, user_id: int
    ) -> Optional[BrokerConnection]:
        """Retrieve the user's Kite broker connection record.

        Args:
            db: SQLAlchemy session.
            user_id: The user's ID.

        Returns:
            The BrokerConnection record, or None if not found.
        """
        return (
            db.query(BrokerConnection)
            .filter(
                BrokerConnection.user_id == user_id,
                BrokerConnection.broker_type == "kite",
            )
            .first()
        )

    def _get_or_create_kite_connection(
        self, db: Session, user_id: int
    ) -> BrokerConnection:
        """Get or create a Kite broker connection record for the user.

        Args:
            db: SQLAlchemy session.
            user_id: The user's ID.

        Returns:
            The existing or newly created BrokerConnection record.
        """
        connection = self._get_kite_connection(db, user_id)
        if connection is None:
            connection = BrokerConnection(
                user_id=user_id,
                broker_type="kite",
                status="disconnected",
            )
            db.add(connection)
            db.flush()
        return connection

    def _get_dhan_connection(
        self, db: Session, user_id: int
    ) -> Optional[BrokerConnection]:
        """Retrieve the user's Dhan broker connection record.

        Args:
            db: SQLAlchemy session.
            user_id: The user's ID.

        Returns:
            The BrokerConnection record, or None if not found.
        """
        return (
            db.query(BrokerConnection)
            .filter(
                BrokerConnection.user_id == user_id,
                BrokerConnection.broker_type == "dhan",
            )
            .first()
        )

    def _get_or_create_dhan_connection(
        self, db: Session, user_id: int
    ) -> BrokerConnection:
        """Get or create a Dhan broker connection record for the user.

        Args:
            db: SQLAlchemy session.
            user_id: The user's ID.

        Returns:
            The existing or newly created BrokerConnection record.
        """
        connection = self._get_dhan_connection(db, user_id)
        if connection is None:
            connection = BrokerConnection(
                user_id=user_id,
                broker_type="dhan",
                status="disconnected",
            )
            db.add(connection)
            db.flush()
        return connection
