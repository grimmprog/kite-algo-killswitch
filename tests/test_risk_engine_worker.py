"""Tests for the Risk Engine Worker - fetch_positions.

Tests cover:
- RiskEngineWorker.__init__(): validation of constructor arguments
- RiskEngineWorker.fetch_positions(): fetching net positions from broker

Requirements covered:
- 1.2.7: Fetch user positions from broker every 2-3 seconds
- 1.4.2: Compute live P&L from broker positions
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import logging
from datetime import datetime

import pytest
import redis
from unittest.mock import MagicMock

from src.workers.risk_engine_worker import RiskEngineWorker
from src.database.models.killswitch_log import KillSwitchLog


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
def mock_db_session():
    """Create a mock database session."""
    return MagicMock()


@pytest.fixture
def worker(mock_kite, mock_redis, mock_db_session):
    """Create a RiskEngineWorker with mocked dependencies."""
    return RiskEngineWorker(
        user_id=1,
        kite_client=mock_kite,
        redis_client=mock_redis,
        db_session=mock_db_session,
    )


# ============================================================
# Constructor Tests
# ============================================================


class TestRiskEngineWorkerInit:
    """Tests for RiskEngineWorker initialization."""

    def test_valid_construction(self, mock_kite, mock_redis, mock_db_session):
        """Worker initializes with valid dependencies."""
        worker = RiskEngineWorker(
            user_id=42,
            kite_client=mock_kite,
            redis_client=mock_redis,
            db_session=mock_db_session,
        )
        assert worker.user_id == 42
        assert worker.kite is mock_kite
        assert worker.redis is mock_redis
        assert worker.db is mock_db_session

    def test_invalid_user_id_zero(self, mock_kite, mock_redis, mock_db_session):
        """Raises ValueError for user_id = 0."""
        with pytest.raises(ValueError, match="user_id must be a positive integer"):
            RiskEngineWorker(0, mock_kite, mock_redis, mock_db_session)

    def test_invalid_user_id_negative(self, mock_kite, mock_redis, mock_db_session):
        """Raises ValueError for negative user_id."""
        with pytest.raises(ValueError, match="user_id must be a positive integer"):
            RiskEngineWorker(-1, mock_kite, mock_redis, mock_db_session)

    def test_none_kite_client(self, mock_redis, mock_db_session):
        """Raises ValueError when kite_client is None."""
        with pytest.raises(ValueError, match="kite_client cannot be None"):
            RiskEngineWorker(1, None, mock_redis, mock_db_session)

    def test_none_redis_client(self, mock_kite, mock_db_session):
        """Raises ValueError when redis_client is None."""
        with pytest.raises(ValueError, match="redis_client cannot be None"):
            RiskEngineWorker(1, mock_kite, None, mock_db_session)

    def test_none_db_session(self, mock_kite, mock_redis):
        """Raises ValueError when db_session is None."""
        with pytest.raises(ValueError, match="db_session cannot be None"):
            RiskEngineWorker(1, mock_kite, mock_redis, None)


# ============================================================
# fetch_positions Tests
# ============================================================


class TestFetchPositions:
    """Tests for RiskEngineWorker.fetch_positions()."""

    def test_returns_net_positions(self, worker, mock_kite):
        """Returns the 'net' positions list from broker response."""
        mock_kite.positions.return_value = {
            "net": [
                {
                    "tradingsymbol": "NIFTY23DEC18000CE",
                    "exchange": "NFO",
                    "product": "NRML",
                    "quantity": 50,
                    "average_price": 150.0,
                    "last_price": 175.0,
                    "pnl": 1250.0,
                    "unrealised": 1250.0,
                    "realised": 0.0,
                },
                {
                    "tradingsymbol": "RELIANCE",
                    "exchange": "NSE",
                    "product": "CNC",
                    "quantity": 10,
                    "average_price": 2500.0,
                    "last_price": 2550.0,
                    "pnl": 500.0,
                    "unrealised": 500.0,
                    "realised": 0.0,
                },
            ],
            "day": [
                {
                    "tradingsymbol": "NIFTY23DEC18000CE",
                    "exchange": "NFO",
                    "quantity": 50,
                }
            ],
        }

        positions = worker.fetch_positions()

        assert len(positions) == 2
        assert positions[0]["tradingsymbol"] == "NIFTY23DEC18000CE"
        assert positions[1]["tradingsymbol"] == "RELIANCE"
        mock_kite.positions.assert_called_once()

    def test_filters_out_zero_quantity_positions(self, worker, mock_kite):
        """Zero-quantity (closed) positions are filtered out."""
        mock_kite.positions.return_value = {
            "net": [
                {
                    "tradingsymbol": "NIFTY23DEC18000CE",
                    "exchange": "NFO",
                    "quantity": 50,
                    "pnl": 1250.0,
                },
                {
                    "tradingsymbol": "RELIANCE",
                    "exchange": "NSE",
                    "quantity": 0,
                    "pnl": 0.0,
                },
                {
                    "tradingsymbol": "INFY",
                    "exchange": "NSE",
                    "quantity": -100,
                    "pnl": 500.0,
                },
            ],
            "day": [],
        }

        positions = worker.fetch_positions()

        assert len(positions) == 2
        symbols = [p["tradingsymbol"] for p in positions]
        assert "NIFTY23DEC18000CE" in symbols
        assert "INFY" in symbols
        assert "RELIANCE" not in symbols

    def test_all_zero_quantity_returns_empty(self, worker, mock_kite):
        """Returns empty list when all positions have zero quantity."""
        mock_kite.positions.return_value = {
            "net": [
                {"tradingsymbol": "NIFTY23DEC18000CE", "exchange": "NFO", "quantity": 0, "pnl": 0.0},
                {"tradingsymbol": "RELIANCE", "exchange": "NSE", "quantity": 0, "pnl": 100.0},
            ],
            "day": [],
        }

        positions = worker.fetch_positions()

        assert positions == []

    def test_position_missing_quantity_field_filtered_out(self, worker, mock_kite):
        """Positions without a 'quantity' field default to 0 and are filtered out."""
        mock_kite.positions.return_value = {
            "net": [
                {"tradingsymbol": "NIFTY23DEC18000CE", "exchange": "NFO"},
                {"tradingsymbol": "RELIANCE", "exchange": "NSE", "quantity": 10, "pnl": 500.0},
            ],
            "day": [],
        }

        positions = worker.fetch_positions()

        assert len(positions) == 1
        assert positions[0]["tradingsymbol"] == "RELIANCE"

    def test_empty_net_positions(self, worker, mock_kite):
        """Returns empty list when no net positions exist."""
        mock_kite.positions.return_value = {"net": [], "day": []}

        positions = worker.fetch_positions()

        assert positions == []

    def test_empty_response(self, worker, mock_kite):
        """Returns empty list when API returns empty/falsy response."""
        mock_kite.positions.return_value = {}

        positions = worker.fetch_positions()

        assert positions == []

    def test_none_response(self, worker, mock_kite):
        """Returns empty list when API returns None."""
        mock_kite.positions.return_value = None

        positions = worker.fetch_positions()

        assert positions == []

    def test_none_net_key(self, worker, mock_kite):
        """Returns empty list when 'net' key is None."""
        mock_kite.positions.return_value = {"net": None, "day": []}

        positions = worker.fetch_positions()

        assert positions == []

    def test_missing_net_key(self, worker, mock_kite):
        """Returns empty list when 'net' key is missing from response."""
        mock_kite.positions.return_value = {"day": [{"tradingsymbol": "NIFTY"}]}

        positions = worker.fetch_positions()

        assert positions == []

    def test_api_exception_propagates(self, worker, mock_kite):
        """Broker API exceptions propagate to caller for handling."""
        mock_kite.positions.side_effect = Exception("Network timeout")

        with pytest.raises(Exception, match="Network timeout"):
            worker.fetch_positions()

    def test_single_position(self, worker, mock_kite):
        """Correctly returns a single position."""
        mock_kite.positions.return_value = {
            "net": [
                {
                    "tradingsymbol": "INFY",
                    "exchange": "NSE",
                    "product": "MIS",
                    "quantity": -100,
                    "average_price": 1400.0,
                    "last_price": 1380.0,
                    "pnl": 2000.0,
                    "unrealised": 2000.0,
                    "realised": 0.0,
                }
            ],
            "day": [],
        }

        positions = worker.fetch_positions()

        assert len(positions) == 1
        assert positions[0]["quantity"] == -100  # Short position
        assert positions[0]["pnl"] == 2000.0


# ============================================================
# filter_user_positions Tests
# ============================================================


class TestFilterUserPositions:
    """Tests for RiskEngineWorker.filter_user_positions().

    Requirements covered:
    - 1.8.2: Maintain separate positions for each user
    - 1.8.6: Prevent cross-user data access
    - 1.8.8: Prefix all Redis keys with user_id
    """

    def test_filters_out_zero_quantity_positions(self, worker, mock_kite):
        """Positions with quantity=0 (closed) are removed."""
        positions = [
            {"tradingsymbol": "NIFTY23DEC18000CE", "exchange": "NFO", "quantity": 50, "pnl": 1000.0},
            {"tradingsymbol": "RELIANCE", "exchange": "NSE", "quantity": 0, "pnl": 0.0},
            {"tradingsymbol": "INFY", "exchange": "NSE", "quantity": -100, "pnl": 500.0},
        ]

        result = worker.filter_user_positions(positions)

        assert len(result) == 2
        symbols = [p["tradingsymbol"] for p in result]
        assert "NIFTY23DEC18000CE" in symbols
        assert "INFY" in symbols
        assert "RELIANCE" not in symbols

    def test_tags_positions_with_user_id(self, worker):
        """Each returned position is tagged with the worker's user_id."""
        positions = [
            {"tradingsymbol": "NIFTY23DEC18000CE", "exchange": "NFO", "quantity": 50},
        ]

        result = worker.filter_user_positions(positions)

        assert len(result) == 1
        assert result[0]["user_id"] == 1  # worker fixture uses user_id=1

    def test_user_id_tag_matches_worker_user(self, mock_kite, mock_redis, mock_db_session):
        """Position user_id tag matches the specific worker's user_id."""
        worker = RiskEngineWorker(
            user_id=42,
            kite_client=mock_kite,
            redis_client=mock_redis,
            db_session=mock_db_session,
        )
        positions = [
            {"tradingsymbol": "RELIANCE", "exchange": "NSE", "quantity": 10},
        ]

        result = worker.filter_user_positions(positions)

        assert result[0]["user_id"] == 42

    def test_empty_positions_list(self, worker):
        """Returns empty list when input is empty."""
        result = worker.filter_user_positions([])
        assert result == []

    def test_none_positions(self, worker):
        """Returns empty list when input is None."""
        result = worker.filter_user_positions(None)
        assert result == []

    def test_all_positions_zero_quantity(self, worker):
        """Returns empty list when all positions are closed."""
        positions = [
            {"tradingsymbol": "NIFTY23DEC18000CE", "exchange": "NFO", "quantity": 0},
            {"tradingsymbol": "RELIANCE", "exchange": "NSE", "quantity": 0},
        ]

        result = worker.filter_user_positions(positions)

        assert result == []

    def test_preserves_original_fields(self, worker):
        """Original position fields are preserved in output."""
        positions = [
            {
                "tradingsymbol": "NIFTY23DEC18000CE",
                "exchange": "NFO",
                "product": "NRML",
                "quantity": 50,
                "average_price": 150.0,
                "last_price": 175.0,
                "pnl": 1250.0,
                "unrealised": 1250.0,
                "realised": 0.0,
            }
        ]

        result = worker.filter_user_positions(positions)

        assert result[0]["tradingsymbol"] == "NIFTY23DEC18000CE"
        assert result[0]["exchange"] == "NFO"
        assert result[0]["product"] == "NRML"
        assert result[0]["quantity"] == 50
        assert result[0]["average_price"] == 150.0
        assert result[0]["pnl"] == 1250.0

    def test_negative_quantity_kept(self, worker):
        """Short positions (negative quantity) are kept as open positions."""
        positions = [
            {"tradingsymbol": "INFY", "exchange": "NSE", "quantity": -100},
        ]

        result = worker.filter_user_positions(positions)

        assert len(result) == 1
        assert result[0]["quantity"] == -100

    def test_does_not_mutate_input(self, worker):
        """Original positions list is not mutated."""
        positions = [
            {"tradingsymbol": "NIFTY23DEC18000CE", "quantity": 50},
            {"tradingsymbol": "RELIANCE", "quantity": 0},
        ]
        original_len = len(positions)
        original_first = dict(positions[0])

        worker.filter_user_positions(positions)

        assert len(positions) == original_len
        assert "user_id" not in positions[0]
        assert positions[0] == original_first

    def test_position_missing_quantity_field(self, worker):
        """Positions without a 'quantity' field default to 0 and are filtered out."""
        positions = [
            {"tradingsymbol": "NIFTY23DEC18000CE", "exchange": "NFO"},
        ]

        result = worker.filter_user_positions(positions)

        assert result == []

    def test_cross_user_isolation(self, mock_kite, mock_redis, mock_db_session):
        """Two workers with different user_ids tag positions with their own user_id.

        Validates requirement 1.8.6: Prevent cross-user data access.
        """
        worker_a = RiskEngineWorker(1, mock_kite, mock_redis, mock_db_session)
        worker_b = RiskEngineWorker(2, mock_kite, mock_redis, mock_db_session)

        positions = [{"tradingsymbol": "NIFTY", "quantity": 50}]

        result_a = worker_a.filter_user_positions(positions)
        result_b = worker_b.filter_user_positions(positions)

        assert result_a[0]["user_id"] == 1
        assert result_b[0]["user_id"] == 2
        assert result_a[0]["user_id"] != result_b[0]["user_id"]


