"""Authentication module for the Multi-User Web Trading Platform.

Provides JWT token generation/validation, password hashing utilities,
authentication service, rate limiting, and custom exceptions.

Requirements covered:
- 1.1.2: Password hashing using bcrypt with cost factor 12
- 1.1.3: Minimum password length of 8 characters
- 1.1.4: JWT-based authentication with 24-hour token expiry
- 1.1.5: Refresh tokens with 30-day expiry
- 1.1.10: Support user logout and token invalidation
- 2.4.8: Rate limit login attempts (5 attempts per 15 minutes)
"""

from src.auth.exceptions import AuthenticationError
from src.auth.jwt_handler import JWTHandler
from src.auth.password import hash_password, verify_password
from src.auth.rate_limiter import LoginRateLimiter
from src.auth.service import AuthService

__all__ = [
    "AuthenticationError",
    "AuthService",
    "JWTHandler",
    "LoginRateLimiter",
    "hash_password",
    "verify_password",
]
