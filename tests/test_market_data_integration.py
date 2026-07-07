"""Integration tests for the Market Data Worker with realistic market data.

Tests simulate a full market data update cycle using realistic NIFTY and
BANKNIFTY price data, verifying the complete pipeline:
    fetch spot price -> store tick -> compute VWAP -> cache market data

These tests use mocked Kite API responses with realistic data patterns
(similar to what live market data would look like) and do NOT require
actual broker connectivity.

Requirements covered:
- 1.6.1: Fetch spot prices for configured instruments every 3-5 seconds
- 1.6.3: Compute VWAP from recent ticks (20 tick lookback)
- 1.6.5: Share market data across all users
- 1.6.6: Store recent ticks for VWAP calculation (last 100 ticks)
- 3.6.5: Cache market ticks with key market:{symbol}:ticks
- 3.6.8: Set TTL of 300 seconds for market ticks
"""

import json
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch

from src.workers.market_data_worker import (
    MarketDataWorker,
    DEFAULT_INSTRUMENTS,
)
from src.cache.redis_keys import RedisKeys, TTL


# ============================================================
# Realistic Market Data Fixtures
# ============================================================

# Realistic NIFTY price range: 18000-25000
NIFTY_REALISTIC_PRICES = [
    22150.35, 22155.80, 22148.90, 22162.45, 22158.20,
    22165.70, 22160.15, 22172.30, 22168.55, 22175.00,
    22170.25, 22178.60, 22180.45, 22176.90, 22183.15,
    22179.50, 22185.70, 22182.30, 22188.95, 22190.10,
    22186.40, 22192.75, 22195.20, 22191.60, 22198.05,
]

# Realistic BANKNIFTY price range: 42000-50000
BANKNIFTY_REALISTIC_PRICES = [
    46520.10, 46535.45, 46510.80, 46548.25, 46542.70,
    46555.90, 46550.15, 46568.30, 46562.45, 46575.80,
    46570.20, 46582.60, 46578.35, 46590.15, 46585.70,
    46598.40, 46592.80, 46605.25, 46600.50, 46612.75,
    46608.30, 46620.15, 46615.90, 46628.45, 46622.80,
]

# Realistic volumes (shares traded per tick)
NIFTY_VOLUMES = [
    15000, 22000, 18500, 31000, 25000, 12000, 28000, 19500,
    35000, 16000, 24000, 20000, 27000, 14000, 33000, 21000,
    17500, 29000, 23000, 11000, 26000, 32000, 15500, 28500,
    20500,
]

BANKNIFTY_VOLUMES = [
    8000, 12000, 9500, 15000, 11000, 7500, 14000, 10000,
    16000, 8500, 13000, 9000, 14500, 7000, 15500, 10500,
    8800, 13500, 11500, 6500, 12500, 16500, 8200, 14200,
    10800,
]


# ============================================================
# In-Memory Redis Mock (simulates real Redis list behavior)
# ============================================================


class InMemoryRedis:
    """In-memory Redis mock that simulates real list behavior for integration tests.

    Unlike a simple MagicMock, this actually stores data and implements
    lpush, lrange, ltrim, llen, expire, setex, and get operations
    so the full pipeline can be tested end-to-end.

    Supports TTL expiry simulation via simulate_expiry(key) to remove
    a key as if its TTL had elapsed.
    """

    def __init__(self):
        self._data = {}  # key -> value (str for strings, list for lists)
        self._ttls = {}  # key -> ttl_seconds

    def lpush(self, key: str, *values: str) -> int:
        if key not in self._data:
            self._data[key] = []
        for val in values:
            self._data[key].insert(0, val)
        return len(self._data[key])

    def lrange(self, key: str, start: int, stop: int) -> list:
        if key not in self._data:
            return []
        lst = self._data[key]
        return lst[start:stop + 1]

    def ltrim(self, key: str, start: int, stop: int) -> bool:
        if key not in self._data:
            return True
        self._data[key] = self._data[key][start:stop + 1]
        return True

    def llen(self, key: str) -> int:
        if key not in self._data:
            return 0
        return len(self._data[key])

    def expire(self, key: str, seconds: int) -> bool:
        self._ttls[key] = seconds
        return True

    def setex(self, key: str, seconds: int, value: str) -> bool:
        self._data[key] = value
        self._ttls[key] = seconds
        return True

    def get(self, key: str) -> str | None:
        val = self._data.get(key)
        if isinstance(val, list):
            return None  # Lists aren't accessible via GET
        return val

    def simulate_expiry(self, key: str) -> None:
        """Simulate TTL expiry by removing the key entirely.

        This mimics what Redis does when a key's TTL reaches zero:
        the key is deleted and subsequent GET/LRANGE calls return None/[].
        """
        self._data.pop(key, None)
        self._ttls.pop(key, None)

    def delete(self, key: str) -> int:
        """Delete a key from the store. Returns 1 if deleted, 0 if not found."""
        if key in self._data:
            del self._data[key]
            self._ttls.pop(key, None)
            return 1
        return 0


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def in_memory_redis():
    """Create an in-memory Redis mock with real list behavior."""
    return InMemoryRedis()


@pytest.fixture
def mock_kite():
    """Create a mock KiteConnect client."""
    return MagicMock()


@pytest.fixture
def worker(mock_kite, in_memory_redis):
    """Create a MarketDataWorker with in-memory Redis for integration tests."""
    return MarketDataWorker(
        kite_client=mock_kite,
        redis_client=in_memory_redis,
    )


# ============================================================
# Full Pipeline Integration Tests
# ============================================================


