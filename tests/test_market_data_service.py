"""Tests for src/services/market_data_service.py

Tests:
- get_user_sources returns sorted sources from DB
- get_user_sources creates defaults when no config exists
- update_user_sources persists valid configuration
- update_user_sources rejects all-disabled config
- is_market_open returns True during market hours (IST weekdays 9:15-15:30)
- is_market_open returns False outside market hours and on weekends
- fetch_live_indices returns cached data when available
- fetch_live_indices fetches and caches on cache miss
- fetch_live_indices falls back to next source on failure
- fetch_live_indices raises DataUnavailableError when all sources fail

Implements Requirements: 6.1, 6.2, 6.5, 6.6, 6.7, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime
from unittest.mock import MagicMock, patch, call
from zoneinfo import ZoneInfo

import pytest

from src.services.market_data_service import (
    MarketDataService,
    DataSourceConfig,
    DataSourceValidationError,
    DataUnavailableError,
    IndexData,
    LiveMarketResponse,
    DEFAULT_SOURCES,
    IST,
)
from src.database.models.market_data_config import MarketDataSourceConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    """Create a mock SQLAlchemy session."""
    return MagicMock()


@pytest.fixture
def mock_redis():
    """Create a mock RedisClient."""
    return MagicMock()


@pytest.fixture
def service(mock_db, mock_redis):
    """Create a MarketDataService instance with mocked dependencies."""
    return MarketDataService(db=mock_db, redis_client=mock_redis)


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------


class TestMarketDataServiceInit:
    """Tests for MarketDataService initialization."""

    def test_raises_on_none_db(self, mock_redis):
        """Should raise ValueError when db is None."""
        with pytest.raises(ValueError, match="db cannot be None"):
            MarketDataService(db=None, redis_client=mock_redis)

    def test_raises_on_none_redis(self, mock_db):
        """Should raise ValueError when redis_client is None."""
        with pytest.raises(ValueError, match="redis_client cannot be None"):
            MarketDataService(db=mock_db, redis_client=None)

    def test_successful_init(self, mock_db, mock_redis):
        """Should initialize with valid dependencies."""
        svc = MarketDataService(db=mock_db, redis_client=mock_redis)
        assert svc.db is mock_db
        assert svc.redis is mock_redis
        assert svc.kite_factory is None
        assert svc.dhan_factory is None


# ---------------------------------------------------------------------------
# get_user_sources
# ---------------------------------------------------------------------------


class TestGetUserSources:
    """Tests for get_user_sources method."""

    def test_returns_sorted_sources_from_db(self, service, mock_db):
        """Should return sources from DB sorted by priority."""
        # Set up mock ORM objects
        config1 = MagicMock(spec=MarketDataSourceConfig)
        config1.source_id = "yfinance"
        config1.display_name = "Yahoo Finance"
        config1.enabled = True
        config1.priority = 1

        config2 = MagicMock(spec=MarketDataSourceConfig)
        config2.source_id = "nsepy"
        config2.display_name = "NSEpy"
        config2.enabled = True
        config2.priority = 0

        # Mock the query chain
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [config2, config1]  # Already sorted

        result = service.get_user_sources(user_id=1)

        assert len(result) == 2
        assert result[0].source_id == "nsepy"
        assert result[0].priority == 0
        assert result[1].source_id == "yfinance"
        assert result[1].priority == 1

    def test_creates_defaults_when_no_config_exists(self, service, mock_db):
        """Should create default sources when user has no configuration."""
        # First query returns empty (no existing config)
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []

        # Mock add to capture added objects
        added_configs = []

        def capture_add(config):
            added_configs.append(config)

        mock_db.add.side_effect = capture_add

        result = service.get_user_sources(user_id=42)

        # Should have created 4 default sources
        assert mock_db.add.call_count == 4
        assert mock_db.commit.call_count == 1
        assert len(result) == 4

        # Verify default source IDs are present
        source_ids = [r.source_id for r in result]
        assert "nsepy" in source_ids
        assert "yfinance" in source_ids
        assert "kite_historical" in source_ids
        assert "dhan_market" in source_ids

    def test_returns_data_source_config_models(self, service, mock_db):
        """Should return proper DataSourceConfig pydantic models."""
        config = MagicMock(spec=MarketDataSourceConfig)
        config.source_id = "nsepy"
        config.display_name = "NSEpy"
        config.enabled = True
        config.priority = 0

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [config]

        result = service.get_user_sources(user_id=1)

        assert len(result) == 1
        assert isinstance(result[0], DataSourceConfig)
        assert result[0].source_id == "nsepy"
        assert result[0].display_name == "NSEpy"
        assert result[0].enabled is True
        assert result[0].priority == 0


# ---------------------------------------------------------------------------
# update_user_sources
# ---------------------------------------------------------------------------


class TestUpdateUserSources:
    """Tests for update_user_sources method."""

    def test_persists_valid_configuration(self, service, mock_db):
        """Should persist sources when at least one is enabled."""
        sources = [
            DataSourceConfig(
                source_id="nsepy",
                display_name="NSEpy",
                enabled=True,
                priority=0,
            ),
            DataSourceConfig(
                source_id="yfinance",
                display_name="Yahoo Finance",
                enabled=False,
                priority=1,
            ),
        ]

        # Mock the delete query
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.delete.return_value = 0

        service.update_user_sources(user_id=1, sources=sources)

        # Should delete existing and add new configs
        mock_query.delete.assert_called_once()
        assert mock_db.add.call_count == 2
        mock_db.commit.assert_called_once()

    def test_rejects_all_disabled_sources(self, service, mock_db):
        """Should raise DataSourceValidationError when all sources are disabled."""
        sources = [
            DataSourceConfig(
                source_id="nsepy",
                display_name="NSEpy",
                enabled=False,
                priority=0,
            ),
            DataSourceConfig(
                source_id="yfinance",
                display_name="Yahoo Finance",
                enabled=False,
                priority=1,
            ),
        ]

        with pytest.raises(
            DataSourceValidationError,
            match="At least one data source must be enabled",
        ):
            service.update_user_sources(user_id=1, sources=sources)

        # Should not have modified DB
        mock_db.commit.assert_not_called()

    def test_rejects_empty_source_list(self, service, mock_db):
        """Should raise DataSourceValidationError when source list is empty."""
        with pytest.raises(
            DataSourceValidationError,
            match="At least one data source must be enabled",
        ):
            service.update_user_sources(user_id=1, sources=[])

        mock_db.commit.assert_not_called()

    def test_accepts_single_enabled_source(self, service, mock_db):
        """Should succeed with a single enabled source."""
        sources = [
            DataSourceConfig(
                source_id="nsepy",
                display_name="NSEpy",
                enabled=True,
                priority=0,
            ),
        ]

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.delete.return_value = 0

        service.update_user_sources(user_id=1, sources=sources)

        mock_db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# is_market_open / _is_market_open_at
# ---------------------------------------------------------------------------


class TestIsMarketOpen:
    """Tests for market hours detection."""

    def test_market_open_during_trading_hours(self, service):
        """Should return True during weekday trading hours."""
        # Wednesday, 10:00 AM IST
        dt = datetime(2024, 1, 10, 10, 0, 0, tzinfo=IST)
        assert service._is_market_open_at(dt) is True

    def test_market_open_at_exact_open_time(self, service):
        """Should return True at exactly 9:15 AM IST on a weekday."""
        # Monday, 9:15 AM IST
        dt = datetime(2024, 1, 8, 9, 15, 0, tzinfo=IST)
        assert service._is_market_open_at(dt) is True

    def test_market_open_at_exact_close_time(self, service):
        """Should return True at exactly 3:30 PM IST on a weekday."""
        # Tuesday, 3:30 PM IST
        dt = datetime(2024, 1, 9, 15, 30, 0, tzinfo=IST)
        assert service._is_market_open_at(dt) is True

    def test_market_closed_before_open(self, service):
        """Should return False before 9:15 AM IST on a weekday."""
        # Thursday, 9:14 AM IST
        dt = datetime(2024, 1, 11, 9, 14, 0, tzinfo=IST)
        assert service._is_market_open_at(dt) is False

    def test_market_closed_after_close(self, service):
        """Should return False after 3:30 PM IST on a weekday."""
        # Friday, 3:31 PM IST
        dt = datetime(2024, 1, 12, 15, 31, 0, tzinfo=IST)
        assert service._is_market_open_at(dt) is False

    def test_market_closed_on_saturday(self, service):
        """Should return False on Saturday even during trading hours."""
        # Saturday, 10:00 AM IST
        dt = datetime(2024, 1, 13, 10, 0, 0, tzinfo=IST)
        assert service._is_market_open_at(dt) is False

    def test_market_closed_on_sunday(self, service):
        """Should return False on Sunday even during trading hours."""
        # Sunday, 12:00 PM IST
        dt = datetime(2024, 1, 14, 12, 0, 0, tzinfo=IST)
        assert service._is_market_open_at(dt) is False

    def test_market_closed_at_midnight(self, service):
        """Should return False at midnight on a weekday."""
        # Wednesday, midnight IST
        dt = datetime(2024, 1, 10, 0, 0, 0, tzinfo=IST)
        assert service._is_market_open_at(dt) is False

    def test_is_market_open_uses_current_time(self, service):
        """is_market_open() should use current IST time."""
        # Patch datetime.now to return a known market-open time
        with patch(
            "src.services.market_data_service.datetime"
        ) as mock_datetime:
            mock_now = datetime(2024, 1, 10, 10, 0, 0, tzinfo=IST)
            mock_datetime.now.return_value = mock_now
            # Also ensure replace works properly on the mock
            mock_datetime.side_effect = lambda *args, **kw: datetime(
                *args, **kw
            )
            result = service.is_market_open()
            mock_datetime.now.assert_called_once_with(IST)
            assert result is True


# ---------------------------------------------------------------------------
# Default sources
# ---------------------------------------------------------------------------


class TestDefaultSources:
    """Tests for default source configuration."""

    def test_default_sources_has_four_entries(self):
        """DEFAULT_SOURCES should contain exactly 4 data sources."""
        assert len(DEFAULT_SOURCES) == 4

    def test_default_source_ids(self):
        """DEFAULT_SOURCES should contain the expected source IDs."""
        source_ids = [s["source_id"] for s in DEFAULT_SOURCES]
        assert "nsepy" in source_ids
        assert "yfinance" in source_ids
        assert "kite_historical" in source_ids
        assert "dhan_market" in source_ids

    def test_default_sources_have_at_least_one_enabled(self):
        """DEFAULT_SOURCES must have at least one enabled source."""
        enabled = [s for s in DEFAULT_SOURCES if s["enabled"]]
        assert len(enabled) >= 1

    def test_default_priorities_are_sequential(self):
        """DEFAULT_SOURCES should have sequential priority values."""
        priorities = sorted(s["priority"] for s in DEFAULT_SOURCES)
        assert priorities == list(range(len(DEFAULT_SOURCES)))



# ---------------------------------------------------------------------------
# fetch_live_indices
# ---------------------------------------------------------------------------


class TestFetchLiveIndices:
    """Tests for fetch_live_indices method."""

    @pytest.fixture
    def sample_indices(self):
        """Sample index data for testing."""
        return [
            IndexData(
                symbol="NIFTY 50",
                value=22000.50,
                change_points=150.25,
                change_percent=0.69,
                last_updated="2024-01-10T10:00:00+05:30",
            ),
            IndexData(
                symbol="SENSEX",
                value=72500.00,
                change_points=400.00,
                change_percent=0.55,
                last_updated="2024-01-10T10:00:00+05:30",
            ),
        ]

    @pytest.fixture
    def service_with_sources(self, mock_db, mock_redis):
        """Create service with mocked get_user_sources returning enabled sources."""
        svc = MarketDataService(db=mock_db, redis_client=mock_redis)
        return svc

    def test_returns_cached_data_on_cache_hit(self, mock_db, mock_redis, sample_indices):
        """Should return cached LiveMarketResponse when Redis has cached data."""
        cached_response = LiveMarketResponse(
            indices=sample_indices,
            market_open=True,
            data_source="nsepy",
            last_successful_fetch="2024-01-10T10:00:00+05:30",
        )
        mock_redis.get.return_value = cached_response.model_dump_json()

        service = MarketDataService(db=mock_db, redis_client=mock_redis)
        result = service.fetch_live_indices(user_id=1)

        assert result.data_source == "nsepy"
        assert result.market_open is True
        assert len(result.indices) == 2
        assert result.indices[0].symbol == "NIFTY 50"
        mock_redis.get.assert_called_once_with("live_indices:1")

    def test_fetches_from_source_on_cache_miss(self, mock_db, mock_redis, sample_indices):
        """Should fetch from data source when cache is empty."""
        mock_redis.get.return_value = None  # Cache miss

        service = MarketDataService(db=mock_db, redis_client=mock_redis)

        # Mock get_user_sources to return enabled sources
        with patch.object(service, "get_user_sources") as mock_sources, \
             patch.object(service, "_fetch_from_source") as mock_fetch, \
             patch.object(service, "is_market_open", return_value=True):
            mock_sources.return_value = [
                DataSourceConfig(
                    source_id="nsepy", display_name="NSEpy", enabled=True, priority=0
                ),
            ]
            mock_fetch.return_value = sample_indices

            result = service.fetch_live_indices(user_id=1)

            assert result.data_source == "nsepy"
            assert result.market_open is True
            assert len(result.indices) == 2
            mock_fetch.assert_called_once_with("nsepy", 1)

    def test_caches_result_with_30s_ttl(self, mock_db, mock_redis, sample_indices):
        """Should cache successful fetch result with 30s TTL."""
        mock_redis.get.return_value = None  # Cache miss

        service = MarketDataService(db=mock_db, redis_client=mock_redis)

        with patch.object(service, "get_user_sources") as mock_sources, \
             patch.object(service, "_fetch_from_source") as mock_fetch, \
             patch.object(service, "is_market_open", return_value=True):
            mock_sources.return_value = [
                DataSourceConfig(
                    source_id="yfinance", display_name="Yahoo Finance", enabled=True, priority=0
                ),
            ]
            mock_fetch.return_value = sample_indices

            service.fetch_live_indices(user_id=42)

            # Verify cache was set with TTL=30
            mock_redis.set.assert_called_once()
            call_args = mock_redis.set.call_args
            assert call_args[1]["ttl"] == 30 or call_args[0][2] == 30 if len(call_args[0]) > 2 else call_args[1].get("ttl") == 30

    def test_falls_back_to_next_source_on_failure(self, mock_db, mock_redis, sample_indices):
        """Should try next source when first source fails."""
        mock_redis.get.return_value = None  # Cache miss

        service = MarketDataService(db=mock_db, redis_client=mock_redis)

        with patch.object(service, "get_user_sources") as mock_sources, \
             patch.object(service, "_fetch_from_source") as mock_fetch, \
             patch.object(service, "is_market_open", return_value=True):
            mock_sources.return_value = [
                DataSourceConfig(
                    source_id="nsepy", display_name="NSEpy", enabled=True, priority=0
                ),
                DataSourceConfig(
                    source_id="yfinance", display_name="Yahoo Finance", enabled=True, priority=1
                ),
            ]
            # First call fails, second succeeds
            mock_fetch.side_effect = [
                ConnectionError("nsepy timeout"),
                sample_indices,
            ]

            result = service.fetch_live_indices(user_id=1)

            assert result.data_source == "yfinance"
            assert mock_fetch.call_count == 2

    def test_raises_data_unavailable_when_all_fail(self, mock_db, mock_redis):
        """Should raise DataUnavailableError when all sources fail."""
        mock_redis.get.return_value = None  # Cache miss

        service = MarketDataService(db=mock_db, redis_client=mock_redis)

        with patch.object(service, "get_user_sources") as mock_sources, \
             patch.object(service, "_fetch_from_source") as mock_fetch:
            mock_sources.return_value = [
                DataSourceConfig(
                    source_id="nsepy", display_name="NSEpy", enabled=True, priority=0
                ),
                DataSourceConfig(
                    source_id="yfinance", display_name="Yahoo Finance", enabled=True, priority=1
                ),
            ]
            mock_fetch.side_effect = ConnectionError("failed")

            with pytest.raises(DataUnavailableError, match="All 2 sources failed"):
                service.fetch_live_indices(user_id=1)

    def test_skips_disabled_sources(self, mock_db, mock_redis, sample_indices):
        """Should only try enabled sources in priority order."""
        mock_redis.get.return_value = None  # Cache miss

        service = MarketDataService(db=mock_db, redis_client=mock_redis)

        with patch.object(service, "get_user_sources") as mock_sources, \
             patch.object(service, "_fetch_from_source") as mock_fetch, \
             patch.object(service, "is_market_open", return_value=False):
            mock_sources.return_value = [
                DataSourceConfig(
                    source_id="nsepy", display_name="NSEpy", enabled=False, priority=0
                ),
                DataSourceConfig(
                    source_id="yfinance", display_name="Yahoo Finance", enabled=True, priority=1
                ),
            ]
            mock_fetch.return_value = sample_indices

            result = service.fetch_live_indices(user_id=1)

            # Should only call yfinance, not nsepy
            mock_fetch.assert_called_once_with("yfinance", 1)
            assert result.data_source == "yfinance"

    def test_market_open_flag_reflects_current_state(self, mock_db, mock_redis, sample_indices):
        """Should set market_open based on is_market_open()."""
        mock_redis.get.return_value = None

        service = MarketDataService(db=mock_db, redis_client=mock_redis)

        with patch.object(service, "get_user_sources") as mock_sources, \
             patch.object(service, "_fetch_from_source") as mock_fetch, \
             patch.object(service, "is_market_open", return_value=False):
            mock_sources.return_value = [
                DataSourceConfig(
                    source_id="nsepy", display_name="NSEpy", enabled=True, priority=0
                ),
            ]
            mock_fetch.return_value = sample_indices

            result = service.fetch_live_indices(user_id=1)

            assert result.market_open is False

    def test_handles_invalid_cache_gracefully(self, mock_db, mock_redis, sample_indices):
        """Should handle corrupt cache data and fetch fresh."""
        mock_redis.get.return_value = "invalid json{{{}"

        service = MarketDataService(db=mock_db, redis_client=mock_redis)

        with patch.object(service, "get_user_sources") as mock_sources, \
             patch.object(service, "_fetch_from_source") as mock_fetch, \
             patch.object(service, "is_market_open", return_value=True):
            mock_sources.return_value = [
                DataSourceConfig(
                    source_id="nsepy", display_name="NSEpy", enabled=True, priority=0
                ),
            ]
            mock_fetch.return_value = sample_indices

            result = service.fetch_live_indices(user_id=1)

            # Should still succeed by fetching fresh data
            assert result.data_source == "nsepy"
            assert len(result.indices) == 2

    def test_raises_when_no_sources_enabled(self, mock_db, mock_redis):
        """Should raise DataUnavailableError when no sources are enabled."""
        mock_redis.get.return_value = None

        service = MarketDataService(db=mock_db, redis_client=mock_redis)

        with patch.object(service, "get_user_sources") as mock_sources:
            mock_sources.return_value = [
                DataSourceConfig(
                    source_id="nsepy", display_name="NSEpy", enabled=False, priority=0
                ),
            ]

            with pytest.raises(DataUnavailableError, match="No data sources are enabled"):
                service.fetch_live_indices(user_id=1)


# ---------------------------------------------------------------------------
# _fetch_from_source
# ---------------------------------------------------------------------------


class TestFetchFromSource:
    """Tests for _fetch_from_source dispatch method."""

    def test_dispatches_to_nsepy(self, mock_db, mock_redis):
        """Should call _fetch_nsepy for nsepy source_id."""
        service = MarketDataService(db=mock_db, redis_client=mock_redis)

        with patch.object(service, "_fetch_nsepy") as mock_adapter:
            mock_adapter.return_value = []
            service._fetch_from_source("nsepy", user_id=1)
            mock_adapter.assert_called_once()

    def test_dispatches_to_yfinance(self, mock_db, mock_redis):
        """Should call _fetch_yfinance for yfinance source_id."""
        service = MarketDataService(db=mock_db, redis_client=mock_redis)

        with patch.object(service, "_fetch_yfinance") as mock_adapter:
            mock_adapter.return_value = []
            service._fetch_from_source("yfinance", user_id=1)
            mock_adapter.assert_called_once()

    def test_dispatches_to_kite(self, mock_db, mock_redis):
        """Should call _fetch_kite with user_id for kite_historical source_id."""
        service = MarketDataService(db=mock_db, redis_client=mock_redis)

        with patch.object(service, "_fetch_kite") as mock_adapter:
            mock_adapter.return_value = []
            service._fetch_from_source("kite_historical", user_id=42)
            mock_adapter.assert_called_once_with(42)

    def test_dispatches_to_dhan(self, mock_db, mock_redis):
        """Should call _fetch_dhan with user_id for dhan_market source_id."""
        service = MarketDataService(db=mock_db, redis_client=mock_redis)

        with patch.object(service, "_fetch_dhan") as mock_adapter:
            mock_adapter.return_value = []
            service._fetch_from_source("dhan_market", user_id=7)
            mock_adapter.assert_called_once_with(7)

    def test_raises_on_unknown_source(self, mock_db, mock_redis):
        """Should raise ValueError for unknown source_id."""
        service = MarketDataService(db=mock_db, redis_client=mock_redis)

        with pytest.raises(ValueError, match="Unknown data source"):
            service._fetch_from_source("unknown_source", user_id=1)


# ---------------------------------------------------------------------------
# Adapter methods
# ---------------------------------------------------------------------------


class TestAdapters:
    """Tests for individual adapter methods."""

    def test_fetch_nsepy_raises_import_error(self, mock_db, mock_redis):
        """Should raise ImportError when nsetools is not available."""
        service = MarketDataService(db=mock_db, redis_client=mock_redis)

        with patch.dict("sys.modules", {"nsetools": None}):
            with pytest.raises(ImportError):
                service._fetch_nsepy()

    def test_fetch_yfinance_raises_import_error(self, mock_db, mock_redis):
        """Should raise ImportError when yfinance is not available."""
        service = MarketDataService(db=mock_db, redis_client=mock_redis)

        with patch.dict("sys.modules", {"yfinance": None}):
            with pytest.raises(ImportError):
                service._fetch_yfinance()

    def test_fetch_kite_raises_when_no_factory(self, mock_db, mock_redis):
        """Should raise ConnectionError when kite_factory is None."""
        service = MarketDataService(db=mock_db, redis_client=mock_redis, kite_factory=None)

        with pytest.raises(ConnectionError, match="Kite factory not configured"):
            service._fetch_kite(user_id=1)

    def test_fetch_dhan_raises_when_no_factory(self, mock_db, mock_redis):
        """Should raise ConnectionError when dhan_factory is None."""
        service = MarketDataService(db=mock_db, redis_client=mock_redis, dhan_factory=None)

        with pytest.raises(ConnectionError, match="Dhan factory not configured"):
            service._fetch_dhan(user_id=1)

    def test_fetch_kite_raises_when_client_none(self, mock_db, mock_redis):
        """Should raise ConnectionError when kite_factory returns None."""
        kite_factory = MagicMock(return_value=None)
        service = MarketDataService(
            db=mock_db, redis_client=mock_redis, kite_factory=kite_factory
        )

        with pytest.raises(ConnectionError, match="Kite client not available"):
            service._fetch_kite(user_id=1)

    def test_fetch_dhan_raises_when_client_none(self, mock_db, mock_redis):
        """Should raise ConnectionError when dhan_factory returns None."""
        dhan_factory = MagicMock(return_value=None)
        service = MarketDataService(
            db=mock_db, redis_client=mock_redis, dhan_factory=dhan_factory
        )

        with pytest.raises(ConnectionError, match="Dhan client not available"):
            service._fetch_dhan(user_id=1)

    def test_fetch_kite_returns_index_data(self, mock_db, mock_redis):
        """Should return IndexData from Kite quotes."""
        mock_kite = MagicMock()
        mock_kite.quote.return_value = {
            "NSE:NIFTY 50": {
                "last_price": 22000.50,
                "ohlc": {"close": 21900.00},
            },
            "NSE:NIFTY BANK": {
                "last_price": 47500.00,
                "ohlc": {"close": 47200.00},
            },
            "NSE:NIFTY IT": {
                "last_price": 35000.00,
                "ohlc": {"close": 34800.00},
            },
        }
        kite_factory = MagicMock(return_value=mock_kite)
        service = MarketDataService(
            db=mock_db, redis_client=mock_redis, kite_factory=kite_factory
        )

        result = service._fetch_kite(user_id=1)

        assert len(result) >= 3
        symbols = [idx.symbol for idx in result]
        assert "NIFTY 50" in symbols
        assert "BANK NIFTY" in symbols
        assert "NIFTY IT" in symbols
        # Verify change calculation
        nifty = next(idx for idx in result if idx.symbol == "NIFTY 50")
        assert nifty.value == 22000.50
        assert nifty.change_points == 100.50

    def test_fetch_dhan_returns_index_data(self, mock_db, mock_redis):
        """Should return IndexData from Dhan market quotes."""
        mock_dhan = MagicMock()
        mock_dhan.get_market_quote.return_value = {
            "status": "success",
            "data": {
                "last_price": 22000.50,
                "prev_close": 21900.00,
            },
        }
        dhan_factory = MagicMock(return_value=mock_dhan)
        service = MarketDataService(
            db=mock_db, redis_client=mock_redis, dhan_factory=dhan_factory
        )

        result = service._fetch_dhan(user_id=1)

        assert len(result) >= 1
        assert result[0].value == 22000.50
        assert result[0].change_points == 100.50
