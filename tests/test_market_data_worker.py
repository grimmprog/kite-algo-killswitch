"""Tests for the Market Data Worker.

Tests cover:
- MarketDataWorker.fetch_spot_price(): fetching LTP for configured instruments
- MarketDataWorker.fetch_all_spot_prices(): batch fetching with per-symbol error handling
- MarketDataWorker.fetch_all_option_chains(): batch fetching with per-symbol error handling
- Error classification (classify_error): transient vs permanent error categorization
- Error handling for API failures, missing data, invalid symbols
- Input validation

Requirements covered:
- 1.6.1: Fetch spot prices for configured instruments every 3-5 seconds
- 1.6.7: Handle market data fetch failures gracefully
- 1.6.8: Continue processing other symbols if one symbol fails
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch

from src.workers.market_data_worker import (
    MarketDataWorker,
    MarketDataError,
    ErrorCategory,
    classify_error,
    DEFAULT_INSTRUMENTS,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def mock_kite():
    """Create a mock KiteConnect client."""
    return MagicMock()


@pytest.fixture
def mock_redis():
    """Create a mock RedisClient."""
    return MagicMock()


@pytest.fixture
def worker(mock_kite, mock_redis):
    """Create a MarketDataWorker with mocked dependencies."""
    return MarketDataWorker(
        kite_client=mock_kite,
        redis_client=mock_redis,
    )


@pytest.fixture
def worker_custom_instruments(mock_kite, mock_redis):
    """Create a MarketDataWorker with custom instrument mapping."""
    instruments = {
        "NIFTY": "NSE:NIFTY 50",
        "BANKNIFTY": "NSE:NIFTY BANK",
        "RELIANCE": "NSE:RELIANCE",
    }
    return MarketDataWorker(
        kite_client=mock_kite,
        redis_client=mock_redis,
        instruments=instruments,
    )


# ============================================================
# Initialization Tests
# ============================================================


class TestMarketDataWorkerInit:
    """Tests for MarketDataWorker initialization."""

    def test_init_with_valid_params(self, mock_kite, mock_redis):
        """Test successful initialization with valid parameters."""
        worker = MarketDataWorker(kite_client=mock_kite, redis_client=mock_redis)
        assert worker.kite is mock_kite
        assert worker.redis is mock_redis
        assert worker.instruments == DEFAULT_INSTRUMENTS

    def test_init_with_custom_instruments(self, mock_kite, mock_redis):
        """Test initialization with custom instrument mapping."""
        custom = {"SENSEX": "BSE:SENSEX"}
        worker = MarketDataWorker(
            kite_client=mock_kite,
            redis_client=mock_redis,
            instruments=custom,
        )
        assert worker.instruments == custom

    def test_init_none_kite_client_raises(self, mock_redis):
        """Test that None kite_client raises ValueError."""
        with pytest.raises(ValueError, match="kite_client cannot be None"):
            MarketDataWorker(kite_client=None, redis_client=mock_redis)

    def test_init_none_redis_client_raises(self, mock_kite):
        """Test that None redis_client raises ValueError."""
        with pytest.raises(ValueError, match="redis_client cannot be None"):
            MarketDataWorker(kite_client=mock_kite, redis_client=None)


# ============================================================
# fetch_spot_price Tests
# ============================================================


class TestFetchSpotPrice:
    """Tests for MarketDataWorker.fetch_spot_price()."""

    def test_fetch_nifty_spot_price(self, worker, mock_kite):
        """Test fetching NIFTY spot price returns correct value."""
        mock_kite.ltp.return_value = {
            "NSE:NIFTY 50": {"instrument_token": 256265, "last_price": 18650.75},
        }

        price = worker.fetch_spot_price("NIFTY")

        assert price == 18650.75
        mock_kite.ltp.assert_called_once_with(["NSE:NIFTY 50"])

    def test_fetch_banknifty_spot_price(self, worker, mock_kite):
        """Test fetching BANKNIFTY spot price returns correct value."""
        mock_kite.ltp.return_value = {
            "NSE:NIFTY BANK": {"instrument_token": 260105, "last_price": 43520.10},
        }

        price = worker.fetch_spot_price("BANKNIFTY")

        assert price == 43520.10
        mock_kite.ltp.assert_called_once_with(["NSE:NIFTY BANK"])

    def test_fetch_spot_price_case_insensitive(self, worker, mock_kite):
        """Test that symbol lookup is case-insensitive."""
        mock_kite.ltp.return_value = {
            "NSE:NIFTY 50": {"instrument_token": 256265, "last_price": 18700.0},
        }

        price = worker.fetch_spot_price("nifty")
        assert price == 18700.0

    def test_fetch_spot_price_strips_whitespace(self, worker, mock_kite):
        """Test that symbol with whitespace is handled correctly."""
        mock_kite.ltp.return_value = {
            "NSE:NIFTY 50": {"instrument_token": 256265, "last_price": 18700.0},
        }

        price = worker.fetch_spot_price("  NIFTY  ")
        assert price == 18700.0

    def test_fetch_spot_price_returns_float(self, worker, mock_kite):
        """Test that return value is always a float."""
        mock_kite.ltp.return_value = {
            "NSE:NIFTY 50": {"instrument_token": 256265, "last_price": 18650},
        }

        price = worker.fetch_spot_price("NIFTY")
        assert isinstance(price, float)

    def test_fetch_spot_price_custom_instrument(self, worker_custom_instruments, mock_kite):
        """Test fetching spot price for a custom instrument."""
        mock_kite.ltp.return_value = {
            "NSE:RELIANCE": {"instrument_token": 738561, "last_price": 2450.30},
        }

        price = worker_custom_instruments.fetch_spot_price("RELIANCE")
        assert price == 2450.30

    # --- Error Cases ---

    def test_fetch_spot_price_empty_symbol_raises(self, worker):
        """Test that empty symbol raises ValueError."""
        with pytest.raises(ValueError, match="Symbol cannot be empty"):
            worker.fetch_spot_price("")

    def test_fetch_spot_price_whitespace_only_raises(self, worker):
        """Test that whitespace-only symbol raises ValueError."""
        with pytest.raises(ValueError, match="Symbol cannot be empty"):
            worker.fetch_spot_price("   ")

    def test_fetch_spot_price_unknown_symbol_raises(self, worker):
        """Test that unknown symbol raises ValueError."""
        with pytest.raises(ValueError, match="not found in configured instruments"):
            worker.fetch_spot_price("INVALID_SYMBOL")

    def test_fetch_spot_price_api_error_raises(self, worker, mock_kite):
        """Test that API error raises MarketDataError."""
        mock_kite.ltp.side_effect = Exception("NetworkException: Connection timeout")

        with pytest.raises(MarketDataError, match="Failed to fetch spot price"):
            worker.fetch_spot_price("NIFTY")

    def test_fetch_spot_price_empty_response_raises(self, worker, mock_kite):
        """Test that empty API response raises MarketDataError."""
        mock_kite.ltp.return_value = {}

        with pytest.raises(MarketDataError, match="No data returned"):
            worker.fetch_spot_price("NIFTY")

    def test_fetch_spot_price_none_response_raises(self, worker, mock_kite):
        """Test that None API response raises MarketDataError."""
        mock_kite.ltp.return_value = None

        with pytest.raises(MarketDataError, match="No data returned"):
            worker.fetch_spot_price("NIFTY")

    def test_fetch_spot_price_missing_last_price_raises(self, worker, mock_kite):
        """Test that missing last_price field raises MarketDataError."""
        mock_kite.ltp.return_value = {
            "NSE:NIFTY 50": {"instrument_token": 256265},
        }

        with pytest.raises(MarketDataError, match="No last_price"):
            worker.fetch_spot_price("NIFTY")

    def test_fetch_spot_price_preserves_original_exception(self, worker, mock_kite):
        """Test that original exception is preserved as __cause__."""
        original = Exception("Network error")
        mock_kite.ltp.side_effect = original

        with pytest.raises(MarketDataError) as exc_info:
            worker.fetch_spot_price("NIFTY")

        assert exc_info.value.__cause__ is original


# ============================================================
# fetch_option_chain Tests
# ============================================================


class TestFetchOptionChain:
    """Tests for MarketDataWorker.fetch_option_chain().

    Requirements covered:
    - 1.6.2: Fetch option chain data for NIFTY and BANKNIFTY
    - 1.6.7: Handle market data fetch failures gracefully
    """

    @pytest.fixture
    def nifty_instruments(self):
        """Sample NFO instruments for NIFTY."""
        return [
            {
                "name": "NIFTY",
                "tradingsymbol": "NIFTY2412518000CE",
                "instrument_type": "CE",
                "strike": 18000.0,
                "expiry": "2024-01-25",
                "exchange": "NFO",
            },
            {
                "name": "NIFTY",
                "tradingsymbol": "NIFTY2412518000PE",
                "instrument_type": "PE",
                "strike": 18000.0,
                "expiry": "2024-01-25",
                "exchange": "NFO",
            },
            {
                "name": "NIFTY",
                "tradingsymbol": "NIFTY2412518500CE",
                "instrument_type": "CE",
                "strike": 18500.0,
                "expiry": "2024-01-25",
                "exchange": "NFO",
            },
            {
                "name": "NIFTY",
                "tradingsymbol": "NIFTY2412518500PE",
                "instrument_type": "PE",
                "strike": 18500.0,
                "expiry": "2024-01-25",
                "exchange": "NFO",
            },
            # Different expiry - should be filtered out
            {
                "name": "NIFTY",
                "tradingsymbol": "NIFTY2420118000CE",
                "instrument_type": "CE",
                "strike": 18000.0,
                "expiry": "2024-02-01",
                "exchange": "NFO",
            },
            # BANKNIFTY - should be filtered out for NIFTY query
            {
                "name": "BANKNIFTY",
                "tradingsymbol": "BANKNIFTY2412543000CE",
                "instrument_type": "CE",
                "strike": 43000.0,
                "expiry": "2024-01-25",
                "exchange": "NFO",
            },
            # FUT instrument - should be filtered out
            {
                "name": "NIFTY",
                "tradingsymbol": "NIFTY24JANFUT",
                "instrument_type": "FUT",
                "strike": 0.0,
                "expiry": "2024-01-25",
                "exchange": "NFO",
            },
        ]

    @pytest.fixture
    def nifty_ltp_response(self):
        """Sample LTP response for NIFTY option chain."""
        return {
            "NFO:NIFTY2412518000CE": {"last_price": 650.50},
            "NFO:NIFTY2412518000PE": {"last_price": 120.25},
            "NFO:NIFTY2412518500CE": {"last_price": 320.75},
            "NFO:NIFTY2412518500PE": {"last_price": 280.10},
        }

    def test_fetch_nifty_option_chain(
        self, worker, mock_kite, nifty_instruments, nifty_ltp_response
    ):
        """Test fetching NIFTY option chain returns correct data."""
        mock_kite.instruments.return_value = nifty_instruments
        mock_kite.ltp.return_value = nifty_ltp_response

        result = worker.fetch_option_chain("NIFTY", "2024-01-25")

        assert len(result) == 4
        mock_kite.instruments.assert_called_once_with("NFO")

    def test_fetch_option_chain_returns_sorted_by_strike(
        self, worker, mock_kite, nifty_instruments, nifty_ltp_response
    ):
        """Test that results are sorted by strike price then option type."""
        mock_kite.instruments.return_value = nifty_instruments
        mock_kite.ltp.return_value = nifty_ltp_response

        result = worker.fetch_option_chain("NIFTY", "2024-01-25")

        # Should be sorted: 18000 CE, 18000 PE, 18500 CE, 18500 PE
        assert result[0]["strike"] == 18000.0
        assert result[0]["option_type"] == "CE"
        assert result[1]["strike"] == 18000.0
        assert result[1]["option_type"] == "PE"
        assert result[2]["strike"] == 18500.0
        assert result[2]["option_type"] == "CE"
        assert result[3]["strike"] == 18500.0
        assert result[3]["option_type"] == "PE"

    def test_fetch_option_chain_includes_ltp(
        self, worker, mock_kite, nifty_instruments, nifty_ltp_response
    ):
        """Test that each entry includes LTP from the quote API."""
        mock_kite.instruments.return_value = nifty_instruments
        mock_kite.ltp.return_value = nifty_ltp_response

        result = worker.fetch_option_chain("NIFTY", "2024-01-25")

        assert result[0]["ltp"] == 650.50
        assert result[1]["ltp"] == 120.25
        assert result[2]["ltp"] == 320.75
        assert result[3]["ltp"] == 280.10

    def test_fetch_option_chain_entry_structure(
        self, worker, mock_kite, nifty_instruments, nifty_ltp_response
    ):
        """Test that each entry has the required fields."""
        mock_kite.instruments.return_value = nifty_instruments
        mock_kite.ltp.return_value = nifty_ltp_response

        result = worker.fetch_option_chain("NIFTY", "2024-01-25")

        for entry in result:
            assert "strike" in entry
            assert "option_type" in entry
            assert "tradingsymbol" in entry
            assert "ltp" in entry
            assert "expiry" in entry
            assert isinstance(entry["strike"], float)
            assert isinstance(entry["ltp"], float)
            assert entry["option_type"] in ("CE", "PE")

    def test_fetch_banknifty_option_chain(self, worker, mock_kite):
        """Test fetching BANKNIFTY option chain."""
        instruments = [
            {
                "name": "BANKNIFTY",
                "tradingsymbol": "BANKNIFTY2412543000CE",
                "instrument_type": "CE",
                "strike": 43000.0,
                "expiry": "2024-01-25",
                "exchange": "NFO",
            },
            {
                "name": "BANKNIFTY",
                "tradingsymbol": "BANKNIFTY2412543000PE",
                "instrument_type": "PE",
                "strike": 43000.0,
                "expiry": "2024-01-25",
                "exchange": "NFO",
            },
        ]
        mock_kite.instruments.return_value = instruments
        mock_kite.ltp.return_value = {
            "NFO:BANKNIFTY2412543000CE": {"last_price": 450.0},
            "NFO:BANKNIFTY2412543000PE": {"last_price": 380.0},
        }

        result = worker.fetch_option_chain("BANKNIFTY", "2024-01-25")

        assert len(result) == 2
        assert result[0]["tradingsymbol"] == "BANKNIFTY2412543000CE"
        assert result[1]["tradingsymbol"] == "BANKNIFTY2412543000PE"

    def test_fetch_option_chain_case_insensitive(
        self, worker, mock_kite, nifty_instruments, nifty_ltp_response
    ):
        """Test that symbol lookup is case-insensitive."""
        mock_kite.instruments.return_value = nifty_instruments
        mock_kite.ltp.return_value = nifty_ltp_response

        result = worker.fetch_option_chain("nifty", "2024-01-25")
        assert len(result) == 4

    def test_fetch_option_chain_strips_whitespace(
        self, worker, mock_kite, nifty_instruments, nifty_ltp_response
    ):
        """Test that symbol and expiry whitespace is handled."""
        mock_kite.instruments.return_value = nifty_instruments
        mock_kite.ltp.return_value = nifty_ltp_response

        result = worker.fetch_option_chain("  NIFTY  ", "  2024-01-25  ")
        assert len(result) == 4

    def test_fetch_option_chain_filters_by_expiry(
        self, worker, mock_kite, nifty_instruments
    ):
        """Test that only matching expiry contracts are returned."""
        mock_kite.instruments.return_value = nifty_instruments
        mock_kite.ltp.return_value = {
            "NFO:NIFTY2420118000CE": {"last_price": 700.0},
        }

        result = worker.fetch_option_chain("NIFTY", "2024-02-01")

        assert len(result) == 1
        assert result[0]["expiry"] == "2024-02-01"

    def test_fetch_option_chain_ltp_missing_defaults_zero(
        self, worker, mock_kite, nifty_instruments
    ):
        """Test that missing LTP defaults to 0.0."""
        mock_kite.instruments.return_value = nifty_instruments
        # Return empty LTP response
        mock_kite.ltp.return_value = {}

        result = worker.fetch_option_chain("NIFTY", "2024-01-25")

        for entry in result:
            assert entry["ltp"] == 0.0

    # --- Error Cases ---

    def test_fetch_option_chain_empty_symbol_raises(self, worker):
        """Test that empty symbol raises ValueError."""
        with pytest.raises(ValueError, match="Symbol cannot be empty"):
            worker.fetch_option_chain("", "2024-01-25")

    def test_fetch_option_chain_whitespace_symbol_raises(self, worker):
        """Test that whitespace-only symbol raises ValueError."""
        with pytest.raises(ValueError, match="Symbol cannot be empty"):
            worker.fetch_option_chain("   ", "2024-01-25")

    def test_fetch_option_chain_empty_expiry_raises(self, worker):
        """Test that empty expiry raises ValueError."""
        with pytest.raises(ValueError, match="Expiry cannot be empty"):
            worker.fetch_option_chain("NIFTY", "")

    def test_fetch_option_chain_whitespace_expiry_raises(self, worker):
        """Test that whitespace-only expiry raises ValueError."""
        with pytest.raises(ValueError, match="Expiry cannot be empty"):
            worker.fetch_option_chain("NIFTY", "   ")

    def test_fetch_option_chain_unsupported_symbol_raises(self, worker):
        """Test that unsupported symbol raises ValueError."""
        with pytest.raises(ValueError, match="not supported for option chain"):
            worker.fetch_option_chain("RELIANCE", "2024-01-25")

    def test_fetch_option_chain_instruments_api_error(self, worker, mock_kite):
        """Test that instruments API error raises MarketDataError."""
        mock_kite.instruments.side_effect = Exception("Connection timeout")

        with pytest.raises(MarketDataError, match="Failed to fetch instruments"):
            worker.fetch_option_chain("NIFTY", "2024-01-25")

    def test_fetch_option_chain_empty_instruments_raises(self, worker, mock_kite):
        """Test that empty instruments list raises MarketDataError."""
        mock_kite.instruments.return_value = []

        with pytest.raises(MarketDataError, match="No instruments returned"):
            worker.fetch_option_chain("NIFTY", "2024-01-25")

    def test_fetch_option_chain_no_matching_contracts_raises(self, worker, mock_kite):
        """Test that no matching contracts raises MarketDataError."""
        # Only BANKNIFTY instruments, no NIFTY
        mock_kite.instruments.return_value = [
            {
                "name": "BANKNIFTY",
                "tradingsymbol": "BANKNIFTY2412543000CE",
                "instrument_type": "CE",
                "strike": 43000.0,
                "expiry": "2024-01-25",
                "exchange": "NFO",
            },
        ]

        with pytest.raises(MarketDataError, match="No option contracts found"):
            worker.fetch_option_chain("NIFTY", "2024-01-25")

    def test_fetch_option_chain_ltp_api_error(self, worker, mock_kite, nifty_instruments):
        """Test that LTP API error raises MarketDataError."""
        mock_kite.instruments.return_value = nifty_instruments
        mock_kite.ltp.side_effect = Exception("Rate limit exceeded")

        with pytest.raises(MarketDataError, match="Failed to fetch option chain LTP"):
            worker.fetch_option_chain("NIFTY", "2024-01-25")

    def test_fetch_option_chain_preserves_original_exception(
        self, worker, mock_kite
    ):
        """Test that original exception is preserved as __cause__."""
        original = Exception("Network failure")
        mock_kite.instruments.side_effect = original

        with pytest.raises(MarketDataError) as exc_info:
            worker.fetch_option_chain("NIFTY", "2024-01-25")

        assert exc_info.value.__cause__ is original

    def test_fetch_option_chain_ltp_preserves_original_exception(
        self, worker, mock_kite, nifty_instruments
    ):
        """Test that LTP exception is preserved as __cause__."""
        original = Exception("Rate limit")
        mock_kite.instruments.return_value = nifty_instruments
        mock_kite.ltp.side_effect = original

        with pytest.raises(MarketDataError) as exc_info:
            worker.fetch_option_chain("NIFTY", "2024-01-25")

        assert exc_info.value.__cause__ is original


# ============================================================
# classify_error Tests
# ============================================================


class TestClassifyError:
    """Tests for the classify_error function.

    Requirements covered:
    - 1.6.7: Handle market data fetch failures gracefully
    """

    # --- Transient errors ---

    def test_timeout_error_is_transient(self):
        """Test that TimeoutError is classified as transient."""
        assert classify_error(TimeoutError("connection timed out")) == ErrorCategory.TRANSIENT

    def test_connection_error_is_transient(self):
        """Test that ConnectionError is classified as transient."""
        assert classify_error(ConnectionError("connection refused")) == ErrorCategory.TRANSIENT

    def test_os_error_is_transient(self):
        """Test that OSError is classified as transient."""
        assert classify_error(OSError("network unreachable")) == ErrorCategory.TRANSIENT

    def test_network_exception_type_is_transient(self):
        """Test that Kite NetworkException (by name) is transient."""

        class NetworkException(Exception):
            pass

        assert classify_error(NetworkException("timeout")) == ErrorCategory.TRANSIENT

    def test_data_exception_type_is_transient(self):
        """Test that Kite DataException (by name) is transient."""

        class DataException(Exception):
            pass

        assert classify_error(DataException("data error")) == ErrorCategory.TRANSIENT

    def test_rate_limit_message_is_transient(self):
        """Test that 'rate limit' in message is classified as transient."""
        assert classify_error(Exception("rate limit exceeded")) == ErrorCategory.TRANSIENT

    def test_429_message_is_transient(self):
        """Test that HTTP 429 in message is transient."""
        assert classify_error(Exception("HTTP 429 Too Many Requests")) == ErrorCategory.TRANSIENT

    def test_503_message_is_transient(self):
        """Test that HTTP 503 in message is transient."""
        assert classify_error(Exception("503 Service Unavailable")) == ErrorCategory.TRANSIENT

    def test_connection_refused_message_is_transient(self):
        """Test that 'connection refused' in message is transient."""
        assert classify_error(Exception("connection refused")) == ErrorCategory.TRANSIENT

    # --- Permanent errors ---

    def test_token_exception_type_is_permanent(self):
        """Test that Kite TokenException (by name) is permanent."""

        class TokenException(Exception):
            pass

        assert classify_error(TokenException("invalid token")) == ErrorCategory.PERMANENT

    def test_permission_exception_type_is_permanent(self):
        """Test that Kite PermissionException (by name) is permanent."""

        class PermissionException(Exception):
            pass

        assert classify_error(PermissionException("not allowed")) == ErrorCategory.PERMANENT

    def test_input_exception_type_is_permanent(self):
        """Test that Kite InputException (by name) is permanent."""

        class InputException(Exception):
            pass

        assert classify_error(InputException("bad input")) == ErrorCategory.PERMANENT

    def test_invalid_token_message_is_permanent(self):
        """Test that 'invalid token' in message is permanent."""
        assert classify_error(Exception("invalid token provided")) == ErrorCategory.PERMANENT

    def test_unauthorized_message_is_permanent(self):
        """Test that 'unauthorized' in message is permanent."""
        assert classify_error(Exception("401 unauthorized")) == ErrorCategory.PERMANENT

    def test_forbidden_message_is_permanent(self):
        """Test that 'forbidden' in message is permanent."""
        assert classify_error(Exception("403 forbidden")) == ErrorCategory.PERMANENT

    # --- Default behavior ---

    def test_unknown_exception_defaults_to_transient(self):
        """Test that unknown exceptions default to transient (safer for retries)."""
        assert classify_error(Exception("something unknown happened")) == ErrorCategory.TRANSIENT


# ============================================================
# MarketDataError Tests
# ============================================================


class TestMarketDataErrorAttributes:
    """Tests for MarketDataError enhanced attributes."""

    def test_default_category_is_transient(self):
        """Test that default category is transient."""
        err = MarketDataError("some error")
        assert err.category == ErrorCategory.TRANSIENT

    def test_custom_category(self):
        """Test that category can be set to permanent."""
        err = MarketDataError("bad input", category=ErrorCategory.PERMANENT)
        assert err.category == ErrorCategory.PERMANENT

    def test_symbol_attribute(self):
        """Test that symbol attribute is stored."""
        err = MarketDataError("failed", symbol="NIFTY")
        assert err.symbol == "NIFTY"

    def test_symbol_default_is_none(self):
        """Test that symbol defaults to None."""
        err = MarketDataError("failed")
        assert err.symbol is None

    def test_message_preserved(self):
        """Test that message is preserved."""
        err = MarketDataError("some message")
        assert str(err) == "some message"


# ============================================================
# fetch_all_spot_prices Tests
# ============================================================


class TestFetchAllSpotPrices:
    """Tests for MarketDataWorker.fetch_all_spot_prices().

    Requirements covered:
    - 1.6.7: Handle market data fetch failures gracefully
    - 1.6.8: Continue processing other symbols if one symbol fails
    """

    def test_all_symbols_succeed(self, worker, mock_kite):
        """Test that all prices are returned when all fetches succeed."""
        mock_kite.ltp.side_effect = [
            {"NSE:NIFTY 50": {"last_price": 18650.75}},
            {"NSE:NIFTY BANK": {"last_price": 43520.10}},
        ]

        result = worker.fetch_all_spot_prices()

        assert result["prices"] == {"NIFTY": 18650.75, "BANKNIFTY": 43520.10}
        assert result["errors"] == {}

    def test_one_symbol_fails_others_continue(self, worker, mock_kite):
        """Test that if one symbol fails, others still succeed (Req 1.6.8)."""
        mock_kite.ltp.side_effect = [
            Exception("Connection timeout"),  # NIFTY fails
            {"NSE:NIFTY BANK": {"last_price": 43520.10}},  # BANKNIFTY succeeds
        ]

        result = worker.fetch_all_spot_prices()

        assert "BANKNIFTY" in result["prices"]
        assert result["prices"]["BANKNIFTY"] == 43520.10
        assert "NIFTY" in result["errors"]
        assert "category" in result["errors"]["NIFTY"]

    def test_all_symbols_fail_returns_empty_prices(self, worker, mock_kite):
        """Test that if all symbols fail, empty prices with all errors returned."""
        mock_kite.ltp.side_effect = Exception("Connection timeout")

        result = worker.fetch_all_spot_prices()

        assert result["prices"] == {}
        assert len(result["errors"]) == 2
        assert "NIFTY" in result["errors"]
        assert "BANKNIFTY" in result["errors"]

    def test_error_includes_category(self, worker, mock_kite):
        """Test that errors include the error category."""
        mock_kite.ltp.side_effect = [
            Exception("Connection timeout"),
            {"NSE:NIFTY BANK": {"last_price": 43520.10}},
        ]

        result = worker.fetch_all_spot_prices()

        assert result["errors"]["NIFTY"]["category"] == "transient"

    def test_permanent_error_categorized(self, worker, mock_kite):
        """Test that permanent errors are correctly categorized."""

        class TokenException(Exception):
            pass

        mock_kite.ltp.side_effect = [
            TokenException("invalid token"),
            {"NSE:NIFTY BANK": {"last_price": 43520.10}},
        ]

        result = worker.fetch_all_spot_prices()

        assert result["errors"]["NIFTY"]["category"] == "permanent"

    def test_does_not_crash_on_unexpected_exception(self, worker, mock_kite):
        """Test that unexpected exceptions are caught and don't crash worker."""
        mock_kite.ltp.side_effect = [
            RuntimeError("unexpected internal error"),
            {"NSE:NIFTY BANK": {"last_price": 43520.10}},
        ]

        # Should not raise
        result = worker.fetch_all_spot_prices()

        assert "NIFTY" in result["errors"]
        assert "BANKNIFTY" in result["prices"]

    def test_custom_instruments_all_fetched(self, mock_kite, mock_redis):
        """Test that custom instruments are all fetched."""
        instruments = {
            "NIFTY": "NSE:NIFTY 50",
            "BANKNIFTY": "NSE:NIFTY BANK",
            "RELIANCE": "NSE:RELIANCE",
        }
        worker = MarketDataWorker(
            kite_client=mock_kite, redis_client=mock_redis, instruments=instruments
        )
        mock_kite.ltp.side_effect = [
            {"NSE:NIFTY 50": {"last_price": 18650.0}},
            {"NSE:NIFTY BANK": {"last_price": 43500.0}},
            {"NSE:RELIANCE": {"last_price": 2450.0}},
        ]

        result = worker.fetch_all_spot_prices()

        assert len(result["prices"]) == 3
        assert result["errors"] == {}