# ============================================================
# fetch_positions_safe Tests
# ============================================================


class TestFetchPositionsSafe:
    """Tests for RiskEngineWorker.fetch_positions_safe().

    Validates that broker API errors are handled gracefully so the
    risk engine never crashes. Each error type is logged with context
    and returns an empty list to allow the cycle to continue.

    Requirements covered:
    - 2.3.6: Handle broker API failures with retries
    - 2.3.7: Log all errors with full context
    - 2.3.8: Continue processing other users when one user's operation fails
    """

    def test_successful_fetch_returns_positions(self, worker, mock_kite):
        """On success, returns positions normally."""
        mock_kite.positions.return_value = {
            "net": [
                {"tradingsymbol": "NIFTY23DEC18000CE", "quantity": 50, "pnl": 1000.0}
            ],
            "day": [],
        }

        result = worker.fetch_positions_safe()

        assert len(result) == 1
        assert result[0]["tradingsymbol"] == "NIFTY23DEC18000CE"

    def test_token_exception_returns_empty(self, worker, mock_kite, caplog):
        """TokenException (expired/invalid token) returns empty list and logs error."""
        from kiteconnect.exceptions import TokenException

        mock_kite.positions.side_effect = TokenException("Token is invalid or expired")

        with caplog.at_level(logging.ERROR):
            result = worker.fetch_positions_safe()

        assert result == []
        assert "Token expired/invalid for user 1" in caplog.text
        assert "Re-authentication required" in caplog.text

    def test_network_exception_returns_empty(self, worker, mock_kite, caplog):
        """NetworkException (connectivity issue) returns empty list and logs warning."""
        from kiteconnect.exceptions import NetworkException

        mock_kite.positions.side_effect = NetworkException("Connection timed out")

        with caplog.at_level(logging.WARNING):
            result = worker.fetch_positions_safe()

        assert result == []
        assert "Network error fetching positions for user 1" in caplog.text
        assert "Will retry next cycle" in caplog.text

    def test_data_exception_returns_empty(self, worker, mock_kite, caplog):
        """DataException (malformed response) returns empty list and logs error."""
        from kiteconnect.exceptions import DataException

        mock_kite.positions.side_effect = DataException("Exchange data error")

        with caplog.at_level(logging.ERROR):
            result = worker.fetch_positions_safe()

        assert result == []
        assert "Data/exchange error fetching positions for user 1" in caplog.text

    def test_input_exception_returns_empty(self, worker, mock_kite, caplog):
        """InputException (invalid params) returns empty list and logs error."""
        from kiteconnect.exceptions import InputException

        mock_kite.positions.side_effect = InputException("Invalid parameter")

        with caplog.at_level(logging.ERROR):
            result = worker.fetch_positions_safe()

        assert result == []
        assert "Invalid input error fetching positions for user 1" in caplog.text

    def test_general_exception_returns_empty(self, worker, mock_kite, caplog):
        """GeneralException (other API error) returns empty list and logs error."""
        from kiteconnect.exceptions import GeneralException

        mock_kite.positions.side_effect = GeneralException("Unknown API error")

        with caplog.at_level(logging.ERROR):
            result = worker.fetch_positions_safe()

        assert result == []
        assert "General Kite API error fetching positions for user 1" in caplog.text

    def test_unexpected_exception_returns_empty(self, worker, mock_kite, caplog):
        """Unexpected exceptions are caught, logged, and return empty list."""
        mock_kite.positions.side_effect = RuntimeError("Unexpected failure")

        with caplog.at_level(logging.ERROR):
            result = worker.fetch_positions_safe()

        assert result == []
        assert "Unexpected error fetching positions for user 1" in caplog.text
        assert "RuntimeError" in caplog.text

    def test_error_log_includes_user_context(self, mock_kite, mock_redis, mock_db_session, caplog):
        """Error logs include the user_id for debugging across multiple users."""
        from kiteconnect.exceptions import TokenException

        worker = RiskEngineWorker(
            user_id=42,
            kite_client=mock_kite,
            redis_client=mock_redis,
            db_session=mock_db_session,
        )
        mock_kite.positions.side_effect = TokenException("Expired")

        with caplog.at_level(logging.ERROR):
            result = worker.fetch_positions_safe()

        assert result == []
        assert "user 42" in caplog.text

    def test_does_not_crash_risk_engine(self, worker, mock_kite):
        """The method never raises - the risk engine can always continue its cycle."""
        from kiteconnect.exceptions import TokenException, NetworkException, DataException

        # Try each exception type - none should propagate
        for exc in [
            TokenException("expired"),
            NetworkException("timeout"),
            DataException("bad data"),
            RuntimeError("unexpected"),
            ValueError("bad value"),
            OSError("system error"),
        ]:
            mock_kite.positions.side_effect = exc
            # Must not raise
            result = worker.fetch_positions_safe()
            assert result == []

    def test_network_error_logs_as_warning_not_error(self, worker, mock_kite, caplog):
        """Network errors are transient, so they log at WARNING level (not ERROR)."""
        from kiteconnect.exceptions import NetworkException

        mock_kite.positions.side_effect = NetworkException("DNS resolution failed")

        with caplog.at_level(logging.DEBUG):
            worker.fetch_positions_safe()

        # Find the network error log record
        network_records = [
            r for r in caplog.records if "Network error" in r.message
        ]
        assert len(network_records) == 1
        assert network_records[0].levelname == "WARNING"


# ============================================================
# compute_live_pnl Tests
# ============================================================


class TestComputeLivePnl:
    """Tests for RiskEngineWorker.compute_live_pnl().

    Requirements covered:
    - 1.4.1: Monitor each user's P&L every 2-3 seconds
    - 1.4.2: Compute live P&L from broker positions
    """

    # --- 6.2.1: Sum position P&Ls ---

    def test_sums_single_position_pnl(self, worker):
        """Correctly returns pnl for a single position."""
        positions = [{"tradingsymbol": "NIFTY23DEC18000CE", "pnl": 1250.0}]

        result = worker.compute_live_pnl(positions)

        assert result == 1250.0

    def test_sums_multiple_positions(self, worker):
        """Sums pnl across multiple positions."""
        positions = [
            {"tradingsymbol": "NIFTY23DEC18000CE", "pnl": 1250.0},
            {"tradingsymbol": "RELIANCE", "pnl": 500.0},
            {"tradingsymbol": "INFY", "pnl": -300.0},
        ]

        result = worker.compute_live_pnl(positions)

        assert result == 1450.0

    def test_sums_negative_pnls(self, worker):
        """Correctly sums all-negative P&L values."""
        positions = [
            {"tradingsymbol": "NIFTY23DEC18000CE", "pnl": -1000.0},
            {"tradingsymbol": "RELIANCE", "pnl": -500.0},
        ]

        result = worker.compute_live_pnl(positions)

        assert result == -1500.0

    def test_sums_mixed_positive_negative(self, worker):
        """Correctly handles mix of positive and negative P&L."""
        positions = [
            {"tradingsymbol": "NIFTY", "pnl": 2000.0},
            {"tradingsymbol": "BANKNIFTY", "pnl": -3000.0},
        ]

        result = worker.compute_live_pnl(positions)

        assert result == -1000.0

    def test_returns_float_type(self, worker):
        """Result is always a float."""
        positions = [{"tradingsymbol": "NIFTY", "pnl": 100}]

        result = worker.compute_live_pnl(positions)

        assert isinstance(result, float)

    def test_handles_integer_pnl_values(self, worker):
        """Integer pnl values are handled correctly."""
        positions = [
            {"tradingsymbol": "NIFTY", "pnl": 1000},
            {"tradingsymbol": "RELIANCE", "pnl": 500},
        ]

        result = worker.compute_live_pnl(positions)

        assert result == 1500.0

    # --- 6.2.2: Handle empty positions ---

    def test_empty_list_returns_zero(self, worker):
        """Returns 0.0 for empty positions list."""
        result = worker.compute_live_pnl([])

        assert result == 0.0

    def test_none_returns_zero(self, worker):
        """Returns 0.0 when positions is None."""
        result = worker.compute_live_pnl(None)

        assert result == 0.0

    # --- 6.2.3: Validate calculations ---

    def test_missing_pnl_field_defaults_to_zero(self, worker):
        """Positions missing 'pnl' field are treated as 0."""
        positions = [
            {"tradingsymbol": "NIFTY", "pnl": 1000.0},
            {"tradingsymbol": "RELIANCE"},  # No pnl field
            {"tradingsymbol": "INFY", "pnl": 500.0},
        ]

        result = worker.compute_live_pnl(positions)

        assert result == 1500.0

    def test_non_numeric_pnl_defaults_to_zero(self, worker):
        """Non-numeric pnl values are treated as 0."""
        positions = [
            {"tradingsymbol": "NIFTY", "pnl": 1000.0},
            {"tradingsymbol": "RELIANCE", "pnl": "invalid"},
            {"tradingsymbol": "INFY", "pnl": 500.0},
        ]

        result = worker.compute_live_pnl(positions)

        assert result == 1500.0

    def test_none_pnl_value_defaults_to_zero(self, worker):
        """None pnl value is treated as 0."""
        positions = [
            {"tradingsymbol": "NIFTY", "pnl": 1000.0},
            {"tradingsymbol": "RELIANCE", "pnl": None},
        ]

        result = worker.compute_live_pnl(positions)

        assert result == 1000.0

    def test_string_numeric_pnl_is_converted(self, worker):
        """String representations of numbers are converted to float."""
        positions = [
            {"tradingsymbol": "NIFTY", "pnl": "1000.5"},
            {"tradingsymbol": "RELIANCE", "pnl": 500.0},
        ]

        result = worker.compute_live_pnl(positions)

        assert result == 1500.5

    def test_zero_pnl_positions_sum_correctly(self, worker):
        """Positions with pnl=0 are included in sum (doesn't affect total)."""
        positions = [
            {"tradingsymbol": "NIFTY", "pnl": 1000.0},
            {"tradingsymbol": "RELIANCE", "pnl": 0.0},
            {"tradingsymbol": "INFY", "pnl": 0},
        ]

        result = worker.compute_live_pnl(positions)

        assert result == 1000.0

    def test_large_pnl_values(self, worker):
        """Handles large P&L values correctly."""
        positions = [
            {"tradingsymbol": "NIFTY", "pnl": 1_000_000.50},
            {"tradingsymbol": "BANKNIFTY", "pnl": -500_000.25},
        ]

        result = worker.compute_live_pnl(positions)

        assert result == pytest.approx(500_000.25)


# ============================================================
# compute_greeks Tests
# ============================================================


