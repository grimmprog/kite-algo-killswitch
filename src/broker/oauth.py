"""Zerodha OAuth flow service.

Requirements covered:
- 1.2.1: Integrate with Zerodha Kite Connect API
- 1.2.2: Support OAuth-based broker authentication
- 1.2.3: Encrypt broker access tokens before storing in database
- 4.4.6: Use OAuth 2.0 for broker authentication
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from kiteconnect import KiteConnect

from src.broker.token_encryption import TokenEncryption

logger = logging.getLogger(__name__)


class OAuthError(Exception):
    """Raised when OAuth flow encounters an error."""
    pass


class ZerodhaOAuth:
    """Handles Zerodha Kite Connect OAuth authentication flow.

    The OAuth flow:
    1. Generate login URL → user is redirected to Zerodha login
    2. After login, Zerodha redirects back with a request_token
    3. Exchange request_token for access_token using API secret
    4. Store encrypted access_token in database
    """

    # Zerodha tokens expire at end of trading day (~3:30 PM IST next day)
    TOKEN_VALIDITY_HOURS = 24

    def __init__(self, api_key: str, api_secret: str, redirect_url: str):
        """Initialize ZerodhaOAuth with API credentials.

        Args:
            api_key: Zerodha Kite Connect API key.
            api_secret: Zerodha Kite Connect API secret.
            redirect_url: OAuth callback URL registered with Zerodha.

        Raises:
            ValueError: If any required parameter is empty.
        """
        if not api_key:
            raise ValueError("API key cannot be empty")
        if not api_secret:
            raise ValueError("API secret cannot be empty")
        if not redirect_url:
            raise ValueError("Redirect URL cannot be empty")

        self.api_key = api_key
        self.api_secret = api_secret
        self.redirect_url = redirect_url
        self._kite = KiteConnect(api_key=api_key)

    def get_login_url(self) -> str:
        """Generate Zerodha OAuth redirect URL.

        Returns:
            The login URL to redirect the user to for Zerodha authentication.
        """
        login_url = self._kite.login_url()
        logger.info("Generated Zerodha OAuth login URL")
        return login_url

    def handle_callback(self, request_token: str) -> dict:
        """Exchange request token for access token.

        This is called after the user completes Zerodha login and is
        redirected back with a request_token.

        Args:
            request_token: The request token received from Zerodha callback.

        Returns:
            Dictionary with keys:
                - access_token (str): The access token for API calls
                - public_token (str): Public token (less privileged)

        Raises:
            OAuthError: If token exchange fails.
            ValueError: If request_token is empty.
        """
        if not request_token:
            raise ValueError("Request token cannot be empty")

        try:
            data = self._kite.generate_session(
                request_token=request_token,
                api_secret=self.api_secret,
            )

            access_token = data.get("access_token")
            public_token = data.get("public_token", "")

            if not access_token:
                raise OAuthError("No access token in response from Zerodha")

            logger.info("Successfully exchanged request token for access token")

            return {
                "access_token": access_token,
                "public_token": public_token,
            }

        except OAuthError:
            raise
        except Exception as e:
            logger.error(f"OAuth token exchange failed: {type(e).__name__}")
            raise OAuthError(f"Failed to exchange request token: {e}")

    def store_tokens(
        self,
        user_id: int,
        access_token: str,
        db_session,
        encryptor: TokenEncryption,
        public_token: Optional[str] = None,
    ):
        """Encrypt and store tokens in database.

        Encrypts the access token using Fernet before persisting to
        the user record in the database.

        Args:
            user_id: The user's database ID.
            access_token: Plaintext access token to encrypt and store.
            db_session: SQLAlchemy database session.
            encryptor: TokenEncryption instance for encrypting tokens.
            public_token: Optional public token to store (also encrypted).

        Raises:
            OAuthError: If token storage fails.
            ValueError: If user_id or access_token is invalid.
        """
        if not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("user_id must be a positive integer")
        if not access_token:
            raise ValueError("Access token cannot be empty")

        try:
            from src.database.models.user import User

            user = db_session.query(User).filter_by(id=user_id).first()
            if not user:
                raise OAuthError(f"User with id {user_id} not found")

            # Encrypt tokens before storage
            encrypted_access = encryptor.encrypt(access_token)
            user.broker_access_token = encrypted_access

            if public_token:
                encrypted_public = encryptor.encrypt(public_token)
                user.broker_refresh_token = encrypted_public

            # Set token expiry (Zerodha tokens valid for ~24 hours)
            user.broker_token_expiry = datetime.now(timezone.utc) + timedelta(
                hours=self.TOKEN_VALIDITY_HOURS
            )

            db_session.commit()
            logger.info(f"Stored encrypted broker tokens for user {user_id}")

        except OAuthError:
            raise
        except Exception as e:
            db_session.rollback()
            logger.error(f"Failed to store tokens for user {user_id}: {type(e).__name__}")
            raise OAuthError(f"Failed to store tokens: {e}")