# ============================================================
# fetch_all_option_chains Tests
# ============================================================


class TestFetchAllOptionChains:
    """Tests for MarketDataWorker.fetch_all_option_chains().

    Requirements covered:
    - 1.6.7: Handle market data fetch failures gracefully
    - 1.6.8: Continue processing other symbols if one symbol fails
    """

    @pytest.fixture
    def nifty_instruments(self):
        """Sample NFO instruments for NIFTY."""
        return [
            {
                "name": "NIFTY",
                "tradingsymbol": "NIFTY2412518000CE",
                "instrument_type": "CE",
                "strike": 18000.0,
                "expiry": "2024-01-25",
                "exchange": "NFO",
            },
        ]

    @pytest.fixture
    def banknifty_instruments(self):
        """Sample NFO instruments for BANKNIFTY."""
        return [
            {
                "name": "BANKNIFTY",
                "tradingsymbol": "BANKNIFTY2412543000CE",
                "instrument_type": "CE",
                "strike": 43000.0,
                "expiry": "2024-01-25",
                "exchange": "NFO",
            },
        ]

    def test_all_symbols_succeed(
        self, worker, mock_kite, nifty_instruments, banknifty_instruments
    ):
        """Test fetching option chains for all default symbols."""
        all_instruments = nifty_instruments + banknifty_instruments
        mock_kite.instruments.return_value = all_instruments
        mock_kite.ltp.side_effect = [
            {"NFO:NIFTY2412518000CE": {"last_price": 650.0}},
            {"NFO:BANKNIFTY2412543000CE": {"last_price": 450.0}},
        ]

        result = worker.fetch_all_option_chains("2024-01-25")

        assert "NIFTY" in result["chains"]
        assert "BANKNIFTY" in result["chains"]
        assert result["errors"] == {}

    def test_one_symbol_fails_others_continue(self, worker, mock_kite):
        """Test that if one symbol fails, others still return (Req 1.6.8)."""
        # NIFTY instruments call succeeds but returns only BANKNIFTY contracts
        banknifty_instruments = [
            {
                "name": "BANKNIFTY",
                "tradingsymbol": "BANKNIFTY2412543000CE",
                "instrument_type": "CE",
                "strike": 43000.0,
                "expiry": "2024-01-25",
                "exchange": "NFO",
            },
        ]
        mock_kite.instruments.return_value = banknifty_instruments
        mock_kite.ltp.return_value = {
            "NFO:BANKNIFTY2412543000CE": {"last_price": 450.0}
        }

        result = worker.fetch_all_option_chains("2024-01-25")

        # NIFTY should fail (no matching contracts), BANKNIFTY should succeed
        assert "NIFTY" in result["errors"]
        assert "BANKNIFTY" in result["chains"]
        assert len(result["chains"]["BANKNIFTY"]) == 1

    def test_all_symbols_fail_returns_empty_chains(self, worker, mock_kite):
        """Test that if all symbols fail, returns empty chains with errors."""
        mock_kite.instruments.side_effect = Exception("Connection timeout")

        result = worker.fetch_all_option_chains("2024-01-25")

        assert result["chains"] == {}
        assert len(result["errors"]) == 2

    def test_custom_symbols_list(self, worker, mock_kite, nifty_instruments):
        """Test fetching option chains with custom symbols list."""
        mock_kite.instruments.return_value = nifty_instruments
        mock_kite.ltp.return_value = {
            "NFO:NIFTY2412518000CE": {"last_price": 650.0}
        }

        result = worker.fetch_all_option_chains("2024-01-25", symbols=["NIFTY"])

        assert "NIFTY" in result["chains"]
        assert len(result["errors"]) == 0

    def test_invalid_symbol_in_list_is_caught(self, worker, mock_kite, nifty_instruments):
        """Test that invalid symbol is caught as error, not crash."""
        mock_kite.instruments.return_value = nifty_instruments
        mock_kite.ltp.return_value = {
            "NFO:NIFTY2412518000CE": {"last_price": 650.0}
        }

        # RELIANCE is not supported for option chain -> ValueError
        result = worker.fetch_all_option_chains("2024-01-25", symbols=["NIFTY", "RELIANCE"])

        assert "NIFTY" in result["chains"]
        assert "RELIANCE" in result["errors"]
        assert result["errors"]["RELIANCE"]["category"] == "permanent"

    def test_error_includes_category_info(self, worker, mock_kite):
        """Test that error entries include category information."""
        mock_kite.instruments.side_effect = Exception("Connection timeout")

        result = worker.fetch_all_option_chains("2024-01-25", symbols=["NIFTY"])

        assert "category" in result["errors"]["NIFTY"]
        assert result["errors"]["NIFTY"]["category"] == "transient"

    def test_does_not_crash_on_unexpected_exception(self, worker, mock_kite):
        """Test that unexpected exceptions are caught gracefully."""
        mock_kite.instruments.side_effect = RuntimeError("unexpected crash")

        # Should not raise
        result = worker.fetch_all_option_chains("2024-01-25")

        assert result["chains"] == {}
        assert len(result["errors"]) == 2


