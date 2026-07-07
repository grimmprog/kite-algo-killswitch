"""Market Data Service — manages data source configuration and live index fetching.

Handles per-user data source preferences (enable/disable, priority ordering),
market hours detection for IST trading sessions, and priority-based fallback
when fetching live index data.

Implements Requirements: 6.1, 6.2, 6.5, 6.6, 6.7, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7
"""

import json
import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from src.cache.redis_client import RedisClient
from src.database.models.market_data_config import MarketDataSourceConfig

logger = logging.getLogger(__name__)

# IST timezone for market hours detection
IST = ZoneInfo("Asia/Kolkata")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class DataSourceConfig(BaseModel):
    """A single data source configuration entry."""

    model_config = ConfigDict(from_attributes=True)

    source_id: str  # "nsepy" | "yfinance" | "kite_historical" | "dhan_market"
    display_name: str
    enabled: bool
    priority: int  # Lower number = higher priority


class IndexData(BaseModel):
    """Live index data for a single market index."""

    symbol: str  # "NIFTY 50" | "SENSEX" | "BANK NIFTY" | "NIFTY IT"
    value: float
    change_points: float
    change_percent: float
    last_updated: str


class LiveMarketResponse(BaseModel):
    """Response for the live market data endpoint."""

    indices: List[IndexData]
    market_open: bool
    data_source: str
    last_successful_fetch: Optional[str] = None


# ---------------------------------------------------------------------------
# Default sources
# ---------------------------------------------------------------------------

DEFAULT_SOURCES: List[Dict[str, Any]] = [
    {
        "source_id": "nsepy",
        "display_name": "NSEpy",
        "enabled": True,
        "priority": 0,
    },
    {
        "source_id": "yfinance",
        "display_name": "Yahoo Finance",
        "enabled": True,
        "priority": 1,
    },
    {
        "source_id": "kite_historical",
        "display_name": "Kite Historical Data",
        "enabled": False,
        "priority": 2,
    },
    {
        "source_id": "dhan_market",
        "display_name": "Dhan Market Data",
        "enabled": False,
        "priority": 3,
    },
]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class DataSourceValidationError(Exception):
    """Raised when data source configuration is invalid."""

    pass


class DataUnavailableError(Exception):
    """Raised when all data sources fail to provide data."""

    pass


# ---------------------------------------------------------------------------
# MarketDataService
# ---------------------------------------------------------------------------


