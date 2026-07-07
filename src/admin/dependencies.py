"""Dependency functions for the Admin Testing UI.

Provides FastAPI dependency injection for Redis client and
SQLAlchemy database sessions, reusing existing patterns from
the trading platform.
"""

import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.cache.redis_client import RedisClient, get_redis_client

# Database URL from environment
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:admin@localhost:5432/trading_platform",
)

# Module-level engine/session factory (lazy init)
_engine = None
_SessionFactory = None


def _get_session_factory():
    """Get or create the SQLAlchemy session factory (lazy singleton).

    Returns:
        A sessionmaker bound to the database engine.
    """
    global _engine, _SessionFactory
    if _SessionFactory is None:
        _engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        _SessionFactory = sessionmaker(bind=_engine)
    return _SessionFactory


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that provides a database session.

    Yields a SQLAlchemy Session and ensures it is closed after the
    request completes.

    Yields:
        A SQLAlchemy Session instance.
    """
    factory = _get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()


def get_redis() -> RedisClient:
    """FastAPI dependency that provides the Redis client.

    Returns the singleton RedisClient instance from the cache module.

    Returns:
        The shared RedisClient instance.
    """
    return get_redis_client()