# ============================================================
# Integration: Error category on fetch_spot_price
# ============================================================


class TestFetchSpotPriceErrorCategory:
    """Tests that fetch_spot_price sets error category properly."""

    def test_network_timeout_is_transient(self, worker, mock_kite):
        """Test that network timeout sets transient category."""
        mock_kite.ltp.side_effect = Exception("NetworkException: Connection timeout")

        with pytest.raises(MarketDataError) as exc_info:
            worker.fetch_spot_price("NIFTY")

        assert exc_info.value.category == ErrorCategory.TRANSIENT
        assert exc_info.value.symbol == "NIFTY"

    def test_token_exception_is_permanent(self, worker, mock_kite):
        """Test that token-related error is permanent."""

        class TokenException(Exception):
            pass

        mock_kite.ltp.side_effect = TokenException("token expired")

        with pytest.raises(MarketDataError) as exc_info:
            worker.fetch_spot_price("NIFTY")

        assert exc_info.value.category == ErrorCategory.PERMANENT
        assert exc_info.value.symbol == "NIFTY"

    def test_empty_response_is_permanent(self, worker, mock_kite):
        """Test that empty response error is permanent."""
        mock_kite.ltp.return_value = {}

        with pytest.raises(MarketDataError) as exc_info:
            worker.fetch_spot_price("NIFTY")

        assert exc_info.value.category == ErrorCategory.PERMANENT

    def test_missing_last_price_is_permanent(self, worker, mock_kite):
        """Test that missing last_price is permanent."""
        mock_kite.ltp.return_value = {"NSE:NIFTY 50": {"instrument_token": 256265}}

        with pytest.raises(MarketDataError) as exc_info:
            worker.fetch_spot_price("NIFTY")

        assert exc_info.value.category == ErrorCategory.PERMANENT