class TestFullUpdateCycleRealisticData:
    """Integration tests simulating a full update_market_data cycle.

    Verifies the complete pipeline: fetch -> store tick -> compute VWAP -> cache
    using realistic NIFTY and BANKNIFTY price data.
    """

    def test_single_cycle_nifty_realistic_price(self, worker, mock_kite, in_memory_redis):
        """Simulate a single update cycle with realistic NIFTY price (~22000 range)."""
        price = NIFTY_REALISTIC_PRICES[0]  # 22150.35
        mock_kite.ltp.return_value = {
            "NSE:NIFTY 50": {"last_price": price},
        }

        # Step 1: Fetch spot price
        fetched_price = worker.fetch_spot_price("NIFTY")
        assert fetched_price == price

        # Step 2: Store tick
        volume = NIFTY_VOLUMES[0]  # 15000
        result = worker.store_tick("NIFTY", fetched_price, volume)
        assert result is True

        # Step 3: Verify tick is stored in Redis
        ticks_key = RedisKeys.market_ticks("NIFTY")
        assert in_memory_redis.llen(ticks_key) == 1

        # Step 4: Compute VWAP (single tick = same as price)
        vwap = worker.compute_vwap("NIFTY")
        assert vwap == pytest.approx(price, rel=1e-6)

        # Step 5: Cache market data
        market_data = {"spot": fetched_price, "vwap": vwap}
        cached = worker.cache_market_data("NIFTY", market_data)
        assert cached is True

        # Step 6: Verify cached data is retrievable
        cached_data = worker.get_cached_market_data("NIFTY")
        assert cached_data is not None
        assert cached_data["spot"] == price
        assert cached_data["vwap"] == pytest.approx(price, rel=1e-6)
        assert "timestamp" in cached_data

    def test_single_cycle_banknifty_realistic_price(self, worker, mock_kite, in_memory_redis):
        """Simulate a single update cycle with realistic BANKNIFTY price (~46000 range)."""
        price = BANKNIFTY_REALISTIC_PRICES[0]  # 46520.10
        mock_kite.ltp.return_value = {
            "NSE:NIFTY BANK": {"last_price": price},
        }

        # Full pipeline
        fetched_price = worker.fetch_spot_price("BANKNIFTY")
        assert fetched_price == price

        volume = BANKNIFTY_VOLUMES[0]  # 8000
        worker.store_tick("BANKNIFTY", fetched_price, volume)

        vwap = worker.compute_vwap("BANKNIFTY")
        assert vwap == pytest.approx(price, rel=1e-6)

        market_data = {"spot": fetched_price, "vwap": vwap}
        cached = worker.cache_market_data("BANKNIFTY", market_data)
        assert cached is True

        cached_data = worker.get_cached_market_data("BANKNIFTY")
        assert cached_data["spot"] == price

    def test_full_cycle_both_instruments(self, worker, mock_kite, in_memory_redis):
        """Simulate a full cycle fetching both NIFTY and BANKNIFTY together."""
        nifty_price = 22150.35
        banknifty_price = 46520.10

        # Mock both instruments returning at once (batch call)
        mock_kite.ltp.side_effect = [
            {"NSE:NIFTY 50": {"last_price": nifty_price}},
            {"NSE:NIFTY BANK": {"last_price": banknifty_price}},
        ]

        # Use fetch_all_spot_prices (like the Celery task does)
        result = worker.fetch_all_spot_prices()

        assert result["prices"]["NIFTY"] == nifty_price
        assert result["prices"]["BANKNIFTY"] == banknifty_price
        assert result["errors"] == {}

        # Store ticks for both
        worker.store_tick("NIFTY", nifty_price, NIFTY_VOLUMES[0])
        worker.store_tick("BANKNIFTY", banknifty_price, BANKNIFTY_VOLUMES[0])

        # Both should have ticks stored
        assert in_memory_redis.llen(RedisKeys.market_ticks("NIFTY")) == 1
        assert in_memory_redis.llen(RedisKeys.market_ticks("BANKNIFTY")) == 1


