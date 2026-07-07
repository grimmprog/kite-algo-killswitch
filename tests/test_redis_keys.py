"""Tests for Redis key structure module.

Tests Requirements: 3.6.1, 3.6.2, 3.6.3, 3.6.4, 3.6.5, 3.6.6, 3.6.7, 3.6.8, 1.8.8
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.cache.redis_keys import RedisKeys, RiskMetrics, TTL


class TestRedisKeysUserRisk:
    """Test user risk metrics key generation (Requirement 3.6.1)."""

    def test_basic_format(self):
        assert RedisKeys.user_risk(1) == "user:1:risk"

    def test_different_user_ids(self):
        assert RedisKeys.user_risk(42) == "user:42:risk"
        assert RedisKeys.user_risk(100) == "user:100:risk"

    def test_user_isolation(self):
        """Keys for different users must be different (Requirement 1.8.8)."""
        assert RedisKeys.user_risk(1) != RedisKeys.user_risk(2)


class TestRedisKeysUserKillswitch:
    """Test user kill switch flag key generation (Requirement 3.6.2)."""

    def test_basic_format(self):
        assert RedisKeys.user_killswitch(1) == "user:1:killswitch"

    def test_different_user_ids(self):
        assert RedisKeys.user_killswitch(5) == "user:5:killswitch"
        assert RedisKeys.user_killswitch(99) == "user:99:killswitch"

    def test_user_isolation(self):
        """Kill switch keys must be per-user (Requirement 1.8.4)."""
        assert RedisKeys.user_killswitch(1) != RedisKeys.user_killswitch(2)


class TestRedisKeysUserRecentOrders:
    """Test recent orders key generation (Requirement 3.6.3)."""

    def test_basic_format(self):
        assert RedisKeys.user_recent_orders(1) == "user:1:recent_orders"

    def test_different_user_ids(self):
        assert RedisKeys.user_recent_orders(10) == "user:10:recent_orders"

    def test_user_isolation(self):
        """Recent orders must be per-user (Requirement 1.8.5)."""
        assert RedisKeys.user_recent_orders(1) != RedisKeys.user_recent_orders(2)


class TestRedisKeysMarketData:
    """Test market data key generation (Requirement 3.6.4)."""

    def test_nifty(self):
        assert RedisKeys.market_data("NIFTY") == "market:NIFTY:data"

    def test_banknifty(self):
        assert RedisKeys.market_data("BANKNIFTY") == "market:BANKNIFTY:data"

    def test_arbitrary_symbol(self):
        assert RedisKeys.market_data("RELIANCE") == "market:RELIANCE:data"


class TestRedisKeysMarketTicks:
    """Test market ticks key generation (Requirement 3.6.5)."""

    def test_nifty(self):
        assert RedisKeys.market_ticks("NIFTY") == "market:NIFTY:ticks"

    def test_banknifty(self):
        assert RedisKeys.market_ticks("BANKNIFTY") == "market:BANKNIFTY:ticks"

    def test_arbitrary_symbol(self):
        assert RedisKeys.market_ticks("RELIANCE") == "market:RELIANCE:ticks"


class TestTTLConstants:
    """Test TTL constants match requirements."""

    def test_market_data_ttl(self):
        """Requirement 3.6.6: Market data TTL = 10 seconds."""
        assert TTL.MARKET_DATA == 10

    def test_recent_orders_ttl(self):
        """Requirement 3.6.7: Recent orders TTL = 60 seconds."""
        assert TTL.RECENT_ORDERS == 60

    def test_market_ticks_ttl(self):
        """Requirement 3.6.8: Market ticks TTL = 300 seconds."""
        assert TTL.MARKET_TICKS == 300


class TestRiskMetrics:
    """Test RiskMetrics dataclass and serialization."""

    def test_default_values(self):
        rm = RiskMetrics()
        assert rm.pnl == 0.0
        assert rm.net_delta == 0.0
        assert rm.net_gamma == 0.0
        assert rm.net_vega == 0.0
        assert rm.margin_used == 0.0
        assert rm.updated_at is not None

    def test_custom_values(self):
        rm = RiskMetrics(
            pnl=-1500.50,
            net_delta=0.45,
            net_gamma=0.02,
            net_vega=150.0,
            margin_used=50000.0,
        )
        assert rm.pnl == -1500.50
        assert rm.net_delta == 0.45
        assert rm.net_gamma == 0.02
        assert rm.net_vega == 150.0
        assert rm.margin_used == 50000.0

    def test_to_redis_hash_returns_strings(self):
        rm = RiskMetrics(pnl=-500.0, net_delta=0.1, net_gamma=0.01, net_vega=50.0, margin_used=20000.0)
        result = rm.to_redis_hash()
        assert all(isinstance(v, str) for v in result.values())
        assert result["pnl"] == "-500.0"
        assert result["net_delta"] == "0.1"
        assert result["net_gamma"] == "0.01"
        assert result["net_vega"] == "50.0"
        assert result["margin_used"] == "20000.0"
        assert "updated_at" in result

    def test_to_redis_hash_keys(self):
        rm = RiskMetrics()
        result = rm.to_redis_hash()
        expected_keys = {"pnl", "net_delta", "net_gamma", "net_vega", "margin_used", "updated_at"}
        assert set(result.keys()) == expected_keys

    def test_from_redis_hash_bytes(self):
        """Parse data as returned by redis-py (bytes keys and values)."""
        data = {
            b"pnl": b"-2000.0",
            b"net_delta": b"0.3",
            b"net_gamma": b"0.01",
            b"net_vega": b"100.0",
            b"margin_used": b"45000.0",
            b"updated_at": b"2024-01-01T10:00:00",
        }
        rm = RiskMetrics.from_redis_hash(data)
        assert rm.pnl == -2000.0
        assert rm.net_delta == 0.3
        assert rm.net_gamma == 0.01
        assert rm.net_vega == 100.0
        assert rm.margin_used == 45000.0
        assert rm.updated_at == "2024-01-01T10:00:00"

    def test_from_redis_hash_strings(self):
        """Parse data with string keys (decode_responses=True)."""
        data = {
            "pnl": "500.25",
            "net_delta": "-0.5",
            "net_gamma": "0.03",
            "net_vega": "-75.0",
            "margin_used": "10000.0",
            "updated_at": "2024-06-15T14:30:00",
        }
        rm = RiskMetrics.from_redis_hash(data)
        assert rm.pnl == 500.25
        assert rm.net_delta == -0.5
        assert rm.net_gamma == 0.03
        assert rm.net_vega == -75.0
        assert rm.margin_used == 10000.0

    def test_roundtrip(self):
        """Ensure to_redis_hash -> from_redis_hash preserves data."""
        original = RiskMetrics(
            pnl=-1234.56,
            net_delta=0.789,
            net_gamma=0.012,
            net_vega=345.67,
            margin_used=67890.12,
            updated_at="2024-03-15T09:15:00",
        )
        redis_data = original.to_redis_hash()
        restored = RiskMetrics.from_redis_hash(redis_data)
        assert restored.pnl == original.pnl
        assert restored.net_delta == original.net_delta
        assert restored.net_gamma == original.net_gamma
        assert restored.net_vega == original.net_vega
        assert restored.margin_used == original.margin_used
        assert restored.updated_at == original.updated_at
