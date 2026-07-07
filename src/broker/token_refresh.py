"""Token refresh logic for broker credentials.

Requirements covered:
- 1.2.4: Automatically refresh broker tokens before expiry
- 1.2.5: Notify users when broker token refresh fails
- 1.2.6: Allow users to manually reconnect broker account
- 4.4.7: Refresh broker tokens automatically
- 4.4.8: Handle broker token expiry
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class TokenRefreshError(Exception):
    """Raised when token refresh fails."""
    pass


class TokenRefreshService:
    """Manages broker token lifecycle and refresh logic.

    Zerodha Kite tokens expire daily (at end of trading day) and cannot
    be refreshed programmatically - users must re-login via OAuth each day.
    This service:
    - Checks token expiry status
    - Detects tokens approaching expiry (within 30-minute window)
    - Handles refresh failures by notifying users
    - Provides token status information for the UI

    Since Zerodha doesn't support traditional refresh tokens,
    "refresh" here means detecting expiry and prompting the user
    to re-authenticate via OAuth.
    """

    # Buffer period before actual expiry to flag token as "needs refresh"
    EXPIRY_BUFFER_MINUTES = 30

    def __init__(self, db_session_factory, notification_callback=None):
        """Initialize TokenRefreshService.

        Args:
            db_session_factory: Callable that returns a new SQLAlchemy session.
            notification_callback: Optional callable(user_id, message) for
                sending notifications to users when refresh is needed.

        Raises:
            ValueError: If db_session_factory is None.
        """
        if not db_session_factory:
            raise ValueError("Database session factory is required")

        self.db_session_factory = db_session_factory
        self.notification_callback = notification_callback

    def check_expiry(self, user_id: int) -> bool:
        """Check if user's broker token is expiring soon (within 30 minutes).

        Args:
            user_id: The user's database ID.

        Returns:
            True if token is expiring within the buffer period (30 min),
            False if token is still fresh or already expired.

        Raises:
            ValueError: If user_id is not a positive integer.
        """
        if not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("user_id must be a positive integer")

        db_session = self.db_session_factory()
        try:
            from src.database.models.user import User

            user = db_session.query(User).filter_by(id=user_id).first()
            if not user:
                return False

            # No token or no expiry set
            if not user.broker_access_token or not user.broker_token_expiry:
                return False

            now = datetime.now(timezone.utc)
            expiry = user.broker_token_expiry
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)

            buffer = timedelta(minutes=self.EXPIRY_BUFFER_MINUTES)

            # Token is "expiring soon" if within buffer period but not yet expired
            return (expiry - buffer) <= now < expiry

        except Exception as e:
            logger.error(f"Error checking token expiry for user {user_id}: {e}")
            return False
        finally:
            db_session.close()

    def is_expired(self, user_id: int) -> bool:
        """Check if user's broker token has already expired.

        Args:
            user_id: The user's database ID.

        Returns:
            True if token is expired or missing, False if still valid.

        Raises:
            ValueError: If user_id is not a positive integer.
        """
        if not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("user_id must be a positive integer")

        db_session = self.db_session_factory()
        try:
            from src.database.models.user import User

            user = db_session.query(User).filter_by(id=user_id).first()
            if not user:
                return True

            if not user.broker_access_token or not user.broker_token_expiry:
                return True

            now = datetime.now(timezone.utc)
            expiry = user.broker_token_expiry
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)

            return now >= expiry

        except Exception as e:
            logger.error(f"Error checking if token expired for user {user_id}: {e}")
            return True
        finally:
            db_session.close()

    def refresh_token(self, user_id: int) -> dict:
        """Attempt to refresh the user's broker token.

        Since Zerodha requires daily re-login via OAuth (no programmatic
        refresh), this method checks the token status and notifies the
        user if re-authentication is needed.

        Args:
            user_id: The user's database ID.

        Returns:
            Dictionary with:
                - status: "valid", "expiring_soon", "expired", or "missing"
                - message: Human-readable status message
                - requires_reauth: bool indicating if user must re-login

        Raises:
            ValueError: If user_id is not a positive integer.
        """
        if not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("user_id must be a positive integer")

        db_session = self.db_session_factory()
        try:
            from src.database.models.user import User

            user = db_session.query(User).filter_by(id=user_id).first()
            if not user:
                return {
                    "status": "missing",
                    "message": "User not found",
                    "requires_reauth": True,
                }

            if not user.broker_access_token:
                return {
                    "status": "missing",
                    "message": "No broker token found. Please connect your Zerodha account.",
                    "requires_reauth": True,
                }

            if not user.broker_token_expiry:
                return {
                    "status": "missing",
                    "message": "Token expiry unknown. Please reconnect your Zerodha account.",
                    "requires_reauth": True,
                }

            now = datetime.now(timezone.utc)
            expiry = user.broker_token_expiry
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)

            # Already expired
            if now >= expiry:
                message = "Broker token has expired. Please re-login to Zerodha."
                self._notify_user(user_id, message)
                return {
                    "status": "expired",
                    "message": message,
                    "requires_reauth": True,
                }

            # Expiring soon (within buffer)
            buffer = timedelta(minutes=self.EXPIRY_BUFFER_MINUTES)
            if (expiry - buffer) <= now:
                message = (
                    "Broker token expiring soon. "
                    "Please re-login to Zerodha to maintain connectivity."
                )
                self._notify_user(user_id, message)
                return {
                    "status": "expiring_soon",
                    "message": message,
                    "requires_reauth": True,
                }

            # Token is still valid
            remaining = expiry - now
            hours_remaining = remaining.total_seconds() / 3600
            return {
                "status": "valid",
                "message": f"Token valid for {hours_remaining:.1f} more hours.",
                "requires_reauth": False,
            }

        except Exception as e:
            logger.error(f"Error during token refresh check for user {user_id}: {e}")
            return {
                "status": "expired",
                "message": "Error checking token status. Please reconnect.",
                "requires_reauth": True,
            }
        finally:
            db_session.close()

    def handle_refresh_failure(self, user_id: int, error: Exception):
        """Handle a token refresh failure.

        Logs the error, marks the token as requiring re-auth, and
        notifies the user that they need to reconnect their broker.

        Args:
            user_id: The user's database ID.
            error: The exception that caused the failure.

        Raises:
            ValueError: If user_id is not a positive integer.
        """
        if not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("user_id must be a positive integer")

        logger.warning(
            f"Token refresh failed for user {user_id}: "
            f"{type(error).__name__}: {error}"
        )

        # Mark token as expired in database
        db_session = self.db_session_factory()
        try:
            from src.database.models.user import User

            user = db_session.query(User).filter_by(id=user_id).first()
            if user:
                # Set expiry to now so token is marked as expired
                user.broker_token_expiry = datetime.now(timezone.utc)
                db_session.commit()
                logger.info(f"Marked token as expired for user {user_id} due to refresh failure")
        except Exception as e:
            db_session.rollback()
            logger.error(
                f"Failed to mark token expired for user {user_id}: {e}"
            )
        finally:
            db_session.close()

        # Notify user
        message = (
            "Your Zerodha session has expired. "
            "Please re-login to continue trading."
        )
        self._notify_user(user_id, message)

    def _notify_user(self, user_id: int, message: str):
        """Send notification to user if callback is configured.

        Args:
            user_id: The user's database ID.
            message: The notification message.
        """
        if self.notification_callback:
            try:
                self.notification_callback(user_id, message)
                logger.info(f"Sent notification to user {user_id}: {message}")
            except Exception as e:
                logger.error(
                    f"Failed to send notification to user {user_id}: {e}"
                )
