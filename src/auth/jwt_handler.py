"""JWT token generation and validation.

Requirements covered:
- 1.1.4: JWT-based authentication with 24-hour access token expiry
- 1.1.5: Refresh tokens with 30-day expiry
- 2.4.2: Validate JWT tokens on every API request
"""

import jwt
from datetime import datetime, timedelta, timezone
from typing import Optional


class JWTHandler:
    """Handles JWT token creation and verification.

    Supports both access tokens (24h expiry) and refresh tokens (30-day expiry).
    Uses HS256 algorithm by default for token signing.
    """

    ACCESS_TOKEN_EXPIRY_HOURS = 24
    REFRESH_TOKEN_EXPIRY_DAYS = 30

    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        """Initialize JWTHandler with signing configuration.

        Args:
            secret_key: Secret key used for signing and verifying tokens.
            algorithm: JWT signing algorithm (default: HS256).

        Raises:
            ValueError: If secret_key is empty or None.
        """
        if not secret_key:
            raise ValueError("Secret key cannot be empty")
        self.secret_key = secret_key
        self.algorithm = algorithm

    def create_access_token(self, user_id: int, extra_claims: Optional[dict] = None) -> str:
        """Create JWT access token with 24-hour expiry.

        Args:
            user_id: The user's unique identifier.
            extra_claims: Optional additional claims to include in the token.

        Returns:
            Encoded JWT access token string.

        Raises:
            ValueError: If user_id is not a positive integer.
        """
        if not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("user_id must be a positive integer")

        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(user_id),
            "type": "access",
            "iat": now,
            "exp": now + timedelta(hours=self.ACCESS_TOKEN_EXPIRY_HOURS),
        }

        if extra_claims:
            payload.update(extra_claims)

        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def create_refresh_token(self, user_id: int) -> str:
        """Create JWT refresh token with 30-day expiry.

        Args:
            user_id: The user's unique identifier.

        Returns:
            Encoded JWT refresh token string.

        Raises:
            ValueError: If user_id is not a positive integer.
        """
        if not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("user_id must be a positive integer")

        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(user_id),
            "type": "refresh",
            "iat": now,
            "exp": now + timedelta(days=self.REFRESH_TOKEN_EXPIRY_DAYS),
        }

        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def verify_token(self, token: str) -> dict:
        """Verify token signature and expiry, return payload.

        Args:
            token: The JWT token string to verify.

        Returns:
            Decoded token payload as dictionary.

        Raises:
            jwt.ExpiredSignatureError: If the token has expired.
            jwt.InvalidTokenError: If the token is invalid or tampered.
            ValueError: If token is empty.
        """
        if not token:
            raise ValueError("Token cannot be empty")

        payload = jwt.decode(
            token,
            self.secret_key,
            algorithms=[self.algorithm],
        )
        return payload

    def extract_user_id(self, token: str) -> int:
        """Extract user_id from token.

        Args:
            token: The JWT token string.

        Returns:
            The user_id (sub claim) from the token.

        Raises:
            jwt.ExpiredSignatureError: If the token has expired.
            jwt.InvalidTokenError: If the token is invalid or tampered.
            ValueError: If token is empty or user_id is missing from payload.
        """
        payload = self.verify_token(token)
        user_id = payload.get("sub")
        if user_id is None:
            raise ValueError("Token does not contain user_id (sub claim)")
        return int(user_id)
