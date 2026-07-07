"""Tests for Redis failover behavior.

Verifies that the Redis client handles connection failures gracefully,
returning safe defaults instead of raising exceptions.

Validates: Requirement 2.3.3 (Handle Redis connection loss gracefully)
"""

import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch

import pytest
import redis as redis_lib

from src.cache.redis_client import RedisClient, reset_redis_client


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the module-level singleton before each test."""
    reset_redis_client()
    yield
    reset_redis_client()


@pytest.fixture
def failing_redis():
    """Create a RedisClient where the underlying client raises ConnectionError on all ops."""
    with patch("src.cache.redis_client.redis.ConnectionPool.from_url") as mock_pool:
        with patch("src.cache.redis_client.redis.Redis") as mock_redis_cls:
            mock_client_instance = MagicMock()
            # Simulate Redis being completely unavailable
            conn_error = redis_lib.ConnectionError("Connection refused")
            mock_client_instance.get.side_effect = conn_error
            mock_client_instance.set.side_effect = conn_error
            mock_client_instance.setex.side_effect = conn_error
            mock_client_instance.hgetall.side_effect = conn_error
            mock_client_instance.lpush.side_effect = conn_error
            mock_client_instance.exists.side_effect = conn_error
            mock_client_instance.ping.side_effect = conn_error
            mock_client_instance.delete.side_effect = conn_error
            mock_client_instance.hset.side_effect = conn_error
            mock_client_instance.hget.side_effect = conn_error
            mock_client_instance.lrange.side_effect = conn_error
            mock_client_instance.ltrim.side_effect = conn_error
            mock_client_instance.llen.side_effect = conn_error
            mock_client_instance.expire.side_effect = conn_error
            mock_client_instance.ttl.side_effect = conn_error
            mock_client_instance.persist.side_effect = conn_error
            mock_redis_cls.return_value = mock_client_instance
            client = RedisClient(url="redis://localhost:6379/0", max_connections=10)
            yield client, mock_client_instance


@pytest.fixture
def recoverable_redis():
    """Create a RedisClient that fails initially then recovers."""
    with patch("src.cache.redis_client.redis.ConnectionPool.from_url") as mock_pool:
        with patch("src.cache.redis_client.redis.Redis") as mock_redis_cls:
            mock_client_instance = MagicMock()
            mock_redis_cls.return_value = mock_client_instance
            client = RedisClient(url="redis://localhost:6379/0", max_connections=10)
            yield client, mock_client_instance


class TestGetFailover:
    """Test that get() returns None when Redis is unavailable."""

    def test_get_returns_none_on_connection_error(self, failing_redis):
        """When Redis is unavailable, get() returns None (not an exception)."""
        client, _ = failing_redis
        result = client.get("some_key")
        assert result is None

    def test_get_returns_none_on_redis_error(self):
        """When Redis raises RedisError, get() returns None."""
        with patch("src.cache.redis_client.redis.ConnectionPool.from_url"):
            with patch("src.cache.redis_client.redis.Redis") as mock_redis_cls:
                mock_instance = MagicMock()
                mock_instance.get.side_effect = redis_lib.RedisError("general error")
                mock_redis_cls.return_value = mock_instance
                client = RedisClient(url="redis://localhost:6379/0")
                assert client.get("key") is None


class TestSetFailover:
    """Test that set() returns False when Redis is unavailable."""

    def test_set_returns_false_on_connection_error(self, failing_redis):
        """When Redis is unavailable, set() returns False (not an exception)."""
        client, _ = failing_redis
        result = client.set("key", "value")
        assert result is False

    def test_set_with_ttl_returns_false_on_connection_error(self, failing_redis):
        """When Redis is unavailable, set() with TTL returns False."""
        client, _ = failing_redis
        result = client.set("key", "value", ttl=60)
        assert result is False


class TestHgetallFailover:
    """Test that hgetall() returns empty dict when Redis is unavailable."""

    def test_hgetall_returns_empty_dict_on_connection_error(self, failing_redis):
        """When Redis is unavailable, hgetall() returns empty dict."""
        client, _ = failing_redis
        result = client.hgetall("myhash")
        assert result == {}
        assert isinstance(result, dict)


class TestLpushFailover:
    """Test that lpush() returns 0 when Redis is unavailable."""

    def test_lpush_returns_zero_on_connection_error(self, failing_redis):
        """When Redis is unavailable, lpush() returns 0."""
        client, _ = failing_redis
        result = client.lpush("mylist", "value1", "value2")
        assert result == 0


class TestExistsFailover:
    """Test that exists() returns False when Redis is unavailable."""

    def test_exists_returns_false_on_connection_error(self, failing_redis):
        """When Redis is unavailable, exists() returns False."""
        client, _ = failing_redis
        result = client.exists("some_key")
        assert result is False


class TestReconnectionAfterFailure:
    """Test that operations succeed again after Redis reconnects."""

    def test_get_succeeds_after_reconnection(self, recoverable_redis):
        """When Redis reconnects after failure, operations succeed again."""
        client, mock = recoverable_redis

        # First call: simulate failure
        mock.get.side_effect = redis_lib.ConnectionError("Connection refused")
        result = client.get("key")
        assert result is None

        # Second call: Redis is back up
        mock.get.side_effect = None
        mock.get.return_value = "recovered_value"
        result = client.get("key")
        assert result == "recovered_value"

    def test_set_succeeds_after_reconnection(self, recoverable_redis):
        """set() succeeds once Redis is available again."""
        client, mock = recoverable_redis

        # Failure
        mock.set.side_effect = redis_lib.ConnectionError("Connection refused")
        assert client.set("key", "value") is False

        # Recovery
        mock.set.side_effect = None
        mock.set.return_value = True
        assert client.set("key", "value") is True

    def test_hgetall_succeeds_after_reconnection(self, recoverable_redis):
        """hgetall() succeeds once Redis is available again."""
        client, mock = recoverable_redis

        # Failure
        mock.hgetall.side_effect = redis_lib.ConnectionError("Connection refused")
        assert client.hgetall("hash") == {}

        # Recovery
        mock.hgetall.side_effect = None
        mock.hgetall.return_value = {"field": "value"}
        assert client.hgetall("hash") == {"field": "value"}

    def test_lpush_succeeds_after_reconnection(self, recoverable_redis):
        """lpush() succeeds once Redis is available again."""
        client, mock = recoverable_redis

        # Failure
        mock.lpush.side_effect = redis_lib.ConnectionError("Connection refused")
        assert client.lpush("list", "val") == 0

        # Recovery
        mock.lpush.side_effect = None
        mock.lpush.return_value = 1
        assert client.lpush("list", "val") == 1


class TestPingFailover:
    """Test that ping() returns False when Redis is unreachable."""

    def test_ping_returns_false_on_connection_error(self, failing_redis):
        """Ping returns False when Redis is unreachable."""
        client, _ = failing_redis
        assert client.ping() is False

    def test_ping_returns_false_on_redis_error(self):
        """Ping returns False on general RedisError."""
        with patch("src.cache.redis_client.redis.ConnectionPool.from_url"):
            with patch("src.cache.redis_client.redis.Redis") as mock_redis_cls:
                mock_instance = MagicMock()
                mock_instance.ping.side_effect = redis_lib.RedisError("timeout")
                mock_redis_cls.return_value = mock_instance
                client = RedisClient(url="redis://localhost:6379/0")
                assert client.ping() is False


class TestErrorLogging:
    """Test that all operations log errors when Redis is down."""

    def test_get_logs_error(self, failing_redis, caplog):
        """get() logs an error when Redis is down."""
        client, _ = failing_redis
        with caplog.at_level(logging.ERROR):
            client.get("test_key")
        assert "Redis GET error" in caplog.text
        assert "test_key" in caplog.text

    def test_set_logs_error(self, failing_redis, caplog):
        """set() logs an error when Redis is down."""
        client, _ = failing_redis
        with caplog.at_level(logging.ERROR):
            client.set("test_key", "value")
        assert "Redis SET error" in caplog.text
        assert "test_key" in caplog.text

    def test_hgetall_logs_error(self, failing_redis, caplog):
        """hgetall() logs an error when Redis is down."""
        client, _ = failing_redis
        with caplog.at_level(logging.ERROR):
            client.hgetall("test_hash")
        assert "Redis HGETALL error" in caplog.text
        assert "test_hash" in caplog.text

    def test_lpush_logs_error(self, failing_redis, caplog):
        """lpush() logs an error when Redis is down."""
        client, _ = failing_redis
        with caplog.at_level(logging.ERROR):
            client.lpush("test_list", "val")
        assert "Redis LPUSH error" in caplog.text
        assert "test_list" in caplog.text

    def test_exists_logs_error(self, failing_redis, caplog):
        """exists() logs an error when Redis is down."""
        client, _ = failing_redis
        with caplog.at_level(logging.ERROR):
            client.exists("test_key")
        assert "Redis EXISTS error" in caplog.text
        assert "test_key" in caplog.text

    def test_ping_logs_error(self, failing_redis, caplog):
        """ping() logs an error when Redis is down."""
        client, _ = failing_redis
        with caplog.at_level(logging.ERROR):
            client.ping()
        assert "Redis PING failed" in caplog.text

    def test_delete_logs_error(self, failing_redis, caplog):
        """delete() logs an error when Redis is down."""
        client, _ = failing_redis
        with caplog.at_level(logging.ERROR):
            client.delete("test_key")
        assert "Redis DELETE error" in caplog.text
        assert "test_key" in caplog.text

    def test_hset_logs_error(self, failing_redis, caplog):
        """hset() logs an error when Redis is down."""
        client, _ = failing_redis
        with caplog.at_level(logging.ERROR):
            client.hset("test_hash", {"f": "v"})
        assert "Redis HSET error" in caplog.text
        assert "test_hash" in caplog.text