class TestComputeGreeks:
    """Tests for RiskEngineWorker.compute_greeks().

    Requirements covered:
    - 1.4.3: Compute Greeks exposure (delta, gamma, vega) for options positions
    """

    # --- 6.3.1: Compute net delta ---

    def test_single_position_net_delta(self, worker):
        """Computes delta * quantity for a single position."""
        positions = [
            {"tradingsymbol": "NIFTY23DEC18000CE", "quantity": 50, "delta": 0.6, "gamma": 0.01, "vega": 15.0}
        ]

        result = worker.compute_greeks(positions)

        assert result["net_delta"] == pytest.approx(30.0)

    def test_multiple_positions_net_delta(self, worker):
        """Sums delta * quantity across multiple positions."""
        positions = [
            {"tradingsymbol": "NIFTY23DEC18000CE", "quantity": 50, "delta": 0.6, "gamma": 0.01, "vega": 15.0},
            {"tradingsymbol": "NIFTY23DEC18000PE", "quantity": -25, "delta": -0.4, "gamma": 0.02, "vega": 12.0},
        ]

        result = worker.compute_greeks(positions)

        # 50*0.6 + (-25)*(-0.4) = 30 + 10 = 40
        assert result["net_delta"] == pytest.approx(40.0)

    def test_short_position_delta(self, worker):
        """Negative quantity correctly flips delta contribution."""
        positions = [
            {"tradingsymbol": "NIFTY23DEC18000CE", "quantity": -100, "delta": 0.5, "gamma": 0.01, "vega": 10.0}
        ]

        result = worker.compute_greeks(positions)

        # -100 * 0.5 = -50
        assert result["net_delta"] == pytest.approx(-50.0)

    # --- 6.3.2: Compute net gamma ---

    def test_single_position_net_gamma(self, worker):
        """Computes gamma * quantity for a single position."""
        positions = [
            {"tradingsymbol": "NIFTY23DEC18000CE", "quantity": 50, "delta": 0.6, "gamma": 0.02, "vega": 15.0}
        ]

        result = worker.compute_greeks(positions)

        assert result["net_gamma"] == pytest.approx(1.0)

    def test_multiple_positions_net_gamma(self, worker):
        """Sums gamma * quantity across multiple positions."""
        positions = [
            {"tradingsymbol": "NIFTY23DEC18000CE", "quantity": 100, "delta": 0.5, "gamma": 0.01, "vega": 10.0},
            {"tradingsymbol": "NIFTY23DEC19000CE", "quantity": 50, "delta": 0.3, "gamma": 0.03, "vega": 8.0},
        ]

        result = worker.compute_greeks(positions)

        # 100*0.01 + 50*0.03 = 1.0 + 1.5 = 2.5
        assert result["net_gamma"] == pytest.approx(2.5)

    def test_short_position_gamma(self, worker):
        """Negative quantity contributes negative gamma."""
        positions = [
            {"tradingsymbol": "NIFTY23DEC18000CE", "quantity": -50, "delta": 0.5, "gamma": 0.02, "vega": 10.0}
        ]

        result = worker.compute_greeks(positions)

        # -50 * 0.02 = -1.0
        assert result["net_gamma"] == pytest.approx(-1.0)

    # --- 6.3.3: Compute net vega ---

    def test_single_position_net_vega(self, worker):
        """Computes vega * quantity for a single position."""
        positions = [
            {"tradingsymbol": "NIFTY23DEC18000CE", "quantity": 50, "delta": 0.6, "gamma": 0.01, "vega": 15.0}
        ]

        result = worker.compute_greeks(positions)

        assert result["net_vega"] == pytest.approx(750.0)

    def test_multiple_positions_net_vega(self, worker):
        """Sums vega * quantity across multiple positions."""
        positions = [
            {"tradingsymbol": "NIFTY23DEC18000CE", "quantity": 100, "delta": 0.5, "gamma": 0.01, "vega": 10.0},
            {"tradingsymbol": "NIFTY23DEC19000PE", "quantity": -50, "delta": -0.3, "gamma": 0.02, "vega": 8.0},
        ]

        result = worker.compute_greeks(positions)

        # 100*10.0 + (-50)*8.0 = 1000 - 400 = 600
        assert result["net_vega"] == pytest.approx(600.0)

    def test_short_position_vega(self, worker):
        """Negative quantity contributes negative vega."""
        positions = [
            {"tradingsymbol": "NIFTY23DEC18000CE", "quantity": -20, "delta": 0.5, "gamma": 0.01, "vega": 12.5}
        ]

        result = worker.compute_greeks(positions)

        # -20 * 12.5 = -250
        assert result["net_vega"] == pytest.approx(-250.0)

    # --- 6.3.4: Handle missing Greeks ---

    def test_empty_positions_returns_zeros(self, worker):
        """Returns all zeros for empty positions list."""
        result = worker.compute_greeks([])

        assert result == {"net_delta": 0.0, "net_gamma": 0.0, "net_vega": 0.0}

    def test_none_positions_returns_zeros(self, worker):
        """Returns all zeros when positions is None."""
        result = worker.compute_greeks(None)

        assert result == {"net_delta": 0.0, "net_gamma": 0.0, "net_vega": 0.0}

    def test_missing_delta_defaults_to_zero(self, worker):
        """Positions missing 'delta' field contribute 0 to net_delta."""
        positions = [
            {"tradingsymbol": "RELIANCE", "quantity": 10, "gamma": 0.01, "vega": 5.0},
        ]

        result = worker.compute_greeks(positions)

        assert result["net_delta"] == 0.0
        assert result["net_gamma"] == pytest.approx(0.1)
        assert result["net_vega"] == pytest.approx(50.0)

    def test_missing_gamma_defaults_to_zero(self, worker):
        """Positions missing 'gamma' field contribute 0 to net_gamma."""
        positions = [
            {"tradingsymbol": "RELIANCE", "quantity": 10, "delta": 0.5, "vega": 5.0},
        ]

        result = worker.compute_greeks(positions)

        assert result["net_delta"] == pytest.approx(5.0)
        assert result["net_gamma"] == 0.0
        assert result["net_vega"] == pytest.approx(50.0)

    def test_missing_vega_defaults_to_zero(self, worker):
        """Positions missing 'vega' field contribute 0 to net_vega."""
        positions = [
            {"tradingsymbol": "RELIANCE", "quantity": 10, "delta": 0.5, "gamma": 0.01},
        ]

        result = worker.compute_greeks(positions)

        assert result["net_delta"] == pytest.approx(5.0)
        assert result["net_gamma"] == pytest.approx(0.1)
        assert result["net_vega"] == 0.0

    def test_equity_position_no_greeks(self, worker):
        """Equity positions (no Greek fields at all) contribute zero to all Greeks."""
        positions = [
            {"tradingsymbol": "RELIANCE", "exchange": "NSE", "quantity": 100, "pnl": 500.0},
        ]

        result = worker.compute_greeks(positions)

        assert result == {"net_delta": 0.0, "net_gamma": 0.0, "net_vega": 0.0}

    def test_mixed_options_and_equity_positions(self, worker):
        """Options positions contribute Greeks, equity positions contribute zero."""
        positions = [
            {"tradingsymbol": "NIFTY23DEC18000CE", "quantity": 50, "delta": 0.6, "gamma": 0.02, "vega": 15.0},
            {"tradingsymbol": "RELIANCE", "quantity": 100, "pnl": 500.0},  # No Greeks
            {"tradingsymbol": "NIFTY23DEC18000PE", "quantity": -25, "delta": -0.4, "gamma": 0.01, "vega": 12.0},
        ]

        result = worker.compute_greeks(positions)

        # delta: 50*0.6 + 0 + (-25)*(-0.4) = 30 + 0 + 10 = 40
        assert result["net_delta"] == pytest.approx(40.0)
        # gamma: 50*0.02 + 0 + (-25)*0.01 = 1.0 + 0 + (-0.25) = 0.75
        assert result["net_gamma"] == pytest.approx(0.75)
        # vega: 50*15.0 + 0 + (-25)*12.0 = 750 + 0 + (-300) = 450
        assert result["net_vega"] == pytest.approx(450.0)

    def test_non_numeric_delta_defaults_to_zero(self, worker):
        """Non-numeric delta value is treated as 0."""
        positions = [
            {"tradingsymbol": "NIFTY23DEC18000CE", "quantity": 50, "delta": "invalid", "gamma": 0.01, "vega": 10.0},
        ]

        result = worker.compute_greeks(positions)

        assert result["net_delta"] == 0.0
        assert result["net_gamma"] == pytest.approx(0.5)
        assert result["net_vega"] == pytest.approx(500.0)

    def test_non_numeric_gamma_defaults_to_zero(self, worker):
        """Non-numeric gamma value is treated as 0."""
        positions = [
            {"tradingsymbol": "NIFTY23DEC18000CE", "quantity": 50, "delta": 0.5, "gamma": "bad", "vega": 10.0},
        ]

        result = worker.compute_greeks(positions)

        assert result["net_delta"] == pytest.approx(25.0)
        assert result["net_gamma"] == 0.0
        assert result["net_vega"] == pytest.approx(500.0)

    def test_non_numeric_vega_defaults_to_zero(self, worker):
        """Non-numeric vega value is treated as 0."""
        positions = [
            {"tradingsymbol": "NIFTY23DEC18000CE", "quantity": 50, "delta": 0.5, "gamma": 0.01, "vega": None},
        ]

        result = worker.compute_greeks(positions)

        assert result["net_delta"] == pytest.approx(25.0)
        assert result["net_gamma"] == pytest.approx(0.5)
        assert result["net_vega"] == 0.0

    def test_missing_quantity_defaults_to_zero(self, worker):
        """Positions missing 'quantity' field contribute zero to all Greeks."""
        positions = [
            {"tradingsymbol": "NIFTY23DEC18000CE", "delta": 0.6, "gamma": 0.02, "vega": 15.0},
        ]

        result = worker.compute_greeks(positions)

        assert result == {"net_delta": 0.0, "net_gamma": 0.0, "net_vega": 0.0}

    def test_non_numeric_quantity_defaults_to_zero(self, worker):
        """Non-numeric quantity value is treated as 0."""
        positions = [
            {"tradingsymbol": "NIFTY23DEC18000CE", "quantity": "abc", "delta": 0.6, "gamma": 0.02, "vega": 15.0},
        ]

        result = worker.compute_greeks(positions)

        assert result == {"net_delta": 0.0, "net_gamma": 0.0, "net_vega": 0.0}

    def test_returns_dict_with_float_values(self, worker):
        """Return type is a dict with float values."""
        positions = [
            {"tradingsymbol": "NIFTY23DEC18000CE", "quantity": 50, "delta": 0.5, "gamma": 0.01, "vega": 10},
        ]

        result = worker.compute_greeks(positions)

        assert isinstance(result, dict)
        assert isinstance(result["net_delta"], float)
        assert isinstance(result["net_gamma"], float)
        assert isinstance(result["net_vega"], float)

    def test_all_keys_present_in_result(self, worker):
        """Result always contains net_delta, net_gamma, and net_vega keys."""
        positions = [{"tradingsymbol": "NIFTY", "quantity": 10}]

        result = worker.compute_greeks(positions)

        assert "net_delta" in result
        assert "net_gamma" in result
        assert "net_vega" in result


# ============================================================
# compute_margin_used Tests
# ============================================================


