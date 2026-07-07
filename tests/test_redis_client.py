"""Tests for Redis client wrapper module.

Tests Requirements: 2.3.3 (graceful Redis error handling), 3.6 (cache operations)
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch, PropertyMock
import pytest
import redis as redis_lib

from src.cache.redis_client import RedisClient, get_redis_client, reset_redis_client


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the module-level singleton before each test."""
    reset_redis_client()
    yield
    reset_redis_client()


@pytest.fixture
def mock_redis():
    """Create a RedisClient with a mocked underlying redis connection."""
    with patch("src.cache.redis_client.redis.ConnectionPool.from_url") as mock_pool:
        with patch("src.cache.redis_client.redis.Redis") as mock_redis_cls:
            mock_client_instance = MagicMock()
            mock_redis_cls.return_value = mock_client_instance
            client = RedisClient(url="redis://localhost:6379/0", max_connections=10)
            yield client, mock_client_instance


class TestConnectionPool:
    """Test 2.2.1: Connection pool creation."""

    @patch("src.cache.redis_client.redis.Redis")
    @patch("src.cache.redis_client.redis.ConnectionPool.from_url")
    def test_creates_connection_pool_with_url(self, mock_pool, mock_redis_cls):
        """Pool is created with the provided URL."""
        RedisClient(url="redis://myhost:6380/1", max_connections=20)
        mock_pool.assert_called_once_with(
            "redis://myhost:6380/1",
            max_connections=20,
            decode_responses=True,
        )

    @patch("src.cache.redis_client.redis.Redis")
    @patch("src.cache.redis_client.redis.ConnectionPool.from_url")
    def test_defaults_to_env_variable(self, mock_pool, mock_redis_cls):
        """Falls back to REDIS_URL env var."""
        with patch.dict(os.environ, {"REDIS_URL": "redis://envhost:6399/2"}):
            RedisClient()
        mock_pool.assert_called_once_with(
            "redis://envhost:6399/2",
            max_connections=50,
            decode_responses=True,
        )

    @patch("src.cache.redis_client.redis.Redis")
    @patch("src.cache.redis_client.redis.ConnectionPool.from_url")
    def test_defaults_to_localhost(self, mock_pool, mock_redis_cls):
        """Falls back to localhost when no URL and no env var."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove REDIS_URL if present
            os.environ.pop("REDIS_URL", None)
            RedisClient()
        mock_pool.assert_called_once_with(
            "redis://localhost:6379/0",
            max_connections=50,
            decode_responses=True,
        )


class TestGetSetHelpers:
    """Test 2.2.2: Get/Set helpers."""

    def test_get_returns_value(self, mock_redis):
        client, mock = mock_redis
        mock.get.return_value = "hello"
        assert client.get("mykey") == "hello"
        mock.get.assert_called_once_with("mykey")

    def test_get_returns_none_when_missing(self, mock_redis):
        client, mock = mock_redis
        mock.get.return_value = None
        assert client.get("missing") is None

    def test_get_returns_none_on_error(self, mock_redis):
        client, mock = mock_redis
        mock.get.side_effect = redis_lib.RedisError("connection lost")
        assert client.get("mykey") is None

    def test_set_without_ttl(self, mock_redis):
        client, mock = mock_redis
        mock.set.return_value = True
        assert client.set("key", "value") is True
        mock.set.assert_called_once_with("key", "value")

    def test_set_with_ttl(self, mock_redis):
        client, mock = mock_redis
        mock.setex.return_value = True
        assert client.set("key", "value", ttl=60) is True
        mock.setex.assert_called_once_with("key", 60, "value")

    def test_set_returns_false_on_error(self, mock_redis):
        client, mock = mock_redis
        mock.set.side_effect = redis_lib.RedisError("write error")
        assert client.set("key", "value") is False

    def test_delete_returns_count(self, mock_redis):
        client, mock = mock_redis
        mock.delete.return_value = 1
        assert client.delete("key") == 1
        mock.delete.assert_called_once_with("key")

    def test_delete_returns_zero_on_error(self, mock_redis):
        client, mock = mock_redis
        mock.delete.side_effect = redis_lib.RedisError("err")
        assert client.delete("key") == 0

    def test_exists_returns_true(self, mock_redis):
        client, mock = mock_redis
        mock.exists.return_value = 1
        assert client.exists("key") is True

    def test_exists_returns_false(self, mock_redis):
        client, mock = mock_redis
        mock.exists.return_value = 0
        assert client.exists("missing") is False

    def test_exists_returns_false_on_error(self, mock_redis):
        client, mock = mock_redis
        mock.exists.side_effect = redis_lib.RedisError("err")
        assert client.exists("key") is False


class TestHashOperations:
    """Test 2.2.3: Hash operations."""

    def test_hset_with_mapping(self, mock_redis):
        client, mock = mock_redis
        mock.hset.return_value = 3
        result = client.hset("myhash", {"a": "1", "b": "2", "c": "3"})
        assert result == 3
        mock.hset.assert_called_once_with("myhash", mapping={"a": "1", "b": "2", "c": "3"})

    def test_hset_returns_zero_on_error(self, mock_redis):
        client, mock = mock_redis
        mock.hset.side_effect = redis_lib.RedisError("err")
        assert client.hset("key", {"field": "val"}) == 0

    def test_hget_returns_value(self, mock_redis):
        client, mock = mock_redis
        mock.hget.return_value = "value1"
        assert client.hget("myhash", "field1") == "value1"
        mock.hget.assert_called_once_with("myhash", "field1")

    def test_hget_returns_none_when_missing(self, mock_redis):
        client, mock = mock_redis
        mock.hget.return_value = None
        assert client.hget("myhash", "missing") is None

    def test_hget_returns_none_on_error(self, mock_redis):
        client, mock = mock_redis
        mock.hget.side_effect = redis_lib.RedisError("err")
        assert client.hget("key", "field") is None

    def test_hgetall_returns_dict(self, mock_redis):
        client, mock = mock_redis
        mock.hgetall.return_value = {"f1": "v1", "f2": "v2"}
        assert client.hgetall("myhash") == {"f1": "v1", "f2": "v2"}

    def test_hgetall_returns_empty_on_error(self, mock_redis):
        client, mock = mock_redis
        mock.hgetall.side_effect = redis_lib.RedisError("err")
        assert client.hgetall("key") == {}

    def test_hdel_removes_fields(self, mock_redis):
        client, mock = mock_redis
        mock.hdel.return_value = 2
        assert client.hdel("myhash", "f1", "f2") == 2
        mock.hdel.assert_called_once_with("myhash", "f1", "f2")

    def test_hdel_returns_zero_on_error(self, mock_redis):
        client, mock = mock_redis
        mock.hdel.side_effect = redis_lib.RedisError("err")
        assert client.hdel("key", "f1") == 0


class TestListOperations:
    """Test 2.2.4: List operations."""

    def test_lpush_returns_length(self, mock_redis):
        client, mock = mock_redis
        mock.lpush.return_value = 3
        assert client.lpush("mylist", "a", "b", "c") == 3
        mock.lpush.assert_called_once_with("mylist", "a", "b", "c")

    def test_lpush_returns_zero_on_error(self, mock_redis):
        client, mock = mock_redis
        mock.lpush.side_effect = redis_lib.RedisError("err")
        assert client.lpush("key", "val") == 0

    def test_lrange_returns_list(self, mock_redis):
        client, mock = mock_redis
        mock.lrange.return_value = ["a", "b", "c"]
        assert client.lrange("mylist", 0, -1) == ["a", "b", "c"]
        mock.lrange.assert_called_once_with("mylist", 0, -1)

    def test_lrange_returns_empty_on_error(self, mock_redis):
        client, mock = mock_redis
        mock.lrange.side_effect = redis_lib.RedisError("err")
        assert client.lrange("key", 0, -1) == []

    def test_ltrim_returns_true(self, mock_redis):
        client, mock = mock_redis
        mock.ltrim.return_value = True
        assert client.ltrim("mylist", 0, 9) is True
        mock.ltrim.assert_called_once_with("mylist", 0, 9)

    def test_ltrim_returns_false_on_error(self, mock_redis):
        client, mock = mock_redis
        mock.ltrim.side_effect = redis_lib.RedisError("err")
        assert client.ltrim("key", 0, 5) is False

    def test_llen_returns_length(self, mock_redis):
        client, mock = mock_redis
        mock.llen.return_value = 5
        assert client.llen("mylist") == 5
        mock.llen.assert_called_once_with("mylist")

    def test_llen_returns_zero_on_error(self, mock_redis):
        client, mock = mock_redis
        mock.llen.side_effect = redis_lib.RedisError("err")
        assert client.llen("key") == 0


class TestTTLManagement:
    """Test 2.2.5: TTL management."""

    def test_expire_sets_ttl(self, mock_redis):
        client, mock = mock_redis
        mock.expire.return_value = True
        assert client.expire("key", 300) is True
        mock.expire.assert_called_once_with("key", 300)

    def test_expire_returns_false_for_missing_key(self, mock_redis):
        client, mock = mock_redis
        mock.expire.return_value = False
        assert client.expire("missing", 60) is False

    def test_expire_returns_false_on_error(self, mock_redis):
        client, mock = mock_redis
        mock.expire.side_effect = redis_lib.RedisError("err")
        assert client.expire("key", 60) is False

    def test_ttl_returns_seconds(self, mock_redis):
        client, mock = mock_redis
        mock.ttl.return_value = 42
        assert client.ttl("key") == 42

    def test_ttl_returns_minus_one_for_persistent(self, mock_redis):
        client, mock = mock_redis
        mock.ttl.return_value = -1
        assert client.ttl("key") == -1

    def test_ttl_returns_minus_two_on_error(self, mock_redis):
        client, mock = mock_redis
        mock.ttl.side_effect = redis_lib.RedisError("err")
        assert client.ttl("key") == -2

    def test_setex_sets_value_with_expiry(self, mock_redis):
        client, mock = mock_redis
        mock.setex.return_value = True
        assert client.setex("key", 10, "value") is True
        mock.setex.assert_called_once_with("key", 10, "value")

    def test_setex_returns_false_on_error(self, mock_redis):
        client, mock = mock_redis
        mock.setex.side_effect = redis_lib.RedisError("err")
        assert client.setex("key", 10, "value") is False

    def test_persist_removes_ttl(self, mock_redis):
        client, mock = mock_redis
        mock.persist.return_value = True
        assert client.persist("key") is True
        mock.persist.assert_called_once_with("key")

    def test_persist_returns_false_for_no_ttl(self, mock_redis):
        client, mock = mock_redis
        mock.persist.return_value = False
        assert client.persist("key") is False

    def test_persist_returns_false_on_error(self, mock_redis):
        client, mock = mock_redis
        mock.persist.side_effect = redis_lib.RedisError("err")
        assert client.persist("key") is False


class TestSingleton:
    """Test get_redis_client singleton pattern."""

    @patch("src.cache.redis_client.redis.Redis")
    @patch("src.cache.redis_client.redis.ConnectionPool.from_url")
    def test_returns_same_instance(self, mock_pool, mock_redis_cls):
        client1 = get_redis_client()
        client2 = get_redis_client()
        assert client1 is client2

    @patch("src.cache.redis_client.redis.Redis")
    @patch("src.cache.redis_client.redis.ConnectionPool.from_url")
    def test_reset_clears_singleton(self, mock_pool, mock_redis_cls):
        client1 = get_redis_client()
        reset_redis_client()
        client2 = get_redis_client()
        assert client1 is not client2


class TestPing:
    """Test ping utility."""

    def test_ping_success(self, mock_redis):
        client, mock = mock_redis
        mock.ping.return_value = True
        assert client.ping() is True

    def test_ping_failure(self, mock_redis):
        client, mock = mock_redis
        mock.ping.side_effect = redis_lib.RedisError("unreachable")
        assert client.ping() is False
