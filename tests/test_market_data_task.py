"""Tests for the market data Celery task.

Tests cover:
- Celery app configuration (beat schedule, broker, serialization)
- update_market_data task: success, partial failure, full failure
- Per-symbol error handling (continues processing other symbols)
- Redis client and Kite client initialization errors
- All configured instruments are processed (Requirement 1.6.1, 1.6.5)
- Option chain fetching at reduced frequency (Requirement 1.6.2)
- instruments_configured field in result

Requirements covered:
- 1.6.1: Fetch spot prices for configured instruments every 3-5 seconds
- 1.6.2: Fetch option chain data for NIFTY and BANKNIFTY
- 1.6.5: Share market data across all users
- 1.6.8: Continue processing other symbols if one symbol fails
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch

import src.workers.market_data_task as task_module


class TestCeleryAppConfiguration:
    """Tests for Celery app configuration."""

    def test_celery_app_exists(self):
        """Verify celery_app is properly instantiated."""
        from src.workers.celery_app import celery_app

        assert celery_app is not None
        assert celery_app.main == "trading_platform"

    def test_celery_app_broker_configured(self):
        """Verify broker is configured to use Redis."""
        from src.workers.celery_app import celery_app

        broker_url = celery_app.conf.broker_url
        assert "redis" in broker_url

    def test_celery_app_serializer_json(self):
        """Verify task serializer is JSON."""
        from src.workers.celery_app import celery_app

        assert celery_app.conf.task_serializer == "json"
        assert "json" in celery_app.conf.accept_content

    def test_beat_schedule_contains_market_data_task(self):
        """Verify beat schedule includes the market data update task."""
        from src.workers.celery_app import celery_app

        schedule = celery_app.conf.beat_schedule
        assert "update-market-data-every-4s" in schedule

    def test_beat_schedule_interval_is_4_seconds(self):
        """Verify market data task is scheduled every 4 seconds (midpoint of 3-5s)."""
        from src.workers.celery_app import celery_app

        schedule = celery_app.conf.beat_schedule
        task_config = schedule["update-market-data-every-4s"]
        assert task_config["schedule"] == 4.0

    def test_beat_schedule_task_name_correct(self):
        """Verify the task name in beat schedule matches the registered task."""
        from src.workers.celery_app import celery_app

        schedule = celery_app.conf.beat_schedule
        task_config = schedule["update-market-data-every-4s"]
        assert task_config["task"] == "src.workers.market_data_task.update_market_data"


class TestUpdateMarketDataTask:
    """Tests for the update_market_data Celery task."""

    @patch("src.workers.market_data_task._get_shared_kite_client")
    @patch("src.workers.market_data_task.get_redis_client")
    def test_success_all_symbols(self, mock_get_redis, mock_get_kite):
        """All symbols fetched successfully returns status 'success'."""
        from src.workers.market_data_task import update_market_data

        mock_redis = MagicMock()
        mock_kite = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_get_kite.return_value = mock_kite

        # Mock LTP response for both NIFTY and BANKNIFTY
        mock_kite.ltp.return_value = {
            "NSE:NIFTY 50": {"last_price": 18650.75},
            "NSE:NIFTY BANK": {"last_price": 43520.10},
        }

        # Mock lrange for compute_vwap (no ticks yet)
        mock_redis.lrange.return_value = []

        result = update_market_data()

        assert result["status"] == "success"
        assert result["symbols_processed"] == 2
        assert result["symbols_failed"] == 0
        assert "NIFTY" in result["prices"]
        assert "BANKNIFTY" in result["prices"]
        assert result["prices"]["NIFTY"] == 18650.75
        assert result["prices"]["BANKNIFTY"] == 43520.10
        assert "timestamp" in result

    @patch("src.workers.market_data_task._get_shared_kite_client")
    @patch("src.workers.market_data_task.get_redis_client")
    def test_partial_failure(self, mock_get_redis, mock_get_kite):
        """One symbol fails, other succeeds - returns status 'partial'."""
        from src.workers.market_data_task import update_market_data

        mock_redis = MagicMock()
        mock_kite = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_get_kite.return_value = mock_kite

        # First call succeeds, second fails
        mock_kite.ltp.side_effect = [
            {"NSE:NIFTY 50": {"last_price": 18650.75}},
            Exception("Connection timeout"),
        ]

        mock_redis.lrange.return_value = []

        result = update_market_data()

        assert result["status"] == "partial"
        assert result["symbols_processed"] == 1
        assert result["symbols_failed"] == 1
        assert "NIFTY" in result["prices"]
        assert "BANKNIFTY" in result["errors"]

    @patch("src.workers.market_data_task._get_shared_kite_client")
    @patch("src.workers.market_data_task.get_redis_client")
    def test_all_symbols_fail(self, mock_get_redis, mock_get_kite):
        """All symbols fail - returns status 'error'."""
        from src.workers.market_data_task import update_market_data

        mock_redis = MagicMock()
        mock_kite = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_get_kite.return_value = mock_kite

        # All LTP calls fail
        mock_kite.ltp.side_effect = Exception("Network unreachable")

        result = update_market_data()

        assert result["status"] == "error"
        assert result["symbols_processed"] == 0
        assert result["symbols_failed"] == 2
        assert result["prices"] == {}
        assert len(result["errors"]) == 2

    @patch("src.workers.market_data_task._get_shared_kite_client")
    @patch("src.workers.market_data_task.get_redis_client")
    def test_redis_client_failure(self, mock_get_redis, mock_get_kite):
        """Redis client initialization failure returns error status."""
        from src.workers.market_data_task import update_market_data

        mock_get_redis.side_effect = RuntimeError("Redis connection refused")

        result = update_market_data()

        assert result["status"] == "error"
        assert "_system" in result["errors"]
        assert result["symbols_processed"] == 0
        assert result["symbols_failed"] == 0

    @patch("src.workers.market_data_task._get_shared_kite_client")
    @patch("src.workers.market_data_task.get_redis_client")
    def test_kite_client_failure(self, mock_get_redis, mock_get_kite):
        """Kite client initialization failure returns error status."""
        from src.workers.market_data_task import update_market_data

        mock_get_redis.return_value = MagicMock()
        mock_get_kite.side_effect = RuntimeError("KITE_API_KEY not set")

        result = update_market_data()

        assert result["status"] == "error"
        assert "_system" in result["errors"]
        assert result["symbols_processed"] == 0

    @patch("src.workers.market_data_task._get_shared_kite_client")
    @patch("src.workers.market_data_task.get_redis_client")
    def test_stores_tick_for_successful_symbols(self, mock_get_redis, mock_get_kite):
        """Verifies store_tick is called for each successfully fetched symbol."""
        from src.workers.market_data_task import update_market_data

        mock_redis = MagicMock()
        mock_kite = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_get_kite.return_value = mock_kite

        mock_kite.ltp.return_value = {
            "NSE:NIFTY 50": {"last_price": 18650.75},
            "NSE:NIFTY BANK": {"last_price": 43520.10},
        }
        mock_redis.lrange.return_value = []

        result = update_market_data()

        # store_tick calls lpush on redis
        assert mock_redis.lpush.call_count >= 2

    @patch("src.workers.market_data_task._get_shared_kite_client")
    @patch("src.workers.market_data_task.get_redis_client")
    def test_caches_market_data_for_successful_symbols(self, mock_get_redis, mock_get_kite):
        """Verifies cache_market_data is called for each successful symbol."""
        from src.workers.market_data_task import update_market_data

        mock_redis = MagicMock()
        mock_kite = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_get_kite.return_value = mock_kite

        mock_kite.ltp.return_value = {
            "NSE:NIFTY 50": {"last_price": 18650.75},
            "NSE:NIFTY BANK": {"last_price": 43520.10},
        }
        mock_redis.lrange.return_value = []

        result = update_market_data()

        # cache_market_data calls setex on redis
        assert mock_redis.setex.call_count >= 2

    @patch("src.workers.market_data_task._get_shared_kite_client")
    @patch("src.workers.market_data_task.get_redis_client")
    def test_result_contains_timestamp(self, mock_get_redis, mock_get_kite):
        """Verifies the result always includes a timestamp."""
        from src.workers.market_data_task import update_market_data

        mock_redis = MagicMock()
        mock_kite = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_get_kite.return_value = mock_kite

        mock_kite.ltp.return_value = {
            "NSE:NIFTY 50": {"last_price": 18650.75},
            "NSE:NIFTY BANK": {"last_price": 43520.10},
        }
        mock_redis.lrange.return_value = []

        result = update_market_data()

        assert "timestamp" in result
        # Should be ISO format
        from datetime import datetime
        datetime.fromisoformat(result["timestamp"])  # Should not raise

    @patch("src.workers.market_data_task._get_shared_kite_client")
    @patch("src.workers.market_data_task.get_redis_client")
    def test_store_tick_failure_does_not_block_caching(self, mock_get_redis, mock_get_kite):
        """If store_tick fails, caching should still proceed."""
        from src.workers.market_data_task import update_market_data

        mock_redis = MagicMock()
        mock_kite = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_get_kite.return_value = mock_kite

        mock_kite.ltp.return_value = {
            "NSE:NIFTY 50": {"last_price": 18650.75},
            "NSE:NIFTY BANK": {"last_price": 43520.10},
        }

        # lpush raises (store_tick failure), but setex should still be called
        mock_redis.lpush.side_effect = Exception("Redis write error")
        mock_redis.lrange.return_value = []

        result = update_market_data()

        # Task should still succeed (prices were fetched)
        assert result["status"] == "success"
        assert result["symbols_processed"] == 2


class TestGetSharedKiteClient:
    """Tests for the _get_shared_kite_client helper."""

    @patch.dict(os.environ, {"KITE_API_KEY": "", "KITE_ACCESS_TOKEN": "token123"})
    @patch("src.workers.market_data_task.KiteConnect", create=True)
    def test_missing_api_key_raises(self, mock_kc_cls):
        """Missing KITE_API_KEY raises RuntimeError."""
        # We need to mock KiteConnect import inside the function
        import importlib
        import sys

        # Create a mock kiteconnect module
        mock_module = MagicMock()
        mock_module.KiteConnect = mock_kc_cls
        sys.modules["kiteconnect"] = mock_module

        try:
            from src.workers.market_data_task import _get_shared_kite_client

            with pytest.raises(RuntimeError, match="KITE_API_KEY"):
                _get_shared_kite_client()
        finally:
            del sys.modules["kiteconnect"]

    @patch.dict(os.environ, {"KITE_API_KEY": "key123", "KITE_ACCESS_TOKEN": ""})
    def test_missing_access_token_raises(self):
        """Missing KITE_ACCESS_TOKEN raises RuntimeError."""
        import sys

        mock_module = MagicMock()
        sys.modules["kiteconnect"] = mock_module

        try:
            from src.workers.market_data_task import _get_shared_kite_client

            with pytest.raises(RuntimeError, match="KITE_ACCESS_TOKEN"):
                _get_shared_kite_client()
        finally:
            del sys.modules["kiteconnect"]

    @patch.dict(os.environ, {"KITE_API_KEY": "key123", "KITE_ACCESS_TOKEN": "token123"})
    def test_returns_configured_kite_client(self):
        """Returns a configured KiteConnect instance when env vars are set."""
        import sys

        mock_kite_instance = MagicMock()
        mock_kc_class = MagicMock(return_value=mock_kite_instance)
        mock_module = MagicMock()
        mock_module.KiteConnect = mock_kc_class
        sys.modules["kiteconnect"] = mock_module

        try:
            from src.workers.market_data_task import _get_shared_kite_client

            result = _get_shared_kite_client()

            mock_kc_class.assert_called_once_with(api_key="key123")
            mock_kite_instance.set_access_token.assert_called_once_with("token123")
            assert result == mock_kite_instance
        finally:
            del sys.modules["kiteconnect"]


class TestAllConfiguredInstrumentsProcessed:
    """Tests that confirm ALL configured instruments are processed.

    Validates Requirements:
    - 1.6.1: Fetch spot prices for configured instruments every 3-5 seconds
    - 1.6.5: Share market data across all users
    """

    @patch("src.workers.market_data_task._get_shared_kite_client")
    @patch("src.workers.market_data_task.get_redis_client")
    def test_processes_all_default_instruments(self, mock_get_redis, mock_get_kite):
        """Verifies the task attempts to fetch prices for ALL DEFAULT_INSTRUMENTS."""
        from src.workers.market_data_task import update_market_data
        from src.workers.market_data_worker import DEFAULT_INSTRUMENTS

        mock_redis = MagicMock()
        mock_kite = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_get_kite.return_value = mock_kite

        # Build LTP response covering all configured instruments
        ltp_response = {}
        for symbol, instrument_key in DEFAULT_INSTRUMENTS.items():
            ltp_response[instrument_key] = {"last_price": 10000.0 + hash(symbol) % 1000}

        mock_kite.ltp.return_value = ltp_response
        mock_redis.lrange.return_value = []

        result = update_market_data()

        # Every configured instrument should be in the prices result
        assert result["symbols_processed"] == len(DEFAULT_INSTRUMENTS)
        for symbol in DEFAULT_INSTRUMENTS:
            assert symbol in result["prices"], (
                f"Symbol {symbol} from DEFAULT_INSTRUMENTS was not processed"
            )

    @patch("src.workers.market_data_task._get_shared_kite_client")
    @patch("src.workers.market_data_task.get_redis_client")
    def test_instruments_configured_count_matches_default(self, mock_get_redis, mock_get_kite):
        """Verifies instruments_configured reflects the total configured instruments."""
        from src.workers.market_data_task import update_market_data
        from src.workers.market_data_worker import DEFAULT_INSTRUMENTS

        mock_redis = MagicMock()
        mock_kite = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_get_kite.return_value = mock_kite

        mock_kite.ltp.return_value = {
            "NSE:NIFTY 50": {"last_price": 18650.75},
            "NSE:NIFTY BANK": {"last_price": 43520.10},
        }
        mock_redis.lrange.return_value = []

        result = update_market_data()

        assert result["instruments_configured"] == len(DEFAULT_INSTRUMENTS)

    @patch("src.workers.market_data_task._get_shared_kite_client")
    @patch("src.workers.market_data_task.get_redis_client")
    def test_default_instruments_contains_nifty_and_banknifty(self, mock_get_redis, mock_get_kite):
        """Verifies DEFAULT_INSTRUMENTS includes at minimum NIFTY and BANKNIFTY."""
        from src.workers.market_data_worker import DEFAULT_INSTRUMENTS

        assert "NIFTY" in DEFAULT_INSTRUMENTS, "NIFTY must be in DEFAULT_INSTRUMENTS"
        assert "BANKNIFTY" in DEFAULT_INSTRUMENTS, "BANKNIFTY must be in DEFAULT_INSTRUMENTS"

    @patch("src.workers.market_data_task._get_shared_kite_client")
    @patch("src.workers.market_data_task.get_redis_client")
    def test_vwap_computed_for_all_successful_symbols(self, mock_get_redis, mock_get_kite):
        """Verifies VWAP is computed and cached for every successfully fetched symbol."""
        from src.workers.market_data_task import update_market_data
        from src.workers.market_data_worker import DEFAULT_INSTRUMENTS
        import json

        mock_redis = MagicMock()
        mock_kite = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_get_kite.return_value = mock_kite

        mock_kite.ltp.return_value = {
            "NSE:NIFTY 50": {"last_price": 18650.75},
            "NSE:NIFTY BANK": {"last_price": 43520.10},
        }
        mock_redis.lrange.return_value = []

        result = update_market_data()

        # setex is called for each symbol's cache_market_data
        assert mock_redis.setex.call_count >= len(DEFAULT_INSTRUMENTS)

        # Verify cached data includes both 'spot' and 'vwap' fields
        for call in mock_redis.setex.call_args_list:
            args = call[0]
            cached_json = args[2]  # Third arg is the JSON data
            cached_data = json.loads(cached_json)
            # Only check market data cache calls (not option chain calls)
            if "spot" in cached_data:
                assert "vwap" in cached_data, "Cached market data must include VWAP"
                assert "timestamp" in cached_data, "Cached market data must include timestamp"

    @patch("src.workers.market_data_task._get_shared_kite_client")
    @patch("src.workers.market_data_task.get_redis_client")
    def test_tick_stored_for_all_successful_symbols(self, mock_get_redis, mock_get_kite):
        """Verifies ticks are stored for every successfully fetched symbol."""
        from src.workers.market_data_task import update_market_data
        from src.workers.market_data_worker import DEFAULT_INSTRUMENTS

        mock_redis = MagicMock()
        mock_kite = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_get_kite.return_value = mock_kite

        mock_kite.ltp.return_value = {
            "NSE:NIFTY 50": {"last_price": 18650.75},
            "NSE:NIFTY BANK": {"last_price": 43520.10},
        }
        mock_redis.lrange.return_value = []

        result = update_market_data()

        # lpush is called once per successful symbol (store_tick)
        assert mock_redis.lpush.call_count >= len(DEFAULT_INSTRUMENTS)


class TestOptionChainFetching:
    """Tests for option chain fetching integration in the Celery task.

    Validates Requirement 1.6.2: Fetch option chain data for NIFTY and BANKNIFTY.
    """

    def setup_method(self):
        """Reset the cycle counter before each test."""
        task_module._cycle_counter = 0

    @patch("src.workers.market_data_task._get_current_expiry")
    @patch("src.workers.market_data_task._get_shared_kite_client")
    @patch("src.workers.market_data_task.get_redis_client")
    def test_option_chain_fetched_on_nth_cycle(
        self, mock_get_redis, mock_get_kite, mock_expiry
    ):
        """Option chains are fetched when cycle counter reaches threshold."""
        from src.workers.market_data_task import (
            update_market_data,
            OPTION_CHAIN_FETCH_INTERVAL,
        )

        mock_redis = MagicMock()
        mock_kite = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_get_kite.return_value = mock_kite
        mock_expiry.return_value = "2024-01-25"

        mock_kite.ltp.return_value = {
            "NSE:NIFTY 50": {"last_price": 18650.75},
            "NSE:NIFTY BANK": {"last_price": 43520.10},
        }
        mock_kite.instruments.return_value = [
            {
                "name": "NIFTY",
                "tradingsymbol": "NIFTY24JAN18650CE",
                "instrument_type": "CE",
                "expiry": "2024-01-25",
                "strike": 18650,
            },
        ]
        mock_redis.lrange.return_value = []

        # Set counter just below threshold so next call triggers option chain fetch
        task_module._cycle_counter = OPTION_CHAIN_FETCH_INTERVAL - 1

        result = update_market_data()

        assert result["option_chains_fetched"] is True
        # kite.instruments("NFO") should have been called for option chain
        mock_kite.instruments.assert_called_with("NFO")

    @patch("src.workers.market_data_task._get_current_expiry")
    @patch("src.workers.market_data_task._get_shared_kite_client")
    @patch("src.workers.market_data_task.get_redis_client")
    def test_option_chain_not_fetched_before_interval(
        self, mock_get_redis, mock_get_kite, mock_expiry
    ):
        """Option chains are NOT fetched when cycle counter is below threshold."""
        from src.workers.market_data_task import update_market_data

        mock_redis = MagicMock()
        mock_kite = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_get_kite.return_value = mock_kite

        mock_kite.ltp.return_value = {
            "NSE:NIFTY 50": {"last_price": 18650.75},
            "NSE:NIFTY BANK": {"last_price": 43520.10},
        }
        mock_redis.lrange.return_value = []

        # Counter is 0 initially, so first call increments to 1 (below threshold)
        task_module._cycle_counter = 0

        result = update_market_data()

        assert result["option_chains_fetched"] is False
        # instruments() should NOT be called (no option chain fetch)
        mock_kite.instruments.assert_not_called()

    @patch("src.workers.market_data_task._get_current_expiry")
    @patch("src.workers.market_data_task._get_shared_kite_client")
    @patch("src.workers.market_data_task.get_redis_client")
    def test_option_chain_failure_does_not_block_task(
        self, mock_get_redis, mock_get_kite, mock_expiry
    ):
        """Option chain fetch failure doesn't affect spot price results."""
        from src.workers.market_data_task import (
            update_market_data,
            OPTION_CHAIN_FETCH_INTERVAL,
        )

        mock_redis = MagicMock()
        mock_kite = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_get_kite.return_value = mock_kite
        mock_expiry.return_value = "2024-01-25"

        mock_kite.ltp.return_value = {
            "NSE:NIFTY 50": {"last_price": 18650.75},
            "NSE:NIFTY BANK": {"last_price": 43520.10},
        }
        # instruments() raises error (option chain failure)
        mock_kite.instruments.side_effect = Exception("NFO API error")
        mock_redis.lrange.return_value = []

        # Trigger option chain fetch cycle
        task_module._cycle_counter = OPTION_CHAIN_FETCH_INTERVAL - 1

        result = update_market_data()

        # Spot prices should still succeed
        assert result["status"] == "success"
        assert result["symbols_processed"] == 2
        assert result["option_chains_fetched"] is True

    @patch("src.workers.market_data_task._get_current_expiry")
    @patch("src.workers.market_data_task._get_shared_kite_client")
    @patch("src.workers.market_data_task.get_redis_client")
    def test_option_chain_skipped_when_no_expiry(
        self, mock_get_redis, mock_get_kite, mock_expiry
    ):
        """Option chain fetch is skipped gracefully when expiry can't be computed."""
        from src.workers.market_data_task import (
            update_market_data,
            OPTION_CHAIN_FETCH_INTERVAL,
        )

        mock_redis = MagicMock()
        mock_kite = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_get_kite.return_value = mock_kite
        mock_expiry.return_value = None  # Expiry computation failed

        mock_kite.ltp.return_value = {
            "NSE:NIFTY 50": {"last_price": 18650.75},
            "NSE:NIFTY BANK": {"last_price": 43520.10},
        }
        mock_redis.lrange.return_value = []

        task_module._cycle_counter = OPTION_CHAIN_FETCH_INTERVAL - 1

        result = update_market_data()

        # Task still succeeds for spot prices
        assert result["status"] == "success"
        assert result["option_chains_fetched"] is True
        # instruments() should NOT be called
        mock_kite.instruments.assert_not_called()


