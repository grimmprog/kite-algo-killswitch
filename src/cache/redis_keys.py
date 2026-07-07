"""
Redis Key Structure for Multi-User Web Trading Platform.

This module defines all Redis key patterns, TTL constants, and data type
documentation for the platform's caching layer.

Key Patterns:
    - user:{user_id}:risk        — Hash with risk metrics (pnl, greeks, margin)
    - user:{user_id}:killswitch  — String "true"/"false" for kill switch state
    - user:{user_id}:recent_orders — List of recent order signatures
    - market:{symbol}:data       — JSON string with spot price, VWAP, option chain
    - market:{symbol}:ticks      — List of recent ticks for VWAP calculation

Validates: Requirements 3.6.1, 3.6.2, 3.6.3, 3.6.4, 3.6.5, 3.6.6, 3.6.7, 3.6.8, 3.6.9
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


class TTL:
    """TTL constants (in seconds) for Redis keys.

    Requirement 3.6.6: Market data TTL = 10s
    Requirement 3.6.7: Recent orders TTL = 60s
    Requirement 3.6.8: Market ticks TTL = 300s
    """

    MARKET_DATA: int = 10
    """TTL for market:{symbol}:data keys. Market data expires after 10 seconds."""

    RECENT_ORDERS: int = 60
    """TTL for user:{user_id}:recent_orders keys. Used for duplicate order detection."""

    MARKET_TICKS: int = 300
    """TTL for market:{symbol}:ticks keys. Recent ticks kept for VWAP calculation."""


@dataclass
class RiskMetrics:
    """Typed representation of the user:{user_id}:risk hash fields.

    This maps to the Redis hash stored at key `user:{user_id}:risk`.
    All numeric values are stored as strings in Redis and must be
    cast to float when reading.

    Requirement 1.4.5: Cache risk metrics in Redis with timestamp.
    Requirement 3.6.1: Cache user risk metrics with key user:{user_id}:risk.
    """

    pnl: float = 0.0
    """Current day P&L for the user (float, can be negative)."""

    net_delta: float = 0.0
    """Net delta exposure across all options positions."""

    net_gamma: float = 0.0
    """Net gamma exposure across all options positions."""

    net_vega: float = 0.0
    """Net vega exposure across all options positions."""

    margin_used: float = 0.0
    """Total margin used across all positions (non-negative)."""

    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    """ISO-format timestamp of last update."""

    def to_redis_hash(self) -> dict[str, str]:
        """Convert to a dict suitable for Redis HSET.

        Returns:
            Dictionary with string keys and string values for Redis storage.
        """
        return {
            "pnl": str(self.pnl),
            "net_delta": str(self.net_delta),
            "net_gamma": str(self.net_gamma),
            "net_vega": str(self.net_vega),
            "margin_used": str(self.margin_used),
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_redis_hash(cls, data: dict[bytes | str, bytes | str]) -> "RiskMetrics":
        """Create RiskMetrics from a Redis HGETALL response.

        Args:
            data: Raw dict from redis HGETALL (may have bytes keys/values).

        Returns:
            RiskMetrics instance with parsed values.
        """
        def _get(key: str) -> str:
            val = data.get(key) or data.get(key.encode(), b"0")
            return val.decode() if isinstance(val, bytes) else val

        return cls(
            pnl=float(_get("pnl")),
            net_delta=float(_get("net_delta")),
            net_gamma=float(_get("net_gamma")),
            net_vega=float(_get("net_vega")),
            margin_used=float(_get("margin_used")),
            updated_at=_get("updated_at") or datetime.now().isoformat(),
        )


class SettingsTTL:
    """TTL constants for settings cache keys."""

    STRATEGY: int = 300
    """TTL for user strategy settings cache (5 minutes). Refreshed on update."""

    KILLSWITCH_THRESHOLDS: int = 300
    """TTL for kill switch thresholds cache (5 minutes). Refreshed on update."""

    AI_SETTINGS: int = 300
    """TTL for AI settings cache (5 minutes). Refreshed on update."""

    WATCHLIST: int = 300
    """TTL for watchlist cache (5 minutes). Refreshed on update."""


class RedisKeys:
    """Generate Redis keys for the trading platform.

    All keys follow a consistent namespace pattern:
    - User-specific keys: user:{user_id}:<resource>
    - Market-wide keys: market:{symbol}:<resource>

    Requirement 1.8.8: Prefix all Redis keys with user_id.
    Requirement 3.6: Cache data structure definitions.
    """

    # --- User Risk Metrics ---
    # Key: user:{user_id}:risk
    # Type: Hash
    # Fields: pnl, net_delta, net_gamma, net_vega, margin_used, updated_at
    # TTL: None (overwritten every 2-3 seconds by risk engine)
    # Requirement 3.6.1

    @staticmethod
    def user_risk(user_id: int) -> str:
        """Redis key for user risk metrics hash.

        Type: Hash
        Fields: pnl (float), net_delta (float), net_gamma (float),
                net_vega (float), margin_used (float), updated_at (ISO timestamp)
        TTL: None (continuously refreshed by risk engine every 2-3s)

        Args:
            user_id: The user's database ID.

        Returns:
            Redis key string, e.g. "user:42:risk"
        """
        return f"user:{user_id}:risk"

    # --- Kill Switch Flag ---
    # Key: user:{user_id}:killswitch
    # Type: String ("true" or "false")
    # TTL: None (persistent until manually cleared)
    # Requirement 3.6.2, 1.5.1

    @staticmethod
    def user_killswitch(user_id: int) -> str:
        """Redis key for user kill switch flag.

        Type: String
        Values: "true" (active) or "false" (inactive)
        TTL: None (persistent, cleared only by manual deactivation)

        The kill switch flag is set atomically (Requirement 1.5.1) and
        blocks all new trades immediately when active (Requirement 1.5.2).

        Args:
            user_id: The user's database ID.

        Returns:
            Redis key string, e.g. "user:42:killswitch"
        """
        return f"user:{user_id}:killswitch"

    # --- Recent Orders ---
    # Key: user:{user_id}:recent_orders
    # Type: List of order signature strings ("SYMBOL:SIDE:QTY")
    # TTL: 60 seconds (Requirement 3.6.7)
    # Used for duplicate order detection (Requirement 1.3.9)

    @staticmethod
    def user_recent_orders(user_id: int) -> str:
        """Redis key for user's recent order signatures list.

        Type: List
        Elements: Order signature strings in format "SYMBOL:SIDE:QUANTITY"
        TTL: 60 seconds
        Max length: 10 entries (trimmed via LTRIM)

        Used for duplicate order detection within a 60-second window
        (Requirement 1.3.9).

        Args:
            user_id: The user's database ID.

        Returns:
            Redis key string, e.g. "user:42:recent_orders"
        """
        return f"user:{user_id}:recent_orders"

    # --- Market Data ---
    # Key: market:{symbol}:data
    # Type: String (JSON-encoded)
    # Fields: spot (float), vwap (float), option_chain (list), timestamp (ISO)
    # TTL: 10 seconds (Requirement 3.6.6)
    # Shared across all users (Requirement 1.6.5)

    @staticmethod
    def market_data(symbol: str) -> str:
        """Redis key for cached market data JSON.

        Type: String (JSON-encoded)
        Structure: {
            "spot": float,       — Current spot price
            "vwap": float,       — Volume-weighted average price
            "option_chain": [],  — Option chain data
            "timestamp": str     — ISO-format update timestamp
        }
        TTL: 10 seconds

        Market data is shared across all users (Requirement 1.6.5).

        Args:
            symbol: Trading symbol, e.g. "NIFTY" or "BANKNIFTY".

        Returns:
            Redis key string, e.g. "market:NIFTY:data"
        """
        return f"market:{symbol}:data"

    # --- Market Ticks ---
    # Key: market:{symbol}:ticks
    # Type: List of tick JSON strings
    # TTL: 300 seconds (Requirement 3.6.8)
    # Used for VWAP calculation (Requirement 1.6.3, 1.6.6)

    @staticmethod
    def market_ticks(symbol: str) -> str:
        """Redis key for recent market ticks list.

        Type: List
        Elements: JSON-encoded tick objects with price and volume data
        TTL: 300 seconds
        Max length: 100 entries (last 100 ticks for VWAP, Requirement 1.6.6)

        Used for VWAP calculation with 20-tick lookback (Requirement 1.6.3).

        Args:
            symbol: Trading symbol, e.g. "NIFTY" or "BANKNIFTY".

        Returns:
            Redis key string, e.g. "market:NIFTY:ticks"
        """
        return f"market:{symbol}:ticks"

    # --- User Settings Cache ---
    # Requirements 5.2, 6.4: Settings changes propagate to running workers

    @staticmethod
    def user_strategy_settings(user_id: int) -> str:
        """Redis key for cached user strategy settings (watchlist, thresholds, etc.).

        Type: String (JSON-encoded)
        Structure: Full StrategySettings dict
        TTL: 300 seconds (refreshed on every settings update)

        Workers read this on each cycle so they pick up the latest watchlist,
        confidence threshold, and trading time windows without hitting the DB.

        Requirements: 5.2

        Args:
            user_id: The user's database ID.

        Returns:
            Redis key string, e.g. "user:42:settings:strategy"
        """
        return f"user:{user_id}:settings:strategy"

    @staticmethod
    def user_killswitch_thresholds(user_id: int) -> str:
        """Redis key for cached kill switch thresholds.

        Type: String (JSON-encoded)
        Structure: KillSwitchThresholdsResponse dict with computed amounts
        TTL: 300 seconds (refreshed on every threshold update)

        The auto-monitor worker reads this on each 5-second cycle so threshold
        changes apply immediately without requiring a DB query.

        Requirements: 6.4

        Args:
            user_id: The user's database ID.

        Returns:
            Redis key string, e.g. "user:42:settings:killswitch"
        """
        return f"user:{user_id}:settings:killswitch"

    @staticmethod
    def user_ai_settings(user_id: int) -> str:
        """Redis key for cached AI feature toggles and provider config.

        Type: String (JSON-encoded)
        Structure: AISettings dict with provider and feature toggle booleans
        TTL: 300 seconds (refreshed on every AI settings update)

        The AI worker reads this to determine which AI features are enabled
        for the user before dispatching analysis tasks.

        Requirements: 17.2

        Args:
            user_id: The user's database ID.

        Returns:
            Redis key string, e.g. "user:42:settings:ai"
        """
        return f"user:{user_id}:settings:ai"

    @staticmethod
    def user_watchlist(user_id: int) -> str:
        """Redis key for cached user watchlist (quick access for scanner worker).

        Type: String (JSON-encoded list of symbols)
        TTL: 300 seconds (refreshed on every strategy settings update)

        The scanner worker reads this to get the symbols to scan without
        requiring a full strategy settings DB query.

        Requirements: 5.2

        Args:
            user_id: The user's database ID.

        Returns:
            Redis key string, e.g. "user:42:settings:watchlist"
        """
        return f"user:{user_id}:settings:watchlist"
