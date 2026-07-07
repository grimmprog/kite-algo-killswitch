"""
Redis Client Wrapper for Multi-User Web Trading Platform.

Provides a convenient wrapper around redis-py with connection pooling,
graceful error handling, and typed helpers for common operations.

Validates: Requirements 2.3.3, 2.3.4, 3.6
"""

import logging
import os
from typing import Any, Dict, List, Optional

import redis

logger = logging.getLogger(__name__)

# Module-level singleton
_redis_client: Optional["RedisClient"] = None


class RedisClient:
    """Wrapper around redis-py providing convenient typed helpers.

    Features:
    - Connection pooling via redis.ConnectionPool
    - Graceful error handling (logs errors, returns safe defaults)
    - Typed get/set, hash, list, and TTL operations

    Usage:
        client = get_redis_client()
        client.set("key", "value", ttl=60)
        value = client.get("key")
    """

    def __init__(
        self,
        url: Optional[str] = None,
        max_connections: int = 50,
    ) -> None:
        """Initialize RedisClient with a connection pool.

        Args:
            url: Redis URL. Defaults to REDIS_URL env var or redis://localhost:6379/0.
            max_connections: Maximum number of connections in the pool.
        """
        self._url = url or os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        self._pool = redis.ConnectionPool.from_url(
            self._url,
            max_connections=max_connections,
            decode_responses=True,
        )
        self._client = redis.Redis(connection_pool=self._pool)
        logger.info("Redis client initialized with pool (max_connections=%d)", max_connections)

    @property
    def client(self) -> redis.Redis:
        """Access the underlying redis.Redis instance."""
        return self._client

    # ------------------------------------------------------------------
    # 2.2.2: Get/Set Helpers
    # ------------------------------------------------------------------

    def get(self, key: str) -> Optional[str]:
        """Get a string value by key.

        Args:
            key: The Redis key.

        Returns:
            The value as a string, or None if the key does not exist.
        """
        try:
            return self._client.get(key)
        except redis.RedisError as e:
            logger.error("Redis GET error for key '%s': %s", key, e)
            return None

    def set(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        """Set a string value, optionally with a TTL.

        Args:
            key: The Redis key.
            value: The string value to store.
            ttl: Optional time-to-live in seconds.

        Returns:
            True if the operation succeeded, False otherwise.
        """
        try:
            if ttl is not None:
                result = self._client.setex(key, ttl, value)
            else:
                result = self._client.set(key, value)
            return bool(result)
        except redis.RedisError as e:
            logger.error("Redis SET error for key '%s': %s", key, e)
            return False

    def delete(self, key: str) -> int:
        """Delete a key.

        Args:
            key: The Redis key to delete.

        Returns:
            Number of keys deleted (0 or 1).
        """
        try:
            return self._client.delete(key)
        except redis.RedisError as e:
            logger.error("Redis DELETE error for key '%s': %s", key, e)
            return 0

    def exists(self, key: str) -> bool:
        """Check if a key exists.

        Args:
            key: The Redis key to check.

        Returns:
            True if the key exists, False otherwise.
        """
        try:
            return bool(self._client.exists(key))
        except redis.RedisError as e:
            logger.error("Redis EXISTS error for key '%s': %s", key, e)
            return False

    # ------------------------------------------------------------------
    # 2.2.3: Hash Operations
    # ------------------------------------------------------------------

    def hset(self, key: str, mapping: Dict[str, Any]) -> int:
        """Set multiple hash fields at once.

        Args:
            key: The Redis hash key.
            mapping: Dictionary of field-value pairs to set.

        Returns:
            Number of fields that were added (not updated).
        """
        try:
            return self._client.hset(key, mapping=mapping)
        except redis.RedisError as e:
            logger.error("Redis HSET error for key '%s': %s", key, e)
            return 0

    def hget(self, key: str, field: str) -> Optional[str]:
        """Get a single field from a hash.

        Args:
            key: The Redis hash key.
            field: The hash field name.

        Returns:
            The field value as a string, or None if not found.
        """
        try:
            return self._client.hget(key, field)
        except redis.RedisError as e:
            logger.error("Redis HGET error for key '%s' field '%s': %s", key, field, e)
            return None

    def hgetall(self, key: str) -> Dict[str, str]:
        """Get all fields and values from a hash.

        Args:
            key: The Redis hash key.

        Returns:
            Dictionary of all field-value pairs, or empty dict on error.
        """
        try:
            return self._client.hgetall(key)
        except redis.RedisError as e:
            logger.error("Redis HGETALL error for key '%s': %s", key, e)
            return {}

    def hdel(self, key: str, *fields: str) -> int:
        """Delete one or more fields from a hash.

        Args:
            key: The Redis hash key.
            *fields: Field names to delete.

        Returns:
            Number of fields that were removed.
        """
        try:
            return self._client.hdel(key, *fields)
        except redis.RedisError as e:
            logger.error("Redis HDEL error for key '%s': %s", key, e)
            return 0

    # ------------------------------------------------------------------
    # 2.2.4: List Operations
    # ------------------------------------------------------------------

    def lpush(self, key: str, *values: str) -> int:
        """Push one or more values to the head of a list.

        Args:
            key: The Redis list key.
            *values: Values to push.

        Returns:
            Length of the list after the push operation.
        """
        try:
            return self._client.lpush(key, *values)
        except redis.RedisError as e:
            logger.error("Redis LPUSH error for key '%s': %s", key, e)
            return 0

    def lrange(self, key: str, start: int, stop: int) -> List[str]:
        """Get a range of elements from a list.

        Args:
            key: The Redis list key.
            start: Start index (0-based, inclusive).
            stop: Stop index (inclusive, use -1 for end).

        Returns:
            List of values in the specified range.
        """
        try:
            return self._client.lrange(key, start, stop)
        except redis.RedisError as e:
            logger.error("Redis LRANGE error for key '%s': %s", key, e)
            return []

    def ltrim(self, key: str, start: int, stop: int) -> bool:
        """Trim a list to the specified range.

        Args:
            key: The Redis list key.
            start: Start index to keep.
            stop: Stop index to keep (inclusive, use -1 for end).

        Returns:
            True if the operation succeeded, False otherwise.
        """
        try:
            return bool(self._client.ltrim(key, start, stop))
        except redis.RedisError as e:
            logger.error("Redis LTRIM error for key '%s': %s", key, e)
            return False

    def llen(self, key: str) -> int:
        """Get the length of a list.

        Args:
            key: The Redis list key.

        Returns:
            Length of the list, or 0 on error.
        """
        try:
            return self._client.llen(key)
        except redis.RedisError as e:
            logger.error("Redis LLEN error for key '%s': %s", key, e)
            return 0

    # ------------------------------------------------------------------
    # 2.2.5: TTL Management
    # ------------------------------------------------------------------

    def expire(self, key: str, seconds: int) -> bool:
        """Set a TTL on an existing key.

        Args:
            key: The Redis key.
            seconds: Number of seconds until expiry.

        Returns:
            True if the timeout was set, False if key does not exist or on error.
        """
        try:
            return bool(self._client.expire(key, seconds))
        except redis.RedisError as e:
            logger.error("Redis EXPIRE error for key '%s': %s", key, e)
            return False

    def ttl(self, key: str) -> int:
        """Get the remaining TTL of a key.

        Args:
            key: The Redis key.

        Returns:
            TTL in seconds, -1 if no TTL, -2 if key does not exist.
        """
        try:
            return self._client.ttl(key)
        except redis.RedisError as e:
            logger.error("Redis TTL error for key '%s': %s", key, e)
            return -2

    def setex(self, key: str, seconds: int, value: str) -> bool:
        """Set a key with an expiry time.

        Args:
            key: The Redis key.
            seconds: Time-to-live in seconds.
            value: The string value to store.

        Returns:
            True if the operation succeeded, False otherwise.
        """
        try:
            return bool(self._client.setex(key, seconds, value))
        except redis.RedisError as e:
            logger.error("Redis SETEX error for key '%s': %s", key, e)
            return False

    def persist(self, key: str) -> bool:
        """Remove the TTL from a key, making it persistent.

        Args:
            key: The Redis key.

        Returns:
            True if the timeout was removed, False if key does not exist
            or has no TTL.
        """
        try:
            return bool(self._client.persist(key))
        except redis.RedisError as e:
            logger.error("Redis PERSIST error for key '%s': %s", key, e)
            return False

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def ping(self) -> bool:
        """Check if Redis is reachable.

        Returns:
            True if Redis responds to PING, False otherwise.
        """
        try:
            return self._client.ping()
        except redis.RedisError as e:
            logger.error("Redis PING failed: %s", e)
            return False

    def close(self) -> None:
        """Close all connections in the pool."""
        self._pool.disconnect()
        logger.info("Redis connection pool closed.")


def get_redis_client(
    url: Optional[str] = None,
    max_connections: int = 50,
) -> RedisClient:
    """Get or create the singleton RedisClient instance.

    Args:
        url: Redis URL (only used on first call).
        max_connections: Max pool connections (only used on first call).

    Returns:
        The shared RedisClient instance.
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient(url=url, max_connections=max_connections)
    return _redis_client


def reset_redis_client() -> None:
    """Reset the singleton (useful for testing)."""
    global _redis_client
    if _redis_client is not None:
        _redis_client.close()
    _redis_client = None