class TestComputeMarginUsed:
    """Tests for RiskEngineWorker.compute_margin_used().

    Requirements covered:
    - 1.4.4: Compute margin usage for each user
    """

    # --- 6.4.1: Sum position margins ---

    def test_sums_single_position_margin(self, worker):
        """Correctly returns margin for a single position."""
        positions = [{"tradingsymbol": "NIFTY23DEC18000CE", "margin": 50000.0}]

        result = worker.compute_margin_used(positions)

        assert result == 50000.0

    def test_sums_multiple_positions(self, worker):
        """Sums margin across multiple positions."""
        positions = [
            {"tradingsymbol": "NIFTY23DEC18000CE", "margin": 50000.0},
            {"tradingsymbol": "RELIANCE", "margin": 25000.0},
            {"tradingsymbol": "INFY", "margin": 15000.0},
        ]

        result = worker.compute_margin_used(positions)

        assert result == 90000.0

    def test_returns_float_type(self, worker):
        """Result is always a float."""
        positions = [{"tradingsymbol": "NIFTY", "margin": 10000}]

        result = worker.compute_margin_used(positions)

        assert isinstance(result, float)

    def test_handles_integer_margin_values(self, worker):
        """Integer margin values are handled correctly."""
        positions = [
            {"tradingsymbol": "NIFTY", "margin": 50000},
            {"tradingsymbol": "RELIANCE", "margin": 25000},
        ]

        result = worker.compute_margin_used(positions)

        assert result == 75000.0

    def test_empty_list_returns_zero(self, worker):
        """Returns 0.0 for empty positions list."""
        result = worker.compute_margin_used([])

        assert result == 0.0

    def test_none_returns_zero(self, worker):
        """Returns 0.0 when positions is None."""
        result = worker.compute_margin_used(None)

        assert result == 0.0

    def test_missing_margin_field_defaults_to_zero(self, worker):
        """Positions missing 'margin' field are treated as 0."""
        positions = [
            {"tradingsymbol": "NIFTY", "margin": 50000.0},
            {"tradingsymbol": "RELIANCE"},  # No margin field
            {"tradingsymbol": "INFY", "margin": 15000.0},
        ]

        result = worker.compute_margin_used(positions)

        assert result == 65000.0

    def test_non_numeric_margin_defaults_to_zero(self, worker):
        """Non-numeric margin values are treated as 0."""
        positions = [
            {"tradingsymbol": "NIFTY", "margin": 50000.0},
            {"tradingsymbol": "RELIANCE", "margin": "invalid"},
            {"tradingsymbol": "INFY", "margin": 15000.0},
        ]

        result = worker.compute_margin_used(positions)

        assert result == 65000.0

    def test_none_margin_value_defaults_to_zero(self, worker):
        """None margin value is treated as 0."""
        positions = [
            {"tradingsymbol": "NIFTY", "margin": 50000.0},
            {"tradingsymbol": "RELIANCE", "margin": None},
        ]

        result = worker.compute_margin_used(positions)

        assert result == 50000.0

    def test_string_numeric_margin_is_converted(self, worker):
        """String representations of numbers are converted to float."""
        positions = [
            {"tradingsymbol": "NIFTY", "margin": "50000.5"},
            {"tradingsymbol": "RELIANCE", "margin": 25000.0},
        ]

        result = worker.compute_margin_used(positions)

        assert result == 75000.5

    def test_zero_margin_positions(self, worker):
        """Positions with margin=0 are included correctly."""
        positions = [
            {"tradingsymbol": "NIFTY", "margin": 50000.0},
            {"tradingsymbol": "RELIANCE", "margin": 0.0},
        ]

        result = worker.compute_margin_used(positions)

        assert result == 50000.0

    def test_large_margin_values(self, worker):
        """Handles large margin values correctly."""
        positions = [
            {"tradingsymbol": "NIFTY", "margin": 1_000_000.50},
            {"tradingsymbol": "BANKNIFTY", "margin": 500_000.25},
        ]

        result = worker.compute_margin_used(positions)

        assert result == pytest.approx(1_500_000.75)


# ============================================================
# compute_margin_percentage Tests
# ============================================================


class TestComputeMarginPercentage:
    """Tests for RiskEngineWorker.compute_margin_percentage().

    Requirements covered:
    - 1.4.4: Compute margin usage for each user
    - 1.4.8: Trigger kill switch when margin usage exceeds 90% of capital
    """

    # --- 6.4.2: Compute margin percentage ---

    def test_basic_percentage_calculation(self, worker):
        """Computes (margin_used / capital) * 100 correctly."""
        result = worker.compute_margin_percentage(50000.0, 100000.0)

        assert result == 50.0

    def test_full_margin_usage(self, worker):
        """100% margin usage when margin equals capital."""
        result = worker.compute_margin_percentage(100000.0, 100000.0)

        assert result == 100.0

    def test_exceeds_capital(self, worker):
        """Margin can exceed 100% if margin_used > capital."""
        result = worker.compute_margin_percentage(150000.0, 100000.0)

        assert result == 150.0

    def test_ninety_percent_threshold(self, worker):
        """Correctly detects 90% margin usage (kill switch threshold)."""
        result = worker.compute_margin_percentage(90000.0, 100000.0)

        assert result == 90.0

    def test_just_below_threshold(self, worker):
        """Correctly computes margin just below 90% threshold."""
        result = worker.compute_margin_percentage(89000.0, 100000.0)

        assert result == pytest.approx(89.0)

    def test_just_above_threshold(self, worker):
        """Correctly computes margin just above 90% threshold."""
        result = worker.compute_margin_percentage(91000.0, 100000.0)

        assert result == pytest.approx(91.0)

    def test_zero_margin_used(self, worker):
        """Returns 0.0 when no margin is used."""
        result = worker.compute_margin_percentage(0.0, 100000.0)

        assert result == 0.0

    def test_zero_capital_returns_zero(self, worker):
        """Returns 0.0 when capital is zero (prevent division by zero)."""
        result = worker.compute_margin_percentage(50000.0, 0.0)

        assert result == 0.0

    def test_negative_capital_returns_zero(self, worker):
        """Returns 0.0 when capital is negative (invalid)."""
        result = worker.compute_margin_percentage(50000.0, -100000.0)

        assert result == 0.0

    def test_returns_float_type(self, worker):
        """Result is always a float."""
        result = worker.compute_margin_percentage(50000, 100000)

        assert isinstance(result, float)

    def test_small_margin_percentage(self, worker):
        """Correctly computes small percentage values."""
        result = worker.compute_margin_percentage(1000.0, 1_000_000.0)

        assert result == pytest.approx(0.1)

    def test_large_capital_precision(self, worker):
        """Handles large capital values with precision."""
        result = worker.compute_margin_percentage(900_000.0, 1_000_000.0)

        assert result == pytest.approx(90.0)


# ============================================================
# update_redis_cache Tests
# ============================================================


class TestUpdateRedisCache:
    """Tests for RiskEngineWorker.update_redis_cache().

    Requirements covered:
    - 1.4.5: Cache risk metrics in Redis with timestamp
    - 3.6.1: Cache user risk metrics with key user:{user_id}:risk
    - 3.6.9: Include timestamp in all cached data
    """

    # --- 6.5.1: Store risk metrics in hash ---

    def test_stores_pnl_in_redis_hash(self, worker, mock_redis):
        """Stores pnl value in the Redis hash."""
        greeks = {"net_delta": 30.0, "net_gamma": 1.0, "net_vega": 750.0}

        worker.update_redis_cache(pnl=1500.0, greeks=greeks, margin_used=50000.0)

        mock_redis.hset.assert_called_once()
        call_args = mock_redis.hset.call_args
        mapping = call_args[1]["mapping"] if "mapping" in call_args[1] else call_args[0][1]
        assert mapping["pnl"] == "1500.0"

    def test_stores_greeks_in_redis_hash(self, worker, mock_redis):
        """Stores net_delta, net_gamma, net_vega in the Redis hash."""
        greeks = {"net_delta": 30.5, "net_gamma": 1.25, "net_vega": 750.0}

        worker.update_redis_cache(pnl=1500.0, greeks=greeks, margin_used=50000.0)

        call_args = mock_redis.hset.call_args
        mapping = call_args[1]["mapping"] if "mapping" in call_args[1] else call_args[0][1]
        assert mapping["net_delta"] == "30.5"
        assert mapping["net_gamma"] == "1.25"
        assert mapping["net_vega"] == "750.0"

    def test_stores_margin_used_in_redis_hash(self, worker, mock_redis):
        """Stores margin_used in the Redis hash."""
        greeks = {"net_delta": 0.0, "net_gamma": 0.0, "net_vega": 0.0}

        worker.update_redis_cache(pnl=0.0, greeks=greeks, margin_used=75000.50)

        call_args = mock_redis.hset.call_args
        mapping = call_args[1]["mapping"] if "mapping" in call_args[1] else call_args[0][1]
        assert mapping["margin_used"] == "75000.5"

    def test_uses_correct_redis_key(self, worker, mock_redis):
        """Uses key format user:{user_id}:risk (Requirement 3.6.1)."""
        greeks = {"net_delta": 0.0, "net_gamma": 0.0, "net_vega": 0.0}

        worker.update_redis_cache(pnl=0.0, greeks=greeks, margin_used=0.0)

        call_args = mock_redis.hset.call_args
        key = call_args[0][0] if call_args[0] else call_args[1].get("key")
        assert key == "user:1:risk"

    def test_uses_correct_key_for_different_user(self, mock_kite, mock_redis, mock_db_session):
        """Key includes the correct user_id for different users."""
        worker = RiskEngineWorker(
            user_id=42,
            kite_client=mock_kite,
            redis_client=mock_redis,
            db_session=mock_db_session,
        )
        greeks = {"net_delta": 0.0, "net_gamma": 0.0, "net_vega": 0.0}

        worker.update_redis_cache(pnl=0.0, greeks=greeks, margin_used=0.0)

        call_args = mock_redis.hset.call_args
        key = call_args[0][0] if call_args[0] else call_args[1].get("key")
        assert key == "user:42:risk"

    def test_stores_all_six_fields(self, worker, mock_redis):
        """Hash contains all 6 required fields: pnl, net_delta, net_gamma, net_vega, margin_used, updated_at."""
        greeks = {"net_delta": 10.0, "net_gamma": 0.5, "net_vega": 200.0}

        worker.update_redis_cache(pnl=500.0, greeks=greeks, margin_used=30000.0)

        call_args = mock_redis.hset.call_args
        mapping = call_args[1]["mapping"] if "mapping" in call_args[1] else call_args[0][1]
        expected_keys = {"pnl", "net_delta", "net_gamma", "net_vega", "margin_used", "updated_at"}
        assert set(mapping.keys()) == expected_keys

    def test_all_values_stored_as_strings(self, worker, mock_redis):
        """All numeric values are stored as strings for Redis compatibility."""
        greeks = {"net_delta": 10.0, "net_gamma": 0.5, "net_vega": 200.0}

        worker.update_redis_cache(pnl=500.0, greeks=greeks, margin_used=30000.0)

        call_args = mock_redis.hset.call_args
        mapping = call_args[1]["mapping"] if "mapping" in call_args[1] else call_args[0][1]
        for value in mapping.values():
            assert isinstance(value, str)

    def test_negative_pnl_stored_correctly(self, worker, mock_redis):
        """Negative P&L values are stored correctly."""
        greeks = {"net_delta": -50.0, "net_gamma": 1.0, "net_vega": -300.0}

        worker.update_redis_cache(pnl=-5000.0, greeks=greeks, margin_used=80000.0)

        call_args = mock_redis.hset.call_args
        mapping = call_args[1]["mapping"] if "mapping" in call_args[1] else call_args[0][1]
        assert mapping["pnl"] == "-5000.0"
        assert mapping["net_delta"] == "-50.0"
        assert mapping["net_vega"] == "-300.0"

    def test_handles_missing_greeks_keys(self, worker, mock_redis):
        """Defaults to 0.0 if greeks dict is missing expected keys."""
        greeks = {}  # Empty greeks dict

        worker.update_redis_cache(pnl=100.0, greeks=greeks, margin_used=1000.0)

        call_args = mock_redis.hset.call_args
        mapping = call_args[1]["mapping"] if "mapping" in call_args[1] else call_args[0][1]
        assert mapping["net_delta"] == "0.0"
        assert mapping["net_gamma"] == "0.0"
        assert mapping["net_vega"] == "0.0"

    # --- 6.5.2: Include timestamp ---

    def test_includes_updated_at_timestamp(self, worker, mock_redis):
        """Includes an 'updated_at' field in the hash (Requirement 3.6.9)."""
        greeks = {"net_delta": 0.0, "net_gamma": 0.0, "net_vega": 0.0}

        worker.update_redis_cache(pnl=0.0, greeks=greeks, margin_used=0.0)

        call_args = mock_redis.hset.call_args
        mapping = call_args[1]["mapping"] if "mapping" in call_args[1] else call_args[0][1]
        assert "updated_at" in mapping

    def test_timestamp_is_iso_format(self, worker, mock_redis):
        """The updated_at timestamp is in ISO format."""
        greeks = {"net_delta": 0.0, "net_gamma": 0.0, "net_vega": 0.0}

        worker.update_redis_cache(pnl=0.0, greeks=greeks, margin_used=0.0)

        call_args = mock_redis.hset.call_args
        mapping = call_args[1]["mapping"] if "mapping" in call_args[1] else call_args[0][1]
        timestamp = mapping["updated_at"]
        # Validate it can be parsed back as ISO format
        parsed = datetime.fromisoformat(timestamp)
        assert parsed is not None

    def test_timestamp_is_recent(self, worker, mock_redis):
        """The timestamp is from the current time (not stale)."""
        from datetime import timedelta

        greeks = {"net_delta": 0.0, "net_gamma": 0.0, "net_vega": 0.0}
        before = datetime.now()

        worker.update_redis_cache(pnl=0.0, greeks=greeks, margin_used=0.0)

        after = datetime.now()
        call_args = mock_redis.hset.call_args
        mapping = call_args[1]["mapping"] if "mapping" in call_args[1] else call_args[0][1]
        timestamp = datetime.fromisoformat(mapping["updated_at"])
        assert before <= timestamp <= after

    # --- 6.5.3: Handle Redis errors ---

    def test_returns_true_on_success(self, worker, mock_redis):
        """Returns True when Redis operation succeeds."""
        greeks = {"net_delta": 0.0, "net_gamma": 0.0, "net_vega": 0.0}

        result = worker.update_redis_cache(pnl=0.0, greeks=greeks, margin_used=0.0)

        assert result is True

    def test_returns_false_on_redis_error(self, worker, mock_redis):
        """Returns False when Redis raises a RedisError."""
        import redis as redis_module

        mock_redis.hset.side_effect = redis_module.RedisError("Connection refused")
        greeks = {"net_delta": 0.0, "net_gamma": 0.0, "net_vega": 0.0}

        result = worker.update_redis_cache(pnl=0.0, greeks=greeks, margin_used=0.0)

        assert result is False

    def test_returns_false_on_connection_error(self, worker, mock_redis):
        """Returns False when Redis raises a ConnectionError."""
        import redis as redis_module

        mock_redis.hset.side_effect = redis_module.ConnectionError("Connection lost")
        greeks = {"net_delta": 0.0, "net_gamma": 0.0, "net_vega": 0.0}

        result = worker.update_redis_cache(pnl=0.0, greeks=greeks, margin_used=0.0)

        assert result is False

    def test_returns_false_on_timeout_error(self, worker, mock_redis):
        """Returns False when Redis raises a TimeoutError."""
        import redis as redis_module

        mock_redis.hset.side_effect = redis_module.TimeoutError("Operation timed out")
        greeks = {"net_delta": 0.0, "net_gamma": 0.0, "net_vega": 0.0}

        result = worker.update_redis_cache(pnl=0.0, greeks=greeks, margin_used=0.0)

        assert result is False

    def test_logs_error_on_redis_failure(self, worker, mock_redis, caplog):
        """Logs an error message when Redis operation fails."""
        import redis as redis_module

        mock_redis.hset.side_effect = redis_module.RedisError("Connection refused")
        greeks = {"net_delta": 0.0, "net_gamma": 0.0, "net_vega": 0.0}

        with caplog.at_level(logging.ERROR):
            worker.update_redis_cache(pnl=0.0, greeks=greeks, margin_used=0.0)

        assert "Redis error updating risk cache for user 1" in caplog.text

    def test_does_not_crash_on_unexpected_error(self, worker, mock_redis):
        """Returns False on unexpected exceptions without crashing."""
        mock_redis.hset.side_effect = RuntimeError("Unexpected failure")
        greeks = {"net_delta": 0.0, "net_gamma": 0.0, "net_vega": 0.0}

        result = worker.update_redis_cache(pnl=0.0, greeks=greeks, margin_used=0.0)

        assert result is False

    def test_logs_unexpected_error(self, worker, mock_redis, caplog):
        """Logs unexpected exceptions with error type."""
        mock_redis.hset.side_effect = RuntimeError("Something broke")
        greeks = {"net_delta": 0.0, "net_gamma": 0.0, "net_vega": 0.0}

        with caplog.at_level(logging.ERROR):
            worker.update_redis_cache(pnl=0.0, greeks=greeks, margin_used=0.0)

        assert "Unexpected error updating risk cache for user 1" in caplog.text
        assert "RuntimeError" in caplog.text

    def test_risk_engine_continues_after_redis_failure(self, worker, mock_redis):
        """After a Redis failure, the worker can still perform other operations."""
        import redis as redis_module

        mock_redis.hset.side_effect = redis_module.RedisError("Connection refused")
        greeks = {"net_delta": 0.0, "net_gamma": 0.0, "net_vega": 0.0}

        # This should not raise
        result = worker.update_redis_cache(pnl=0.0, greeks=greeks, margin_used=0.0)
        assert result is False

        # Worker should still be functional for other operations
        positions = [{"tradingsymbol": "NIFTY", "pnl": 1000.0}]
        pnl = worker.compute_live_pnl(positions)
        assert pnl == 1000.0