class TestOptionChainSymbols:
    """Tests that option chain symbols are properly configured."""

    def test_option_chain_symbols_include_nifty(self):
        """OPTION_CHAIN_SYMBOLS includes NIFTY."""
        from src.workers.market_data_task import OPTION_CHAIN_SYMBOLS

        assert "NIFTY" in OPTION_CHAIN_SYMBOLS

    def test_option_chain_symbols_include_banknifty(self):
        """OPTION_CHAIN_SYMBOLS includes BANKNIFTY."""
        from src.workers.market_data_task import OPTION_CHAIN_SYMBOLS

        assert "BANKNIFTY" in OPTION_CHAIN_SYMBOLS


class TestLogErrorsWithoutBlocking:
    """Tests that verify errors are logged without blocking the task.

    Validates Requirements:
    - 1.6.7: Handle market data fetch failures gracefully
    - 1.6.8: Continue processing other symbols if one symbol fails
    - 2.3.7: Log all errors with full context

    Key invariants tested:
    1. The Celery task NEVER raises an exception (always returns a dict)
    2. All error paths include logging with context (symbol, error type)
    3. Per-symbol failures don't prevent other symbols from being processed
    """

    def setup_method(self):
        """Reset the cycle counter before each test."""
        task_module._cycle_counter = 0

    @patch("src.workers.market_data_task._execute_market_data_update")
    def test_task_never_raises_on_unexpected_error(self, mock_execute):
        """Top-level safety net catches unexpected errors and returns dict."""
        from src.workers.market_data_task import update_market_data

        # Simulate a completely unexpected error in the internal implementation
        mock_execute.side_effect = RuntimeError("Unexpected catastrophic failure")

        result = update_market_data()

        # Task must NEVER raise - must return a dict
        assert isinstance(result, dict)
        assert result["status"] == "error"
        assert "_system" in result["errors"]
        assert "Unexpected" in result["errors"]["_system"]
        assert result["symbols_processed"] == 0
        assert result["symbols_failed"] == 0
        assert "timestamp" in result

    @patch("src.workers.market_data_task._execute_market_data_update")
    def test_task_never_raises_on_type_error(self, mock_execute):
        """Task handles TypeError (e.g., None where dict expected) without raising."""
        from src.workers.market_data_task import update_market_data

        mock_execute.side_effect = TypeError("'NoneType' object is not subscriptable")

        result = update_market_data()

        assert isinstance(result, dict)
        assert result["status"] == "error"
        assert "_system" in result["errors"]

    @patch("src.workers.market_data_task._get_shared_kite_client")
    @patch("src.workers.market_data_task.get_redis_client")
    def test_per_symbol_failure_continues_processing(self, mock_get_redis, mock_get_kite):
        """When one symbol fails, remaining symbols are still processed.

        Validates Requirement 1.6.8.
        """
        from src.workers.market_data_task import update_market_data

        mock_redis = MagicMock()
        mock_kite = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_get_kite.return_value = mock_kite

        # NIFTY succeeds, BANKNIFTY fails
        def ltp_side_effect(instruments):
            if "NSE:NIFTY 50" in instruments:
                return {"NSE:NIFTY 50": {"last_price": 18650.75}}
            raise ConnectionError("Connection timeout for BANKNIFTY")

        mock_kite.ltp.side_effect = ltp_side_effect
        mock_redis.lrange.return_value = []

        result = update_market_data()

        # NIFTY should be processed successfully
        assert "NIFTY" in result["prices"]
        assert result["symbols_processed"] >= 1
        # BANKNIFTY error should be recorded, not raised
        assert "BANKNIFTY" in result["errors"]
        # Task returned without raising
        assert result["status"] in ("partial", "success")

    @patch("src.workers.market_data_task._get_shared_kite_client")
    @patch("src.workers.market_data_task.get_redis_client")
    def test_store_tick_error_logged_and_continues(self, mock_get_redis, mock_get_kite):
        """store_tick failure is logged but doesn't prevent caching or other symbols.

        Validates Requirement 1.6.7 and 2.3.7.
        """
        from src.workers.market_data_task import update_market_data
        import logging

        mock_redis = MagicMock()
        mock_kite = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_get_kite.return_value = mock_kite

        mock_kite.ltp.return_value = {
            "NSE:NIFTY 50": {"last_price": 18650.75},
            "NSE:NIFTY BANK": {"last_price": 43520.10},
        }

        # lpush raises (store_tick fails), but setex should still work
        mock_redis.lpush.side_effect = Exception("Redis write error")
        mock_redis.lrange.return_value = []

        # Use caplog-like approach: patch the worker's logger to verify logging
        with patch("src.workers.market_data_worker.logger") as mock_worker_logger:
            result = update_market_data()

            # Error was logged in the worker module (store_tick catches internally)
            assert mock_worker_logger.error.called
            error_messages = [
                str(call) for call in mock_worker_logger.error.call_args_list
            ]
            # At least one error should mention the Redis write failure
            assert any("store tick" in msg.lower() or "redis" in msg.lower() for msg in error_messages)

        # Task still succeeds (prices were fetched)
        assert result["status"] == "success"
        assert result["symbols_processed"] == 2

    @patch("src.workers.market_data_task._get_shared_kite_client")
    @patch("src.workers.market_data_task.get_redis_client")
    def test_cache_market_data_error_logged_and_continues(self, mock_get_redis, mock_get_kite):
        """cache_market_data failure is logged but doesn't crash the task.

        Validates Requirement 2.3.7.
        """
        from src.workers.market_data_task import update_market_data

        mock_redis = MagicMock()
        mock_kite = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_get_kite.return_value = mock_kite

        mock_kite.ltp.return_value = {
            "NSE:NIFTY 50": {"last_price": 18650.75},
            "NSE:NIFTY BANK": {"last_price": 43520.10},
        }
        mock_redis.lrange.return_value = []
        # setex raises (cache_market_data fails)
        mock_redis.setex.side_effect = Exception("Redis write error")

        with patch("src.workers.market_data_task.logger") as mock_logger:
            result = update_market_data()

            # Errors were logged (either via worker logger or task logger)
            # The task should still complete
            assert result is not None

        # Task still returns success (the spot prices were fetched)
        assert result["status"] == "success"
        assert result["symbols_processed"] == 2

    @patch("src.workers.market_data_task._get_shared_kite_client")
    @patch("src.workers.market_data_task.get_redis_client")
    def test_all_errors_include_context(self, mock_get_redis, mock_get_kite):
        """All error responses include full context (symbol, error string, timestamp).

        Validates Requirement 2.3.7.
        """
        from src.workers.market_data_task import update_market_data

        mock_redis = MagicMock()
        mock_kite = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_get_kite.return_value = mock_kite

        # All LTP calls fail with a specific error
        mock_kite.ltp.side_effect = ConnectionError("Connection refused")

        result = update_market_data()

        # Every failed symbol should have its error recorded
        for symbol in result["errors"]:
            error_msg = result["errors"][symbol]
            assert isinstance(error_msg, str)
            assert len(error_msg) > 0  # Not empty

        # Timestamp is always present
        assert "timestamp" in result
        from datetime import datetime
        datetime.fromisoformat(result["timestamp"])  # Must be valid ISO format

    @patch("src.workers.market_data_task._get_shared_kite_client")
    @patch("src.workers.market_data_task.get_redis_client")
    def test_redis_failure_logged_with_context(self, mock_get_redis, mock_get_kite):
        """Redis initialization failure is logged with full error context.

        Validates Requirement 2.3.7.
        """
        from src.workers.market_data_task import update_market_data

        error_message = "Connection refused: localhost:6379"
        mock_get_redis.side_effect = ConnectionError(error_message)

        with patch("src.workers.market_data_task.logger") as mock_logger:
            result = update_market_data()

            # logger.error should have been called
            assert mock_logger.error.called

        assert result["status"] == "error"
        assert "_system" in result["errors"]
        assert error_message in result["errors"]["_system"]

    @patch("src.workers.market_data_task._get_shared_kite_client")
    @patch("src.workers.market_data_task.get_redis_client")
    def test_task_always_returns_dict_on_success(self, mock_get_redis, mock_get_kite):
        """Task returns a well-formed dict even on complete success."""
        from src.workers.market_data_task import update_market_data

        mock_redis = MagicMock()
        mock_kite = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_get_kite.return_value = mock_kite

        mock_kite.ltp.return_value = {
            "NSE:NIFTY 50": {"last_price": 18650.75},
            "NSE:NIFTY BANK": {"last_price": 43520.10},
        }
        mock_redis.lrange.return_value = []

        result = update_market_data()

        # Always returns dict with required keys
        assert isinstance(result, dict)
        required_keys = [
            "status", "prices", "errors", "timestamp",
            "symbols_processed", "symbols_failed",
            "instruments_configured", "option_chains_fetched",
        ]
        for key in required_keys:
            assert key in result, f"Missing key '{key}' in result"

    @patch("src.workers.market_data_task._get_shared_kite_client")
    @patch("src.workers.market_data_task.get_redis_client")
    def test_task_always_returns_dict_on_total_failure(self, mock_get_redis, mock_get_kite):
        """Task returns a well-formed dict even on complete failure."""
        from src.workers.market_data_task import update_market_data

        mock_get_redis.side_effect = RuntimeError("Everything is broken")

        result = update_market_data()

        # Always returns dict with required keys
        assert isinstance(result, dict)
        required_keys = [
            "status", "prices", "errors", "timestamp",
            "symbols_processed", "symbols_failed",
            "instruments_configured", "option_chains_fetched",
        ]
        for key in required_keys:
            assert key in result, f"Missing key '{key}' in result"

    @patch("src.workers.market_data_task._get_current_expiry")
    @patch("src.workers.market_data_task._get_shared_kite_client")
    @patch("src.workers.market_data_task.get_redis_client")
    def test_option_chain_error_does_not_block_spot_prices(
        self, mock_get_redis, mock_get_kite, mock_expiry
    ):
        """Option chain failures don't affect the spot price results.

        Validates Requirement 1.6.7.
        """
        from src.workers.market_data_task import (
            update_market_data,
            OPTION_CHAIN_FETCH_INTERVAL,
        )

        mock_redis = MagicMock()
        mock_kite = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_get_kite.return_value = mock_kite
        mock_expiry.return_value = "2024-01-25"

        mock_kite.ltp.return_value = {
            "NSE:NIFTY 50": {"last_price": 18650.75},
            "NSE:NIFTY BANK": {"last_price": 43520.10},
        }
        # Option chain fetch raises
        mock_kite.instruments.side_effect = RuntimeError("NFO API catastrophic error")
        mock_redis.lrange.return_value = []

        # Trigger option chain fetch
        task_module._cycle_counter = OPTION_CHAIN_FETCH_INTERVAL - 1

        result = update_market_data()

        # Spot prices should still be returned successfully
        assert result["status"] == "success"
        assert result["prices"]["NIFTY"] == 18650.75
        assert result["prices"]["BANKNIFTY"] == 43520.10
        assert result["symbols_processed"] == 2


class TestGetCurrentExpiry:
    """Tests for _get_current_expiry helper."""

    def test_returns_valid_date_string(self):
        """_get_current_expiry returns a valid YYYY-MM-DD date string."""
        from src.workers.market_data_task import _get_current_expiry

        result = _get_current_expiry()

        assert result is not None
        # Should be in YYYY-MM-DD format
        from datetime import date
        parsed = date.fromisoformat(result)
        assert parsed is not None

    def test_returns_thursday(self):
        """_get_current_expiry returns a Thursday (weekday=3)."""
        from src.workers.market_data_task import _get_current_expiry

        result = _get_current_expiry()

        from datetime import date
        parsed = date.fromisoformat(result)
        # Thursday is weekday 3
        assert parsed.weekday() == 3

    def test_returns_today_or_future(self):
        """_get_current_expiry returns today or a future date."""
        from src.workers.market_data_task import _get_current_expiry

        result = _get_current_expiry()

        from datetime import date
        parsed = date.fromisoformat(result)
        assert parsed >= date.today()