# ============================================================
# store_tick Tests
# ============================================================


class TestStoreTick:
    """Tests for MarketDataWorker.store_tick().

    Requirements covered:
    - 1.6.6: Store recent ticks for VWAP calculation (last 100 ticks)
    - 3.6.5: Cache market ticks with key market:{symbol}:ticks
    - 3.6.8: Set TTL of 300 seconds for market ticks
    - 3.6.9: Include timestamp in all cached data
    """

    def test_store_tick_returns_true_on_success(self, worker, mock_redis):
        """Test that store_tick returns True when storage succeeds."""
        mock_redis.lpush.return_value = 1
        mock_redis.ltrim.return_value = True
        mock_redis.expire.return_value = True

        result = worker.store_tick("NIFTY", 18650.75, 1000)

        assert result is True

    def test_store_tick_uses_correct_key(self, worker, mock_redis):
        """Test that store_tick uses key market:{symbol}:ticks (Req 3.6.5)."""
        mock_redis.lpush.return_value = 1
        mock_redis.ltrim.return_value = True
        mock_redis.expire.return_value = True

        worker.store_tick("NIFTY", 18650.75, 1000)

        # Verify the key passed to lpush starts with market:NIFTY:ticks
        call_args = mock_redis.lpush.call_args
        assert call_args[0][0] == "market:NIFTY:ticks"

    def test_store_tick_stores_json_with_price_volume_timestamp(self, worker, mock_redis):
        """Test that tick data contains price, volume, and timestamp (Req 3.6.9)."""
        import json

        mock_redis.lpush.return_value = 1
        mock_redis.ltrim.return_value = True
        mock_redis.expire.return_value = True

        worker.store_tick("NIFTY", 18650.75, 1000)

        call_args = mock_redis.lpush.call_args
        tick_json = call_args[0][1]
        tick_data = json.loads(tick_json)

        assert tick_data["price"] == 18650.75
        assert tick_data["volume"] == 1000
        assert "timestamp" in tick_data
        assert isinstance(tick_data["timestamp"], float)

    def test_store_tick_trims_to_100_entries(self, worker, mock_redis):
        """Test that list is trimmed to keep only last 100 ticks (Req 1.6.6)."""
        mock_redis.lpush.return_value = 1
        mock_redis.ltrim.return_value = True
        mock_redis.expire.return_value = True

        worker.store_tick("NIFTY", 18650.75, 1000)

        mock_redis.ltrim.assert_called_once_with("market:NIFTY:ticks", 0, 99)

    def test_store_tick_sets_ttl_300_seconds(self, worker, mock_redis):
        """Test that TTL of 300 seconds is set on ticks key (Req 3.6.8)."""
        mock_redis.lpush.return_value = 1
        mock_redis.ltrim.return_value = True
        mock_redis.expire.return_value = True

        worker.store_tick("NIFTY", 18650.75, 1000)

        mock_redis.expire.assert_called_once_with("market:NIFTY:ticks", 300)

    def test_store_tick_symbol_case_insensitive(self, worker, mock_redis):
        """Test that symbol is uppercased before use."""
        mock_redis.lpush.return_value = 1
        mock_redis.ltrim.return_value = True
        mock_redis.expire.return_value = True

        worker.store_tick("nifty", 18650.75, 1000)

        call_args = mock_redis.lpush.call_args
        assert call_args[0][0] == "market:NIFTY:ticks"

    def test_store_tick_strips_whitespace(self, worker, mock_redis):
        """Test that symbol whitespace is trimmed."""
        mock_redis.lpush.return_value = 1
        mock_redis.ltrim.return_value = True
        mock_redis.expire.return_value = True

        worker.store_tick("  NIFTY  ", 18650.75, 1000)

        call_args = mock_redis.lpush.call_args
        assert call_args[0][0] == "market:NIFTY:ticks"

    def test_store_tick_different_symbols(self, worker, mock_redis):
        """Test that different symbols use different keys."""
        mock_redis.lpush.return_value = 1
        mock_redis.ltrim.return_value = True
        mock_redis.expire.return_value = True

        worker.store_tick("BANKNIFTY", 43520.10, 500)

        call_args = mock_redis.lpush.call_args
        assert call_args[0][0] == "market:BANKNIFTY:ticks"

    # --- Error Cases ---

    def test_store_tick_empty_symbol_raises(self, worker):
        """Test that empty symbol raises ValueError."""
        with pytest.raises(ValueError, match="Symbol cannot be empty"):
            worker.store_tick("", 18650.75, 1000)

    def test_store_tick_whitespace_symbol_raises(self, worker):
        """Test that whitespace-only symbol raises ValueError."""
        with pytest.raises(ValueError, match="Symbol cannot be empty"):
            worker.store_tick("   ", 18650.75, 1000)

    def test_store_tick_zero_price_raises(self, worker):
        """Test that zero price raises ValueError."""
        with pytest.raises(ValueError, match="Price must be positive"):
            worker.store_tick("NIFTY", 0, 1000)

    def test_store_tick_negative_price_raises(self, worker):
        """Test that negative price raises ValueError."""
        with pytest.raises(ValueError, match="Price must be positive"):
            worker.store_tick("NIFTY", -100.0, 1000)

    def test_store_tick_negative_volume_raises(self, worker):
        """Test that negative volume raises ValueError."""
        with pytest.raises(ValueError, match="Volume must be non-negative"):
            worker.store_tick("NIFTY", 18650.75, -1)

    def test_store_tick_zero_volume_succeeds(self, worker, mock_redis):
        """Test that zero volume is valid (e.g., no-trade tick)."""
        mock_redis.lpush.return_value = 1
        mock_redis.ltrim.return_value = True
        mock_redis.expire.return_value = True

        result = worker.store_tick("NIFTY", 18650.75, 0)

        assert result is True

    def test_store_tick_redis_error_returns_false(self, worker, mock_redis):
        """Test that Redis error returns False instead of raising."""
        mock_redis.lpush.side_effect = Exception("Redis connection lost")

        result = worker.store_tick("NIFTY", 18650.75, 1000)

        assert result is False