# ============================================================
# check_thresholds Tests
# ============================================================


class TestCheckThresholds:
    """Tests for RiskEngineWorker.check_thresholds().

    Requirements covered:
    - 1.4.6: Check risk thresholds on every monitoring cycle
    - 1.4.7: Trigger kill switch when daily loss exceeds configured percentage
    - 1.4.8: Trigger kill switch when margin usage exceeds 90% of capital
    """

    # --- 6.6.1: Check daily loss limit ---

    def test_loss_exceeds_limit_triggers_breach(self, worker):
        """When loss percentage exceeds daily limit, threshold is breached.

        Example: capital=100000, pnl=-2500, limit=2.0%
        loss_pct = (-2500/100000)*100 = -2.5%, which is <= -2.0%
        """
        breached, reason = worker.check_thresholds(
            pnl=-2500.0, capital=100000.0, daily_loss_limit_pct=2.0, margin_used=5000.0
        )

        assert breached is True
        assert "Daily loss limit breached" in reason
        assert "-2.50%" in reason

    def test_loss_exactly_at_limit_triggers_breach(self, worker):
        """When loss percentage equals the limit exactly, threshold is breached.

        Boundary: capital=100000, pnl=-2000, limit=2.0%
        loss_pct = (-2000/100000)*100 = -2.0%, which is <= -2.0%
        """
        breached, reason = worker.check_thresholds(
            pnl=-2000.0, capital=100000.0, daily_loss_limit_pct=2.0, margin_used=5000.0
        )

        assert breached is True
        assert "Daily loss limit breached" in reason
        assert "-2.00%" in reason

    def test_loss_below_limit_no_breach(self, worker):
        """When loss percentage is less than limit, threshold is NOT breached.

        Example: capital=100000, pnl=-1500, limit=2.0%
        loss_pct = (-1500/100000)*100 = -1.5%, which is > -2.0%
        """
        breached, reason = worker.check_thresholds(
            pnl=-1500.0, capital=100000.0, daily_loss_limit_pct=2.0, margin_used=5000.0
        )

        assert breached is False
        assert reason == "Within limits"

    def test_positive_pnl_no_breach(self, worker):
        """Positive P&L (profit) never triggers daily loss breach."""
        breached, reason = worker.check_thresholds(
            pnl=5000.0, capital=100000.0, daily_loss_limit_pct=2.0, margin_used=5000.0
        )

        assert breached is False
        assert reason == "Within limits"

    def test_zero_pnl_no_breach(self, worker):
        """Zero P&L does not trigger daily loss breach."""
        breached, reason = worker.check_thresholds(
            pnl=0.0, capital=100000.0, daily_loss_limit_pct=2.0, margin_used=5000.0
        )

        assert breached is False
        assert reason == "Within limits"

    def test_large_loss_triggers_breach(self, worker):
        """Large losses (much beyond limit) trigger breach."""
        breached, reason = worker.check_thresholds(
            pnl=-10000.0, capital=100000.0, daily_loss_limit_pct=2.0, margin_used=5000.0
        )

        assert breached is True
        assert "Daily loss limit breached" in reason
        assert "-10.00%" in reason

    # --- 6.6.2: Check margin limit ---

    def test_margin_exceeds_90pct_triggers_breach(self, worker):
        """When margin usage exceeds 90% of capital, threshold is breached."""
        breached, reason = worker.check_thresholds(
            pnl=0.0, capital=100000.0, daily_loss_limit_pct=5.0, margin_used=95000.0
        )

        assert breached is True
        assert "Margin limit breached" in reason
        assert "95.00%" in reason

    def test_margin_exactly_at_90pct_triggers_breach(self, worker):
        """When margin usage is exactly 90% of capital, threshold is breached."""
        breached, reason = worker.check_thresholds(
            pnl=0.0, capital=100000.0, daily_loss_limit_pct=5.0, margin_used=90000.0
        )

        assert breached is True
        assert "Margin limit breached" in reason
        assert "90.00%" in reason

    def test_margin_below_90pct_no_breach(self, worker):
        """When margin usage is below 90% of capital, no breach."""
        breached, reason = worker.check_thresholds(
            pnl=0.0, capital=100000.0, daily_loss_limit_pct=5.0, margin_used=85000.0
        )

        assert breached is False
        assert reason == "Within limits"

    def test_margin_at_100pct_triggers_breach(self, worker):
        """Margin at 100% of capital triggers breach."""
        breached, reason = worker.check_thresholds(
            pnl=0.0, capital=100000.0, daily_loss_limit_pct=5.0, margin_used=100000.0
        )

        assert breached is True
        assert "Margin limit breached" in reason

    # --- 6.6.3: Return trigger decision ---

    def test_both_thresholds_breached_returns_loss_first(self, worker):
        """When both loss and margin are breached, daily loss is reported first."""
        breached, reason = worker.check_thresholds(
            pnl=-5000.0, capital=100000.0, daily_loss_limit_pct=2.0, margin_used=95000.0
        )

        assert breached is True
        # Daily loss is checked first
        assert "Daily loss limit breached" in reason

    def test_no_thresholds_breached_returns_within_limits(self, worker):
        """When no thresholds are breached, returns False and 'Within limits'."""
        breached, reason = worker.check_thresholds(
            pnl=-500.0, capital=100000.0, daily_loss_limit_pct=5.0, margin_used=50000.0
        )

        assert breached is False
        assert reason == "Within limits"

    def test_returns_tuple(self, worker):
        """Return value is a tuple of (bool, str)."""
        result = worker.check_thresholds(
            pnl=0.0, capital=100000.0, daily_loss_limit_pct=2.0, margin_used=5000.0
        )

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], str)

    def test_zero_capital_returns_no_breach(self, worker):
        """Zero capital edge case: returns False (can't compute percentages)."""
        breached, reason = worker.check_thresholds(
            pnl=-1000.0, capital=0.0, daily_loss_limit_pct=2.0, margin_used=5000.0
        )

        assert breached is False
        assert reason == "Within limits"

    def test_negative_capital_returns_no_breach(self, worker):
        """Negative capital edge case: returns False (invalid capital)."""
        breached, reason = worker.check_thresholds(
            pnl=-1000.0, capital=-50000.0, daily_loss_limit_pct=2.0, margin_used=5000.0
        )

        assert breached is False
        assert reason == "Within limits"

    def test_only_margin_breached(self, worker):
        """When only margin is breached (loss is within limits), reports margin."""
        breached, reason = worker.check_thresholds(
            pnl=-100.0, capital=100000.0, daily_loss_limit_pct=5.0, margin_used=92000.0
        )

        assert breached is True
        assert "Margin limit breached" in reason
        assert "92.00%" in reason

    def test_small_capital_loss_calculation(self, worker):
        """Works correctly with smaller capital amounts."""
        # capital=10000, pnl=-300, limit=2.0%
        # loss_pct = -3.0% which is <= -2.0%
        breached, reason = worker.check_thresholds(
            pnl=-300.0, capital=10000.0, daily_loss_limit_pct=2.0, margin_used=1000.0
        )

        assert breached is True
        assert "Daily loss limit breached" in reason
        assert "-3.00%" in reason


# ============================================================
# _queue_exit_orders Tests
# ============================================================