class TestVWAPConvergenceMultipleCycles:
    """Tests verifying VWAP computation converges correctly over multiple cycles.

    Simulates price changes over multiple update cycles and verifies that
    VWAP (volume-weighted average price) converges as expected.
    """

    def test_vwap_converges_with_20_nifty_ticks(self, worker, mock_kite, in_memory_redis):
        """VWAP should be a volume-weighted average of the last 20 NIFTY ticks."""
        # Store 20 ticks with realistic NIFTY prices
        for i in range(20):
            worker.store_tick("NIFTY", NIFTY_REALISTIC_PRICES[i], NIFTY_VOLUMES[i])

        # Compute VWAP with 20 tick lookback
        vwap = worker.compute_vwap("NIFTY", lookback=20)

        # Manually compute expected VWAP
        total_pv = sum(
            NIFTY_REALISTIC_PRICES[i] * NIFTY_VOLUMES[i] for i in range(20)
        )
        total_vol = sum(NIFTY_VOLUMES[i] for i in range(20))
        expected_vwap = total_pv / total_vol

        assert vwap == pytest.approx(expected_vwap, rel=1e-9)
        # VWAP should be within realistic NIFTY range
        assert 18000 <= vwap <= 25000

    def test_vwap_converges_with_20_banknifty_ticks(self, worker, mock_kite, in_memory_redis):
        """VWAP should be a volume-weighted average of the last 20 BANKNIFTY ticks."""
        for i in range(20):
            worker.store_tick("BANKNIFTY", BANKNIFTY_REALISTIC_PRICES[i], BANKNIFTY_VOLUMES[i])

        vwap = worker.compute_vwap("BANKNIFTY", lookback=20)

        # Manually compute expected VWAP
        total_pv = sum(
            BANKNIFTY_REALISTIC_PRICES[i] * BANKNIFTY_VOLUMES[i] for i in range(20)
        )
        total_vol = sum(BANKNIFTY_VOLUMES[i] for i in range(20))
        expected_vwap = total_pv / total_vol

        assert vwap == pytest.approx(expected_vwap, rel=1e-9)
        # VWAP should be within realistic BANKNIFTY range
        assert 42000 <= vwap <= 50000

    def test_vwap_weights_high_volume_ticks_more(self, worker, mock_kite, in_memory_redis):
        """VWAP should weight high-volume ticks more heavily than low-volume ones."""
        # Store a high-volume tick at a low price
        worker.store_tick("NIFTY", 22000.0, 100000)  # Big volume at 22000
        # Store a low-volume tick at a high price
        worker.store_tick("NIFTY", 22500.0, 1000)  # Small volume at 22500

        vwap = worker.compute_vwap("NIFTY", lookback=20)

        # VWAP should be much closer to 22000 (high volume) than 22500
        # Expected: (22000*100000 + 22500*1000) / (100000+1000) = 22004.95
        expected = (22000.0 * 100000 + 22500.0 * 1000) / (100000 + 1000)
        assert vwap == pytest.approx(expected, rel=1e-9)
        assert vwap < 22050  # Much closer to 22000 than 22500

    def test_vwap_uses_only_lookback_window(self, worker, mock_kite, in_memory_redis):
        """VWAP with lookback=5 should only use the 5 most recent ticks."""
        # Store 10 ticks - first 5 at ~22000, next 5 at ~23000
        for i in range(5):
            worker.store_tick("NIFTY", 22000.0 + i, 10000)

        for i in range(5):
            worker.store_tick("NIFTY", 23000.0 + i, 10000)

        # VWAP with lookback=5 should only use the last 5 ticks (~23000)
        vwap = worker.compute_vwap("NIFTY", lookback=5)

        # The most recent 5 ticks are 23000-23004 (stored via lpush, most recent first)
        assert vwap >= 23000.0
        assert vwap <= 23004.0

    def test_multiple_cycles_simulating_price_drift(self, worker, mock_kite, in_memory_redis):
        """Simulate 25 update cycles with gradual price drift (uptrend)."""
        for i in range(25):
            price = NIFTY_REALISTIC_PRICES[i]
            volume = NIFTY_VOLUMES[i]
            worker.store_tick("NIFTY", price, volume)

        # After 25 ticks, VWAP (lookback=20) uses the most recent 20
        vwap = worker.compute_vwap("NIFTY", lookback=20)

        # VWAP should be within the range of the most recent 20 prices
        recent_prices = NIFTY_REALISTIC_PRICES[5:25]  # Most recent 20 (lpush reverses)
        # Actually lpush inserts at head, so lrange(0,19) gets the 20 most recently pushed
        # which are indices 5-24 of our original list
        min_price = min(recent_prices)
        max_price = max(recent_prices)
        assert min_price <= vwap <= max_price


class TestTickStorageAndTrimming:
    """Tests verifying tick storage, trimming to 100 ticks, and TTL behavior."""

    def test_ticks_trimmed_to_100(self, worker, mock_kite, in_memory_redis):
        """Storing more than 100 ticks should trim list to keep only 100."""
        # Store 110 ticks
        for i in range(110):
            price = 22000.0 + i * 0.5
            worker.store_tick("NIFTY", price, 10000)

        # List should be trimmed to 100
        ticks_key = RedisKeys.market_ticks("NIFTY")
        assert in_memory_redis.llen(ticks_key) == 100

    def test_ttl_set_to_300_seconds_for_ticks(self, worker, mock_kite, in_memory_redis):
        """TTL should be set to 300 seconds on market ticks key."""
        worker.store_tick("NIFTY", 22150.35, 15000)

        ticks_key = RedisKeys.market_ticks("NIFTY")
        assert in_memory_redis._ttls.get(ticks_key) == TTL.MARKET_TICKS
        assert in_memory_redis._ttls.get(ticks_key) == 300

    def test_tick_data_structure_contains_price_volume_timestamp(
        self, worker, mock_kite, in_memory_redis
    ):
        """Each stored tick should have price, volume, and timestamp fields."""
        worker.store_tick("NIFTY", 22150.35, 15000)

        ticks_key = RedisKeys.market_ticks("NIFTY")
        raw_tick = in_memory_redis.lrange(ticks_key, 0, 0)[0]
        tick = json.loads(raw_tick)

        assert tick["price"] == 22150.35
        assert tick["volume"] == 15000
        assert "timestamp" in tick
        assert isinstance(tick["timestamp"], float)

    def test_most_recent_tick_is_at_head_of_list(self, worker, mock_kite, in_memory_redis):
        """Ticks should be stored newest-first (lpush to head)."""
        worker.store_tick("NIFTY", 22100.0, 10000)
        worker.store_tick("NIFTY", 22200.0, 20000)
        worker.store_tick("NIFTY", 22300.0, 30000)

        ticks_key = RedisKeys.market_ticks("NIFTY")
        raw_ticks = in_memory_redis.lrange(ticks_key, 0, 2)

        # Most recent (22300) should be first
        ticks = [json.loads(t) for t in raw_ticks]
        assert ticks[0]["price"] == 22300.0
        assert ticks[1]["price"] == 22200.0
        assert ticks[2]["price"] == 22100.0


