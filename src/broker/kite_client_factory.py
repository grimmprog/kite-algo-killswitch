"""Factory for creating user-specific Kite Connect clients.

Requirements covered:
- 1.2.1: Integrate with Zerodha Kite Connect API
- 1.2.4: Automatically refresh broker tokens before expiry
- 4.4.1: Use Kite Connect API for all broker operations
- 4.4.3: Handle broker API errors gracefully
"""

import logging
import threading
from datetime import datetime, timezone
from typing import Optional

from kiteconnect import KiteConnect

from src.broker.token_encryption import TokenEncryption, TokenEncryptionError

logger = logging.getLogger(__name__)


class BrokerAuthError(Exception):
    """Raised when broker authentication fails or token is invalid."""
    pass


class TokenExpiredError(BrokerAuthError):
    """Raised when the broker token has expired and needs re-authentication."""
    pass


class KiteClientFactory:
    """Factory to get user-specific Kite Connect clients.

    Manages a pool of KiteConnect instances per user, handles token
    decryption, validates token expiry, and handles authentication errors.

    Thread-safe: uses locks for client pool access.
    """

    # Refresh buffer: refresh tokens 30 minutes before expiry
    REFRESH_BUFFER_MINUTES = 30

    def __init__(self, api_key: str, token_encryption: TokenEncryption, db_session_factory):
        """Initialize KiteClientFactory.

        Args:
            api_key: Zerodha Kite Connect API key.
            token_encryption: TokenEncryption instance for decrypting stored tokens.
            db_session_factory: Callable that returns a new SQLAlchemy session.

        Raises:
            ValueError: If api_key is empty.
        """
        if not api_key:
            raise ValueError("API key cannot be empty")
        if not token_encryption:
            raise ValueError("Token encryption instance is required")
        if not db_session_factory:
            raise ValueError("Database session factory is required")

        self.api_key = api_key
        self.token_encryption = token_encryption
        self.db_session_factory = db_session_factory

        # Connection pool: user_id -> KiteConnect instance
        self._clients: dict[int, KiteConnect] = {}
        self._lock = threading.Lock()

    def get_client(self, user_id: int) -> KiteConnect:
        """Get a configured Kite client for a specific user.

        Retrieves or creates a KiteConnect instance with the user's
        decrypted access token. Validates token hasn't expired.

        Args:
            user_id: The user's database ID.

        Returns:
            A configured KiteConnect instance ready for API calls.

        Raises:
            BrokerAuthError: If user has no broker token or token is invalid.
            TokenExpiredError: If the token has expired and needs re-auth.
            ValueError: If user_id is invalid.
        """
        if not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("user_id must be a positive integer")

        # Check token validity first
        if not self.check_token_validity(user_id):
            self._invalidate_client(user_id)
            raise TokenExpiredError(
                f"Broker token expired for user {user_id}. Re-authentication required."
            )

        with self._lock:
            # Return cached client if available
            if user_id in self._clients:
                return self._clients[user_id]

        # Create new client
        access_token = self._get_decrypted_token(user_id)
        client = KiteConnect(api_key=self.api_key)
        client.set_access_token(access_token)

        with self._lock:
            self._clients[user_id] = client

        logger.info(f"Created Kite client for user {user_id}")
        return client

    def check_token_validity(self, user_id: int) -> bool:
        """Check if user's token is still valid (not expired).

        Considers a token invalid if it expires within the refresh buffer
        period (30 minutes before actual expiry).

        Args:
            user_id: The user's database ID.

        Returns:
            True if token is valid, False if expired or missing.
        """
        if not isinstance(user_id, int) or user_id <= 0:
            return False

        db_session = self.db_session_factory()
        try:
            from src.database.models.user import User

            user = db_session.query(User).filter_by(id=user_id).first()
            if not user:
                return False

            # No token stored
            if not user.broker_access_token:
                return False

            # No expiry set - treat as invalid
            if not user.broker_token_expiry:
                return False

            # Check if token expires within refresh buffer
            now = datetime.now(timezone.utc)
            # Handle timezone-naive expiry from database
            expiry = user.broker_token_expiry
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)

            from datetime import timedelta
            buffer_time = timedelta(minutes=self.REFRESH_BUFFER_MINUTES)

            return now < (expiry - buffer_time)

        except Exception as e:
            logger.error(f"Error checking token validity for user {user_id}: {e}")
            return False
        finally:
            db_session.close()

    def needs_refresh(self, user_id: int) -> bool:
        """Check if user's token needs refresh (within buffer period).

        Args:
            user_id: The user's database ID.

        Returns:
            True if token needs refresh but hasn't fully expired yet.
        """
        if not isinstance(user_id, int) or user_id <= 0:
            return False

        db_session = self.db_session_factory()
        try:
            from src.database.models.user import User

            user = db_session.query(User).filter_by(id=user_id).first()
            if not user or not user.broker_token_expiry:
                return False

            now = datetime.now(timezone.utc)
            expiry = user.broker_token_expiry
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)

            from datetime import timedelta
            buffer_time = timedelta(minutes=self.REFRESH_BUFFER_MINUTES)

            # Needs refresh if within buffer but not yet expired
            return (expiry - buffer_time) <= now < expiry

        except Exception as e:
            logger.error(f"Error checking refresh need for user {user_id}: {e}")
            return False
        finally:
            db_session.close()

    def handle_auth_error(self, user_id: int, error: Exception):
        """Handle authentication errors (mark token as invalid).

        When a broker API call fails with an auth error, this invalidates
        the cached client and marks the token as expired in the database
        so the user is prompted to re-authenticate.

        Args:
            user_id: The user's database ID.
            error: The exception that triggered the auth error.
        """
        logger.warning(
            f"Broker auth error for user {user_id}: {type(error).__name__}: {error}"
        )

        # Remove cached client
        self._invalidate_client(user_id)

        # Mark token as expired in database
        db_session = self.db_session_factory()
        try:
            from src.database.models.user import User

            user = db_session.query(User).filter_by(id=user_id).first()
            if user:
                user.broker_token_expiry = datetime.now(timezone.utc)
                db_session.commit()
                logger.info(f"Marked broker token as expired for user {user_id}")
        except Exception as e:
            db_session.rollback()
            logger.error(f"Failed to mark token expired for user {user_id}: {e}")
        finally:
            db_session.close()

    def invalidate_user(self, user_id: int):
        """Remove a user's client from the pool.

        Call this when a user logs out or their token is explicitly revoked.

        Args:
            user_id: The user's database ID.
        """
        self._invalidate_client(user_id)
        logger.info(f"Invalidated Kite client for user {user_id}")

    def get_pool_size(self) -> int:
        """Get the current number of cached clients.

        Returns:
            Number of active clients in the pool.
        """
        with self._lock:
            return len(self._clients)

    def _get_decrypted_token(self, user_id: int) -> str:
        """Retrieve and decrypt user's broker access token.

        Args:
            user_id: The user's database ID.

        Returns:
            Decrypted plaintext access token.

        Raises:
            BrokerAuthError: If no token found or decryption fails.
        """
        db_session = self.db_session_factory()
        try:
            from src.database.models.user import User

            user = db_session.query(User).filter_by(id=user_id).first()
            if not user:
                raise BrokerAuthError(f"User {user_id} not found")

            if not user.broker_access_token:
                raise BrokerAuthError(
                    f"No broker token stored for user {user_id}. "
                    "Please connect your Zerodha account."
                )

            try:
                decrypted = self.token_encryption.decrypt(user.broker_access_token)
                return decrypted
            except TokenEncryptionError as e:
                raise BrokerAuthError(
                    f"Failed to decrypt broker token for user {user_id}: {e}"
                )

        finally:
            db_session.close()

    def _invalidate_client(self, user_id: int):
        """Remove client from the pool (thread-safe).

        Args:
            user_id: The user's database ID.
        """
        with self._lock:
            self._clients.pop(user_id, None)