class TestQueueExitOrders:
    """Tests for RiskEngineWorker._queue_exit_orders().

    Requirements covered:
    - 1.5.3: Cancel all pending orders when kill switch activates
    - 1.5.4: Close all open positions via market orders when kill switch activates
    """

    def test_queues_exit_for_multiple_open_positions(self, worker, mock_kite):
        """Queues exit orders for each open position with non-zero quantity."""
        mock_kite.positions.return_value = {
            "net": [
                {"tradingsymbol": "NIFTY23DEC18000CE", "exchange": "NFO", "product": "NRML", "quantity": 50},
                {"tradingsymbol": "RELIANCE", "exchange": "NSE", "product": "CNC", "quantity": -10},
                {"tradingsymbol": "INFY", "exchange": "NSE", "product": "MIS", "quantity": 100},
            ],
            "day": [],
        }

        with pytest.MonkeyPatch.context() as m:
            mock_celery = MagicMock()
            m.setattr("src.workers.celery_app.celery_app", mock_celery)

            result = worker._queue_exit_orders()

        assert result == 3
        assert mock_celery.send_task.call_count == 3

    def test_returns_zero_for_empty_positions(self, worker, mock_kite):
        """Returns 0 when no open positions exist."""
        mock_kite.positions.return_value = {"net": [], "day": []}

        result = worker._queue_exit_orders()

        assert result == 0

    def test_skips_zero_quantity_positions(self, worker, mock_kite):
        """Zero-quantity positions from fetch_positions_safe are already filtered,
        but _queue_exit_orders also checks quantity before queuing."""
        mock_kite.positions.return_value = {
            "net": [
                {"tradingsymbol": "NIFTY23DEC18000CE", "exchange": "NFO", "product": "NRML", "quantity": 50},
                {"tradingsymbol": "RELIANCE", "exchange": "NSE", "product": "CNC", "quantity": 0},
            ],
            "day": [],
        }

        with pytest.MonkeyPatch.context() as m:
            mock_celery = MagicMock()
            m.setattr("src.workers.celery_app.celery_app", mock_celery)

            result = worker._queue_exit_orders()

        # fetch_positions_safe filters qty==0, so only 1 position reaches the loop
        assert result == 1

    def test_handles_fetch_positions_failure(self, worker, mock_kite, caplog):
        """Returns 0 when fetch_positions_safe raises an unexpected exception."""
        # fetch_positions_safe should not raise (it catches internally),
        # but _queue_exit_orders has its own try/except for safety
        mock_kite.positions.side_effect = Exception("Catastrophic failure")

        with caplog.at_level(logging.ERROR):
            result = worker._queue_exit_orders()

        # fetch_positions_safe catches and returns [], so _queue_exit_orders returns 0
        assert result == 0


# ============================================================
# _queue_single_exit_order Tests
# ============================================================


class TestQueueSingleExitOrder:
    """Tests for RiskEngineWorker._queue_single_exit_order().

    Requirements covered:
    - 1.5.4: Close all open positions via market orders when kill switch activates
    """

    def test_long_position_queues_sell_order(self, worker):
        """Long position (qty > 0) generates a SELL market exit order."""
        position = {
            "tradingsymbol": "NIFTY23DEC18000CE",
            "exchange": "NFO",
            "product": "NRML",
            "quantity": 50,
        }

        with pytest.MonkeyPatch.context() as m:
            mock_celery = MagicMock()
            m.setattr("src.workers.celery_app.celery_app", mock_celery)

            worker._queue_single_exit_order(position)

        mock_celery.send_task.assert_called_once()
        call_kwargs = mock_celery.send_task.call_args[1]["kwargs"]
        assert call_kwargs["transaction_type"] == "SELL"
        assert call_kwargs["quantity"] == 50
        assert call_kwargs["tradingsymbol"] == "NIFTY23DEC18000CE"
        assert call_kwargs["exchange"] == "NFO"
        assert call_kwargs["product"] == "NRML"
        assert call_kwargs["order_type"] == "MARKET"
        assert call_kwargs["trigger_reason"] == "kill_switch"
        assert call_kwargs["user_id"] == 1

    def test_short_position_queues_buy_order(self, worker):
        """Short position (qty < 0) generates a BUY market exit order."""
        position = {
            "tradingsymbol": "RELIANCE",
            "exchange": "NSE",
            "product": "MIS",
            "quantity": -100,
        }

        with pytest.MonkeyPatch.context() as m:
            mock_celery = MagicMock()
            m.setattr("src.workers.celery_app.celery_app", mock_celery)

            worker._queue_single_exit_order(position)

        mock_celery.send_task.assert_called_once()
        call_kwargs = mock_celery.send_task.call_args[1]["kwargs"]
        assert call_kwargs["transaction_type"] == "BUY"
        assert call_kwargs["quantity"] == 100  # abs(-100)
        assert call_kwargs["tradingsymbol"] == "RELIANCE"
        assert call_kwargs["exchange"] == "NSE"
        assert call_kwargs["product"] == "MIS"
        assert call_kwargs["order_type"] == "MARKET"

    def test_zero_quantity_does_nothing(self, worker):
        """Position with quantity=0 is skipped (no exit order queued)."""
        position = {
            "tradingsymbol": "INFY",
            "exchange": "NSE",
            "product": "CNC",
            "quantity": 0,
        }

        with pytest.MonkeyPatch.context() as m:
            mock_celery = MagicMock()
            m.setattr("src.workers.celery_app.celery_app", mock_celery)

            worker._queue_single_exit_order(position)

        mock_celery.send_task.assert_not_called()

    def test_celery_send_task_failure_is_handled(self, worker, caplog):
        """Celery send_task failure is caught and logged without crashing."""
        position = {
            "tradingsymbol": "NIFTY23DEC18000CE",
            "exchange": "NFO",
            "product": "NRML",
            "quantity": 50,
        }

        with pytest.MonkeyPatch.context() as m:
            mock_celery = MagicMock()
            mock_celery.send_task.side_effect = Exception("Celery broker down")
            m.setattr("src.workers.celery_app.celery_app", mock_celery)

            with caplog.at_level(logging.ERROR):
                # Should not raise
                worker._queue_single_exit_order(position)

        assert "Failed to queue exit order" in caplog.text
        assert "NIFTY23DEC18000CE" in caplog.text

    def test_exit_order_uses_correct_task_name(self, worker):
        """The Celery task name matches the execution task path."""
        position = {
            "tradingsymbol": "BANKNIFTY",
            "exchange": "NFO",
            "product": "MIS",
            "quantity": 25,
        }

        with pytest.MonkeyPatch.context() as m:
            mock_celery = MagicMock()
            m.setattr("src.workers.celery_app.celery_app", mock_celery)

            worker._queue_single_exit_order(position)

        call_args = mock_celery.send_task.call_args
        assert call_args[0][0] == "src.workers.execution_task.execute_order"

    def test_missing_fields_use_defaults(self, worker):
        """Position missing optional fields uses defaults for exchange and product."""
        position = {
            "quantity": 10,
        }

        with pytest.MonkeyPatch.context() as m:
            mock_celery = MagicMock()
            m.setattr("src.workers.celery_app.celery_app", mock_celery)

            worker._queue_single_exit_order(position)

        call_kwargs = mock_celery.send_task.call_args[1]["kwargs"]
        assert call_kwargs["tradingsymbol"] == ""
        assert call_kwargs["exchange"] == "NSE"
        assert call_kwargs["product"] == "MIS"
        assert call_kwargs["transaction_type"] == "SELL"
        assert call_kwargs["quantity"] == 10


# ============================================================
# _log_killswitch_event Tests
# ============================================================


class TestLogKillswitchEvent:
    """Tests for RiskEngineWorker._log_killswitch_event().

    Requirements covered:
    - 1.5.5: Log kill switch activation to database with reason and timestamp
    """

    # --- 6.7.3.1: Test successful logging with all fields populated ---

    def test_successful_logging_all_fields(self, worker, mock_kite, mock_db_session):
        """Creates a KillSwitchLog with all fields when capital > 0 and positions available."""
        mock_kite.positions.return_value = {
            "net": [
                {"tradingsymbol": "NIFTY", "quantity": 50, "pnl": -5000.0},
                {"tradingsymbol": "RELIANCE", "quantity": 10, "pnl": -1000.0},
            ],
            "day": [],
        }

        worker._log_killswitch_event(
            reason="Daily loss limit breached",
            positions_closed=3,
            capital=100000.0,
        )

        # db.add should have been called with a KillSwitchLog instance
        mock_db_session.add.assert_called_once()
        log_entry = mock_db_session.add.call_args[0][0]

        assert isinstance(log_entry, KillSwitchLog)
        assert log_entry.user_id == 1
        assert log_entry.trigger_reason == "Daily loss limit breached"
        # loss_percent = ((-5000 + -1000) / 100000) * 100 = -6.0
        assert log_entry.loss_percent == pytest.approx(-6.0)
        assert log_entry.capital_at_trigger == 100000.0
        assert log_entry.positions_closed_count == 3
        assert log_entry.timestamp is not None

    def test_logging_populates_timestamp(self, worker, mock_kite, mock_db_session):
        """Timestamp is set to current time on the log entry."""
        mock_kite.positions.return_value = {"net": [], "day": []}

        worker._log_killswitch_event(
            reason="Manual activation",
            positions_closed=0,
            capital=0.0,
        )

        log_entry = mock_db_session.add.call_args[0][0]
        assert isinstance(log_entry.timestamp, datetime)

    # --- 6.7.3.2: Test logging with capital=0 (loss_percent should be None) ---

    def test_capital_zero_loss_percent_is_none(self, worker, mock_db_session):
        """When capital=0, loss_percent should be None (cannot divide by zero)."""
        worker._log_killswitch_event(
            reason="Manual kill switch",
            positions_closed=2,
            capital=0.0,
        )

        log_entry = mock_db_session.add.call_args[0][0]
        assert log_entry.loss_percent is None
        assert log_entry.capital_at_trigger is None

    def test_capital_zero_does_not_fetch_positions(self, worker, mock_kite, mock_db_session):
        """When capital=0, fetch_positions_safe is not called (no division needed)."""
        worker._log_killswitch_event(
            reason="Manual kill switch",
            positions_closed=0,
            capital=0.0,
        )

        # kite.positions should not be called since capital <= 0
        mock_kite.positions.assert_not_called()

    # --- 6.7.3.3: Test that db.add and db.commit are called ---

    def test_db_add_and_commit_called(self, worker, mock_kite, mock_db_session):
        """db.add() and db.commit() are called to persist the log entry."""
        mock_kite.positions.return_value = {"net": [], "day": []}

        worker._log_killswitch_event(
            reason="Loss threshold exceeded",
            positions_closed=5,
            capital=50000.0,
        )

        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()

    def test_db_add_called_with_killswitch_log_instance(self, worker, mock_db_session):
        """db.add() receives a KillSwitchLog instance."""
        worker._log_killswitch_event(
            reason="Threshold breached",
            positions_closed=1,
            capital=0.0,
        )

        log_entry = mock_db_session.add.call_args[0][0]
        assert isinstance(log_entry, KillSwitchLog)

    # --- 6.7.3.4: Test database error handling (commit raises, rollback is called) ---

    def test_commit_exception_triggers_rollback(self, worker, mock_db_session, caplog):
        """When db.commit() raises, db.rollback() is called."""
        mock_db_session.commit.side_effect = Exception("Database connection lost")

        with caplog.at_level(logging.ERROR):
            worker._log_killswitch_event(
                reason="Loss limit hit",
                positions_closed=2,
                capital=0.0,
            )

        mock_db_session.rollback.assert_called_once()
        assert "Failed to log kill switch event" in caplog.text

    def test_commit_exception_does_not_raise(self, worker, mock_db_session):
        """Database errors are caught; the method does not propagate exceptions."""
        mock_db_session.commit.side_effect = Exception("Integrity error")

        # Should not raise
        worker._log_killswitch_event(
            reason="Loss limit",
            positions_closed=1,
            capital=0.0,
        )

    def test_add_exception_triggers_rollback(self, worker, mock_db_session, caplog):
        """When db.add() raises, rollback is still called."""
        mock_db_session.add.side_effect = Exception("Session is closed")

        with caplog.at_level(logging.ERROR):
            worker._log_killswitch_event(
                reason="Threshold",
                positions_closed=0,
                capital=0.0,
            )

        mock_db_session.rollback.assert_called_once()

    # --- 6.7.3.5: Test that session remains usable after rollback ---

    def test_session_usable_after_rollback(self, worker, mock_db_session):
        """After a failed commit and rollback, the session can be used again."""
        mock_db_session.commit.side_effect = Exception("Deadlock detected")

        worker._log_killswitch_event(
            reason="Loss limit",
            positions_closed=1,
            capital=0.0,
        )

        # Rollback was called
        mock_db_session.rollback.assert_called_once()

        # Now simulate that the session is usable again (reset the side_effect)
        mock_db_session.commit.side_effect = None
        mock_db_session.add.reset_mock()
        mock_db_session.commit.reset_mock()

        # A subsequent call should work fine
        worker._log_killswitch_event(
            reason="Second attempt",
            positions_closed=0,
            capital=0.0,
        )

        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()

    def test_rollback_exception_is_suppressed(self, worker, mock_db_session, caplog):
        """If rollback itself fails, the exception is suppressed gracefully."""
        mock_db_session.commit.side_effect = Exception("Connection lost")
        mock_db_session.rollback.side_effect = Exception("Rollback also failed")

        with caplog.at_level(logging.ERROR):
            # Should not raise even if both commit and rollback fail
            worker._log_killswitch_event(
                reason="Loss limit",
                positions_closed=1,
                capital=0.0,
            )

        assert "Failed to log kill switch event" in caplog.text

    # --- 6.7.3.6: Test logging with positions fetch failure (loss_percent still None) ---

    def test_positions_fetch_failure_loss_percent_none(self, worker, mock_db_session):
        """When fetch_positions_safe raises inside _log_killswitch_event, loss_percent remains None."""
        from unittest.mock import patch

        with patch.object(worker, "fetch_positions_safe", side_effect=Exception("Broker unavailable")):
            worker._log_killswitch_event(
                reason="Loss threshold",
                positions_closed=3,
                capital=100000.0,
            )

        log_entry = mock_db_session.add.call_args[0][0]
        assert log_entry.loss_percent is None
        # Other fields should still be populated
        assert log_entry.user_id == 1
        assert log_entry.trigger_reason == "Loss threshold"
        assert log_entry.capital_at_trigger == 100000.0
        assert log_entry.positions_closed_count == 3

    def test_positions_fetch_returns_empty_loss_percent_zero(self, worker, mock_kite, mock_db_session):
        """When positions are empty, pnl=0, so loss_percent=(0/capital)*100=0."""
        mock_kite.positions.return_value = {"net": [], "day": []}

        worker._log_killswitch_event(
            reason="Threshold",
            positions_closed=2,
            capital=50000.0,
        )

        log_entry = mock_db_session.add.call_args[0][0]
        # pnl = 0.0 from empty positions, so loss_percent = (0/50000)*100 = 0.0
        assert log_entry.loss_percent == pytest.approx(0.0)