class TestCacheMarketDataIntegration:
    """Tests verifying market data caching with TTL and retrieval."""

    def test_cache_with_realistic_nifty_data(self, worker, mock_kite, in_memory_redis):
        """Cache realistic NIFTY market data and verify retrieval."""
        market_data = {
            "spot": 22150.35,
            "vwap": 22145.80,
        }
        result = worker.cache_market_data("NIFTY", market_data)
        assert result is True

        # Verify TTL is 10 seconds
        data_key = RedisKeys.market_data("NIFTY")
        assert in_memory_redis._ttls.get(data_key) == TTL.MARKET_DATA
        assert in_memory_redis._ttls.get(data_key) == 10

        # Verify retrieval
        cached = worker.get_cached_market_data("NIFTY")
        assert cached["spot"] == 22150.35
        assert cached["vwap"] == 22145.80
        assert "timestamp" in cached

    def test_cache_with_realistic_banknifty_data(self, worker, mock_kite, in_memory_redis):
        """Cache realistic BANKNIFTY market data and verify retrieval."""
        market_data = {
            "spot": 46520.10,
            "vwap": 46515.45,
        }
        result = worker.cache_market_data("BANKNIFTY", market_data)
        assert result is True

        cached = worker.get_cached_market_data("BANKNIFTY")
        assert cached["spot"] == 46520.10
        assert cached["vwap"] == 46515.45

    def test_cache_miss_returns_none(self, worker, mock_kite, in_memory_redis):
        """Cache miss (no data stored) should return None."""
        cached = worker.get_cached_market_data("NIFTY")
        assert cached is None

    def test_cache_overwrite_on_new_cycle(self, worker, mock_kite, in_memory_redis):
        """New market data should overwrite previous cached data."""
        # First cycle
        worker.cache_market_data("NIFTY", {"spot": 22150.35, "vwap": 22145.80})

        # Second cycle (price moved up)
        worker.cache_market_data("NIFTY", {"spot": 22165.70, "vwap": 22155.20})

        cached = worker.get_cached_market_data("NIFTY")
        assert cached["spot"] == 22165.70
        assert cached["vwap"] == 22155.20


class TestEndToEndCeleryTaskSimulation:
    """End-to-end tests simulating what the Celery task does.

    Simulates multiple consecutive cycles of the update_market_data task
    logic (without actually using Celery) to verify the full pipeline
    works correctly with realistic data over time.
    """

    def test_simulate_5_consecutive_cycles(self, worker, mock_kite, in_memory_redis):
        """Simulate 5 consecutive market data update cycles."""
        for cycle in range(5):
            nifty_price = NIFTY_REALISTIC_PRICES[cycle]
            banknifty_price = BANKNIFTY_REALISTIC_PRICES[cycle]

            # Mock LTP for this cycle
            mock_kite.ltp.side_effect = [
                {"NSE:NIFTY 50": {"last_price": nifty_price}},
                {"NSE:NIFTY BANK": {"last_price": banknifty_price}},
            ]

            # Fetch all prices (like the task does)
            result = worker.fetch_all_spot_prices()
            assert result["errors"] == {}

            # Store ticks and cache for each symbol
            for symbol, price in result["prices"].items():
                volume = NIFTY_VOLUMES[cycle] if symbol == "NIFTY" else BANKNIFTY_VOLUMES[cycle]
                worker.store_tick(symbol, price, volume)
                vwap = worker.compute_vwap(symbol)
                worker.cache_market_data(symbol, {"spot": price, "vwap": vwap})

        # After 5 cycles, verify state
        nifty_ticks_key = RedisKeys.market_ticks("NIFTY")
        banknifty_ticks_key = RedisKeys.market_ticks("BANKNIFTY")
        assert in_memory_redis.llen(nifty_ticks_key) == 5
        assert in_memory_redis.llen(banknifty_ticks_key) == 5

        # Cached data should reflect the last cycle
        nifty_cached = worker.get_cached_market_data("NIFTY")
        assert nifty_cached["spot"] == NIFTY_REALISTIC_PRICES[4]

        banknifty_cached = worker.get_cached_market_data("BANKNIFTY")
        assert banknifty_cached["spot"] == BANKNIFTY_REALISTIC_PRICES[4]

    def test_simulate_20_cycles_vwap_fully_populated(self, worker, mock_kite, in_memory_redis):
        """After 20 cycles, VWAP should use a full 20-tick lookback window."""
        for cycle in range(20):
            nifty_price = NIFTY_REALISTIC_PRICES[cycle]
            mock_kite.ltp.side_effect = [
                {"NSE:NIFTY 50": {"last_price": nifty_price}},
                {"NSE:NIFTY BANK": {"last_price": BANKNIFTY_REALISTIC_PRICES[cycle]}},
            ]

            result = worker.fetch_all_spot_prices()

            for symbol, price in result["prices"].items():
                volume = NIFTY_VOLUMES[cycle] if symbol == "NIFTY" else BANKNIFTY_VOLUMES[cycle]
                worker.store_tick(symbol, price, volume)

        # After 20 cycles, sufficient ticks for full VWAP
        assert worker.has_sufficient_ticks("NIFTY", min_ticks=20) is True
        assert worker.has_sufficient_ticks("BANKNIFTY", min_ticks=20) is True

        # VWAP should be computed from all 20 ticks
        vwap = worker.compute_vwap("NIFTY", lookback=20)
        assert 18000 <= vwap <= 25000  # Within realistic NIFTY range

    def test_get_market_data_cache_aside_pattern(self, worker, mock_kite, in_memory_redis):
        """Test the cache-aside pattern: cache miss triggers live fetch."""
        # No cached data initially
        assert worker.get_cached_market_data("NIFTY") is None

        # Mock the LTP call for get_market_data's cache-miss path
        mock_kite.ltp.return_value = {
            "NSE:NIFTY 50": {"last_price": 22150.35},
        }

        # get_market_data should fetch live and cache it
        data = worker.get_market_data("NIFTY")
        assert data is not None
        assert data["spot"] == 22150.35
        assert "vwap" in data
        assert "timestamp" in data

        # Subsequent call should hit cache
        cached = worker.get_cached_market_data("NIFTY")
        assert cached is not None
        assert cached["spot"] == 22150.35


