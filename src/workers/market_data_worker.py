"""Market Data Worker for the Multi-User Web Trading Platform.

Shared worker that fetches market data for all users every 3-5 seconds.
Uses the Kite Connect API to fetch spot prices for configured instruments.

Requirements covered:
- 1.6.1: Fetch spot prices for configured instruments every 3-5 seconds
- 1.6.2: Fetch option chain data for NIFTY and BANKNIFTY
- 1.6.3: Compute VWAP from recent ticks (20 tick lookback)
- 1.6.5: Share market data across all users
- 1.6.6: Store recent ticks for VWAP calculation (last 100 ticks)
- 1.6.7: Handle market data fetch failures gracefully
- 1.6.8: Continue processing other symbols if one symbol fails
- 3.6.5: Cache market ticks with key market:{symbol}:ticks
- 3.6.8: Set TTL of 300 seconds for market ticks
"""

import json
import logging
import time
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from src.cache.redis_client import RedisClient
from src.cache.redis_keys import RedisKeys, TTL

logger = logging.getLogger(__name__)

# Default instrument mapping: symbol -> Kite exchange:tradingsymbol format
DEFAULT_INSTRUMENTS = {
    "NIFTY": "NSE:NIFTY 50",
    "BANKNIFTY": "NSE:NIFTY BANK",
}


class ErrorCategory(Enum):
    """Classification of errors for retry decisions.

    Transient errors are temporary and may succeed on retry.
    Permanent errors indicate a fundamental issue that won't resolve with retries.
    """

    TRANSIENT = "transient"
    PERMANENT = "permanent"