# ============================================================
# compute_vwap Tests
# ============================================================


class TestComputeVwap:
    """Tests for MarketDataWorker.compute_vwap().

    Requirements covered:
    - 1.6.3: Compute VWAP from recent ticks (20 tick lookback)
    """

    def test_compute_vwap_basic(self, worker, mock_redis):
        """Test basic VWAP computation with known values."""
        import json

        # VWAP = sum(price * volume) / sum(volume)
        # = (100*10 + 200*20) / (10 + 20) = (1000 + 4000) / 30 = 166.67
        ticks = [
            json.dumps({"price": 100.0, "volume": 10, "timestamp": 1000.0}),
            json.dumps({"price": 200.0, "volume": 20, "timestamp": 999.0}),
        ]
        mock_redis.lrange.return_value = ticks

        result = worker.compute_vwap("NIFTY")

        expected = (100.0 * 10 + 200.0 * 20) / (10 + 20)
        assert abs(result - expected) < 1e-9

    def test_compute_vwap_single_tick(self, worker, mock_redis):
        """Test VWAP with a single tick equals the tick price."""
        import json

        ticks = [
            json.dumps({"price": 18650.75, "volume": 500, "timestamp": 1000.0}),
        ]
        mock_redis.lrange.return_value = ticks

        result = worker.compute_vwap("NIFTY")

        assert result == 18650.75

    def test_compute_vwap_uses_correct_key(self, worker, mock_redis):
        """Test that compute_vwap reads from market:{symbol}:ticks."""
        mock_redis.lrange.return_value = []

        worker.compute_vwap("NIFTY")

        mock_redis.lrange.assert_called_once_with("market:NIFTY:ticks", 0, 19)

    def test_compute_vwap_default_lookback_20(self, worker, mock_redis):
        """Test that default lookback is 20 ticks."""
        mock_redis.lrange.return_value = []

        worker.compute_vwap("NIFTY")

        mock_redis.lrange.assert_called_once_with("market:NIFTY:ticks", 0, 19)

    def test_compute_vwap_custom_lookback(self, worker, mock_redis):
        """Test that custom lookback is respected."""
        mock_redis.lrange.return_value = []

        worker.compute_vwap("NIFTY", lookback=50)

        mock_redis.lrange.assert_called_once_with("market:NIFTY:ticks", 0, 49)

    def test_compute_vwap_no_ticks_returns_zero(self, worker, mock_redis):
        """Test that empty tick list returns 0.0."""
        mock_redis.lrange.return_value = []

        result = worker.compute_vwap("NIFTY")

        assert result == 0.0

    def test_compute_vwap_all_zero_volume_returns_zero(self, worker, mock_redis):
        """Test that all-zero volume ticks return 0.0 (avoid division by zero)."""
        import json

        ticks = [
            json.dumps({"price": 100.0, "volume": 0, "timestamp": 1000.0}),
            json.dumps({"price": 200.0, "volume": 0, "timestamp": 999.0}),
        ]
        mock_redis.lrange.return_value = ticks

        result = worker.compute_vwap("NIFTY")

        assert result == 0.0

    def test_compute_vwap_symbol_case_insensitive(self, worker, mock_redis):
        """Test that symbol is uppercased."""
        mock_redis.lrange.return_value = []

        worker.compute_vwap("nifty")

        mock_redis.lrange.assert_called_once_with("market:NIFTY:ticks", 0, 19)

    def test_compute_vwap_strips_whitespace(self, worker, mock_redis):
        """Test that symbol whitespace is stripped."""
        mock_redis.lrange.return_value = []

        worker.compute_vwap("  NIFTY  ")

        mock_redis.lrange.assert_called_once_with("market:NIFTY:ticks", 0, 19)

    def test_compute_vwap_skips_malformed_ticks(self, worker, mock_redis):
        """Test that malformed ticks are skipped gracefully."""
        import json

        ticks = [
            json.dumps({"price": 100.0, "volume": 10, "timestamp": 1000.0}),
            "not valid json",
            json.dumps({"price": 200.0, "volume": 20, "timestamp": 999.0}),
        ]
        mock_redis.lrange.return_value = ticks

        result = worker.compute_vwap("NIFTY")

        # Should compute from valid ticks only
        expected = (100.0 * 10 + 200.0 * 20) / (10 + 20)
        assert abs(result - expected) < 1e-9

    def test_compute_vwap_skips_ticks_missing_fields(self, worker, mock_redis):
        """Test that ticks missing required fields are skipped."""
        import json

        ticks = [
            json.dumps({"price": 100.0, "volume": 10, "timestamp": 1000.0}),
            json.dumps({"price": 150.0, "timestamp": 999.0}),  # missing volume
            json.dumps({"volume": 30, "timestamp": 998.0}),  # missing price
        ]
        mock_redis.lrange.return_value = ticks

        result = worker.compute_vwap("NIFTY")

        # Only first tick is valid
        assert result == 100.0

    def test_compute_vwap_redis_error_returns_zero(self, worker, mock_redis):
        """Test that Redis error returns 0.0 gracefully."""
        mock_redis.lrange.side_effect = Exception("Redis connection lost")

        result = worker.compute_vwap("NIFTY")

        assert result == 0.0

    # --- Error Cases ---

    def test_compute_vwap_empty_symbol_raises(self, worker):
        """Test that empty symbol raises ValueError."""
        with pytest.raises(ValueError, match="Symbol cannot be empty"):
            worker.compute_vwap("")

    def test_compute_vwap_whitespace_symbol_raises(self, worker):
        """Test that whitespace-only symbol raises ValueError."""
        with pytest.raises(ValueError, match="Symbol cannot be empty"):
            worker.compute_vwap("   ")

    def test_compute_vwap_zero_lookback_raises(self, worker):
        """Test that zero lookback raises ValueError."""
        with pytest.raises(ValueError, match="Lookback must be positive"):
            worker.compute_vwap("NIFTY", lookback=0)

    def test_compute_vwap_negative_lookback_raises(self, worker):
        """Test that negative lookback raises ValueError."""
        with pytest.raises(ValueError, match="Lookback must be positive"):
            worker.compute_vwap("NIFTY", lookback=-5)

    def test_compute_vwap_weighted_average(self, worker, mock_redis):
        """Test that VWAP correctly weights by volume (not simple average)."""
        import json

        # If volumes are equal, VWAP = simple average
        # price1=100, vol1=100; price2=200, vol2=100
        # Simple avg = 150, VWAP = (100*100 + 200*100) / (100+100) = 150
        ticks_equal_vol = [
            json.dumps({"price": 100.0, "volume": 100, "timestamp": 1000.0}),
            json.dumps({"price": 200.0, "volume": 100, "timestamp": 999.0}),
        ]
        mock_redis.lrange.return_value = ticks_equal_vol
        result_equal = worker.compute_vwap("NIFTY")
        assert abs(result_equal - 150.0) < 1e-9

        # If volumes are unequal, VWAP != simple average
        # price1=100, vol1=900; price2=200, vol2=100
        # VWAP = (100*900 + 200*100) / (900+100) = 110000/1000 = 110
        ticks_unequal_vol = [
            json.dumps({"price": 100.0, "volume": 900, "timestamp": 1000.0}),
            json.dumps({"price": 200.0, "volume": 100, "timestamp": 999.0}),
        ]
        mock_redis.lrange.return_value = ticks_unequal_vol
        result_unequal = worker.compute_vwap("NIFTY")
        assert abs(result_unequal - 110.0) < 1e-9
        # Not simple average which would be 150
        assert abs(result_unequal - 150.0) > 1.0