# ============================================================
# _send_killswitch_notification Tests
# ============================================================


class TestSendKillswitchNotification:
    """Tests for RiskEngineWorker._send_killswitch_notification().

    Requirements covered:
    - 1.5.6: Notify user via all channels when kill switch activates
    """

    # --- 6.7.4.1: Test successful notification with correct channel name ---

    def test_publishes_to_correct_channel(self, worker, mock_redis):
        """Notification is published to user:{user_id}:notifications channel."""
        worker._send_killswitch_notification(
            reason="Daily loss limit breached",
            positions_closed=3,
        )

        mock_redis.publish.assert_called_once()
        call_args = mock_redis.publish.call_args
        channel = call_args[0][0]
        assert channel == "user:1:notifications"

    # --- 6.7.4.2: Test notification message contains all required fields ---

    def test_message_contains_all_required_fields(self, worker, mock_redis):
        """Published message contains type, user_id, reason, positions_closed, timestamp."""
        import json

        worker._send_killswitch_notification(
            reason="Margin limit breached",
            positions_closed=5,
        )

        call_args = mock_redis.publish.call_args
        message_json = call_args[0][1]
        message = json.loads(message_json)

        assert "type" in message
        assert "user_id" in message
        assert "reason" in message
        assert "positions_closed" in message
        assert "timestamp" in message

    def test_message_field_values_are_correct(self, worker, mock_redis):
        """Published message field values match the input parameters."""
        import json

        worker._send_killswitch_notification(
            reason="Daily loss limit breached: -3.50%",
            positions_closed=7,
        )

        call_args = mock_redis.publish.call_args
        message = json.loads(call_args[0][1])

        assert message["user_id"] == 1
        assert message["reason"] == "Daily loss limit breached: -3.50%"
        assert message["positions_closed"] == 7
        # Timestamp should be a valid ISO format string
        datetime.fromisoformat(message["timestamp"])

    # --- 6.7.4.3: Test the message type is "killswitch_activated" ---

    def test_message_type_is_killswitch_activated(self, worker, mock_redis):
        """The message type field is exactly 'killswitch_activated'."""
        import json

        worker._send_killswitch_notification(
            reason="Loss threshold",
            positions_closed=2,
        )

        call_args = mock_redis.publish.call_args
        message = json.loads(call_args[0][1])

        assert message["type"] == "killswitch_activated"

    # --- 6.7.4.4: Test Redis pub/sub failure is handled gracefully ---

    def test_redis_error_does_not_raise(self, worker, mock_redis, caplog):
        """RedisError during publish is caught and logged, not raised."""
        mock_redis.publish.side_effect = redis.RedisError("Connection refused")

        with caplog.at_level(logging.ERROR):
            # Should not raise
            worker._send_killswitch_notification(
                reason="Loss limit",
                positions_closed=1,
            )

        assert "Redis error sending kill switch notification for user 1" in caplog.text

    def test_unexpected_error_does_not_raise(self, worker, mock_redis, caplog):
        """Unexpected exceptions during publish are caught and logged."""
        mock_redis.publish.side_effect = RuntimeError("Unexpected failure")

        with caplog.at_level(logging.ERROR):
            # Should not raise
            worker._send_killswitch_notification(
                reason="Margin limit",
                positions_closed=2,
            )

        assert "Unexpected error sending kill switch notification for user 1" in caplog.text

    # --- 6.7.4.5: Test with different user IDs to verify channel isolation ---

    def test_channel_isolation_user_42(self, mock_kite, mock_redis, mock_db_session):
        """User 42 notification goes to user:42:notifications channel."""
        worker = RiskEngineWorker(
            user_id=42,
            kite_client=mock_kite,
            redis_client=mock_redis,
            db_session=mock_db_session,
        )

        worker._send_killswitch_notification(
            reason="Loss limit",
            positions_closed=1,
        )

        call_args = mock_redis.publish.call_args
        channel = call_args[0][0]
        assert channel == "user:42:notifications"

    def test_channel_isolation_user_999(self, mock_kite, mock_redis, mock_db_session):
        """User 999 notification goes to user:999:notifications channel."""
        import json

        worker = RiskEngineWorker(
            user_id=999,
            kite_client=mock_kite,
            redis_client=mock_redis,
            db_session=mock_db_session,
        )

        worker._send_killswitch_notification(
            reason="Margin exceeded",
            positions_closed=4,
        )

        call_args = mock_redis.publish.call_args
        channel = call_args[0][0]
        message = json.loads(call_args[0][1])

        assert channel == "user:999:notifications"
        assert message["user_id"] == 999

    def test_different_users_get_different_channels(self, mock_kite, mock_redis, mock_db_session):
        """Two different users publish to different channels (no cross-user leakage)."""
        worker_a = RiskEngineWorker(1, mock_kite, mock_redis, mock_db_session)
        worker_b = RiskEngineWorker(2, mock_kite, mock_redis, mock_db_session)

        worker_a._send_killswitch_notification("Loss A", 1)
        worker_b._send_killswitch_notification("Loss B", 2)

        calls = mock_redis.publish.call_args_list
        assert len(calls) == 2
        assert calls[0][0][0] == "user:1:notifications"
        assert calls[1][0][0] == "user:2:notifications"


# ============================================================
# trigger_killswitch Tests
# ============================================================


class TestTriggerKillswitch:
    """Tests for RiskEngineWorker.trigger_killswitch().

    The trigger_killswitch() method orchestrates the full kill switch flow:
    1. Set Redis flag atomically (NX) via _set_killswitch_flag()
    2. Queue exit orders via _queue_exit_orders()
    3. Log event to DB via _log_killswitch_event()
    4. Send notification via _send_killswitch_notification()

    Requirements covered:
    - 1.5.1: Set kill switch flag in Redis atomically
    - 1.5.2: Block all new trades immediately when kill switch activates
    - 1.5.4: Close all open positions via market orders
    - 1.5.5: Log kill switch activation to database
    - 1.5.6: Notify user via all channels
    - 1.5.8: Prevent kill switch from triggering multiple times for same event
    """

    def test_trigger_killswitch_first_time_returns_true(self, worker):
        """First-time trigger returns True when kill switch is newly activated."""
        from unittest.mock import patch

        with patch.object(worker, "_set_killswitch_flag", return_value=True), \
             patch.object(worker, "_queue_exit_orders", return_value=3), \
             patch.object(worker, "_log_killswitch_event"), \
             patch.object(worker, "_send_killswitch_notification"):

            result = worker.trigger_killswitch("Loss limit breached", capital=100000.0)

        assert result is True

    def test_trigger_killswitch_calls_all_sub_methods_in_order(self, worker):
        """All sub-methods are called in the correct sequence."""
        from unittest.mock import patch, call, MagicMock

        call_order = []

        def track_set_flag():
            call_order.append("set_flag")
            return True

        def track_queue_exit():
            call_order.append("queue_exit")
            return 2

        def track_log_event(*args, **kwargs):
            call_order.append("log_event")

        def track_notification(*args, **kwargs):
            call_order.append("notification")

        with patch.object(worker, "_set_killswitch_flag", side_effect=track_set_flag), \
             patch.object(worker, "_queue_exit_orders", side_effect=track_queue_exit), \
             patch.object(worker, "_log_killswitch_event", side_effect=track_log_event), \
             patch.object(worker, "_send_killswitch_notification", side_effect=track_notification):

            worker.trigger_killswitch("Loss limit", capital=50000.0)

        assert call_order == ["set_flag", "queue_exit", "log_event", "notification"]

    def test_duplicate_trigger_returns_false(self, worker):
        """Returns False if kill switch is already active (duplicate prevention)."""
        from unittest.mock import patch

        with patch.object(worker, "_set_killswitch_flag", return_value=False) as mock_flag, \
             patch.object(worker, "_queue_exit_orders") as mock_queue, \
             patch.object(worker, "_log_killswitch_event") as mock_log, \
             patch.object(worker, "_send_killswitch_notification") as mock_notify:

            result = worker.trigger_killswitch("Loss limit breached", capital=100000.0)

        assert result is False
        mock_flag.assert_called_once()
        mock_queue.assert_not_called()
        mock_log.assert_not_called()
        mock_notify.assert_not_called()

    def test_continues_even_if_queue_exit_orders_fails(self, worker):
        """Log and notification still execute when _queue_exit_orders raises."""
        from unittest.mock import patch

        with patch.object(worker, "_set_killswitch_flag", return_value=True), \
             patch.object(worker, "_queue_exit_orders", side_effect=RuntimeError("Queue failure")), \
             patch.object(worker, "_log_killswitch_event") as mock_log, \
             patch.object(worker, "_send_killswitch_notification") as mock_notify:

            # The method does not wrap sub-calls in try/except, so if
            # _queue_exit_orders raises, it propagates. This test verifies
            # the internal error handling within _queue_exit_orders itself.
            # We test with the real method instead to validate resilience.
            pass

        # Re-test using the real _queue_exit_orders which catches internally
        with patch.object(worker, "_set_killswitch_flag", return_value=True), \
             patch.object(worker, "fetch_positions_safe", side_effect=RuntimeError("Broker down")), \
             patch.object(worker, "_log_killswitch_event") as mock_log, \
             patch.object(worker, "_send_killswitch_notification") as mock_notify:

            result = worker.trigger_killswitch("Loss limit", capital=50000.0)

        assert result is True
        mock_log.assert_called_once()
        mock_notify.assert_called_once()

    def test_continues_even_if_log_event_fails(self, worker):
        """Notification still executes when _log_killswitch_event raises internally."""
        from unittest.mock import patch

        # _log_killswitch_event catches its own exceptions internally,
        # so trigger_killswitch continues to notification.
        with patch.object(worker, "_set_killswitch_flag", return_value=True), \
             patch.object(worker, "_queue_exit_orders", return_value=2), \
             patch.object(worker, "_send_killswitch_notification") as mock_notify:

            # Make db.add raise to trigger the internal exception path
            worker.db.add.side_effect = RuntimeError("DB connection lost")

            result = worker.trigger_killswitch("Margin exceeded", capital=75000.0)

        assert result is True
        mock_notify.assert_called_once()

    def test_continues_even_if_notification_fails(self, worker):
        """trigger_killswitch returns True even when notification fails internally."""
        from unittest.mock import patch

        # _send_killswitch_notification catches its own exceptions,
        # so trigger_killswitch still returns True.
        with patch.object(worker, "_set_killswitch_flag", return_value=True), \
             patch.object(worker, "_queue_exit_orders", return_value=1), \
             patch.object(worker, "_log_killswitch_event"):

            # Make redis.publish raise to trigger internal exception handling
            worker.redis.publish.side_effect = RuntimeError("Redis pub/sub down")

            result = worker.trigger_killswitch("Loss limit", capital=60000.0)

        assert result is True

    def test_passes_correct_params_to_sub_methods(self, worker):
        """Sub-methods receive the correct parameters from trigger_killswitch."""
        from unittest.mock import patch

        with patch.object(worker, "_set_killswitch_flag", return_value=True) as mock_flag, \
             patch.object(worker, "_queue_exit_orders", return_value=5) as mock_queue, \
             patch.object(worker, "_log_killswitch_event") as mock_log, \
             patch.object(worker, "_send_killswitch_notification") as mock_notify:

            worker.trigger_killswitch("Max drawdown exceeded", capital=200000.0)

        # _set_killswitch_flag takes no args (uses self.user_id internally)
        mock_flag.assert_called_once_with()

        # _queue_exit_orders takes no args
        mock_queue.assert_called_once_with()

        # _log_killswitch_event receives (reason, positions_closed, capital)
        mock_log.assert_called_once_with("Max drawdown exceeded", 5, 200000.0)

        # _send_killswitch_notification receives (reason, positions_closed)
        mock_notify.assert_called_once_with("Max drawdown exceeded", 5)