class TestRealisticPriceRanges:
    """Tests verifying the worker handles realistic Indian market price ranges.

    NIFTY typically trades in 18000-25000 range.
    BANKNIFTY typically trades in 42000-50000 range.
    """

    def test_nifty_lower_bound_price(self, worker, mock_kite, in_memory_redis):
        """Worker handles NIFTY at the lower realistic bound (~18000)."""
        mock_kite.ltp.return_value = {"NSE:NIFTY 50": {"last_price": 18050.25}}

        price = worker.fetch_spot_price("NIFTY")
        assert price == 18050.25

        worker.store_tick("NIFTY", price, 20000)
        vwap = worker.compute_vwap("NIFTY")
        assert vwap == pytest.approx(18050.25, rel=1e-6)

    def test_nifty_upper_bound_price(self, worker, mock_kite, in_memory_redis):
        """Worker handles NIFTY at the upper realistic bound (~25000)."""
        mock_kite.ltp.return_value = {"NSE:NIFTY 50": {"last_price": 24980.50}}

        price = worker.fetch_spot_price("NIFTY")
        assert price == 24980.50

        worker.store_tick("NIFTY", price, 20000)
        vwap = worker.compute_vwap("NIFTY")
        assert vwap == pytest.approx(24980.50, rel=1e-6)

    def test_banknifty_lower_bound_price(self, worker, mock_kite, in_memory_redis):
        """Worker handles BANKNIFTY at the lower realistic bound (~42000)."""
        mock_kite.ltp.return_value = {"NSE:NIFTY BANK": {"last_price": 42100.75}}

        price = worker.fetch_spot_price("BANKNIFTY")
        assert price == 42100.75

        worker.store_tick("BANKNIFTY", price, 10000)
        vwap = worker.compute_vwap("BANKNIFTY")
        assert vwap == pytest.approx(42100.75, rel=1e-6)

    def test_banknifty_upper_bound_price(self, worker, mock_kite, in_memory_redis):
        """Worker handles BANKNIFTY at the upper realistic bound (~50000)."""
        mock_kite.ltp.return_value = {"NSE:NIFTY BANK": {"last_price": 49850.30}}

        price = worker.fetch_spot_price("BANKNIFTY")
        assert price == 49850.30

        worker.store_tick("BANKNIFTY", price, 10000)
        vwap = worker.compute_vwap("BANKNIFTY")
        assert vwap == pytest.approx(49850.30, rel=1e-6)

    def test_nifty_volatile_session_large_move(self, worker, mock_kite, in_memory_redis):
        """Simulate a volatile session with 2% intraday move on NIFTY."""
        # Opening price
        base_price = 22000.0
        # Simulate a sharp 2% drop followed by recovery
        volatile_prices = [
            22000.0, 21900.0, 21800.0, 21700.0, 21560.0,  # Drop
            21600.0, 21700.0, 21800.0, 21900.0, 22000.0,  # Recovery
        ]

        for i, price in enumerate(volatile_prices):
            worker.store_tick("NIFTY", price, 25000 + i * 1000)

        vwap = worker.compute_vwap("NIFTY", lookback=10)
        # VWAP should be within the price range seen
        assert min(volatile_prices) <= vwap <= max(volatile_prices)



# ============================================================
# Error Handling Integration Tests
# ============================================================