# ============================================================
# has_sufficient_ticks Tests
# ============================================================


class TestHasSufficientTicks:
    """Tests for MarketDataWorker.has_sufficient_ticks().

    Requirements covered:
    - 1.6.3: Compute VWAP from recent ticks (20 tick lookback)
    - 1.6.7: Handle market data fetch failures gracefully
    """

    def test_sufficient_ticks_returns_true(self, worker, mock_redis):
        """Test that True is returned when enough ticks are available."""
        mock_redis.llen.return_value = 20

        result = worker.has_sufficient_ticks("NIFTY")

        assert result is True

    def test_more_than_min_ticks_returns_true(self, worker, mock_redis):
        """Test that True is returned when more than min_ticks are available."""
        mock_redis.llen.return_value = 50

        result = worker.has_sufficient_ticks("NIFTY", min_ticks=20)

        assert result is True

    def test_fewer_ticks_returns_false(self, worker, mock_redis):
        """Test that False is returned when fewer ticks than required."""
        mock_redis.llen.return_value = 5

        result = worker.has_sufficient_ticks("NIFTY")

        assert result is False

    def test_zero_ticks_returns_false(self, worker, mock_redis):
        """Test that False is returned when no ticks exist."""
        mock_redis.llen.return_value = 0

        result = worker.has_sufficient_ticks("NIFTY")

        assert result is False

    def test_custom_min_ticks(self, worker, mock_redis):
        """Test that custom min_ticks threshold works."""
        mock_redis.llen.return_value = 10

        assert worker.has_sufficient_ticks("NIFTY", min_ticks=10) is True
        assert worker.has_sufficient_ticks("NIFTY", min_ticks=11) is False

    def test_uses_correct_redis_key(self, worker, mock_redis):
        """Test that the correct Redis key is queried."""
        mock_redis.llen.return_value = 20

        worker.has_sufficient_ticks("NIFTY")

        mock_redis.llen.assert_called_with("market:NIFTY:ticks")

    def test_symbol_case_insensitive(self, worker, mock_redis):
        """Test that symbol is uppercased."""
        mock_redis.llen.return_value = 20

        worker.has_sufficient_ticks("nifty")

        mock_redis.llen.assert_called_with("market:NIFTY:ticks")

    def test_symbol_strips_whitespace(self, worker, mock_redis):
        """Test that symbol whitespace is stripped."""
        mock_redis.llen.return_value = 20

        worker.has_sufficient_ticks("  NIFTY  ")

        mock_redis.llen.assert_called_with("market:NIFTY:ticks")

    def test_redis_error_returns_false(self, worker, mock_redis):
        """Test that Redis error returns False gracefully."""
        mock_redis.llen.side_effect = Exception("Redis connection lost")

        result = worker.has_sufficient_ticks("NIFTY")

        assert result is False

    # --- Error Cases ---

    def test_empty_symbol_raises(self, worker):
        """Test that empty symbol raises ValueError."""
        with pytest.raises(ValueError, match="Symbol cannot be empty"):
            worker.has_sufficient_ticks("")

    def test_whitespace_symbol_raises(self, worker):
        """Test that whitespace-only symbol raises ValueError."""
        with pytest.raises(ValueError, match="Symbol cannot be empty"):
            worker.has_sufficient_ticks("   ")

    def test_zero_min_ticks_raises(self, worker):
        """Test that zero min_ticks raises ValueError."""
        with pytest.raises(ValueError, match="min_ticks must be positive"):
            worker.has_sufficient_ticks("NIFTY", min_ticks=0)

    def test_negative_min_ticks_raises(self, worker):
        """Test that negative min_ticks raises ValueError."""
        with pytest.raises(ValueError, match="min_ticks must be positive"):
            worker.has_sufficient_ticks("NIFTY", min_ticks=-5)


# ============================================================
# compute_vwap Insufficient Data Handling Tests
# ============================================================


class TestComputeVwapInsufficientData:
    """Tests for compute_vwap behavior with insufficient data.

    Requirements covered:
    - 1.6.3: Compute VWAP from recent ticks (20 tick lookback)
    - 1.6.7: Handle market data fetch failures gracefully

    Verifies:
    - VWAP is computed from partial data when fewer ticks than lookback exist
    - Warning is logged when insufficient data is used
    - Returns 0.0 for no ticks without crashing
    """

    def test_partial_data_computes_vwap(self, worker, mock_redis):
        """Test that VWAP is computed correctly with fewer ticks than lookback."""
        import json

        # Only 5 ticks available but 20 requested
        ticks = [
            json.dumps({"price": 100.0, "volume": 10, "timestamp": 1000.0}),
            json.dumps({"price": 110.0, "volume": 20, "timestamp": 999.0}),
            json.dumps({"price": 105.0, "volume": 15, "timestamp": 998.0}),
            json.dumps({"price": 120.0, "volume": 25, "timestamp": 997.0}),
            json.dumps({"price": 115.0, "volume": 30, "timestamp": 996.0}),
        ]
        mock_redis.lrange.return_value = ticks

        result = worker.compute_vwap("NIFTY", lookback=20)

        # VWAP = sum(p*v) / sum(v)
        expected = (100*10 + 110*20 + 105*15 + 120*25 + 115*30) / (10+20+15+25+30)
        assert abs(result - expected) < 1e-9

    def test_partial_data_logs_warning(self, worker, mock_redis, caplog):
        """Test that a warning is logged when fewer ticks than lookback."""
        import json
        import logging

        ticks = [
            json.dumps({"price": 100.0, "volume": 10, "timestamp": 1000.0}),
            json.dumps({"price": 110.0, "volume": 20, "timestamp": 999.0}),
        ]
        mock_redis.lrange.return_value = ticks

        with caplog.at_level(logging.WARNING):
            worker.compute_vwap("NIFTY", lookback=20)

        assert any("Insufficient ticks" in record.message for record in caplog.records)
        assert any("2 available" in record.message for record in caplog.records)
        assert any("20 requested" in record.message for record in caplog.records)

    def test_no_ticks_logs_warning(self, worker, mock_redis, caplog):
        """Test that a warning is logged when no ticks are available."""
        import logging

        mock_redis.lrange.return_value = []

        with caplog.at_level(logging.WARNING):
            result = worker.compute_vwap("NIFTY", lookback=20)

        assert result == 0.0
        assert any("No ticks available" in record.message for record in caplog.records)

    def test_exact_lookback_no_warning(self, worker, mock_redis, caplog):
        """Test that no warning is logged when exactly lookback ticks available."""
        import json
        import logging

        # Exactly 20 ticks
        ticks = [
            json.dumps({"price": 100.0 + i, "volume": 10, "timestamp": 1000.0 - i})
            for i in range(20)
        ]
        mock_redis.lrange.return_value = ticks

        with caplog.at_level(logging.WARNING):
            worker.compute_vwap("NIFTY", lookback=20)

        # No "Insufficient" warning should be logged
        assert not any("Insufficient ticks" in record.message for record in caplog.records)

    def test_single_tick_available_computes_correctly(self, worker, mock_redis):
        """Test VWAP with only 1 tick when 20 requested."""
        import json

        ticks = [
            json.dumps({"price": 18650.75, "volume": 500, "timestamp": 1000.0}),
        ]
        mock_redis.lrange.return_value = ticks

        result = worker.compute_vwap("NIFTY", lookback=20)

        # Single tick: VWAP = that tick's price
        assert result == 18650.75

    def test_redis_error_returns_zero_gracefully(self, worker, mock_redis):
        """Test that Redis error during VWAP returns 0.0 without crash."""
        mock_redis.lrange.side_effect = ConnectionError("Redis unavailable")

        result = worker.compute_vwap("NIFTY", lookback=20)

        assert result == 0.0

    def test_all_malformed_ticks_returns_zero(self, worker, mock_redis):
        """Test that all malformed ticks result in 0.0."""
        ticks = [
            "not json",
            "also not json",
            "{invalid",
        ]
        mock_redis.lrange.return_value = ticks

        result = worker.compute_vwap("NIFTY", lookback=20)

        assert result == 0.0


# ============================================================
# cache_market_data Tests
# ============================================================


