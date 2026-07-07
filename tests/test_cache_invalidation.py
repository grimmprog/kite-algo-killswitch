"""Tests for cache invalidation module.

Tests Requirements: 3.6.10 (expire stale cache entries automatically)
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch
import pytest

from src.cache.invalidation import (
    invalidate_user_risk,
    invalidate_user_killswitch,
    invalidate_user_recent_orders,
    invalidate_market_data,
    invalidate_market_ticks,
    invalidate_all_user_cache,
    invalidate_all_market_cache,
)
from src.cache.redis_client import reset_redis_client


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the module-level singleton before each test."""
    reset_redis_client()
    yield
    reset_redis_client()


@pytest.fixture
def mock_client():
    """Patch get_redis_client to return a mock RedisClient."""
    with patch("src.cache.invalidation.get_redis_client") as mock_get:
        mock_redis = MagicMock()
        mock_redis.delete.return_value = 1
        mock_get.return_value = mock_redis
        yield mock_redis


class TestInvalidateUserRisk:
    """Test invalidate_user_risk function."""

    def test_deletes_correct_key(self, mock_client):
        result = invalidate_user_risk(42)
        assert result is True
        mock_client.delete.assert_called_once_with("user:42:risk")

    def test_returns_true_when_key_missing(self, mock_client):
        mock_client.delete.return_value = 0
        result = invalidate_user_risk(99)
        assert result is True

    def test_returns_false_on_error(self, mock_client):
        mock_client.delete.side_effect = Exception("connection lost")
        result = invalidate_user_risk(42)
        assert result is False


class TestInvalidateUserKillswitch:
    """Test invalidate_user_killswitch function."""

    def test_deletes_correct_key(self, mock_client):
        result = invalidate_user_killswitch(7)
        assert result is True
        mock_client.delete.assert_called_once_with("user:7:killswitch")

    def test_returns_true_when_key_missing(self, mock_client):
        mock_client.delete.return_value = 0
        result = invalidate_user_killswitch(7)
        assert result is True

    def test_returns_false_on_error(self, mock_client):
        mock_client.delete.side_effect = Exception("timeout")
        result = invalidate_user_killswitch(7)
        assert result is False


class TestInvalidateUserRecentOrders:
    """Test invalidate_user_recent_orders function."""

    def test_deletes_correct_key(self, mock_client):
        result = invalidate_user_recent_orders(15)
        assert result is True
        mock_client.delete.assert_called_once_with("user:15:recent_orders")

    def test_returns_true_when_key_missing(self, mock_client):
        mock_client.delete.return_value = 0
        result = invalidate_user_recent_orders(15)
        assert result is True

    def test_returns_false_on_error(self, mock_client):
        mock_client.delete.side_effect = Exception("error")
        result = invalidate_user_recent_orders(15)
        assert result is False


class TestInvalidateMarketData:
    """Test invalidate_market_data function."""

    def test_deletes_correct_key(self, mock_client):
        result = invalidate_market_data("NIFTY")
        assert result is True
        mock_client.delete.assert_called_once_with("market:NIFTY:data")

    def test_handles_banknifty(self, mock_client):
        result = invalidate_market_data("BANKNIFTY")
        assert result is True
        mock_client.delete.assert_called_once_with("market:BANKNIFTY:data")

    def test_returns_false_on_error(self, mock_client):
        mock_client.delete.side_effect = Exception("redis down")
        result = invalidate_market_data("NIFTY")
        assert result is False


class TestInvalidateMarketTicks:
    """Test invalidate_market_ticks function."""

    def test_deletes_correct_key(self, mock_client):
        result = invalidate_market_ticks("NIFTY")
        assert result is True
        mock_client.delete.assert_called_once_with("market:NIFTY:ticks")

    def test_handles_banknifty(self, mock_client):
        result = invalidate_market_ticks("BANKNIFTY")
        assert result is True
        mock_client.delete.assert_called_once_with("market:BANKNIFTY:ticks")

    def test_returns_false_on_error(self, mock_client):
        mock_client.delete.side_effect = Exception("connection refused")
        result = invalidate_market_ticks("NIFTY")
        assert result is False


class TestInvalidateAllUserCache:
    """Test invalidate_all_user_cache function."""

    def test_deletes_all_user_keys(self, mock_client):
        result = invalidate_all_user_cache(42)
        assert result is True
        assert mock_client.delete.call_count == 3
        calls = [c.args[0] for c in mock_client.delete.call_args_list]
        assert "user:42:risk" in calls
        assert "user:42:killswitch" in calls
        assert "user:42:recent_orders" in calls

    def test_returns_false_on_error(self, mock_client):
        mock_client.delete.side_effect = Exception("bulk error")
        result = invalidate_all_user_cache(42)
        assert result is False


class TestInvalidateAllMarketCache:
    """Test invalidate_all_market_cache function."""

    def test_deletes_all_market_keys(self, mock_client):
        result = invalidate_all_market_cache("NIFTY")
        assert result is True
        assert mock_client.delete.call_count == 2
        calls = [c.args[0] for c in mock_client.delete.call_args_list]
        assert "market:NIFTY:data" in calls
        assert "market:NIFTY:ticks" in calls

    def test_returns_false_on_error(self, mock_client):
        mock_client.delete.side_effect = Exception("bulk error")
        result = invalidate_all_market_cache("NIFTY")
        assert result is False