class TestErrorHandlingIntegration:
    """Integration tests for error handling in the Market Data Worker.

    Verifies graceful failure handling across various error scenarios:
    - Network timeouts
    - Malformed API responses
    - Redis connection failures
    - Intermittent/flaky failures
    - Token expiry
    - Rate limiting (HTTP 429)
    - Partial option chain failures

    Requirements covered:
    - 1.6.7: Handle market data fetch failures gracefully
    - 1.6.8: Continue processing other symbols if one symbol fails
    """

    def test_network_timeout_continues_with_other_symbols(
        self, worker, mock_kite, in_memory_redis
    ):
        """Network timeout on NIFTY should not prevent BANKNIFTY from being fetched.

        Simulates a network timeout when fetching NIFTY spot price.
        The worker should catch the error, log it, and still successfully
        fetch BANKNIFTY (Requirement 1.6.8).
        """
        # NIFTY times out, BANKNIFTY succeeds
        timeout_error = TimeoutError("Connection timed out after 10 seconds")
        mock_kite.ltp.side_effect = [
            timeout_error,  # NIFTY call fails
            {"NSE:NIFTY BANK": {"last_price": 46520.10}},  # BANKNIFTY succeeds
        ]

        result = worker.fetch_all_spot_prices()

        # BANKNIFTY should be fetched successfully
        assert "BANKNIFTY" in result["prices"]
        assert result["prices"]["BANKNIFTY"] == 46520.10

        # NIFTY should be in errors
        assert "NIFTY" in result["errors"]
        assert result["errors"]["NIFTY"]["category"] == "transient"

    def test_malformed_api_response_handled_gracefully(
        self, worker, mock_kite, in_memory_redis
    ):
        """Kite API returning malformed data (missing last_price) should be handled.

        Simulates a response that has the instrument key but no last_price field.
        The worker should raise MarketDataError with permanent category since
        the data format is invalid.
        """
        # Return response with missing last_price field
        mock_kite.ltp.return_value = {
            "NSE:NIFTY 50": {"volume": 1000000},  # No last_price key
        }

        from src.workers.market_data_worker import MarketDataError

        with pytest.raises(MarketDataError) as exc_info:
            worker.fetch_spot_price("NIFTY")

        assert exc_info.value.category.value == "permanent"
        assert "NIFTY" in str(exc_info.value)

    def test_redis_failure_during_tick_storage_returns_prices(
        self, worker, mock_kite, in_memory_redis
    ):
        """Redis connection failure during tick storage should not crash task.

        Even if Redis fails during store_tick, the task should still have
        successfully fetched prices from the broker. The store_tick method
        returns False on failure instead of raising (Requirement 1.6.7).
        """
        # First fetch prices successfully
        mock_kite.ltp.side_effect = [
            {"NSE:NIFTY 50": {"last_price": 22150.35}},
            {"NSE:NIFTY BANK": {"last_price": 46520.10}},
        ]

        result = worker.fetch_all_spot_prices()
        assert result["prices"]["NIFTY"] == 22150.35
        assert result["prices"]["BANKNIFTY"] == 46520.10

        # Now simulate Redis failure during tick storage
        # Override the redis lpush to raise an exception
        original_lpush = in_memory_redis.lpush
        in_memory_redis.lpush = MagicMock(
            side_effect=ConnectionError("Redis connection lost")
        )

        # store_tick should return False (not raise)
        tick_result = worker.store_tick("NIFTY", 22150.35, 15000)
        assert tick_result is False

        # Prices were still fetched successfully despite Redis failure
        assert result["prices"]["NIFTY"] == 22150.35

        # Restore
        in_memory_redis.lpush = original_lpush

    def test_redis_failure_during_cache_write_reports_success(
        self, worker, mock_kite, in_memory_redis
    ):
        """Redis failure during cache_market_data write should not crash.

        If caching fails, the task still has the prices and should report
        success for the fetch phase. cache_market_data returns False on
        failure (Requirement 1.6.7).
        """
        # Fetch prices successfully
        mock_kite.ltp.side_effect = [
            {"NSE:NIFTY 50": {"last_price": 22150.35}},
            {"NSE:NIFTY BANK": {"last_price": 46520.10}},
        ]

        result = worker.fetch_all_spot_prices()
        assert result["prices"]["NIFTY"] == 22150.35

        # Simulate Redis failure during cache write
        original_setex = in_memory_redis.setex
        in_memory_redis.setex = MagicMock(
            side_effect=ConnectionError("Redis connection refused")
        )

        # cache_market_data should return False, not raise
        cache_result = worker.cache_market_data(
            "NIFTY", {"spot": 22150.35, "vwap": 22145.0}
        )
        assert cache_result is False

        # The fetch result is still valid - prices were obtained
        assert result["prices"]["NIFTY"] == 22150.35
        assert result["errors"] == {}

        # Restore
        in_memory_redis.setex = original_setex

    def test_intermittent_failure_first_call_fails_second_succeeds(
        self, worker, mock_kite, in_memory_redis
    ):
        """Simulates flaky network: first fetch_all_spot_prices has NIFTY fail,
        second call succeeds for both symbols.

        This models intermittent network issues that resolve on the next
        Celery beat cycle.
        """
        # First cycle: NIFTY fails, BANKNIFTY succeeds
        mock_kite.ltp.side_effect = [
            ConnectionError("Connection reset by peer"),  # NIFTY fails
            {"NSE:NIFTY BANK": {"last_price": 46520.10}},  # BANKNIFTY OK
        ]

        result_1 = worker.fetch_all_spot_prices()
        assert "NIFTY" in result_1["errors"]
        assert result_1["errors"]["NIFTY"]["category"] == "transient"
        assert result_1["prices"]["BANKNIFTY"] == 46520.10

        # Second cycle: both succeed (flaky network resolved)
        mock_kite.ltp.side_effect = [
            {"NSE:NIFTY 50": {"last_price": 22155.80}},
            {"NSE:NIFTY BANK": {"last_price": 46535.45}},
        ]

        result_2 = worker.fetch_all_spot_prices()
        assert result_2["errors"] == {}
        assert result_2["prices"]["NIFTY"] == 22155.80
        assert result_2["prices"]["BANKNIFTY"] == 46535.45

    def test_token_expiry_classified_as_permanent_error(
        self, worker, mock_kite, in_memory_redis
    ):
        """Token expiry during market hours should be classified as permanent error.

        When the Kite access token expires, the API raises a TokenException.
        This is a permanent error - retrying with the same token won't help.
        The error should be categorized appropriately.
        """
        from src.workers.market_data_worker import classify_error, ErrorCategory

        # Simulate a token expiry exception (Kite raises TokenException)
        # We create an exception that mimics Kite's TokenException by name
        class TokenException(Exception):
            pass

        token_error = TokenException("Token is invalid or has expired")
        # Override __class__.__name__ isn't needed; classify_error checks type name
        token_error.__class__.__name__ = "TokenException"

        category = classify_error(token_error)
        assert category == ErrorCategory.PERMANENT

        # Also test via the worker's fetch_all_spot_prices
        mock_kite.ltp.side_effect = token_error

        result = worker.fetch_all_spot_prices()
        # Both symbols should fail with permanent error
        assert len(result["errors"]) > 0
        for symbol, error_info in result["errors"].items():
            assert error_info["category"] == "permanent"

    def test_rate_limiting_429_classified_as_transient(
        self, worker, mock_kite, in_memory_redis
    ):
        """HTTP 429 (rate limiting) should be classified as transient error.

        When the Kite API rate limits requests, the error should be classified
        as transient since a subsequent request (after backing off) may succeed.
        """
        from src.workers.market_data_worker import classify_error, ErrorCategory

        # Simulate a rate limit error with 429 in the message
        rate_limit_error = Exception("HTTP 429: Too many requests - rate limit exceeded")

        category = classify_error(rate_limit_error)
        assert category == ErrorCategory.TRANSIENT

        # Also test via worker: rate limited on NIFTY, BANKNIFTY also fails
        mock_kite.ltp.side_effect = rate_limit_error

        result = worker.fetch_all_spot_prices()
        assert len(result["errors"]) > 0
        for symbol, error_info in result["errors"].items():
            assert error_info["category"] == "transient"

    def test_partial_option_chain_failure_spot_prices_still_work(
        self, worker, mock_kite, in_memory_redis
    ):
        """Option chain failure for one symbol should not affect spot prices.

        If NIFTY option chain fetch fails but BANKNIFTY succeeds, the spot
        price fetching should be completely independent and unaffected.
        This verifies isolation between spot price and option chain pipelines.
        """
        # Spot prices work fine for both
        mock_kite.ltp.side_effect = [
            {"NSE:NIFTY 50": {"last_price": 22150.35}},
            {"NSE:NIFTY BANK": {"last_price": 46520.10}},
        ]

        spot_result = worker.fetch_all_spot_prices()
        assert spot_result["prices"]["NIFTY"] == 22150.35
        assert spot_result["prices"]["BANKNIFTY"] == 46520.10
        assert spot_result["errors"] == {}

        # Now option chain: NIFTY fails, BANKNIFTY succeeds
        # First call to instruments() for NIFTY fails
        mock_kite.instruments.side_effect = [
            ConnectionError("Network error fetching NIFTY options"),  # NIFTY fails
            [  # BANKNIFTY instruments returned
                {
                    "name": "BANKNIFTY",
                    "instrument_type": "CE",
                    "expiry": "2024-01-25",
                    "tradingsymbol": "BANKNIFTY24JAN46500CE",
                    "strike": 46500.0,
                },
                {
                    "name": "BANKNIFTY",
                    "instrument_type": "PE",
                    "expiry": "2024-01-25",
                    "tradingsymbol": "BANKNIFTY24JAN46500PE",
                    "strike": 46500.0,
                },
            ],
        ]

        # LTP for BANKNIFTY option chain
        mock_kite.ltp.side_effect = [
            {
                "NFO:BANKNIFTY24JAN46500CE": {"last_price": 250.50},
                "NFO:BANKNIFTY24JAN46500PE": {"last_price": 180.25},
            },
        ]

        chain_result = worker.fetch_all_option_chains(
            expiry="2024-01-25", symbols=["NIFTY", "BANKNIFTY"]
        )

        # NIFTY option chain should be in errors
        assert "NIFTY" in chain_result["errors"]
        assert chain_result["errors"]["NIFTY"]["category"] == "transient"

        # BANKNIFTY option chain should succeed
        assert "BANKNIFTY" in chain_result["chains"]
        assert len(chain_result["chains"]["BANKNIFTY"]) == 2

        # Original spot prices remain valid and unaffected
        assert spot_result["prices"]["NIFTY"] == 22150.35
        assert spot_result["prices"]["BANKNIFTY"] == 46520.10

