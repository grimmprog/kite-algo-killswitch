"""FastAPI dependency injection utilities.

Provides reusable dependencies for route handlers:
- Database session (auto-closed after request)
- Redis client
- Current authenticated user (from JWT token)

Requirements covered:
- 2.4.2: Validate JWT tokens on every API request
- 1.1.4: JWT-based authentication
"""

import os
from typing import Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.cache.redis_client import RedisClient, get_redis_client

# Database URL from environment
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/trading_platform",
)

# JWT secret from environment
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-secret-key")

# Module-level engine/session factory (lazy init)
_engine = None
_SessionFactory = None


def _get_session_factory() -> sessionmaker:
    """Get or create the SQLAlchemy session factory (lazy singleton).

    Returns:
        A sessionmaker bound to the database engine.
    """
    global _engine, _SessionFactory
    if _SessionFactory is None:
        _engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        _SessionFactory = sessionmaker(bind=_engine)
    return _SessionFactory


# --------------------------------------------------------------------------
# 8.2.1: Database session dependency
# --------------------------------------------------------------------------


def get_db() -> Generator[Session, None, None]:
    """Yield a database session that auto-closes after the request.

    Yields:
        A SQLAlchemy Session instance.
    """
    factory = _get_session_factory()
    db = factory()
    try:
        yield db
    finally:
        db.close()


# --------------------------------------------------------------------------
# 8.2.2: Redis client dependency
# --------------------------------------------------------------------------


def get_redis() -> RedisClient:
    """Return the shared Redis client.

    Returns:
        The singleton RedisClient instance.
    """
    return get_redis_client()


# --------------------------------------------------------------------------
# 8.2.3: Current user dependency
# --------------------------------------------------------------------------

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> int:
    """Extract and validate user_id from JWT token.

    Decodes the Bearer token, verifies the signature and expiry,
    then confirms the user exists and is active in the database.

    Args:
        credentials: HTTP Bearer token from the Authorization header.
        db: Database session (injected).

    Returns:
        The user_id (int) from the token.

    Raises:
        HTTPException: 401 if token is invalid, expired, or user not found/inactive.
    """
    from src.auth.jwt_handler import JWTHandler
    from src.database.models.user import User

    import jwt as pyjwt

    token = credentials.credentials

    handler = JWTHandler(secret_key=JWT_SECRET_KEY)

    try:
        payload = handler.verify_token(token)
    except (pyjwt.ExpiredSignatureError, pyjwt.InvalidTokenError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub") or payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing user identifier",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify user exists and is active
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user.id