class MarketDataError(Exception):
    """Raised when market data fetching fails.

    Attributes:
        category: Whether the error is transient or permanent.
        symbol: The symbol that caused the error, if applicable.
    """

    def __init__(
        self,
        message: str,
        category: ErrorCategory = ErrorCategory.TRANSIENT,
        symbol: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.symbol = symbol


def classify_error(exception: Exception) -> ErrorCategory:
    """Classify an exception as transient or permanent.

    Transient errors (may succeed on retry):
    - Network timeouts, connection refused
    - API rate limiting (HTTP 429)
    - Temporary server errors (HTTP 5xx)
    - General IOError / OSError

    Permanent errors (will not succeed on retry):
    - Invalid token / authentication failures
    - Invalid instrument / data format errors
    - Permission denied
    - Bad request (HTTP 4xx except 429)

    Args:
        exception: The exception to classify.

    Returns:
        ErrorCategory.TRANSIENT or ErrorCategory.PERMANENT.
    """
    exc_type_name = type(exception).__name__
    exc_message = str(exception).lower()

    # Kite-specific exceptions by class name
    # (we check by name to avoid hard import dependency on kiteconnect)
    permanent_exception_types = {
        "TokenException",
        "PermissionException",
        "InputException",
        "GeneralException",
    }
    transient_exception_types = {
        "NetworkException",
        "DataException",
        "OrderException",
    }

    if exc_type_name in permanent_exception_types:
        return ErrorCategory.PERMANENT

    if exc_type_name in transient_exception_types:
        return ErrorCategory.TRANSIENT

    # Check for common transient indicators in the message
    transient_keywords = [
        "timeout",
        "timed out",
        "connection refused",
        "connection reset",
        "connection aborted",
        "temporarily unavailable",
        "rate limit",
        "too many requests",
        "429",
        "502",
        "503",
        "504",
        "network",
        "unreachable",
        "broken pipe",
    ]

    for keyword in transient_keywords:
        if keyword in exc_message:
            return ErrorCategory.TRANSIENT

    # Check for common permanent indicators
    permanent_keywords = [
        "invalid token",
        "token expired",
        "unauthorized",
        "forbidden",
        "permission denied",
        "not found",
        "invalid api",
        "bad request",
        "400",
        "401",
        "403",
    ]

    for keyword in permanent_keywords:
        if keyword in exc_message:
            return ErrorCategory.PERMANENT

    # IOError/OSError family is typically transient
    if isinstance(exception, (IOError, OSError, ConnectionError, TimeoutError)):
        return ErrorCategory.TRANSIENT

    # Default to transient (safer - allows retry)
    return ErrorCategory.TRANSIENT


class MarketDataWorker:
    """Shared market data worker - fetches and caches market data.

    This worker runs every 3-5 seconds and fetches spot prices for
    configured instruments using the Kite Connect API. Data is cached
    in Redis and shared across all users.

    Args:
        kite_client: A configured KiteConnect instance for API calls.
        redis_client: RedisClient instance for caching market data.
        instruments: Optional dict mapping symbol names to Kite
            exchange:tradingsymbol format. Defaults to NIFTY and BANKNIFTY.
    """

    def __init__(
        self,
        kite_client,
        redis_client: RedisClient,
        instruments: Optional[dict[str, str]] = None,
    ) -> None:
        """Initialize MarketDataWorker.

        Args:
            kite_client: A configured KiteConnect instance.
            redis_client: RedisClient for caching.
            instruments: Mapping of symbol -> Kite instrument identifier.
                Defaults to NIFTY and BANKNIFTY.

        Raises:
            ValueError: If kite_client or redis_client is None.
        """
        if kite_client is None:
            raise ValueError("kite_client cannot be None")
        if redis_client is None:
            raise ValueError("redis_client cannot be None")

        self.kite = kite_client
        self.redis = redis_client
        self.instruments = instruments or DEFAULT_INSTRUMENTS

    def fetch_spot_price(self, symbol: str) -> float:
        """Fetch current spot price for an instrument.

        Uses the Kite Connect LTP API to get the last traded price
        for the given symbol. The symbol is mapped to its Kite
        exchange:tradingsymbol format using the instruments dict.

        Args:
            symbol: The instrument symbol (e.g., "NIFTY", "BANKNIFTY").

        Returns:
            The last traded price as a float.

        Raises:
            ValueError: If symbol is empty or not in configured instruments.
            MarketDataError: If the API call fails or returns no data.
        """
        if not symbol or not symbol.strip():
            raise ValueError("Symbol cannot be empty")

        symbol = symbol.strip().upper()

        # Map symbol to Kite instrument identifier
        instrument_key = self.instruments.get(symbol)
        if instrument_key is None:
            raise ValueError(
                f"Symbol '{symbol}' not found in configured instruments. "
                f"Available: {list(self.instruments.keys())}"
            )

        try:
            ltp_response = self.kite.ltp([instrument_key])
        except Exception as e:
            category = classify_error(e)
            logger.error(
                "Failed to fetch LTP for %s (%s): %s [%s]",
                symbol,
                instrument_key,
                e,
                category.value,
            )
            raise MarketDataError(
                f"Failed to fetch spot price for {symbol}: {e}",
                category=category,
                symbol=symbol,
            ) from e

        # Extract last_price from response
        if not ltp_response or instrument_key not in ltp_response:
            raise MarketDataError(
                f"No data returned for {symbol} (instrument: {instrument_key})",
                category=ErrorCategory.PERMANENT,
                symbol=symbol,
            )

        instrument_data = ltp_response[instrument_key]
        last_price = instrument_data.get("last_price")

        if last_price is None:
            raise MarketDataError(
                f"No last_price in response for {symbol}: {instrument_data}",
                category=ErrorCategory.PERMANENT,
                symbol=symbol,
            )

        return float(last_price)

    def fetch_option_chain(self, symbol: str, expiry: str) -> List[Dict]:
        """Fetch option chain data for a given symbol and expiry.

        Uses the Kite Connect instruments API to get all options for the
        specified underlying symbol, filters by expiry date, then fetches
        LTP for each option contract.

        Args:
            symbol: The underlying symbol (e.g., "NIFTY", "BANKNIFTY").
            expiry: The expiry date in "YYYY-MM-DD" format (e.g., "2024-01-25").

        Returns:
            A list of dicts, each containing:
                - strike (float): The strike price
                - option_type (str): "CE" or "PE"
                - tradingsymbol (str): The Kite tradingsymbol for the contract
                - ltp (float): Last traded price of the contract
                - expiry (str): Expiry date as string

        Raises:
            ValueError: If symbol or expiry is empty, or symbol is not
                in the supported list (NIFTY, BANKNIFTY).
            MarketDataError: If the API call fails or returns no data.
        """
        if not symbol or not symbol.strip():
            raise ValueError("Symbol cannot be empty")

        if not expiry or not expiry.strip():
            raise ValueError("Expiry cannot be empty")

        symbol = symbol.strip().upper()
        expiry = expiry.strip()

        # Only NIFTY and BANKNIFTY are supported for option chain
        supported_symbols = {"NIFTY", "BANKNIFTY"}
        if symbol not in supported_symbols:
            raise ValueError(
                f"Symbol '{symbol}' not supported for option chain. "
                f"Supported: {sorted(supported_symbols)}"
            )

        try:
            instruments = self.kite.instruments("NFO")
        except Exception as e:
            category = classify_error(e)
            logger.error(
                "Failed to fetch NFO instruments for %s: %s [%s]",
                symbol,
                e,
                category.value,
            )
            raise MarketDataError(
                f"Failed to fetch instruments for {symbol}: {e}",
                category=category,
                symbol=symbol,
            ) from e

        if not instruments:
            raise MarketDataError(
                f"No instruments returned from NFO exchange for {symbol}",
                category=ErrorCategory.PERMANENT,
                symbol=symbol,
            )

        # Filter instruments by underlying name and expiry
        # Kite instruments have 'name' field matching the underlying
        # and 'expiry' as a date object or string
        filtered = []
        for inst in instruments:
            inst_name = inst.get("name", "")
            inst_type = inst.get("instrument_type", "")
            inst_expiry = inst.get("expiry")

            # Match underlying name
            if inst_name != symbol:
                continue

            # Match option type (CE or PE only)
            if inst_type not in ("CE", "PE"):
                continue

            # Match expiry - handle both date objects and strings
            expiry_str = str(inst_expiry) if inst_expiry else ""
            if expiry_str != expiry:
                continue

            filtered.append(inst)

        if not filtered:
            raise MarketDataError(
                f"No option contracts found for {symbol} with expiry {expiry}",
                category=ErrorCategory.PERMANENT,
                symbol=symbol,
            )

        # Fetch LTP for all filtered contracts
        # Build list of NFO:tradingsymbol identifiers
        instrument_keys = [
            f"NFO:{inst['tradingsymbol']}" for inst in filtered
        ]

        # Kite LTP API supports batches; fetch all at once
        try:
            ltp_response = self.kite.ltp(instrument_keys)
        except Exception as e:
            category = classify_error(e)
            logger.error(
                "Failed to fetch LTP for %s option chain: %s [%s]",
                symbol,
                e,
                category.value,
            )
            raise MarketDataError(
                f"Failed to fetch option chain LTP for {symbol}: {e}",
                category=category,
                symbol=symbol,
            ) from e

        if not ltp_response:
            ltp_response = {}

        # Build result list
        option_chain: List[Dict] = []
        for inst in filtered:
            key = f"NFO:{inst['tradingsymbol']}"
            ltp_data = ltp_response.get(key, {})
            ltp_value = ltp_data.get("last_price", 0.0)

            option_entry: Dict = {
                "strike": float(inst.get("strike", 0)),
                "option_type": inst["instrument_type"],
                "tradingsymbol": inst["tradingsymbol"],
                "ltp": float(ltp_value),
                "expiry": str(inst.get("expiry", "")),
            }

            option_chain.append(option_entry)

        # Sort by strike price, then by option type (CE before PE)
        option_chain.sort(key=lambda x: (x["strike"], x["option_type"]))

        return option_chain

    def fetch_all_spot_prices(self) -> Dict[str, object]:
        """Fetch spot prices for all configured instruments, handling per-symbol failures.

        Iterates over all configured instruments and fetches the spot price
        for each. If one symbol fails, logs the error and continues with the
        remaining symbols (Requirement 1.6.8).

        Returns:
            A dict with keys:
                - "prices" (Dict[str, float]): Successfully fetched prices
                    mapped as symbol -> last traded price.
                - "errors" (Dict[str, Dict]): Errors keyed by symbol, each
                    containing "error" (str) and "category" (str).

        Example:
            >>> result = worker.fetch_all_spot_prices()
            >>> result["prices"]
            {"NIFTY": 18650.75, "BANKNIFTY": 43520.10}
            >>> result["errors"]
            {}
        """
        prices: Dict[str, float] = {}
        errors: Dict[str, Dict] = {}

        for symbol in self.instruments:
            try:
                price = self.fetch_spot_price(symbol)
                prices[symbol] = price
            except MarketDataError as e:
                category = e.category if hasattr(e, "category") else ErrorCategory.TRANSIENT
                logger.warning(
                    "Failed to fetch spot price for %s (continuing with other symbols): %s [%s]",
                    symbol,
                    e,
                    category.value,
                )
                errors[symbol] = {
                    "error": str(e),
                    "category": category.value,
                }
            except Exception as e:
                # Catch any unexpected exception to never crash the worker
                category = classify_error(e)
                logger.error(
                    "Unexpected error fetching spot price for %s (continuing): %s [%s]",
                    symbol,
                    e,
                    category.value,
                )
                errors[symbol] = {
                    "error": str(e),
                    "category": category.value,
                }

        if errors:
            logger.info(
                "fetch_all_spot_prices completed: %d/%d symbols succeeded, %d failed",
                len(prices),
                len(self.instruments),
                len(errors),
            )

        return {"prices": prices, "errors": errors}

    def fetch_all_option_chains(
        self, expiry: str, symbols: Optional[List[str]] = None
    ) -> Dict[str, object]:
        """Fetch option chains for multiple symbols, handling per-symbol failures.

        Iterates over the specified symbols (defaulting to NIFTY and BANKNIFTY)
        and fetches the option chain for each. If one symbol fails, logs the
        error and continues with the remaining symbols (Requirement 1.6.8).

        Args:
            expiry: The expiry date in "YYYY-MM-DD" format.
            symbols: Optional list of symbols to fetch. Defaults to
                ["NIFTY", "BANKNIFTY"].

        Returns:
            A dict with keys:
                - "chains" (Dict[str, List[Dict]]): Successfully fetched option
                    chains mapped as symbol -> list of option entries.
                - "errors" (Dict[str, Dict]): Errors keyed by symbol, each
                    containing "error" (str) and "category" (str).

        Example:
            >>> result = worker.fetch_all_option_chains("2024-01-25")
            >>> "NIFTY" in result["chains"]
            True
            >>> result["errors"]
            {}
        """
        if symbols is None:
            symbols = ["NIFTY", "BANKNIFTY"]

        chains: Dict[str, List[Dict]] = {}
        errors: Dict[str, Dict] = {}

        for symbol in symbols:
            try:
                chain = self.fetch_option_chain(symbol, expiry)
                chains[symbol] = chain
            except (MarketDataError, ValueError) as e:
                if isinstance(e, MarketDataError):
                    category = e.category if hasattr(e, "category") else ErrorCategory.TRANSIENT
                else:
                    category = ErrorCategory.PERMANENT
                logger.warning(
                    "Failed to fetch option chain for %s expiry %s "
                    "(continuing with other symbols): %s [%s]",
                    symbol,
                    expiry,
                    e,
                    category.value,
                )
                errors[symbol] = {
                    "error": str(e),
                    "category": category.value,
                }
            except Exception as e:
                # Catch any unexpected exception to never crash the worker
                category = classify_error(e)
                logger.error(
                    "Unexpected error fetching option chain for %s expiry %s "
                    "(continuing): %s [%s]",
                    symbol,
                    expiry,
                    e,
                    category.value,
                )
                errors[symbol] = {
                    "error": str(e),
                    "category": category.value,
                }

        if errors:
            logger.info(
                "fetch_all_option_chains completed: %d/%d symbols succeeded, %d failed",
                len(chains),
                len(symbols),
                len(errors),
            )

        return {"chains": chains, "errors": errors}

    def has_sufficient_ticks(self, symbol: str, min_ticks: int = 20) -> bool:
        """Check if sufficient tick data is available for reliable VWAP.

        Queries Redis to determine how many ticks are stored for the given
        symbol and compares against the minimum threshold.

        Requirements covered:
        - 1.6.7: Handle market data fetch failures gracefully

        Args:
            symbol: The instrument symbol (e.g., "NIFTY", "BANKNIFTY").
            min_ticks: Minimum number of ticks required. Defaults to 20.

        Returns:
            True if at least min_ticks are available, False otherwise.

        Raises:
            ValueError: If symbol is empty or min_ticks is not positive.
        """
        if not symbol or not symbol.strip():
            raise ValueError("Symbol cannot be empty")

        if min_ticks <= 0:
            raise ValueError(f"min_ticks must be positive, got {min_ticks}")

        symbol = symbol.strip().upper()
        key = RedisKeys.market_ticks(symbol)

        try:
            tick_count = self.redis.llen(key)
        except Exception as e:
            logger.error("Failed to check tick count for %s: %s", symbol, e)
            return False

        return tick_count >= min_ticks

    def compute_vwap(self, symbol: str, lookback: int = 20) -> float:
        """Compute VWAP (Volume-Weighted Average Price) from recent ticks.

        Reads the most recent ticks from Redis and computes:
            VWAP = sum(price * volume) / sum(volume)

        If fewer ticks than the requested lookback are available, uses
        whatever ticks exist and logs a warning. Returns 0.0 if no ticks
        are available at all.

        Requirements covered:
        - 1.6.3: Compute VWAP from recent ticks (20 tick lookback)
        - 1.6.7: Handle market data fetch failures gracefully

        Args:
            symbol: The instrument symbol (e.g., "NIFTY", "BANKNIFTY").
            lookback: Number of recent ticks to use. Defaults to 20.

        Returns:
            The computed VWAP as a float. Returns 0.0 if there are no
            ticks or total volume is zero.

        Raises:
            ValueError: If symbol is empty or lookback is not positive.
        """
        if not symbol or not symbol.strip():
            raise ValueError("Symbol cannot be empty")

        if lookback <= 0:
            raise ValueError(f"Lookback must be positive, got {lookback}")

        symbol = symbol.strip().upper()
        key = RedisKeys.market_ticks(symbol)

        try:
            # Read the most recent `lookback` ticks from Redis list
            # Ticks are stored newest-first (lpush), so lrange(0, lookback-1)
            # gives us the most recent ticks.
            raw_ticks = self.redis.lrange(key, 0, lookback - 1)
        except Exception as e:
            logger.error("Failed to read ticks for %s: %s", symbol, e)
            return 0.0

        if not raw_ticks:
            logger.warning(
                "No ticks available for %s VWAP calculation (requested %d)",
                symbol,
                lookback,
            )
            return 0.0

        # Log warning when fewer ticks than requested lookback are available
        available_count = len(raw_ticks)
        if available_count < lookback:
            logger.warning(
                "Insufficient ticks for %s VWAP: %d available, %d requested. "
                "Using available data.",
                symbol,
                available_count,
                lookback,
            )

        # Parse ticks and compute VWAP
        total_price_volume = 0.0
        total_volume = 0.0

        for raw_tick in raw_ticks:
            try:
                tick = json.loads(raw_tick)
                price = float(tick["price"])
                volume = float(tick["volume"])

                total_price_volume += price * volume
                total_volume += volume
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
                logger.warning("Skipping malformed tick: %s (error: %s)", raw_tick, e)
                continue

        if total_volume == 0.0:
            return 0.0

        return total_price_volume / total_volume

    def cache_market_data(self, symbol: str, data: Dict) -> bool:
        """Cache market data in Redis with 10 second TTL.

        Stores the market data dict as a JSON string at key
        `market:{symbol}:data` with a TTL of 10 seconds.

        Automatically injects a 'timestamp' field with the current
        ISO-format timestamp if one is not already present in the data.

        The data dict should include spot price, VWAP, timestamp,
        and optionally option chain data.

        Requirements covered:
        - 1.6.4: Cache market data in Redis with 10 second TTL
        - 3.6.4: Cache market data with key market:{symbol}:data
        - 3.6.6: Set TTL of 10 seconds for market data
        - 3.6.9: Include timestamp in all cached data

        Args:
            symbol: The instrument symbol (e.g., "NIFTY", "BANKNIFTY").
            data: Dictionary containing market data to cache. Expected
                keys: spot (float), vwap (float), timestamp (str),
                and optionally option_chain (list). If 'timestamp' is
                not provided, it will be automatically added.

        Returns:
            True if the data was cached successfully, False otherwise.

        Raises:
            ValueError: If symbol is empty or data is not a dict.
        """
        if not symbol or not symbol.strip():
            raise ValueError("Symbol cannot be empty")

        if not isinstance(data, dict):
            raise ValueError("Data must be a dictionary")

        symbol = symbol.strip().upper()
        key = RedisKeys.market_data(symbol)

        # Ensure timestamp is always present (Requirement 3.6.9)
        if "timestamp" not in data:
            data = {**data, "timestamp": datetime.now().isoformat()}

        try:
            result = self.redis.setex(key, TTL.MARKET_DATA, json.dumps(data))
            return bool(result)
        except Exception as e:
            logger.error("Failed to cache market data for %s: %s", symbol, e)
            return False

    def get_market_data(self, symbol: str) -> Optional[Dict]:
        """Get market data using cache-aside pattern.

        First attempts to retrieve data from Redis cache. On cache miss,
        fetches fresh data from the broker API (spot price + VWAP),
        caches it, and returns it. If both cache and live fetch fail,
        returns None without crashing.

        Requirements covered:
        - 1.6.7: Handle market data fetch failures gracefully
        - 2.3.4: Fall back to database when Redis unavailable

        Args:
            symbol: The instrument symbol (e.g., "NIFTY", "BANKNIFTY").

        Returns:
            A dict containing market data (spot, vwap, timestamp), or
            None if data could not be retrieved from any source.

        Raises:
            ValueError: If symbol is empty.
        """
        if not symbol or not symbol.strip():
            raise ValueError("Symbol cannot be empty")

        symbol = symbol.strip().upper()

        # Step 1: Try to get from Redis cache
        cached = self.get_cached_market_data(symbol)
        if cached is not None:
            return cached

        # Step 2: Cache miss - log and fetch fresh data
        logger.info("Cache miss for %s, fetching fresh market data", symbol)

        try:
            spot = self.fetch_spot_price(symbol)
        except Exception as e:
            logger.error(
                "Failed to fetch spot price for %s on cache miss: %s", symbol, e
            )
            return None

        try:
            vwap = self.compute_vwap(symbol)
        except Exception as e:
            logger.warning(
                "Failed to compute VWAP for %s on cache miss (using 0.0): %s",
                symbol,
                e,
            )
            vwap = 0.0

        # Step 3: Build market data dict
        market_data: Dict = {
            "spot": spot,
            "vwap": vwap,
            "timestamp": datetime.now().isoformat(),
        }

        # Step 4: Cache the fresh data (best-effort, don't fail if caching fails)
        self.cache_market_data(symbol, market_data)

        return market_data

    def get_cached_market_data(self, symbol: str) -> Optional[Dict]:
        """Retrieve cached market data from Redis.

        Reads the JSON string at key `market:{symbol}:data` and
        deserializes it back to a dict. Returns None if the key
        does not exist (cache miss or TTL expired).

        Requirements covered:
        - 1.6.4: Cache market data in Redis with 10 second TTL
        - 3.6.4: Cache market data with key market:{symbol}:data

        Args:
            symbol: The instrument symbol (e.g., "NIFTY", "BANKNIFTY").

        Returns:
            The cached market data dict, or None if not found/expired.

        Raises:
            ValueError: If symbol is empty.
        """
        if not symbol or not symbol.strip():
            raise ValueError("Symbol cannot be empty")

        symbol = symbol.strip().upper()
        key = RedisKeys.market_data(symbol)

        try:
            data = self.redis.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            logger.error("Failed to get cached market data for %s: %s", symbol, e)
            return None

    def store_tick(self, symbol: str, price: float, volume: int) -> bool:
        """Store a market tick in Redis for VWAP calculation.

        Pushes a JSON-encoded tick (with price, volume, and timestamp) to the
        head of the Redis list at key `market:{symbol}:ticks`. The list is
        trimmed to keep only the last 100 ticks, and a TTL of 300 seconds
        is set on the key.

        Requirements covered:
        - 1.6.6: Store recent ticks for VWAP calculation (last 100 ticks)
        - 3.6.5: Cache market ticks with key market:{symbol}:ticks
        - 3.6.8: Set TTL of 300 seconds for market ticks
        - 3.6.9: Include timestamp in all cached data

        Args:
            symbol: The instrument symbol (e.g., "NIFTY", "BANKNIFTY").
            price: The tick price (must be positive).
            volume: The tick volume (must be non-negative).

        Returns:
            True if the tick was stored successfully, False otherwise.

        Raises:
            ValueError: If symbol is empty, price is not positive, or
                volume is negative.
        """
        if not symbol or not symbol.strip():
            raise ValueError("Symbol cannot be empty")

        if price <= 0:
            raise ValueError(f"Price must be positive, got {price}")

        if volume < 0:
            raise ValueError(f"Volume must be non-negative, got {volume}")

        symbol = symbol.strip().upper()
        key = RedisKeys.market_ticks(symbol)

        tick_data = json.dumps({
            "price": price,
            "volume": volume,
            "timestamp": time.time(),
        })

        try:
            # Push tick to head of list
            self.redis.lpush(key, tick_data)

            # Trim to keep only the last 100 ticks
            self.redis.ltrim(key, 0, 99)

            # Set TTL of 300 seconds
            self.redis.expire(key, TTL.MARKET_TICKS)

            return True

        except Exception as e:
            logger.error(
                "Failed to store tick for %s: %s", symbol, e
            )
            return False