# ============================================================
# Cache Behavior Integration Tests
# ============================================================


class TestCacheBehaviorIntegration:
    """Comprehensive cache behavior tests for the Market Data Worker.

    Verifies Redis caching patterns including TTL expiry, cache-aside logic,
    timestamp inclusion, key format correctness, symbol isolation, overwrite
    semantics, and cache hit behavior.

    Requirements covered:
    - 1.6.4: Cache market data in Redis with 10 second TTL
    - 3.6.4: Cache market data with key market:{symbol}:data
    - 3.6.5: Cache market ticks with key market:{symbol}:ticks
    - 3.6.6: Set TTL of 10 seconds for market data
    - 3.6.9: Include timestamp in all cached data
    - 2.3.4: Fall back to database when Redis unavailable
    """

    def test_cache_expiry_simulation_10_second_ttl(self, worker, mock_kite, in_memory_redis):
        """Cache expiry: after TTL elapses, cached market data is gone (Req 1.6.4, 3.6.6).

        Simulates TTL expiry by removing the key (as Redis would do when
        the 10-second TTL expires). After expiry, get_cached_market_data
        must return None.
        """
        # Cache some market data
        market_data = {"spot": 22150.35, "vwap": 22145.80}
        worker.cache_market_data("NIFTY", market_data)

        # Verify data is cached with TTL of 10 seconds
        data_key = RedisKeys.market_data("NIFTY")
        assert in_memory_redis._ttls[data_key] == 10
        assert worker.get_cached_market_data("NIFTY") is not None

        # Simulate TTL expiry (Redis deletes key after 10s)
        in_memory_redis.simulate_expiry(data_key)

        # After expiry, cache should return None
        assert worker.get_cached_market_data("NIFTY") is None

    def test_cache_aside_pattern_miss_triggers_fresh_fetch(self, worker, mock_kite, in_memory_redis):
        """Cache-aside: cache miss triggers live fetch then caches result (Req 2.3.4).

        When get_market_data is called and cache is empty, it should:
        1. Detect the cache miss
        2. Fetch fresh data from the broker API
        3. Cache the result for subsequent calls
        """
        # Ensure cache is empty
        assert worker.get_cached_market_data("NIFTY") is None

        # Mock broker API for the fresh fetch
        mock_kite.ltp.return_value = {"NSE:NIFTY 50": {"last_price": 22180.50}}

        # get_market_data should fetch fresh and cache it
        data = worker.get_market_data("NIFTY")
        assert data is not None
        assert data["spot"] == 22180.50

        # Verify the data is now cached
        cached = worker.get_cached_market_data("NIFTY")
        assert cached is not None
        assert cached["spot"] == 22180.50

        # Verify TTL was set correctly on the cached data
        data_key = RedisKeys.market_data("NIFTY")
        assert in_memory_redis._ttls[data_key] == TTL.MARKET_DATA

    def test_cached_data_always_includes_timestamp(self, worker, mock_kite, in_memory_redis):
        """All cached market data must include a timestamp field (Req 3.6.9).

        Even if the original data dict does not contain a 'timestamp' field,
        cache_market_data must inject one before storing.
        """
        # Cache data WITHOUT a timestamp field
        market_data = {"spot": 22150.35, "vwap": 22145.80}
        worker.cache_market_data("NIFTY", market_data)

        cached = worker.get_cached_market_data("NIFTY")
        assert cached is not None
        assert "timestamp" in cached
        assert isinstance(cached["timestamp"], str)
        assert len(cached["timestamp"]) > 0  # Non-empty timestamp

    def test_market_data_key_format(self, worker, mock_kite, in_memory_redis):
        """Market data key format must be market:{symbol}:data (Req 3.6.4).

        Verifies the exact Redis key used for market data caching follows
        the required pattern.
        """
        # Verify the key generation utility
        assert RedisKeys.market_data("NIFTY") == "market:NIFTY:data"
        assert RedisKeys.market_data("BANKNIFTY") == "market:BANKNIFTY:data"

        # Cache data and verify it's stored at the correct key
        worker.cache_market_data("NIFTY", {"spot": 22150.35, "vwap": 22145.80})

        # Direct access to in-memory store confirms key format
        assert "market:NIFTY:data" in in_memory_redis._data

    def test_market_ticks_key_format(self, worker, mock_kite, in_memory_redis):
        """Market ticks key format must be market:{symbol}:ticks (Req 3.6.5).

        Verifies the exact Redis key used for market tick storage follows
        the required pattern.
        """
        # Verify the key generation utility
        assert RedisKeys.market_ticks("NIFTY") == "market:NIFTY:ticks"
        assert RedisKeys.market_ticks("BANKNIFTY") == "market:BANKNIFTY:ticks"

        # Store a tick and verify it's stored at the correct key
        worker.store_tick("NIFTY", 22150.35, 15000)

        # Direct access to in-memory store confirms key format
        assert "market:NIFTY:ticks" in in_memory_redis._data

    def test_multiple_symbols_separate_cache_entries(self, worker, mock_kite, in_memory_redis):
        """Multiple symbols must have separate cache entries (no cross-contamination).

        NIFTY and BANKNIFTY data must be stored independently. Updating
        one symbol's cache must not affect the other.
        """
        # Cache data for both symbols
        nifty_data = {"spot": 22150.35, "vwap": 22145.80}
        banknifty_data = {"spot": 46520.10, "vwap": 46515.45}

        worker.cache_market_data("NIFTY", nifty_data)
        worker.cache_market_data("BANKNIFTY", banknifty_data)

        # Retrieve and verify each symbol has its own data
        nifty_cached = worker.get_cached_market_data("NIFTY")
        banknifty_cached = worker.get_cached_market_data("BANKNIFTY")

        assert nifty_cached["spot"] == 22150.35
        assert banknifty_cached["spot"] == 46520.10

        # Update NIFTY - BANKNIFTY should remain unchanged
        worker.cache_market_data("NIFTY", {"spot": 22200.00, "vwap": 22190.00})

        nifty_updated = worker.get_cached_market_data("NIFTY")
        banknifty_unchanged = worker.get_cached_market_data("BANKNIFTY")

        assert nifty_updated["spot"] == 22200.00
        assert banknifty_unchanged["spot"] == 46520.10  # Unchanged

        # Expire NIFTY - BANKNIFTY should still be available
        in_memory_redis.simulate_expiry(RedisKeys.market_data("NIFTY"))
        assert worker.get_cached_market_data("NIFTY") is None
        assert worker.get_cached_market_data("BANKNIFTY") is not None

    def test_cache_overwrite_newer_data_replaces_older(self, worker, mock_kite, in_memory_redis):
        """Cache overwrite: newer market data replaces older cached data.

        Each call to cache_market_data for the same symbol must fully
        overwrite the previously cached value.
        """
        # First write
        worker.cache_market_data("NIFTY", {"spot": 22100.00, "vwap": 22095.00})
        cached_1 = worker.get_cached_market_data("NIFTY")
        assert cached_1["spot"] == 22100.00
        timestamp_1 = cached_1["timestamp"]

        # Second write (newer data)
        worker.cache_market_data("NIFTY", {"spot": 22200.00, "vwap": 22195.00})
        cached_2 = worker.get_cached_market_data("NIFTY")
        assert cached_2["spot"] == 22200.00
        assert cached_2["vwap"] == 22195.00

        # Old spot value should be completely gone
        assert cached_2["spot"] != 22100.00

        # Third write (even newer)
        worker.cache_market_data("NIFTY", {"spot": 22300.00, "vwap": 22295.00})
        cached_3 = worker.get_cached_market_data("NIFTY")
        assert cached_3["spot"] == 22300.00

    def test_get_market_data_returns_cached_on_hit_without_api_call(
        self, worker, mock_kite, in_memory_redis
    ):
        """get_market_data returns cached data on cache hit without calling API.

        When data exists in cache (hasn't expired), get_market_data must
        return it directly without making a broker API call.
        """
        # Pre-populate cache
        worker.cache_market_data("NIFTY", {"spot": 22150.35, "vwap": 22145.80})

        # Reset the mock to track new calls
        mock_kite.ltp.reset_mock()

        # get_market_data should return cached data without calling API
        data = worker.get_market_data("NIFTY")
        assert data is not None
        assert data["spot"] == 22150.35
        assert data["vwap"] == 22145.80

        # Verify the broker API was NOT called (cache hit)
        mock_kite.ltp.assert_not_called()