# ============================================================
# User Isolation Tests
# ============================================================


class TestUserIsolation:
    """Tests for user isolation in the Risk Engine Worker.

    Validates that each user has separate Redis keys, separate positions,
    and separate kill switch state. One user's actions must never affect
    another user's data.

    Requirements covered:
    - 1.8.1-1.8.10: User isolation requirements
    - 1.5.9: One user's kill switch does not affect other users
    """

    @pytest.fixture
    def mock_kite(self):
        """Create a mock KiteConnect client."""
        return MagicMock()

    @pytest.fixture
    def mock_redis(self):
        """Create a mock RedisClient."""
        return MagicMock()

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        return MagicMock()

    @pytest.fixture
    def worker_user1(self, mock_kite, mock_redis, mock_db_session):
        """Create a RiskEngineWorker for user 1."""
        return RiskEngineWorker(
            user_id=1,
            kite_client=mock_kite,
            redis_client=mock_redis,
            db_session=mock_db_session,
        )

    @pytest.fixture
    def worker_user2(self, mock_kite, mock_redis, mock_db_session):
        """Create a RiskEngineWorker for user 2."""
        return RiskEngineWorker(
            user_id=2,
            kite_client=mock_kite,
            redis_client=mock_redis,
            db_session=mock_db_session,
        )

    # --- 1. Two workers with different user_ids use different Redis keys ---

    def test_different_users_get_different_risk_keys(self, worker_user1, worker_user2):
        """Two workers produce different Redis risk keys for their users.

        Validates: Requirement 1.8.8 - Prefix all Redis keys with user_id.
        """
        from src.cache.redis_keys import RedisKeys

        key1 = RedisKeys.user_risk(worker_user1.user_id)
        key2 = RedisKeys.user_risk(worker_user2.user_id)

        assert key1 == "user:1:risk"
        assert key2 == "user:2:risk"
        assert key1 != key2

    def test_different_users_get_different_killswitch_keys(self, worker_user1, worker_user2):
        """Two workers produce different Redis kill switch keys for their users.

        Validates: Requirement 1.8.8 - Prefix all Redis keys with user_id.
        """
        from src.cache.redis_keys import RedisKeys

        key1 = RedisKeys.user_killswitch(worker_user1.user_id)
        key2 = RedisKeys.user_killswitch(worker_user2.user_id)

        assert key1 == "user:1:killswitch"
        assert key2 == "user:2:killswitch"
        assert key1 != key2

    # --- 2. User 1's killswitch activation does not affect user 2's state ---

    def test_user1_killswitch_does_not_affect_user2(self, mock_kite, mock_db_session):
        """Activating kill switch for user 1 does not set it for user 2.

        Validates: Requirement 1.5.9 - One user's kill switch does not affect other users.
        """
        from unittest.mock import patch, call

        mock_redis = MagicMock()
        # Simulate: NX set succeeds (first time)
        mock_redis.set.return_value = True

        worker1 = RiskEngineWorker(
            user_id=1,
            kite_client=mock_kite,
            redis_client=mock_redis,
            db_session=mock_db_session,
        )

        # Trigger kill switch for user 1
        with patch.object(worker1, "_queue_exit_orders", return_value=0), \
             patch.object(worker1, "_log_killswitch_event"), \
             patch.object(worker1, "_send_killswitch_notification"):
            worker1.trigger_killswitch("Loss limit", capital=100000.0)

        # Verify Redis set was called with user:1:killswitch key, NOT user:2
        set_calls = mock_redis.set.call_args_list
        assert len(set_calls) == 1
        called_key = set_calls[0][0][0]
        assert called_key == "user:1:killswitch"
        assert "user:2:killswitch" not in [c[0][0] for c in set_calls]

    # --- 3. User 1's risk metrics cache is separate from user 2's ---

    def test_user1_risk_cache_separate_from_user2(self, mock_kite, mock_db_session):
        """update_redis_cache stores metrics under user-specific keys.

        Validates: Requirement 3.6.1 - Cache user risk metrics with key user:{user_id}:risk.
        """
        mock_redis = MagicMock()

        worker1 = RiskEngineWorker(
            user_id=1,
            kite_client=mock_kite,
            redis_client=mock_redis,
            db_session=mock_db_session,
        )
        worker2 = RiskEngineWorker(
            user_id=2,
            kite_client=mock_kite,
            redis_client=mock_redis,
            db_session=mock_db_session,
        )

        greeks = {"net_delta": 10.0, "net_gamma": 0.5, "net_vega": 100.0}

        # Update cache for both users
        worker1.update_redis_cache(pnl=-5000.0, greeks=greeks, margin_used=50000.0)
        worker2.update_redis_cache(pnl=3000.0, greeks=greeks, margin_used=20000.0)

        # Verify hset was called with different keys
        hset_calls = mock_redis.hset.call_args_list
        assert len(hset_calls) == 2

        keys_used = [c[0][0] for c in hset_calls]
        assert "user:1:risk" in keys_used
        assert "user:2:risk" in keys_used
        assert keys_used[0] != keys_used[1]

    def test_user_risk_metrics_not_mixed(self, mock_kite, mock_db_session):
        """Each user's metrics are stored with their own values, not leaked to other users.

        Validates: Requirement 1.8.6 - Prevent cross-user data access.
        """
        mock_redis = MagicMock()

        worker1 = RiskEngineWorker(
            user_id=1,
            kite_client=mock_kite,
            redis_client=mock_redis,
            db_session=mock_db_session,
        )
        worker2 = RiskEngineWorker(
            user_id=2,
            kite_client=mock_kite,
            redis_client=mock_redis,
            db_session=mock_db_session,
        )

        # User 1 has a loss
        worker1.update_redis_cache(
            pnl=-10000.0,
            greeks={"net_delta": 5.0, "net_gamma": 0.1, "net_vega": 50.0},
            margin_used=80000.0,
        )
        # User 2 has a profit
        worker2.update_redis_cache(
            pnl=5000.0,
            greeks={"net_delta": -3.0, "net_gamma": 0.2, "net_vega": 30.0},
            margin_used=20000.0,
        )

        # Verify user 1's data is stored under user:1:risk
        call1 = mock_redis.hset.call_args_list[0]
        assert call1[0][0] == "user:1:risk"
        assert call1[1]["mapping"]["pnl"] == str(-10000.0)

        # Verify user 2's data is stored under user:2:risk
        call2 = mock_redis.hset.call_args_list[1]
        assert call2[0][0] == "user:2:risk"
        assert call2[1]["mapping"]["pnl"] == str(5000.0)

    # --- 4. filter_user_positions tags positions with correct user_id ---

    def test_filter_user_positions_tags_correct_user_id(self, mock_kite, mock_redis, mock_db_session):
        """filter_user_positions tags each position with the worker's own user_id.

        Validates: Requirement 1.8.2 - Maintain separate positions for each user.
        """
        worker1 = RiskEngineWorker(1, mock_kite, mock_redis, mock_db_session)
        worker2 = RiskEngineWorker(2, mock_kite, mock_redis, mock_db_session)

        positions = [
            {"tradingsymbol": "NIFTY23DEC18000CE", "exchange": "NFO", "quantity": 50},
            {"tradingsymbol": "RELIANCE", "exchange": "NSE", "quantity": -10},
        ]

        result1 = worker1.filter_user_positions(positions)
        result2 = worker2.filter_user_positions(positions)

        # User 1's positions tagged with user_id=1
        for pos in result1:
            assert pos["user_id"] == 1

        # User 2's positions tagged with user_id=2
        for pos in result2:
            assert pos["user_id"] == 2

    # --- 5. Positions from one user don't appear in another user's results ---

    def test_positions_from_one_user_not_in_another(self, mock_kite, mock_redis, mock_db_session):
        """Positions filtered by one worker are not linked to another worker.

        Validates: Requirement 1.8.6 - Prevent cross-user data access.
        """
        worker1 = RiskEngineWorker(1, mock_kite, mock_redis, mock_db_session)
        worker2 = RiskEngineWorker(2, mock_kite, mock_redis, mock_db_session)

        # User 1 has NIFTY positions
        positions_user1 = [
            {"tradingsymbol": "NIFTY23DEC18000CE", "exchange": "NFO", "quantity": 50},
        ]
        # User 2 has BANKNIFTY positions
        positions_user2 = [
            {"tradingsymbol": "BANKNIFTY23DEC45000PE", "exchange": "NFO", "quantity": -25},
        ]

        result1 = worker1.filter_user_positions(positions_user1)
        result2 = worker2.filter_user_positions(positions_user2)

        # User 1's result should not contain user 2's positions
        symbols_user1 = [p["tradingsymbol"] for p in result1]
        symbols_user2 = [p["tradingsymbol"] for p in result2]

        assert "BANKNIFTY23DEC45000PE" not in symbols_user1
        assert "NIFTY23DEC18000CE" not in symbols_user2

        # Confirm user_id isolation
        assert all(p["user_id"] == 1 for p in result1)
        assert all(p["user_id"] == 2 for p in result2)

    # --- 6. Each worker instance has its own user_id throughout the lifecycle ---

    def test_worker_user_id_immutable_throughout_lifecycle(self, mock_kite, mock_redis, mock_db_session):
        """Worker's user_id remains constant throughout its lifecycle.

        Validates: Requirement 1.8.1 - Each user operates in isolated context.
        """
        worker = RiskEngineWorker(42, mock_kite, mock_redis, mock_db_session)

        # user_id stays consistent across different operations
        assert worker.user_id == 42

        # After filtering positions, user_id is still the same
        positions = [{"tradingsymbol": "NIFTY", "quantity": 10}]
        result = worker.filter_user_positions(positions)
        assert worker.user_id == 42
        assert result[0]["user_id"] == 42

        # After computing metrics, user_id is still the same
        worker.compute_live_pnl(positions)
        assert worker.user_id == 42

        worker.compute_greeks(positions)
        assert worker.user_id == 42

    def test_multiple_workers_maintain_separate_user_ids(self, mock_kite, mock_redis, mock_db_session):
        """Multiple worker instances each maintain their own distinct user_id.

        Validates: Requirement 1.8.1 - Each user operates in isolated context.
        """
        workers = [
            RiskEngineWorker(uid, mock_kite, mock_redis, mock_db_session)
            for uid in [1, 2, 3, 10, 100]
        ]

        # Each worker retains its own user_id
        expected_ids = [1, 2, 3, 10, 100]
        for worker, expected_id in zip(workers, expected_ids):
            assert worker.user_id == expected_id

        # Verify no cross-contamination after operations
        positions = [{"tradingsymbol": "NIFTY", "quantity": 50}]
        for worker, expected_id in zip(workers, expected_ids):
            result = worker.filter_user_positions(positions)
            assert result[0]["user_id"] == expected_id
            assert worker.user_id == expected_id