class TestCacheMarketData:
    """Tests for MarketDataWorker.cache_market_data().

    Requirements covered:
    - 1.6.4: Cache market data in Redis with 10 second TTL
    - 3.6.4: Cache market data with key market:{symbol}:data
    - 3.6.6: Set TTL of 10 seconds for market data
    """

    def test_cache_market_data_returns_true_on_success(self, worker, mock_redis):
        """Test that cache_market_data returns True when storage succeeds."""
        mock_redis.setex.return_value = True

        data = {"spot": 18650.75, "vwap": 18645.0, "timestamp": "2024-01-25T10:30:00"}
        result = worker.cache_market_data("NIFTY", data)

        assert result is True

    def test_cache_market_data_uses_correct_key(self, worker, mock_redis):
        """Test that cache uses key market:{symbol}:data (Req 3.6.4)."""
        mock_redis.setex.return_value = True

        data = {"spot": 18650.75, "vwap": 18645.0, "timestamp": "2024-01-25T10:30:00"}
        worker.cache_market_data("NIFTY", data)

        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == "market:NIFTY:data"

    def test_cache_market_data_sets_ttl_10_seconds(self, worker, mock_redis):
        """Test that TTL of 10 seconds is set (Req 3.6.6)."""
        mock_redis.setex.return_value = True

        data = {"spot": 18650.75, "vwap": 18645.0, "timestamp": "2024-01-25T10:30:00"}
        worker.cache_market_data("NIFTY", data)

        call_args = mock_redis.setex.call_args
        assert call_args[0][1] == 10

    def test_cache_market_data_stores_json(self, worker, mock_redis):
        """Test that data is stored as JSON string."""
        import json

        mock_redis.setex.return_value = True

        data = {"spot": 18650.75, "vwap": 18645.0, "timestamp": "2024-01-25T10:30:00"}
        worker.cache_market_data("NIFTY", data)

        call_args = mock_redis.setex.call_args
        stored_json = call_args[0][2]
        parsed = json.loads(stored_json)

        assert parsed["spot"] == 18650.75
        assert parsed["vwap"] == 18645.0
        assert parsed["timestamp"] == "2024-01-25T10:30:00"

    def test_cache_market_data_with_option_chain(self, worker, mock_redis):
        """Test caching data that includes option chain."""
        import json

        mock_redis.setex.return_value = True

        data = {
            "spot": 18650.75,
            "vwap": 18645.0,
            "timestamp": "2024-01-25T10:30:00",
            "option_chain": [
                {"strike": 18000.0, "option_type": "CE", "ltp": 650.50},
                {"strike": 18000.0, "option_type": "PE", "ltp": 120.25},
            ],
        }
        worker.cache_market_data("NIFTY", data)

        call_args = mock_redis.setex.call_args
        stored_json = call_args[0][2]
        parsed = json.loads(stored_json)

        assert len(parsed["option_chain"]) == 2
        assert parsed["option_chain"][0]["strike"] == 18000.0

    def test_cache_market_data_symbol_case_insensitive(self, worker, mock_redis):
        """Test that symbol is uppercased."""
        mock_redis.setex.return_value = True

        data = {"spot": 18650.75, "vwap": 18645.0, "timestamp": "2024-01-25T10:30:00"}
        worker.cache_market_data("nifty", data)

        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == "market:NIFTY:data"

    def test_cache_market_data_strips_whitespace(self, worker, mock_redis):
        """Test that symbol whitespace is trimmed."""
        mock_redis.setex.return_value = True

        data = {"spot": 18650.75, "vwap": 18645.0, "timestamp": "2024-01-25T10:30:00"}
        worker.cache_market_data("  NIFTY  ", data)

        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == "market:NIFTY:data"

    def test_cache_market_data_banknifty(self, worker, mock_redis):
        """Test caching BANKNIFTY data uses correct key."""
        mock_redis.setex.return_value = True

        data = {"spot": 43520.10, "vwap": 43500.0, "timestamp": "2024-01-25T10:30:00"}
        worker.cache_market_data("BANKNIFTY", data)

        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == "market:BANKNIFTY:data"

    def test_cache_market_data_redis_error_returns_false(self, worker, mock_redis):
        """Test that Redis error returns False instead of raising."""
        mock_redis.setex.side_effect = Exception("Redis connection lost")

        data = {"spot": 18650.75, "vwap": 18645.0, "timestamp": "2024-01-25T10:30:00"}
        result = worker.cache_market_data("NIFTY", data)

        assert result is False

    # --- Error Cases ---

    def test_cache_market_data_empty_symbol_raises(self, worker):
        """Test that empty symbol raises ValueError."""
        with pytest.raises(ValueError, match="Symbol cannot be empty"):
            worker.cache_market_data("", {"spot": 100.0})

    def test_cache_market_data_whitespace_symbol_raises(self, worker):
        """Test that whitespace-only symbol raises ValueError."""
        with pytest.raises(ValueError, match="Symbol cannot be empty"):
            worker.cache_market_data("   ", {"spot": 100.0})

    def test_cache_market_data_non_dict_raises(self, worker):
        """Test that non-dict data raises ValueError."""
        with pytest.raises(ValueError, match="Data must be a dictionary"):
            worker.cache_market_data("NIFTY", "not a dict")

    def test_cache_market_data_list_raises(self, worker):
        """Test that list data raises ValueError."""
        with pytest.raises(ValueError, match="Data must be a dictionary"):
            worker.cache_market_data("NIFTY", [1, 2, 3])

    # --- Timestamp injection tests (Req 3.6.9) ---

    def test_cache_market_data_injects_timestamp_when_missing(self, worker, mock_redis):
        """Test that timestamp is automatically injected when not present (Req 3.6.9)."""
        import json

        mock_redis.setex.return_value = True

        data = {"spot": 18650.75, "vwap": 18645.0}
        worker.cache_market_data("NIFTY", data)

        call_args = mock_redis.setex.call_args
        stored_json = call_args[0][2]
        parsed = json.loads(stored_json)

        assert "timestamp" in parsed
        # Verify it's a valid ISO format string
        from datetime import datetime
        datetime.fromisoformat(parsed["timestamp"])

    def test_cache_market_data_preserves_existing_timestamp(self, worker, mock_redis):
        """Test that existing timestamp is not overwritten."""
        import json

        mock_redis.setex.return_value = True

        existing_ts = "2024-01-25T10:30:00"
        data = {"spot": 18650.75, "vwap": 18645.0, "timestamp": existing_ts}
        worker.cache_market_data("NIFTY", data)

        call_args = mock_redis.setex.call_args
        stored_json = call_args[0][2]
        parsed = json.loads(stored_json)

        assert parsed["timestamp"] == existing_ts

    def test_cache_market_data_does_not_mutate_original_dict(self, worker, mock_redis):
        """Test that the original data dict is not mutated when timestamp is injected."""
        mock_redis.setex.return_value = True

        data = {"spot": 18650.75, "vwap": 18645.0}
        worker.cache_market_data("NIFTY", data)

        # Original dict should not have timestamp added
        assert "timestamp" not in data

    def test_cache_market_data_timestamp_is_iso_format(self, worker, mock_redis):
        """Test that the injected timestamp is in ISO format."""
        import json
        from datetime import datetime

        mock_redis.setex.return_value = True

        data = {"spot": 18650.75}
        worker.cache_market_data("NIFTY", data)

        call_args = mock_redis.setex.call_args
        stored_json = call_args[0][2]
        parsed = json.loads(stored_json)

        # Should parse without error as ISO format
        ts = datetime.fromisoformat(parsed["timestamp"])
        assert ts.year >= 2024


# ============================================================
# get_cached_market_data Tests
# ============================================================


class TestGetCachedMarketData:
    """Tests for MarketDataWorker.get_cached_market_data().

    Requirements covered:
    - 1.6.4: Cache market data in Redis with 10 second TTL
    - 3.6.4: Cache market data with key market:{symbol}:data
    """

    def test_get_cached_data_returns_dict(self, worker, mock_redis):
        """Test that cached data is returned as a dict."""
        import json

        cached = {"spot": 18650.75, "vwap": 18645.0, "timestamp": "2024-01-25T10:30:00"}
        mock_redis.get.return_value = json.dumps(cached)

        result = worker.get_cached_market_data("NIFTY")

        assert result == cached
        assert isinstance(result, dict)

    def test_get_cached_data_uses_correct_key(self, worker, mock_redis):
        """Test that get uses key market:{symbol}:data (Req 3.6.4)."""
        mock_redis.get.return_value = None

        worker.get_cached_market_data("NIFTY")

        mock_redis.get.assert_called_once_with("market:NIFTY:data")

    def test_get_cached_data_cache_miss_returns_none(self, worker, mock_redis):
        """Test that cache miss (key expired or not set) returns None."""
        mock_redis.get.return_value = None

        result = worker.get_cached_market_data("NIFTY")

        assert result is None

    def test_get_cached_data_with_option_chain(self, worker, mock_redis):
        """Test retrieving data that includes option chain."""
        import json

        cached = {
            "spot": 18650.75,
            "vwap": 18645.0,
            "timestamp": "2024-01-25T10:30:00",
            "option_chain": [
                {"strike": 18000.0, "option_type": "CE", "ltp": 650.50},
            ],
        }
        mock_redis.get.return_value = json.dumps(cached)

        result = worker.get_cached_market_data("NIFTY")

        assert result["option_chain"][0]["strike"] == 18000.0

    def test_get_cached_data_symbol_case_insensitive(self, worker, mock_redis):
        """Test that symbol is uppercased."""
        mock_redis.get.return_value = None

        worker.get_cached_market_data("nifty")

        mock_redis.get.assert_called_once_with("market:NIFTY:data")

    def test_get_cached_data_strips_whitespace(self, worker, mock_redis):
        """Test that symbol whitespace is stripped."""
        mock_redis.get.return_value = None

        worker.get_cached_market_data("  NIFTY  ")

        mock_redis.get.assert_called_once_with("market:NIFTY:data")

    def test_get_cached_data_banknifty(self, worker, mock_redis):
        """Test retrieving BANKNIFTY data uses correct key."""
        mock_redis.get.return_value = None

        worker.get_cached_market_data("BANKNIFTY")

        mock_redis.get.assert_called_once_with("market:BANKNIFTY:data")

    def test_get_cached_data_redis_error_returns_none(self, worker, mock_redis):
        """Test that Redis error returns None instead of raising."""
        mock_redis.get.side_effect = Exception("Redis connection lost")

        result = worker.get_cached_market_data("NIFTY")

        assert result is None

    # --- Error Cases ---

    def test_get_cached_data_empty_symbol_raises(self, worker):
        """Test that empty symbol raises ValueError."""
        with pytest.raises(ValueError, match="Symbol cannot be empty"):
            worker.get_cached_market_data("")

    def test_get_cached_data_whitespace_symbol_raises(self, worker):
        """Test that whitespace-only symbol raises ValueError."""
        with pytest.raises(ValueError, match="Symbol cannot be empty"):
            worker.get_cached_market_data("   ")


