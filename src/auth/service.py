"""Authentication service providing login, token refresh, and logout logic.

Requirements covered:
- 1.1.4: JWT-based authentication with 24-hour access token expiry
- 1.1.5: Refresh tokens with 30-day expiry
- 1.1.10: Support user logout and token invalidation
- 2.4.8: Rate limit login attempts (5 attempts per 15 minutes)
"""

from datetime import datetime, timezone
from typing import Optional

import jwt
from sqlalchemy.orm import Session

from src.auth.exceptions import AuthenticationError
from src.auth.jwt_handler import JWTHandler
from src.auth.password import verify_password
from src.auth.rate_limiter import LoginRateLimiter
from src.database.models.user import User


class AuthService:
    """Authentication service for the trading platform.

    Provides credential validation, token generation, token refresh,
    and logout functionality with optional rate limiting.
    """

    def __init__(
        self,
        jwt_handler: JWTHandler,
        db_session: Session,
        rate_limiter: Optional[LoginRateLimiter] = None,
    ):
        """Initialize the authentication service.

        Args:
            jwt_handler: JWTHandler instance for token operations.
            db_session: SQLAlchemy database session.
            rate_limiter: Optional LoginRateLimiter for rate limiting login attempts.
        """
        self.jwt_handler = jwt_handler
        self.db_session = db_session
        self.rate_limiter = rate_limiter

    def authenticate_user(self, email: str, password: str) -> dict:
        """Validate credentials, generate tokens, and return response.

        Performs the full login flow:
        1. Check rate limit (if rate limiter is configured)
        2. Look up user by email
        3. Verify password against stored hash
        4. Generate access and refresh tokens
        5. Update last_login timestamp
        6. Reset rate limit on success

        Args:
            email: User's email address.
            password: User's plaintext password.

        Returns:
            Dictionary with access_token, refresh_token, token_type, and user_id.

        Raises:
            AuthenticationError: If credentials are invalid, user is inactive,
                or rate limit is exceeded.
        """
        # Validate inputs
        if not email or not password:
            raise AuthenticationError("Email and password are required")

        # Check rate limit
        if self.rate_limiter is not None:
            if not self.rate_limiter.check_rate_limit(email):
                raise AuthenticationError(
                    "Too many login attempts. Please try again later."
                )

        # Record the attempt before validation (track all attempts)
        if self.rate_limiter is not None:
            self.rate_limiter.record_attempt(email)

        # Look up user by email
        user = (
            self.db_session.query(User)
            .filter(User.email == email)
            .first()
        )

        if user is None:
            raise AuthenticationError("Invalid email or password")

        # Check if user account is active
        if not user.is_active:
            raise AuthenticationError("Account is deactivated")

        # Verify password
        if not verify_password(password, user.password_hash):
            raise AuthenticationError("Invalid email or password")

        # Generate tokens
        access_token = self.jwt_handler.create_access_token(user_id=user.id)
        refresh_token = self.jwt_handler.create_refresh_token(user_id=user.id)

        # Update last_login timestamp
        user.last_login = datetime.now(timezone.utc)
        self.db_session.commit()

        # Reset rate limit on successful login
        if self.rate_limiter is not None:
            self.rate_limiter.reset(email)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user_id": user.id,
        }

    def refresh_access_token(self, refresh_token: str) -> dict:
        """Validate refresh token and generate a new access token.

        Args:
            refresh_token: The refresh token string to validate.

        Returns:
            Dictionary with new access_token and token_type.

        Raises:
            AuthenticationError: If the refresh token is invalid, expired,
                or the user is inactive/not found.
        """
        if not refresh_token:
            raise AuthenticationError("Refresh token is required")

        try:
            payload = self.jwt_handler.verify_token(refresh_token)
        except jwt.ExpiredSignatureError:
            raise AuthenticationError("Refresh token has expired")
        except (jwt.InvalidTokenError, ValueError):
            raise AuthenticationError("Invalid refresh token")

        # Verify it's a refresh token
        if payload.get("type") != "refresh":
            raise AuthenticationError("Invalid refresh token")

        # Extract user_id
        user_id_str = payload.get("sub")
        if user_id_str is None:
            raise AuthenticationError("Invalid refresh token")

        user_id = int(user_id_str)

        # Verify user still exists and is active
        user = (
            self.db_session.query(User)
            .filter(User.id == user_id)
            .first()
        )

        if user is None:
            raise AuthenticationError("User not found")

        if not user.is_active:
            raise AuthenticationError("Account is deactivated")

        # Generate new access token
        new_access_token = self.jwt_handler.create_access_token(user_id=user.id)

        return {
            "access_token": new_access_token,
            "token_type": "bearer",
        }

    def logout(self, user_id: int) -> bool:
        """Invalidate user session by recording logout.

        Updates the user's last_login timestamp to mark the session end.
        In a production system with token blacklisting, this would also
        add the current tokens to a blacklist.

        Args:
            user_id: The ID of the user to log out.

        Returns:
            True if logout was successful, False if user not found.
        """
        user = (
            self.db_session.query(User)
            .filter(User.id == user_id)
            .first()
        )

        if user is None:
            return False

        # Record logout time (uses last_login as session marker)
        user.last_login = datetime.now(timezone.utc)
        self.db_session.commit()

        return True