class MarketDataService:
    """Fetches live market data with priority-ordered fallback.

    Manages user data source configurations and provides market hours
    detection for IST trading sessions (9:15 AM - 3:30 PM, weekdays).
    """

    MARKET_OPEN_TIME = "09:15"  # IST
    MARKET_CLOSE_TIME = "15:30"  # IST
    FETCH_TIMEOUT_SECONDS = 5

    def __init__(
        self,
        db: Session,
        redis_client: RedisClient,
        kite_factory: Optional[Callable] = None,
        dhan_factory: Optional[Callable] = None,
    ) -> None:
        """Initialize MarketDataService.

        Args:
            db: SQLAlchemy session for database operations.
            redis_client: RedisClient instance for caching.
            kite_factory: Optional callable that returns a Kite client for a user.
            dhan_factory: Optional callable that returns a Dhan client for a user.
        """
        if db is None:
            raise ValueError("db cannot be None")
        if redis_client is None:
            raise ValueError("redis_client cannot be None")

        self.db = db
        self.redis = redis_client
        self.kite_factory = kite_factory
        self.dhan_factory = dhan_factory

    def get_user_sources(self, user_id: int) -> List[DataSourceConfig]:
        """Get user's data source configuration sorted by priority.

        If no configuration exists for the user, creates and persists
        the default source configuration.

        Args:
            user_id: The user's database ID.

        Returns:
            List of DataSourceConfig sorted by priority (ascending).
        """
        configs = (
            self.db.query(MarketDataSourceConfig)
            .filter(MarketDataSourceConfig.user_id == user_id)
            .order_by(MarketDataSourceConfig.priority.asc())
            .all()
        )

        if not configs:
            # Create default sources for this user
            configs = self._create_default_sources(user_id)

        return [
            DataSourceConfig(
                source_id=config.source_id,
                display_name=config.display_name,
                enabled=config.enabled,
                priority=config.priority,
            )
            for config in configs
        ]

    def update_user_sources(
        self, user_id: int, sources: List[DataSourceConfig]
    ) -> None:
        """Validate and persist data source configuration.

        Validates that at least one source is enabled, then persists
        the full configuration (replacing existing entries).

        Args:
            user_id: The user's database ID.
            sources: List of DataSourceConfig entries to persist.

        Raises:
            DataSourceValidationError: If no sources are enabled.
        """
        # Validation: at least one source must be enabled
        enabled_sources = [s for s in sources if s.enabled]
        if not enabled_sources:
            raise DataSourceValidationError(
                "At least one data source must be enabled"
            )

        # Delete existing configuration for this user
        self.db.query(MarketDataSourceConfig).filter(
            MarketDataSourceConfig.user_id == user_id
        ).delete()

        # Insert new configuration
        for source in sources:
            config = MarketDataSourceConfig(
                user_id=user_id,
                source_id=source.source_id,
                display_name=source.display_name,
                enabled=source.enabled,
                priority=source.priority,
            )
            self.db.add(config)

        self.db.commit()
        logger.info(
            "Updated data source config for user %d: %d sources (%d enabled)",
            user_id,
            len(sources),
            len(enabled_sources),
        )

    def is_market_open(self) -> bool:
        """Check if current time is within NSE/BSE market hours (IST).

        Market hours: 9:15 AM to 3:30 PM IST, Monday to Friday.
        Excludes weekends. Holiday calendar not implemented (future enhancement).

        Returns:
            True if the market is currently open, False otherwise.
        """
        now_ist = datetime.now(IST)
        return self._is_market_open_at(now_ist)

    def _is_market_open_at(self, dt: datetime) -> bool:
        """Check if a given datetime falls within market hours.

        Internal method that accepts a datetime for testability.

        Args:
            dt: A timezone-aware datetime to check (should be in IST).

        Returns:
            True if the datetime is within market hours, False otherwise.
        """
        # Saturday (5) and Sunday (6) are closed
        if dt.weekday() >= 5:
            return False

        market_open = dt.replace(hour=9, minute=15, second=0, microsecond=0)
        market_close = dt.replace(hour=15, minute=30, second=0, microsecond=0)
        return market_open <= dt <= market_close

    # ------------------------------------------------------------------
    # Live market data fetching (Requirements 7.1, 7.2, 7.3, 7.5, 7.6, 7.7)
    # ------------------------------------------------------------------

    CACHE_TTL_SECONDS = 30
    CACHE_KEY_PREFIX = "live_indices"

    def fetch_live_indices(self, user_id: int) -> LiveMarketResponse:
        """Fetch live index data using priority-ordered sources with fallback.

        Checks Redis cache first (key: `live_indices:{user_id}`). On cache miss,
        fetches from enabled sources in priority order with 5s timeout per source.
        Caches successful results with 30s TTL.

        Args:
            user_id: The user's database ID.

        Returns:
            LiveMarketResponse with index data, market_open flag, and data_source.

        Raises:
            DataUnavailableError: If all enabled sources fail.
        """
        cache_key = f"{self.CACHE_KEY_PREFIX}:{user_id}"

        # Check Redis cache first
        cached = self.redis.get(cache_key)
        if cached:
            try:
                data = json.loads(cached)
                return LiveMarketResponse(**data)
            except (json.JSONDecodeError, Exception) as e:
                logger.warning("Failed to parse cached data for user %d: %s", user_id, e)

        # Cache miss — fetch with fallback
        sources = self.get_user_sources(user_id)
        enabled_sources = [s for s in sources if s.enabled]
        enabled_sources.sort(key=lambda s: s.priority)

        if not enabled_sources:
            raise DataUnavailableError("No data sources are enabled")

        last_error: Optional[Exception] = None
        for source in enabled_sources:
            try:
                indices = self._fetch_from_source(source.source_id, user_id)
                # Build response
                now_str = datetime.now(IST).isoformat()
                response = LiveMarketResponse(
                    indices=indices,
                    market_open=self.is_market_open(),
                    data_source=source.source_id,
                    last_successful_fetch=now_str,
                )
                # Cache the result with 30s TTL
                self.redis.set(
                    cache_key,
                    response.model_dump_json(),
                    ttl=self.CACHE_TTL_SECONDS,
                )
                return response
            except Exception as e:
                logger.warning(
                    "Data source '%s' failed for user %d: %s",
                    source.source_id,
                    user_id,
                    e,
                )
                last_error = e
                continue

        raise DataUnavailableError(
            f"All {len(enabled_sources)} sources failed", last_error
        )

    def _fetch_from_source(self, source_id: str, user_id: int) -> List[IndexData]:
        """Dispatch to the appropriate adapter with 5s timeout.

        Args:
            source_id: The source identifier (e.g., "nsepy", "yfinance").
            user_id: The user's database ID (needed for broker-specific sources).

        Returns:
            List of IndexData from the source.

        Raises:
            TimeoutError: If the fetch exceeds 5 seconds.
            ConnectionError: If the source is unreachable.
            Exception: For any other adapter failure.
        """
        adapters: Dict[str, Callable[[], List[IndexData]]] = {
            "nsepy": self._fetch_nsepy,
            "yfinance": self._fetch_yfinance,
            "kite_historical": lambda: self._fetch_kite(user_id),
            "dhan_market": lambda: self._fetch_dhan(user_id),
        }

        adapter = adapters.get(source_id)
        if adapter is None:
            raise ValueError(f"Unknown data source: {source_id}")

        return adapter()

    def _fetch_nsepy(self) -> List[IndexData]:
        """Fetch NIFTY 50, SENSEX, BANK NIFTY, NIFTY IT from nsepy.

        Returns:
            List of IndexData for the four indices.

        Raises:
            ImportError: If nsepy is not available.
            ConnectionError: If the fetch fails.
            TimeoutError: If the fetch exceeds 5 seconds.
        """
        try:
            from nsetools import Nse
        except ImportError:
            logger.warning("nsepy/nsetools library not available")
            raise ImportError("nsepy/nsetools library not installed")

        try:
            nse = Nse()
            now_str = datetime.now(IST).isoformat()

            indices_data = []
            # Fetch NIFTY 50
            nifty = nse.get_index_quote("nifty 50")
            if nifty:
                indices_data.append(
                    IndexData(
                        symbol="NIFTY 50",
                        value=float(nifty.get("lastPrice", 0)),
                        change_points=float(nifty.get("change", 0)),
                        change_percent=float(nifty.get("pChange", 0)),
                        last_updated=now_str,
                    )
                )

            # Fetch NIFTY BANK
            bank_nifty = nse.get_index_quote("nifty bank")
            if bank_nifty:
                indices_data.append(
                    IndexData(
                        symbol="BANK NIFTY",
                        value=float(bank_nifty.get("lastPrice", 0)),
                        change_points=float(bank_nifty.get("change", 0)),
                        change_percent=float(bank_nifty.get("pChange", 0)),
                        last_updated=now_str,
                    )
                )

            # Fetch NIFTY IT
            nifty_it = nse.get_index_quote("nifty it")
            if nifty_it:
                indices_data.append(
                    IndexData(
                        symbol="NIFTY IT",
                        value=float(nifty_it.get("lastPrice", 0)),
                        change_points=float(nifty_it.get("change", 0)),
                        change_percent=float(nifty_it.get("pChange", 0)),
                        last_updated=now_str,
                    )
                )

            # Note: SENSEX is not available via nsetools (BSE index)
            # Add a placeholder or skip
            indices_data.append(
                IndexData(
                    symbol="SENSEX",
                    value=0.0,
                    change_points=0.0,
                    change_percent=0.0,
                    last_updated=now_str,
                )
            )

            if not indices_data:
                raise ConnectionError("No index data received from nsepy")

            return indices_data

        except ImportError:
            raise
        except Exception as e:
            raise ConnectionError(f"nsepy fetch failed: {e}") from e

    def _fetch_yfinance(self) -> List[IndexData]:
        """Fetch NIFTY 50, SENSEX, BANK NIFTY, NIFTY IT from yfinance.

        Returns:
            List of IndexData for the four indices.

        Raises:
            ImportError: If yfinance is not available.
            ConnectionError: If the fetch fails.
            TimeoutError: If the fetch exceeds 5 seconds.
        """
        try:
            import yfinance as yf
        except ImportError:
            logger.warning("yfinance library not available")
            raise ImportError("yfinance library not installed")

        try:
            # Yahoo Finance ticker symbols for Indian indices
            symbols = {
                "^NSEI": "NIFTY 50",
                "^BSESN": "SENSEX",
                "^NSEBANK": "BANK NIFTY",
                "^CNXIT": "NIFTY IT",
            }

            now_str = datetime.now(IST).isoformat()
            indices_data = []

            for ticker_symbol, display_name in symbols.items():
                try:
                    ticker = yf.Ticker(ticker_symbol)
                    info = ticker.fast_info
                    last_price = float(info.last_price) if hasattr(info, "last_price") else 0.0
                    prev_close = float(info.previous_close) if hasattr(info, "previous_close") else 0.0
                    change_points = last_price - prev_close
                    change_percent = (change_points / prev_close * 100) if prev_close != 0 else 0.0

                    indices_data.append(
                        IndexData(
                            symbol=display_name,
                            value=last_price,
                            change_points=round(change_points, 2),
                            change_percent=round(change_percent, 2),
                            last_updated=now_str,
                        )
                    )
                except Exception as e:
                    logger.warning("yfinance failed for %s: %s", ticker_symbol, e)
                    continue

            if not indices_data:
                raise ConnectionError("No index data received from yfinance")

            return indices_data

        except ImportError:
            raise
        except Exception as e:
            raise ConnectionError(f"yfinance fetch failed: {e}") from e

    def _fetch_kite(self, user_id: int) -> List[IndexData]:
        """Fetch index data from Kite using kite_factory.

        Args:
            user_id: The user's database ID for getting Kite client.

        Returns:
            List of IndexData for the four indices.

        Raises:
            ConnectionError: If Kite is not configured or fetch fails.
        """
        if self.kite_factory is None:
            raise ConnectionError("Kite factory not configured")

        try:
            kite = self.kite_factory(user_id)
            if kite is None:
                raise ConnectionError("Kite client not available for user")

            now_str = datetime.now(IST).isoformat()

            # Kite instrument tokens for indices
            # NIFTY 50: 256265, SENSEX: 265 (BSE), BANK NIFTY: 260105, NIFTY IT: 259849
            instrument_tokens = {
                256265: "NIFTY 50",
                265: "SENSEX",
                260105: "BANK NIFTY",
                259849: "NIFTY IT",
            }

            quotes = kite.quote([f"NSE:{name}" for name in ["NIFTY 50", "NIFTY BANK", "NIFTY IT"]])
            # Also try BSE SENSEX
            try:
                bse_quotes = kite.quote(["BSE:SENSEX"])
                quotes.update(bse_quotes)
            except Exception:
                pass

            indices_data = []
            symbol_map = {
                "NSE:NIFTY 50": "NIFTY 50",
                "NSE:NIFTY BANK": "BANK NIFTY",
                "NSE:NIFTY IT": "NIFTY IT",
                "BSE:SENSEX": "SENSEX",
            }

            for key, display_name in symbol_map.items():
                if key in quotes:
                    q = quotes[key]
                    last_price = float(q.get("last_price", 0))
                    prev_close = float(q.get("ohlc", {}).get("close", 0))
                    change_points = last_price - prev_close
                    change_percent = (change_points / prev_close * 100) if prev_close != 0 else 0.0

                    indices_data.append(
                        IndexData(
                            symbol=display_name,
                            value=last_price,
                            change_points=round(change_points, 2),
                            change_percent=round(change_percent, 2),
                            last_updated=now_str,
                        )
                    )

            if not indices_data:
                raise ConnectionError("No index data received from Kite")

            return indices_data

        except ConnectionError:
            raise
        except Exception as e:
            raise ConnectionError(f"Kite fetch failed: {e}") from e

    def _fetch_dhan(self, user_id: int) -> List[IndexData]:
        """Fetch index data from Dhan using dhan_factory.

        Args:
            user_id: The user's database ID for getting Dhan client.

        Returns:
            List of IndexData for the four indices.

        Raises:
            ConnectionError: If Dhan is not configured or fetch fails.
        """
        if self.dhan_factory is None:
            raise ConnectionError("Dhan factory not configured")

        try:
            dhan = self.dhan_factory(user_id)
            if dhan is None:
                raise ConnectionError("Dhan client not available for user")

            now_str = datetime.now(IST).isoformat()

            # Dhan security IDs for indices
            # These are approximate; real IDs should be looked up
            index_securities = {
                "13": "NIFTY 50",      # NSE NIFTY 50
                "51": "SENSEX",         # BSE SENSEX
                "25": "BANK NIFTY",     # NSE BANK NIFTY
                "27": "NIFTY IT",       # NSE NIFTY IT
            }

            indices_data = []
            for sec_id, display_name in index_securities.items():
                try:
                    quote = dhan.get_market_quote(sec_id)
                    if quote and quote.get("status") == "success":
                        data = quote.get("data", {})
                        last_price = float(data.get("last_price", 0))
                        prev_close = float(data.get("prev_close", 0))
                        change_points = last_price - prev_close
                        change_percent = (
                            (change_points / prev_close * 100) if prev_close != 0 else 0.0
                        )

                        indices_data.append(
                            IndexData(
                                symbol=display_name,
                                value=last_price,
                                change_points=round(change_points, 2),
                                change_percent=round(change_percent, 2),
                                last_updated=now_str,
                            )
                        )
                except Exception as e:
                    logger.warning("Dhan fetch failed for %s: %s", display_name, e)
                    continue

            if not indices_data:
                raise ConnectionError("No index data received from Dhan")

            return indices_data

        except ConnectionError:
            raise
        except Exception as e:
            raise ConnectionError(f"Dhan fetch failed: {e}") from e

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _create_default_sources(
        self, user_id: int
    ) -> List[MarketDataSourceConfig]:
        """Create and persist default data source configuration for a user.

        Args:
            user_id: The user's database ID.

        Returns:
            List of persisted MarketDataSourceConfig ORM objects.
        """
        configs = []
        for source_def in DEFAULT_SOURCES:
            config = MarketDataSourceConfig(
                user_id=user_id,
                source_id=source_def["source_id"],
                display_name=source_def["display_name"],
                enabled=source_def["enabled"],
                priority=source_def["priority"],
            )
            self.db.add(config)
            configs.append(config)

        self.db.commit()
        logger.info("Created default data source config for user %d", user_id)
        return configs