# ============================================================
# get_market_data Tests (Cache-Aside Pattern)
# ============================================================


class TestGetMarketData:
    """Tests for MarketDataWorker.get_market_data().

    Implements cache-aside pattern:
    1. Check Redis cache first
    2. On cache miss, fetch from broker API (spot + VWAP)
    3. Cache fresh data before returning
    4. Return None if both cache and fetch fail

    Requirements covered:
    - 1.6.7: Handle market data fetch failures gracefully
    - 2.3.4: Fall back to database when Redis unavailable
    """

    def test_returns_cached_data_on_cache_hit(self, worker, mock_redis):
        """Test that cached data is returned directly on cache hit."""
        import json

        cached = {"spot": 18650.75, "vwap": 18645.0, "timestamp": "2024-01-25T10:30:00"}
        mock_redis.get.return_value = json.dumps(cached)

        result = worker.get_market_data("NIFTY")

        assert result == cached
        # Should NOT call fetch_spot_price or compute_vwap (no kite call)
        mock_redis.get.assert_called_once_with("market:NIFTY:data")

    def test_fetches_fresh_data_on_cache_miss(self, worker, mock_kite, mock_redis):
        """Test that fresh data is fetched from broker when cache misses."""
        import json

        # Cache miss
        mock_redis.get.return_value = None
        # Fresh spot price
        mock_kite.ltp.return_value = {"NSE:NIFTY 50": {"last_price": 18700.0}}
        # VWAP from ticks
        ticks = [
            json.dumps({"price": 18690.0, "volume": 100, "timestamp": 1000.0}),
            json.dumps({"price": 18710.0, "volume": 200, "timestamp": 999.0}),
        ]
        mock_redis.lrange.return_value = ticks
        # Cache write succeeds
        mock_redis.setex.return_value = True

        result = worker.get_market_data("NIFTY")

        assert result is not None
        assert result["spot"] == 18700.0
        expected_vwap = (18690.0 * 100 + 18710.0 * 200) / (100 + 200)
        assert abs(result["vwap"] - expected_vwap) < 1e-9
        assert "timestamp" in result

    def test_caches_fresh_data_after_fetch(self, worker, mock_kite, mock_redis):
        """Test that freshly fetched data is cached in Redis."""
        import json

        # Cache miss
        mock_redis.get.return_value = None
        # Fresh spot price
        mock_kite.ltp.return_value = {"NSE:NIFTY 50": {"last_price": 18700.0}}
        # No ticks for VWAP
        mock_redis.lrange.return_value = []
        # Cache write succeeds
        mock_redis.setex.return_value = True

        worker.get_market_data("NIFTY")

        # Verify setex was called (cache_market_data)
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == "market:NIFTY:data"
        assert call_args[0][1] == 10  # TTL

    def test_returns_none_when_fetch_fails(self, worker, mock_kite, mock_redis):
        """Test that None is returned when both cache and fetch fail."""
        # Cache miss
        mock_redis.get.return_value = None
        # API fetch fails
        mock_kite.ltp.side_effect = Exception("Connection timeout")

        result = worker.get_market_data("NIFTY")

        assert result is None

    def test_returns_data_when_vwap_fails_but_spot_succeeds(
        self, worker, mock_kite, mock_redis
    ):
        """Test that data is returned with vwap=0.0 if VWAP computation fails."""
        # Cache miss
        mock_redis.get.return_value = None
        # Fresh spot price succeeds
        mock_kite.ltp.return_value = {"NSE:NIFTY 50": {"last_price": 18700.0}}
        # VWAP computation fails (Redis lrange fails)
        mock_redis.lrange.side_effect = Exception("Redis unavailable")
        # Cache write succeeds
        mock_redis.setex.return_value = True

        result = worker.get_market_data("NIFTY")

        assert result is not None
        assert result["spot"] == 18700.0
        assert result["vwap"] == 0.0

    def test_returns_data_even_if_caching_fails(self, worker, mock_kite, mock_redis):
        """Test that data is returned even if caching the fresh data fails."""
        import json

        # Cache miss
        mock_redis.get.return_value = None
        # Fresh spot price
        mock_kite.ltp.return_value = {"NSE:NIFTY 50": {"last_price": 18700.0}}
        # VWAP
        mock_redis.lrange.return_value = []
        # Cache write fails
        mock_redis.setex.side_effect = Exception("Redis write failed")

        result = worker.get_market_data("NIFTY")

        assert result is not None
        assert result["spot"] == 18700.0

    def test_does_not_call_api_on_cache_hit(self, worker, mock_kite, mock_redis):
        """Test that broker API is not called when cache has data."""
        import json

        cached = {"spot": 18650.75, "vwap": 18645.0, "timestamp": "2024-01-25T10:30:00"}
        mock_redis.get.return_value = json.dumps(cached)

        worker.get_market_data("NIFTY")

        mock_kite.ltp.assert_not_called()

    def test_symbol_case_insensitive(self, worker, mock_redis):
        """Test that symbol is uppercased before cache lookup."""
        import json

        cached = {"spot": 18650.75, "vwap": 18645.0, "timestamp": "2024-01-25T10:30:00"}
        mock_redis.get.return_value = json.dumps(cached)

        result = worker.get_market_data("nifty")

        assert result == cached

    def test_symbol_strips_whitespace(self, worker, mock_redis):
        """Test that symbol whitespace is stripped."""
        import json

        cached = {"spot": 18650.75, "vwap": 18645.0, "timestamp": "2024-01-25T10:30:00"}
        mock_redis.get.return_value = json.dumps(cached)

        result = worker.get_market_data("  NIFTY  ")

        assert result == cached

    def test_empty_symbol_raises_valueerror(self, worker):
        """Test that empty symbol raises ValueError."""
        with pytest.raises(ValueError, match="Symbol cannot be empty"):
            worker.get_market_data("")

    def test_whitespace_symbol_raises_valueerror(self, worker):
        """Test that whitespace-only symbol raises ValueError."""
        with pytest.raises(ValueError, match="Symbol cannot be empty"):
            worker.get_market_data("   ")

    def test_logs_cache_miss_event(self, worker, mock_kite, mock_redis, caplog):
        """Test that cache miss is logged for monitoring."""
        import logging

        # Cache miss
        mock_redis.get.return_value = None
        # Fresh spot price
        mock_kite.ltp.return_value = {"NSE:NIFTY 50": {"last_price": 18700.0}}
        # VWAP
        mock_redis.lrange.return_value = []
        mock_redis.setex.return_value = True

        with caplog.at_level(logging.INFO):
            worker.get_market_data("NIFTY")

        assert any("Cache miss" in record.message for record in caplog.records)
        assert any("NIFTY" in record.message for record in caplog.records)

    def test_banknifty_cache_aside(self, worker, mock_kite, mock_redis):
        """Test cache-aside pattern works for BANKNIFTY."""
        import json

        # Cache miss
        mock_redis.get.return_value = None
        # Fresh spot price
        mock_kite.ltp.return_value = {"NSE:NIFTY BANK": {"last_price": 43520.10}}
        # VWAP
        mock_redis.lrange.return_value = []
        mock_redis.setex.return_value = True

        result = worker.get_market_data("BANKNIFTY")

        assert result is not None
        assert result["spot"] == 43520.10

    def test_redis_unavailable_for_cache_read_fetches_fresh(
        self, worker, mock_kite, mock_redis
    ):
        """Test that if Redis is unavailable for cache read, fresh data is fetched (Req 2.3.4)."""
        # Redis get fails (simulating unavailability)
        mock_redis.get.side_effect = Exception("Redis connection lost")
        # Fresh spot price
        mock_kite.ltp.return_value = {"NSE:NIFTY 50": {"last_price": 18700.0}}
        # VWAP - also fails since Redis is down
        mock_redis.lrange.side_effect = Exception("Redis connection lost")
        # Cache write also fails
        mock_redis.setex.side_effect = Exception("Redis connection lost")

        result = worker.get_market_data("NIFTY")

        # Should still return data (from broker) even though Redis is entirely down
        assert result is not None
        assert result["spot"] == 18700.0
        assert result["vwap"] == 0.0

    def test_includes_timestamp_in_fresh_data(self, worker, mock_kite, mock_redis):
        """Test that fresh data includes a valid ISO timestamp."""
        from datetime import datetime

        # Cache miss
        mock_redis.get.return_value = None
        # Fresh spot price
        mock_kite.ltp.return_value = {"NSE:NIFTY 50": {"last_price": 18700.0}}
        # VWAP
        mock_redis.lrange.return_value = []
        mock_redis.setex.return_value = True

        result = worker.get_market_data("NIFTY")

        assert "timestamp" in result
        # Verify it's valid ISO format
        ts = datetime.fromisoformat(result["timestamp"])
        assert ts.year >= 2024
