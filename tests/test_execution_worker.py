"""Tests for the Execution Worker - initialization, kill switch check, and margin check.

Tests cover:
- ExecutionWorker.__init__(): validation of constructor arguments
- ExecutionWorker.check_killswitch(): reading kill switch status from Redis
- ExecutionWorker.check_margin_availability(): margin validation against 90% of capital

Requirements covered:
- 1.3.3: Validate trades before execution (kill switch, margin, duplicates)
- 1.3.10: Block new trades when kill switch is active
- 1.4.8: Trigger kill switch when margin usage exceeds 90% of capital
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import logging

import pytest
import redis
from sqlalchemy.exc import SQLAlchemyError
from unittest.mock import MagicMock, patch, PropertyMock

from src.workers.execution_worker import ExecutionWorker
from src.cache.redis_keys import RedisKeys
from src.database.models.user import User
from src.database.models.order import Order
from src.database.models.trade import Trade
from kiteconnect import exceptions as kite_exceptions


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def mock_kite():
    """Create a mock KiteConnect client."""
    return MagicMock()


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    return MagicMock()


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    return MagicMock()


@pytest.fixture
def worker(mock_kite, mock_redis, mock_db_session):
    """Create an ExecutionWorker with mocked dependencies."""
    return ExecutionWorker(
        user_id=1,
        kite_client=mock_kite,
        redis_client=mock_redis,
        db_session=mock_db_session,
    )


# ============================================================
# Constructor Tests
# ============================================================


class TestExecutionWorkerInit:
    """Tests for ExecutionWorker initialization."""

    def test_valid_construction(self, mock_kite, mock_redis, mock_db_session):
        """Worker initializes with valid dependencies."""
        worker = ExecutionWorker(
            user_id=42,
            kite_client=mock_kite,
            redis_client=mock_redis,
            db_session=mock_db_session,
        )
        assert worker.user_id == 42
        assert worker.kite is mock_kite
        assert worker.redis is mock_redis
        assert worker.db is mock_db_session
        assert worker.max_retries == 3
        assert worker.retry_backoff == 1.0

    def test_invalid_user_id_zero(self, mock_kite, mock_redis, mock_db_session):
        """Raises ValueError for user_id = 0."""
        with pytest.raises(ValueError, match="user_id must be a positive integer"):
            ExecutionWorker(0, mock_kite, mock_redis, mock_db_session)

    def test_invalid_user_id_negative(self, mock_kite, mock_redis, mock_db_session):
        """Raises ValueError for negative user_id."""
        with pytest.raises(ValueError, match="user_id must be a positive integer"):
            ExecutionWorker(-1, mock_kite, mock_redis, mock_db_session)

    def test_invalid_user_id_non_integer(self, mock_kite, mock_redis, mock_db_session):
        """Raises ValueError for non-integer user_id."""
        with pytest.raises(ValueError, match="user_id must be a positive integer"):
            ExecutionWorker("abc", mock_kite, mock_redis, mock_db_session)

    def test_none_kite_client(self, mock_redis, mock_db_session):
        """Raises ValueError when kite_client is None."""
        with pytest.raises(ValueError, match="kite_client cannot be None"):
            ExecutionWorker(1, None, mock_redis, mock_db_session)

    def test_none_redis_client(self, mock_kite, mock_db_session):
        """Raises ValueError when redis_client is None."""
        with pytest.raises(ValueError, match="redis_client cannot be None"):
            ExecutionWorker(1, mock_kite, None, mock_db_session)

    def test_none_db_session(self, mock_kite, mock_redis):
        """Raises ValueError when db_session is None."""
        with pytest.raises(ValueError, match="db_session cannot be None"):
            ExecutionWorker(1, mock_kite, mock_redis, None)


# ============================================================
# Kill Switch Check Tests
# ============================================================


class TestCheckKillswitch:
    """Tests for ExecutionWorker.check_killswitch()."""

    def test_returns_true_when_killswitch_active_bytes(self, worker, mock_redis):
        """Returns True when Redis returns b'true' (kill switch active)."""
        mock_redis.get.return_value = b"true"

        result = worker.check_killswitch()

        assert result is True
        mock_redis.get.assert_called_once_with(RedisKeys.user_killswitch(1))

    def test_returns_false_when_killswitch_inactive_bytes(self, worker, mock_redis):
        """Returns False when Redis returns b'false' (kill switch inactive)."""
        mock_redis.get.return_value = b"false"

        result = worker.check_killswitch()

        assert result is False

    def test_returns_false_when_key_not_exists(self, worker, mock_redis):
        """Returns False when the kill switch key doesn't exist (None)."""
        mock_redis.get.return_value = None

        result = worker.check_killswitch()

        assert result is False

    def test_returns_true_when_killswitch_active_string(self, worker, mock_redis):
        """Returns True when Redis returns string 'true' (some clients decode)."""
        mock_redis.get.return_value = "true"

        result = worker.check_killswitch()

        assert result is True

    def test_returns_false_when_killswitch_inactive_string(self, worker, mock_redis):
        """Returns False when Redis returns string 'false'."""
        mock_redis.get.return_value = "false"

        result = worker.check_killswitch()

        assert result is False

    def test_returns_true_on_redis_connection_error(self, worker, mock_redis):
        """Returns True (safe default) when Redis connection fails."""
        mock_redis.get.side_effect = redis.ConnectionError("Connection refused")

        result = worker.check_killswitch()

        assert result is True

    def test_returns_true_on_redis_timeout_error(self, worker, mock_redis):
        """Returns True (safe default) when Redis times out."""
        mock_redis.get.side_effect = redis.TimeoutError("Read timed out")

        result = worker.check_killswitch()

        assert result is True

    def test_returns_true_on_unexpected_exception(self, worker, mock_redis):
        """Returns True (safe default) on any unexpected exception."""
        mock_redis.get.side_effect = RuntimeError("Something unexpected")

        result = worker.check_killswitch()

        assert result is True

    def test_uses_correct_redis_key(self, worker, mock_redis):
        """Uses RedisKeys.user_killswitch(user_id) for the key lookup."""
        mock_redis.get.return_value = None

        worker.check_killswitch()

        expected_key = f"user:1:killswitch"
        mock_redis.get.assert_called_once_with(expected_key)

    def test_different_user_id_uses_correct_key(self, mock_kite, mock_redis, mock_db_session):
        """Different user_id results in different Redis key."""
        worker = ExecutionWorker(
            user_id=99,
            kite_client=mock_kite,
            redis_client=mock_redis,
            db_session=mock_db_session,
        )
        mock_redis.get.return_value = None

        worker.check_killswitch()

        expected_key = f"user:99:killswitch"
        mock_redis.get.assert_called_once_with(expected_key)

    def test_returns_false_for_arbitrary_bytes_value(self, worker, mock_redis):
        """Returns False for any value other than b'true'."""
        mock_redis.get.return_value = b"yes"

        result = worker.check_killswitch()

        assert result is False

    def test_logs_error_on_redis_failure(self, worker, mock_redis, caplog):
        """Logs an error message when Redis fails."""
        mock_redis.get.side_effect = redis.ConnectionError("Connection refused")

        with caplog.at_level(logging.ERROR):
            worker.check_killswitch()

        assert "Redis error checking kill switch" in caplog.text


# ============================================================
# Margin Availability Check Tests
# ============================================================


class TestCheckMarginAvailability:
    """Tests for ExecutionWorker.check_margin_availability().

    Requirements covered:
    - 1.3.3: Validate trades before execution (margin check)
    - 1.4.8: Trigger kill switch when margin usage exceeds 90% of capital
    """

    def _setup_user(self, mock_db_session, capital: float = 100000.0):
        """Helper to configure mock DB to return a user with given capital."""
        mock_user = MagicMock(spec=User)
        mock_user.capital = capital
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_filter.first.return_value = mock_user
        mock_query.filter_by.return_value = mock_filter
        mock_db_session.query.return_value = mock_query
        return mock_user

    def test_margin_available_below_90_percent(self, worker, mock_redis, mock_db_session):
        """Returns (True, 'Margin available') when margin_used < 90% of capital."""
        # margin_used = 80000, capital = 100000, limit = 90000
        mock_redis.hgetall.return_value = {b"margin_used": b"80000.0"}
        self._setup_user(mock_db_session, capital=100000.0)

        result = worker.check_margin_availability()

        assert result == (True, "Margin available")

    def test_margin_insufficient_at_exactly_90_percent(self, worker, mock_redis, mock_db_session):
        """Returns (False, 'Insufficient margin') when margin_used == 90% of capital."""
        # margin_used = 90000, capital = 100000, limit = 90000
        mock_redis.hgetall.return_value = {b"margin_used": b"90000.0"}
        self._setup_user(mock_db_session, capital=100000.0)

        result = worker.check_margin_availability()

        assert result == (False, "Insufficient margin")

    def test_margin_insufficient_above_90_percent(self, worker, mock_redis, mock_db_session):
        """Returns (False, 'Insufficient margin') when margin_used > 90% of capital."""
        # margin_used = 95000, capital = 100000, limit = 90000
        mock_redis.hgetall.return_value = {b"margin_used": b"95000.0"}
        self._setup_user(mock_db_session, capital=100000.0)

        result = worker.check_margin_availability()

        assert result == (False, "Insufficient margin")

    def test_margin_available_just_below_90_percent(self, worker, mock_redis, mock_db_session):
        """Returns (True, 'Margin available') when margin_used is just below 90% threshold."""
        # margin_used = 89999.99, capital = 100000, limit = 90000
        mock_redis.hgetall.return_value = {b"margin_used": b"89999.99"}
        self._setup_user(mock_db_session, capital=100000.0)

        result = worker.check_margin_availability()

        assert result == (True, "Margin available")

    def test_no_risk_data_in_redis_defaults_to_zero_margin(self, worker, mock_redis, mock_db_session):
        """Returns (True, 'Margin available') when no risk data exists (fresh user)."""
        mock_redis.hgetall.return_value = {}
        self._setup_user(mock_db_session, capital=100000.0)

        result = worker.check_margin_availability()

        assert result == (True, "Margin available")

    def test_handles_string_keys_from_redis(self, worker, mock_redis, mock_db_session):
        """Handles string keys (some Redis clients decode automatically)."""
        mock_redis.hgetall.return_value = {"margin_used": "50000.0"}
        self._setup_user(mock_db_session, capital=100000.0)

        result = worker.check_margin_availability()

        assert result == (True, "Margin available")

    def test_uses_correct_redis_key(self, worker, mock_redis, mock_db_session):
        """Uses RedisKeys.user_risk(user_id) for the risk hash lookup."""
        mock_redis.hgetall.return_value = {}
        self._setup_user(mock_db_session, capital=100000.0)

        worker.check_margin_availability()

        expected_key = f"user:1:risk"
        mock_redis.hgetall.assert_called_once_with(expected_key)

    def test_queries_correct_user_from_db(self, worker, mock_redis, mock_db_session):
        """Queries the database for the correct user_id."""
        mock_redis.hgetall.return_value = {b"margin_used": b"0"}
        self._setup_user(mock_db_session, capital=100000.0)

        worker.check_margin_availability()

        mock_db_session.query.return_value.filter_by.assert_called_once_with(id=1)

    def test_returns_failure_on_redis_connection_error(self, worker, mock_redis, mock_db_session):
        """Returns failure tuple on Redis connection error."""
        mock_redis.hgetall.side_effect = redis.ConnectionError("Connection refused")

        result = worker.check_margin_availability()

        assert result == (False, "Margin check failed: Redis unavailable")

    def test_returns_failure_on_redis_timeout_error(self, worker, mock_redis, mock_db_session):
        """Returns failure tuple on Redis timeout."""
        mock_redis.hgetall.side_effect = redis.TimeoutError("Read timed out")

        result = worker.check_margin_availability()

        assert result == (False, "Margin check failed: Redis unavailable")

    def test_returns_failure_on_invalid_margin_data(self, worker, mock_redis, mock_db_session):
        """Returns failure tuple when margin_used is not a valid number."""
        mock_redis.hgetall.return_value = {b"margin_used": b"not_a_number"}

        result = worker.check_margin_availability()

        assert result == (False, "Margin check failed: invalid margin data")

    def test_returns_failure_when_user_not_found(self, worker, mock_redis, mock_db_session):
        """Returns failure tuple when user doesn't exist in database."""
        mock_redis.hgetall.return_value = {b"margin_used": b"5000.0"}
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_filter.first.return_value = None
        mock_query.filter_by.return_value = mock_filter
        mock_db_session.query.return_value = mock_query

        result = worker.check_margin_availability()

        assert result == (False, "Margin check failed: user not found")

    def test_returns_failure_on_database_error(self, worker, mock_redis, mock_db_session):
        """Returns failure tuple on SQLAlchemy database error."""
        mock_redis.hgetall.return_value = {b"margin_used": b"5000.0"}
        mock_db_session.query.side_effect = SQLAlchemyError("DB connection lost")

        result = worker.check_margin_availability()

        assert result == (False, "Margin check failed: database unavailable")

    def test_returns_failure_on_unexpected_db_error(self, worker, mock_redis, mock_db_session):
        """Returns failure tuple on unexpected database error."""
        mock_redis.hgetall.return_value = {b"margin_used": b"5000.0"}
        mock_db_session.query.side_effect = RuntimeError("Something unexpected")

        result = worker.check_margin_availability()

        assert result == (False, "Margin check failed: unexpected error")

    def test_logs_warning_when_margin_exceeded(self, worker, mock_redis, mock_db_session, caplog):
        """Logs a warning message when margin limit is exceeded."""
        mock_redis.hgetall.return_value = {b"margin_used": b"95000.0"}
        self._setup_user(mock_db_session, capital=100000.0)

        with caplog.at_level(logging.WARNING):
            worker.check_margin_availability()

        assert "Margin limit exceeded" in caplog.text

    def test_different_user_capital(self, mock_kite, mock_redis, mock_db_session):
        """Works correctly with different capital amounts."""
        worker = ExecutionWorker(
            user_id=5,
            kite_client=mock_kite,
            redis_client=mock_redis,
            db_session=mock_db_session,
        )
        # Capital = 50000, 90% limit = 45000, margin_used = 44000 -> available
        mock_redis.hgetall.return_value = {b"margin_used": b"44000.0"}
        mock_user = MagicMock(spec=User)
        mock_user.capital = 50000.0
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_filter.first.return_value = mock_user
        mock_query.filter_by.return_value = mock_filter
        mock_db_session.query.return_value = mock_query

        result = worker.check_margin_availability()

        assert result == (True, "Margin available")

    def test_zero_margin_used_is_available(self, worker, mock_redis, mock_db_session):
        """Zero margin used is always valid."""
        mock_redis.hgetall.return_value = {b"margin_used": b"0.0"}
        self._setup_user(mock_db_session, capital=100000.0)

        result = worker.check_margin_availability()

        assert result == (True, "Margin available")


# ============================================================
# Create Order Signature Tests
# ============================================================


class TestCreateOrderSignature:
    """Tests for ExecutionWorker.create_order_signature().

    Requirements covered:
    - 1.3.9: Prevent duplicate orders within 60 seconds
    """

    def test_returns_correct_format(self, worker):
        """Generates signature in symbol:side:quantity format."""
        order = {"symbol": "NIFTY", "side": "BUY", "quantity": 50}

        result = worker.create_order_signature(order)

        assert result == "NIFTY:BUY:50"

    def test_different_symbols(self, worker):
        """Works with different trading symbols."""
        order = {"symbol": "BANKNIFTY", "side": "SELL", "quantity": 100}

        result = worker.create_order_signature(order)

        assert result == "BANKNIFTY:SELL:100"

    def test_raises_type_error_for_none_order(self, worker):
        """Raises TypeError when order is None."""
        with pytest.raises(TypeError, match="order cannot be None"):
            worker.create_order_signature(None)

    def test_raises_type_error_for_non_dict(self, worker):
        """Raises TypeError when order is not a dictionary."""
        with pytest.raises(TypeError, match="order must be a dictionary"):
            worker.create_order_signature("not_a_dict")

    def test_raises_key_error_for_missing_symbol(self, worker):
        """Raises KeyError when 'symbol' key is missing."""
        order = {"side": "BUY", "quantity": 50}

        with pytest.raises(KeyError, match="symbol"):
            worker.create_order_signature(order)

    def test_raises_key_error_for_missing_side(self, worker):
        """Raises KeyError when 'side' key is missing."""
        order = {"symbol": "NIFTY", "quantity": 50}

        with pytest.raises(KeyError, match="side"):
            worker.create_order_signature(order)

    def test_raises_key_error_for_missing_quantity(self, worker):
        """Raises KeyError when 'quantity' key is missing."""
        order = {"symbol": "NIFTY", "side": "BUY"}

        with pytest.raises(KeyError, match="quantity"):
            worker.create_order_signature(order)

    def test_raises_key_error_for_empty_dict(self, worker):
        """Raises KeyError for an empty dictionary."""
        with pytest.raises(KeyError, match="symbol.*side.*quantity"):
            worker.create_order_signature({})

    def test_extra_keys_ignored(self, worker):
        """Extra keys in the order dict don't affect the signature."""
        order = {"symbol": "NIFTY", "side": "BUY", "quantity": 50, "price": 100.5, "reason": "user"}

        result = worker.create_order_signature(order)

        assert result == "NIFTY:BUY:50"

    def test_numeric_quantity_included_as_is(self, worker):
        """Quantity value is converted to string representation as-is."""
        order = {"symbol": "RELIANCE", "side": "SELL", "quantity": 75}

        result = worker.create_order_signature(order)

        assert result == "RELIANCE:SELL:75"


# ============================================================
# Duplicate Order Check Tests
# ============================================================


class TestIsDuplicateOrder:
    """Tests for ExecutionWorker.is_duplicate_order().

    Requirements covered:
    - 1.3.3: Validate trades before execution (duplicate check)
    - 1.3.9: Prevent duplicate orders within 60 seconds
    """

    def test_returns_true_when_duplicate_found_bytes(self, worker, mock_redis):
        """Returns True when matching order signature exists in recent orders (bytes)."""
        order = {"symbol": "NIFTY", "side": "BUY", "quantity": 50}
        mock_redis.lrange.return_value = [b"NIFTY:BUY:50"]

        result = worker.is_duplicate_order(order)

        assert result is True

    def test_returns_false_when_no_duplicate(self, worker, mock_redis):
        """Returns False when no matching order signature in recent orders."""
        order = {"symbol": "NIFTY", "side": "BUY", "quantity": 50}
        mock_redis.lrange.return_value = [b"BANKNIFTY:SELL:25"]

        result = worker.is_duplicate_order(order)

        assert result is False

    def test_returns_false_when_recent_orders_empty(self, worker, mock_redis):
        """Returns False when recent orders list is empty."""
        order = {"symbol": "NIFTY", "side": "BUY", "quantity": 50}
        mock_redis.lrange.return_value = []

        result = worker.is_duplicate_order(order)

        assert result is False

    def test_returns_true_when_duplicate_found_string(self, worker, mock_redis):
        """Returns True when matching order signature exists (string response)."""
        order = {"symbol": "NIFTY", "side": "BUY", "quantity": 50}
        mock_redis.lrange.return_value = ["NIFTY:BUY:50"]

        result = worker.is_duplicate_order(order)

        assert result is True

    def test_order_signature_format(self, worker, mock_redis):
        """Order signature is symbol:side:quantity."""
        order = {"symbol": "BANKNIFTY", "side": "SELL", "quantity": 100}
        mock_redis.lrange.return_value = [b"BANKNIFTY:SELL:100"]

        result = worker.is_duplicate_order(order)

        assert result is True

    def test_different_symbol_not_duplicate(self, worker, mock_redis):
        """Different symbol means not a duplicate."""
        order = {"symbol": "NIFTY", "side": "BUY", "quantity": 50}
        mock_redis.lrange.return_value = [b"BANKNIFTY:BUY:50"]

        result = worker.is_duplicate_order(order)

        assert result is False

    def test_different_side_not_duplicate(self, worker, mock_redis):
        """Different side means not a duplicate."""
        order = {"symbol": "NIFTY", "side": "BUY", "quantity": 50}
        mock_redis.lrange.return_value = [b"NIFTY:SELL:50"]

        result = worker.is_duplicate_order(order)

        assert result is False

    def test_different_quantity_not_duplicate(self, worker, mock_redis):
        """Different quantity means not a duplicate."""
        order = {"symbol": "NIFTY", "side": "BUY", "quantity": 50}
        mock_redis.lrange.return_value = [b"NIFTY:BUY:25"]

        result = worker.is_duplicate_order(order)

        assert result is False

    def test_uses_correct_redis_key(self, worker, mock_redis):
        """Uses RedisKeys.user_recent_orders(user_id) for the list lookup."""
        order = {"symbol": "NIFTY", "side": "BUY", "quantity": 50}
        mock_redis.lrange.return_value = []

        worker.is_duplicate_order(order)

        expected_key = "user:1:recent_orders"
        mock_redis.lrange.assert_called_once_with(expected_key, 0, -1)

    def test_different_user_id_uses_correct_key(self, mock_kite, mock_redis, mock_db_session):
        """Different user_id results in different Redis key."""
        worker = ExecutionWorker(
            user_id=77,
            kite_client=mock_kite,
            redis_client=mock_redis,
            db_session=mock_db_session,
        )
        order = {"symbol": "NIFTY", "side": "BUY", "quantity": 50}
        mock_redis.lrange.return_value = []

        worker.is_duplicate_order(order)

        expected_key = "user:77:recent_orders"
        mock_redis.lrange.assert_called_once_with(expected_key, 0, -1)

    def test_returns_false_on_redis_connection_error(self, worker, mock_redis):
        """Returns False (permissive default) when Redis connection fails."""
        order = {"symbol": "NIFTY", "side": "BUY", "quantity": 50}
        mock_redis.lrange.side_effect = redis.ConnectionError("Connection refused")

        result = worker.is_duplicate_order(order)

        assert result is False

    def test_returns_false_on_redis_timeout_error(self, worker, mock_redis):
        """Returns False (permissive default) when Redis times out."""
        order = {"symbol": "NIFTY", "side": "BUY", "quantity": 50}
        mock_redis.lrange.side_effect = redis.TimeoutError("Read timed out")

        result = worker.is_duplicate_order(order)

        assert result is False

    def test_returns_false_on_missing_order_key(self, worker, mock_redis):
        """Returns False (permissive default) when order dict is missing required keys."""
        order = {"symbol": "NIFTY"}  # Missing 'side' and 'quantity'
        mock_redis.lrange.return_value = []

        result = worker.is_duplicate_order(order)

        assert result is False

    def test_returns_false_on_none_order(self, worker, mock_redis):
        """Returns False (permissive default) when order is None."""
        result = worker.is_duplicate_order(None)

        assert result is False

    def test_detects_duplicate_among_multiple_recent_orders(self, worker, mock_redis):
        """Finds duplicate even when it's not the first item in the list."""
        order = {"symbol": "NIFTY", "side": "BUY", "quantity": 50}
        mock_redis.lrange.return_value = [
            b"BANKNIFTY:SELL:25",
            b"RELIANCE:BUY:10",
            b"NIFTY:BUY:50",
            b"INFY:SELL:75",
        ]

        result = worker.is_duplicate_order(order)

        assert result is True

    def test_logs_warning_on_duplicate_detected(self, worker, mock_redis, caplog):
        """Logs a warning when duplicate order is detected."""
        order = {"symbol": "NIFTY", "side": "BUY", "quantity": 50}
        mock_redis.lrange.return_value = [b"NIFTY:BUY:50"]

        with caplog.at_level(logging.WARNING):
            worker.is_duplicate_order(order)

        assert "Duplicate order detected" in caplog.text

    def test_logs_error_on_redis_failure(self, worker, mock_redis, caplog):
        """Logs an error when Redis fails during duplicate check."""
        order = {"symbol": "NIFTY", "side": "BUY", "quantity": 50}
        mock_redis.lrange.side_effect = redis.ConnectionError("Connection refused")

        with caplog.at_level(logging.ERROR):
            worker.is_duplicate_order(order)

        assert "Redis error checking duplicate orders" in caplog.text


# ============================================================
# Validate Order Tests
# ============================================================


class TestValidateOrder:
    """Tests for ExecutionWorker.validate_order().

    The validate_order method combines kill switch, margin, and duplicate
    checks into a single validation pipeline. Returns (False, reason)
    on the first failed check, or (True, "Valid") if all pass.

    Requirements covered:
    - 1.3.3: Validate trades before execution (kill switch, margin, duplicates)
    - 1.3.10: Block new trades when kill switch is active
    """

    def _setup_user(self, mock_db_session, capital: float = 100000.0):
        """Helper to configure mock DB to return a user with given capital."""
        mock_user = MagicMock(spec=User)
        mock_user.capital = capital
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_filter.first.return_value = mock_user
        mock_query.filter_by.return_value = mock_filter
        mock_db_session.query.return_value = mock_query
        return mock_user

    def test_all_checks_pass_returns_valid(self, worker, mock_redis, mock_db_session):
        """Returns (True, 'Valid') when kill switch off, margin OK, no duplicate."""
        # Kill switch inactive
        mock_redis.get.return_value = b"false"
        # Margin OK
        mock_redis.hgetall.return_value = {b"margin_used": b"50000.0"}
        self._setup_user(mock_db_session, capital=100000.0)
        # No duplicates
        mock_redis.lrange.return_value = []

        order = {"symbol": "NIFTY", "side": "BUY", "quantity": 50}
        result = worker.validate_order(order)

        assert result == (True, "Valid")

    def test_killswitch_active_blocks_order(self, worker, mock_redis):
        """Returns (False, 'Kill switch is active') when kill switch is on."""
        mock_redis.get.return_value = b"true"

        order = {"symbol": "NIFTY", "side": "BUY", "quantity": 50}
        result = worker.validate_order(order)

        assert result == (False, "Kill switch is active")

    def test_killswitch_exit_order_bypasses_killswitch(self, worker, mock_redis, mock_db_session):
        """Orders with reason='killswitch_exit' bypass the kill switch check."""
        # Kill switch is active
        mock_redis.get.return_value = b"true"
        # Margin OK
        mock_redis.hgetall.return_value = {b"margin_used": b"50000.0"}
        self._setup_user(mock_db_session, capital=100000.0)
        # No duplicates
        mock_redis.lrange.return_value = []

        order = {"symbol": "NIFTY", "side": "SELL", "quantity": 50, "reason": "killswitch_exit"}
        result = worker.validate_order(order)

        assert result == (True, "Valid")

    def test_killswitch_exit_still_checks_margin(self, worker, mock_redis, mock_db_session):
        """Kill switch exit orders still fail on insufficient margin."""
        # Kill switch is active
        mock_redis.get.return_value = b"true"
        # Margin exceeded
        mock_redis.hgetall.return_value = {b"margin_used": b"95000.0"}
        self._setup_user(mock_db_session, capital=100000.0)

        order = {"symbol": "NIFTY", "side": "SELL", "quantity": 50, "reason": "killswitch_exit"}
        result = worker.validate_order(order)

        assert result == (False, "Insufficient margin")

    def test_killswitch_exit_still_checks_duplicates(self, worker, mock_redis, mock_db_session):
        """Kill switch exit orders still fail on duplicate detection."""
        # Kill switch is active
        mock_redis.get.return_value = b"true"
        # Margin OK
        mock_redis.hgetall.return_value = {b"margin_used": b"50000.0"}
        self._setup_user(mock_db_session, capital=100000.0)
        # Duplicate exists
        mock_redis.lrange.return_value = [b"NIFTY:SELL:50"]

        order = {"symbol": "NIFTY", "side": "SELL", "quantity": 50, "reason": "killswitch_exit"}
        result = worker.validate_order(order)

        assert result == (False, "Duplicate order detected")

    def test_insufficient_margin_blocks_order(self, worker, mock_redis, mock_db_session):
        """Returns (False, 'Insufficient margin') when margin >= 90% capital."""
        # Kill switch inactive
        mock_redis.get.return_value = b"false"
        # Margin exceeded (90000 >= 90% of 100000)
        mock_redis.hgetall.return_value = {b"margin_used": b"90000.0"}
        self._setup_user(mock_db_session, capital=100000.0)

        order = {"symbol": "NIFTY", "side": "BUY", "quantity": 50}
        result = worker.validate_order(order)

        assert result == (False, "Insufficient margin")

    def test_duplicate_order_blocks(self, worker, mock_redis, mock_db_session):
        """Returns (False, 'Duplicate order detected') when duplicate found."""
        # Kill switch inactive
        mock_redis.get.return_value = b"false"
        # Margin OK
        mock_redis.hgetall.return_value = {b"margin_used": b"50000.0"}
        self._setup_user(mock_db_session, capital=100000.0)
        # Duplicate exists
        mock_redis.lrange.return_value = [b"NIFTY:BUY:50"]

        order = {"symbol": "NIFTY", "side": "BUY", "quantity": 50}
        result = worker.validate_order(order)

        assert result == (False, "Duplicate order detected")

    def test_killswitch_checked_first(self, worker, mock_redis, mock_db_session):
        """Kill switch is the first check — blocks before margin or duplicate checks."""
        # Kill switch active
        mock_redis.get.return_value = b"true"

        order = {"symbol": "NIFTY", "side": "BUY", "quantity": 50}
        result = worker.validate_order(order)

        assert result == (False, "Kill switch is active")
        # Margin and duplicate checks should not have been called
        mock_redis.hgetall.assert_not_called()
        mock_redis.lrange.assert_not_called()

    def test_margin_checked_before_duplicates(self, worker, mock_redis, mock_db_session):
        """Margin check comes before duplicate check."""
        # Kill switch inactive
        mock_redis.get.return_value = b"false"
        # Margin fails
        mock_redis.hgetall.return_value = {b"margin_used": b"95000.0"}
        self._setup_user(mock_db_session, capital=100000.0)

        order = {"symbol": "NIFTY", "side": "BUY", "quantity": 50}
        result = worker.validate_order(order)

        assert result == (False, "Insufficient margin")
        # Duplicate check should not have been called
        mock_redis.lrange.assert_not_called()

    def test_margin_error_propagates_message(self, worker, mock_redis, mock_db_session):
        """Margin check error messages are passed through to validate_order result."""
        # Kill switch inactive
        mock_redis.get.return_value = b"false"
        # Margin check fails due to Redis error
        mock_redis.hgetall.side_effect = redis.ConnectionError("Connection refused")

        order = {"symbol": "NIFTY", "side": "BUY", "quantity": 50}
        result = worker.validate_order(order)

        assert result == (False, "Margin check failed: Redis unavailable")

    def test_non_killswitch_reason_does_not_bypass(self, worker, mock_redis):
        """Orders with reason != 'killswitch_exit' do NOT bypass kill switch."""
        mock_redis.get.return_value = b"true"

        order = {"symbol": "NIFTY", "side": "BUY", "quantity": 50, "reason": "user_order"}
        result = worker.validate_order(order)

        assert result == (False, "Kill switch is active")

    def test_order_without_reason_field(self, worker, mock_redis):
        """Orders without a 'reason' field do not bypass kill switch."""
        mock_redis.get.return_value = b"true"

        order = {"symbol": "NIFTY", "side": "BUY", "quantity": 50}
        result = worker.validate_order(order)

        assert result == (False, "Kill switch is active")


# ============================================================
# Mark Recent Order Tests
# ============================================================


class TestMarkRecentOrder:
    """Tests for ExecutionWorker.mark_recent_order().

    Requirements covered:
    - 1.3.9: Prevent duplicate orders within 60 seconds
    """

    def test_successful_marking_calls_lpush(self, worker, mock_redis):
        """Pushes order signature to left of user's recent_orders list."""
        order = {"symbol": "NIFTY", "side": "BUY", "quantity": 50}

        worker.mark_recent_order(order)

        expected_key = "user:1:recent_orders"
        mock_redis.lpush.assert_called_once_with(expected_key, "NIFTY:BUY:50")

    def test_successful_marking_calls_ltrim(self, worker, mock_redis):
        """Trims list to keep only the last 10 orders."""
        order = {"symbol": "NIFTY", "side": "BUY", "quantity": 50}

        worker.mark_recent_order(order)

        expected_key = "user:1:recent_orders"
        mock_redis.ltrim.assert_called_once_with(expected_key, 0, 9)

    def test_successful_marking_calls_expire(self, worker, mock_redis):
        """Sets 60-second TTL on the recent_orders list."""
        order = {"symbol": "NIFTY", "side": "BUY", "quantity": 50}

        worker.mark_recent_order(order)

        expected_key = "user:1:recent_orders"
        mock_redis.expire.assert_called_once_with(expected_key, 60)

    def test_uses_correct_user_scoped_key(self, mock_kite, mock_redis, mock_db_session):
        """Uses RedisKeys.user_recent_orders(user_id) for the correct user-scoped key."""
        worker = ExecutionWorker(
            user_id=42,
            kite_client=mock_kite,
            redis_client=mock_redis,
            db_session=mock_db_session,
        )
        order = {"symbol": "BANKNIFTY", "side": "SELL", "quantity": 25}

        worker.mark_recent_order(order)

        expected_key = "user:42:recent_orders"
        mock_redis.lpush.assert_called_once_with(expected_key, "BANKNIFTY:SELL:25")
        mock_redis.ltrim.assert_called_once_with(expected_key, 0, 9)
        mock_redis.expire.assert_called_once_with(expected_key, 60)

    def test_uses_create_order_signature(self, worker, mock_redis):
        """Uses create_order_signature to generate the signature."""
        order = {"symbol": "RELIANCE", "side": "BUY", "quantity": 100}

        with patch.object(worker, "create_order_signature", return_value="RELIANCE:BUY:100") as mock_sig:
            worker.mark_recent_order(order)

        mock_sig.assert_called_once_with(order)
        mock_redis.lpush.assert_called_once_with("user:1:recent_orders", "RELIANCE:BUY:100")

    def test_redis_error_does_not_raise(self, worker, mock_redis):
        """Redis errors are caught and don't propagate — trade flow is not broken."""
        order = {"symbol": "NIFTY", "side": "BUY", "quantity": 50}
        mock_redis.lpush.side_effect = redis.ConnectionError("Connection refused")

        # Should not raise
        worker.mark_recent_order(order)

    def test_redis_timeout_does_not_raise(self, worker, mock_redis):
        """Redis timeout errors are caught and don't propagate."""
        order = {"symbol": "NIFTY", "side": "BUY", "quantity": 50}
        mock_redis.lpush.side_effect = redis.TimeoutError("Read timed out")

        # Should not raise
        worker.mark_recent_order(order)

    def test_logs_error_on_redis_failure(self, worker, mock_redis, caplog):
        """Logs an error when Redis fails during marking."""
        order = {"symbol": "NIFTY", "side": "BUY", "quantity": 50}
        mock_redis.lpush.side_effect = redis.ConnectionError("Connection refused")

        with caplog.at_level(logging.ERROR):
            worker.mark_recent_order(order)

        assert "Redis error marking recent order" in caplog.text

    def test_invalid_order_does_not_raise(self, worker, mock_redis):
        """Invalid order data is handled gracefully without raising."""
        # Missing required keys
        order = {"symbol": "NIFTY"}

        # Should not raise
        worker.mark_recent_order(order)

    def test_none_order_does_not_raise(self, worker, mock_redis):
        """None order is handled gracefully without raising."""
        # Should not raise
        worker.mark_recent_order(None)

    def test_operation_order_lpush_ltrim_expire(self, worker, mock_redis):
        """Operations are called in correct order: lpush, ltrim, expire."""
        order = {"symbol": "NIFTY", "side": "BUY", "quantity": 50}
        call_order = []
        mock_redis.lpush.side_effect = lambda *a: call_order.append("lpush")
        mock_redis.ltrim.side_effect = lambda *a: call_order.append("ltrim")
        mock_redis.expire.side_effect = lambda *a: call_order.append("expire")

        worker.mark_recent_order(order)

        assert call_order == ["lpush", "ltrim", "expire"]


# ============================================================
# Place Order Tests
# ============================================================


class TestPlaceOrder:
    """Tests for ExecutionWorker.place_order().

    Requirements covered:
    - 1.3.4: Place orders with broker via Kite API
    """

    def test_successful_market_order(self, worker, mock_kite):
        """Returns success dict with order_id when kite.place_order succeeds."""
        mock_kite.VARIETY_REGULAR = "regular"
        mock_kite.place_order.return_value = "220901000012345"

        order = {
            "exchange": "NFO",
            "symbol": "NIFTY2390718000CE",
            "side": "BUY",
            "quantity": 50,
        }

        result = worker.place_order(order)

        assert result == {
            "success": True,
            "order_id": "220901000012345",
            "message": "Order placed successfully",
            "error_type": None,
            "retryable": False,
        }

    def test_calls_kite_with_correct_params_market_order(self, worker, mock_kite):
        """Passes correct parameters to kite.place_order for a MARKET order."""
        mock_kite.VARIETY_REGULAR = "regular"
        mock_kite.place_order.return_value = "123456"

        order = {
            "exchange": "NFO",
            "symbol": "BANKNIFTY2390745000PE",
            "side": "SELL",
            "quantity": 25,
        }

        worker.place_order(order)

        mock_kite.place_order.assert_called_once_with(
            variety="regular",
            exchange="NFO",
            tradingsymbol="BANKNIFTY2390745000PE",
            transaction_type="SELL",
            quantity=25,
            product="MIS",
            order_type="MARKET",
            price=None,
        )

    def test_calls_kite_with_limit_order_type(self, worker, mock_kite):
        """Uses order_type from order dict when specified (e.g., LIMIT)."""
        mock_kite.VARIETY_REGULAR = "regular"
        mock_kite.place_order.return_value = "789012"

        order = {
            "exchange": "NSE",
            "symbol": "RELIANCE",
            "side": "BUY",
            "quantity": 10,
            "order_type": "LIMIT",
            "price": 2450.50,
        }

        worker.place_order(order)

        mock_kite.place_order.assert_called_once_with(
            variety="regular",
            exchange="NSE",
            tradingsymbol="RELIANCE",
            transaction_type="BUY",
            quantity=10,
            product="MIS",
            order_type="LIMIT",
            price=2450.50,
        )

    def test_defaults_order_type_to_market(self, worker, mock_kite):
        """Defaults to MARKET order_type when not specified in order dict."""
        mock_kite.VARIETY_REGULAR = "regular"
        mock_kite.place_order.return_value = "111111"

        order = {
            "exchange": "NFO",
            "symbol": "NIFTY2390718000CE",
            "side": "BUY",
            "quantity": 50,
        }

        worker.place_order(order)

        call_kwargs = mock_kite.place_order.call_args[1]
        assert call_kwargs["order_type"] == "MARKET"

    def test_price_is_none_for_market_order(self, worker, mock_kite):
        """Price is None when not specified (market orders don't need price)."""
        mock_kite.VARIETY_REGULAR = "regular"
        mock_kite.place_order.return_value = "111111"

        order = {
            "exchange": "NFO",
            "symbol": "NIFTY2390718000CE",
            "side": "BUY",
            "quantity": 50,
        }

        worker.place_order(order)

        call_kwargs = mock_kite.place_order.call_args[1]
        assert call_kwargs["price"] is None

    def test_uses_variety_regular(self, worker, mock_kite):
        """Always uses VARIETY_REGULAR for order placement."""
        mock_kite.VARIETY_REGULAR = "regular"
        mock_kite.place_order.return_value = "111111"

        order = {
            "exchange": "NFO",
            "symbol": "NIFTY2390718000CE",
            "side": "BUY",
            "quantity": 50,
        }

        worker.place_order(order)

        call_kwargs = mock_kite.place_order.call_args[1]
        assert call_kwargs["variety"] == "regular"

    def test_uses_product_mis(self, worker, mock_kite):
        """Always uses product='MIS' for intraday trading."""
        mock_kite.VARIETY_REGULAR = "regular"
        mock_kite.place_order.return_value = "111111"

        order = {
            "exchange": "NFO",
            "symbol": "NIFTY2390718000CE",
            "side": "BUY",
            "quantity": 50,
        }

        worker.place_order(order)

        call_kwargs = mock_kite.place_order.call_args[1]
        assert call_kwargs["product"] == "MIS"

    def test_maps_symbol_to_tradingsymbol(self, worker, mock_kite):
        """Maps order['symbol'] to tradingsymbol parameter in Kite API."""
        mock_kite.VARIETY_REGULAR = "regular"
        mock_kite.place_order.return_value = "111111"

        order = {
            "exchange": "NFO",
            "symbol": "INFY2390718000CE",
            "side": "BUY",
            "quantity": 50,
        }

        worker.place_order(order)

        call_kwargs = mock_kite.place_order.call_args[1]
        assert call_kwargs["tradingsymbol"] == "INFY2390718000CE"

    def test_maps_side_to_transaction_type(self, worker, mock_kite):
        """Maps order['side'] to transaction_type parameter in Kite API."""
        mock_kite.VARIETY_REGULAR = "regular"
        mock_kite.place_order.return_value = "111111"

        order = {
            "exchange": "NFO",
            "symbol": "NIFTY2390718000CE",
            "side": "SELL",
            "quantity": 50,
        }

        worker.place_order(order)

        call_kwargs = mock_kite.place_order.call_args[1]
        assert call_kwargs["transaction_type"] == "SELL"

    def test_return_dict_keys(self, worker, mock_kite):
        """Return dict always has keys: success, order_id, message, error_type, retryable."""
        mock_kite.VARIETY_REGULAR = "regular"
        mock_kite.place_order.return_value = "220901000012345"

        order = {
            "exchange": "NFO",
            "symbol": "NIFTY2390718000CE",
            "side": "BUY",
            "quantity": 50,
        }

        result = worker.place_order(order)

        assert "success" in result
        assert "order_id" in result
        assert "message" in result
        assert "error_type" in result
        assert "retryable" in result

    def test_success_is_true_on_successful_placement(self, worker, mock_kite):
        """success is True when kite.place_order returns an order_id."""
        mock_kite.VARIETY_REGULAR = "regular"
        mock_kite.place_order.return_value = "220901000012345"

        order = {
            "exchange": "NFO",
            "symbol": "NIFTY2390718000CE",
            "side": "BUY",
            "quantity": 50,
        }

        result = worker.place_order(order)

        assert result["success"] is True

    def test_exception_returns_failure_dict(self, worker, mock_kite):
        """Returns failure dict with error message when kite.place_order raises."""
        mock_kite.VARIETY_REGULAR = "regular"
        mock_kite.place_order.side_effect = Exception("Insufficient funds")

        order = {
            "exchange": "NFO",
            "symbol": "NIFTY2390718000CE",
            "side": "BUY",
            "quantity": 50,
        }

        result = worker.place_order(order)

        assert result == {
            "success": False,
            "order_id": None,
            "message": "Insufficient funds",
            "error_type": "Exception",
            "retryable": False,
        }

    def test_nse_exchange_order(self, worker, mock_kite):
        """Handles NSE exchange orders correctly."""
        mock_kite.VARIETY_REGULAR = "regular"
        mock_kite.place_order.return_value = "654321"

        order = {
            "exchange": "NSE",
            "symbol": "RELIANCE",
            "side": "BUY",
            "quantity": 1,
        }

        result = worker.place_order(order)

        assert result["success"] is True
        assert result["order_id"] == "654321"
        call_kwargs = mock_kite.place_order.call_args[1]
        assert call_kwargs["exchange"] == "NSE"


# ============================================================
# Place Order - Kite API Error Handling Tests
# ============================================================


class TestPlaceOrderKiteErrors:
    """Tests for specific Kite API exception handling in place_order().

    Requirements covered:
    - 1.3.5: Retry failed orders up to 3 times with exponential backoff
    - 2.3.6: Handle broker API failures with retries

    Each test verifies:
    - The correct error_type is returned
    - The retryable flag is correctly set
    - The appropriate log level is used
    - The message contains useful error context
    """

    def test_token_exception_returns_non_retryable(self, worker, mock_kite):
        """TokenException is logged at ERROR and marked non-retryable."""
        mock_kite.VARIETY_REGULAR = "regular"
        mock_kite.place_order.side_effect = kite_exceptions.TokenException(
            "Token is invalid or has expired"
        )

        order = {
            "exchange": "NFO",
            "symbol": "NIFTY2390718000CE",
            "side": "BUY",
            "quantity": 50,
        }

        result = worker.place_order(order)

        assert result["success"] is False
        assert result["order_id"] is None
        assert result["error_type"] == "TokenException"
        assert result["retryable"] is False
        assert "Token" in result["message"] or "token" in result["message"].lower()

    def test_token_exception_logs_at_error_level(self, worker, mock_kite, caplog):
        """TokenException is logged at ERROR level."""
        mock_kite.VARIETY_REGULAR = "regular"
        mock_kite.place_order.side_effect = kite_exceptions.TokenException(
            "Token is invalid or has expired"
        )

        order = {
            "exchange": "NFO",
            "symbol": "NIFTY2390718000CE",
            "side": "BUY",
            "quantity": 50,
        }

        with caplog.at_level(logging.ERROR):
            worker.place_order(order)

        assert "Token error" in caplog.text
        assert any(r.levelno == logging.ERROR for r in caplog.records)

    def test_network_exception_returns_retryable(self, worker, mock_kite):
        """NetworkException is logged at WARNING and marked retryable."""
        mock_kite.VARIETY_REGULAR = "regular"
        mock_kite.place_order.side_effect = kite_exceptions.NetworkException(
            "Connection timed out"
        )

        order = {
            "exchange": "NFO",
            "symbol": "NIFTY2390718000CE",
            "side": "BUY",
            "quantity": 50,
        }

        result = worker.place_order(order)

        assert result["success"] is False
        assert result["order_id"] is None
        assert result["error_type"] == "NetworkException"
        assert result["retryable"] is True
        assert "Network" in result["message"] or "network" in result["message"].lower()

    def test_network_exception_logs_at_warning_level(self, worker, mock_kite, caplog):
        """NetworkException is logged at WARNING level (transient)."""
        mock_kite.VARIETY_REGULAR = "regular"
        mock_kite.place_order.side_effect = kite_exceptions.NetworkException(
            "Connection timed out"
        )

        order = {
            "exchange": "NFO",
            "symbol": "NIFTY2390718000CE",
            "side": "BUY",
            "quantity": 50,
        }

        with caplog.at_level(logging.WARNING):
            worker.place_order(order)

        assert "Network error" in caplog.text
        assert any(r.levelno == logging.WARNING for r in caplog.records)

    def test_order_exception_returns_non_retryable(self, worker, mock_kite):
        """OrderException is logged at WARNING and marked non-retryable."""
        mock_kite.VARIETY_REGULAR = "regular"
        mock_kite.place_order.side_effect = kite_exceptions.OrderException(
            "Order rejected: Insufficient margin"
        )

        order = {
            "exchange": "NFO",
            "symbol": "NIFTY2390718000CE",
            "side": "BUY",
            "quantity": 50,
        }

        result = worker.place_order(order)

        assert result["success"] is False
        assert result["order_id"] is None
        assert result["error_type"] == "OrderException"
        assert result["retryable"] is False
        assert "rejected" in result["message"].lower()

    def test_order_exception_logs_at_warning_level(self, worker, mock_kite, caplog):
        """OrderException is logged at WARNING level."""
        mock_kite.VARIETY_REGULAR = "regular"
        mock_kite.place_order.side_effect = kite_exceptions.OrderException(
            "Order rejected: Insufficient margin"
        )

        order = {
            "exchange": "NFO",
            "symbol": "NIFTY2390718000CE",
            "side": "BUY",
            "quantity": 50,
        }

        with caplog.at_level(logging.WARNING):
            worker.place_order(order)

        assert "Order rejected" in caplog.text
        assert any(r.levelno == logging.WARNING for r in caplog.records)

    def test_input_exception_returns_non_retryable(self, worker, mock_kite):
        """InputException is logged at ERROR and marked non-retryable."""
        mock_kite.VARIETY_REGULAR = "regular"
        mock_kite.place_order.side_effect = kite_exceptions.InputException(
            "Invalid quantity: must be positive"
        )

        order = {
            "exchange": "NFO",
            "symbol": "NIFTY2390718000CE",
            "side": "BUY",
            "quantity": -10,
        }

        result = worker.place_order(order)

        assert result["success"] is False
        assert result["order_id"] is None
        assert result["error_type"] == "InputException"
        assert result["retryable"] is False
        assert "Invalid" in result["message"] or "parameter" in result["message"].lower()

    def test_input_exception_logs_at_error_level(self, worker, mock_kite, caplog):
        """InputException is logged at ERROR level."""
        mock_kite.VARIETY_REGULAR = "regular"
        mock_kite.place_order.side_effect = kite_exceptions.InputException(
            "Invalid quantity: must be positive"
        )

        order = {
            "exchange": "NFO",
            "symbol": "NIFTY2390718000CE",
            "side": "BUY",
            "quantity": -10,
        }

        with caplog.at_level(logging.ERROR):
            worker.place_order(order)

        assert "Invalid order parameters" in caplog.text
        assert any(r.levelno == logging.ERROR for r in caplog.records)

    def test_general_exception_returns_non_retryable(self, worker, mock_kite):
        """GeneralException is logged at ERROR and marked non-retryable."""
        mock_kite.VARIETY_REGULAR = "regular"
        mock_kite.place_order.side_effect = kite_exceptions.GeneralException(
            "Internal server error"
        )

        order = {
            "exchange": "NFO",
            "symbol": "NIFTY2390718000CE",
            "side": "BUY",
            "quantity": 50,
        }

        result = worker.place_order(order)

        assert result["success"] is False
        assert result["order_id"] is None
        assert result["error_type"] == "GeneralException"
        assert result["retryable"] is False
        assert "API error" in result["message"] or "error" in result["message"].lower()

    def test_general_exception_logs_at_error_level(self, worker, mock_kite, caplog):
        """GeneralException is logged at ERROR level."""
        mock_kite.VARIETY_REGULAR = "regular"
        mock_kite.place_order.side_effect = kite_exceptions.GeneralException(
            "Internal server error"
        )

        order = {
            "exchange": "NFO",
            "symbol": "NIFTY2390718000CE",
            "side": "BUY",
            "quantity": 50,
        }

        with caplog.at_level(logging.ERROR):
            worker.place_order(order)

        assert "General Kite API error" in caplog.text
        assert any(r.levelno == logging.ERROR for r in caplog.records)

    def test_unknown_exception_returns_non_retryable(self, worker, mock_kite):
        """Unknown exceptions are logged at ERROR and marked non-retryable."""
        mock_kite.VARIETY_REGULAR = "regular"
        mock_kite.place_order.side_effect = RuntimeError("Something unexpected")

        order = {
            "exchange": "NFO",
            "symbol": "NIFTY2390718000CE",
            "side": "BUY",
            "quantity": 50,
        }

        result = worker.place_order(order)

        assert result["success"] is False
        assert result["order_id"] is None
        assert result["error_type"] == "RuntimeError"
        assert result["retryable"] is False
        assert "Something unexpected" in result["message"]

    def test_unknown_exception_logs_at_error_level(self, worker, mock_kite, caplog):
        """Unknown exceptions are logged at ERROR level."""
        mock_kite.VARIETY_REGULAR = "regular"
        mock_kite.place_order.side_effect = RuntimeError("Something unexpected")

        order = {
            "exchange": "NFO",
            "symbol": "NIFTY2390718000CE",
            "side": "BUY",
            "quantity": 50,
        }

        with caplog.at_level(logging.ERROR):
            worker.place_order(order)

        assert "Unexpected error" in caplog.text
        assert any(r.levelno == logging.ERROR for r in caplog.records)

    def test_success_has_no_error_type(self, worker, mock_kite):
        """Successful orders have error_type=None and retryable=False."""
        mock_kite.VARIETY_REGULAR = "regular"
        mock_kite.place_order.return_value = "111222333"

        order = {
            "exchange": "NFO",
            "symbol": "NIFTY2390718000CE",
            "side": "BUY",
            "quantity": 50,
        }

        result = worker.place_order(order)

        assert result["error_type"] is None
        assert result["retryable"] is False

    def test_only_network_exception_is_retryable(self, worker, mock_kite):
        """Only NetworkException sets retryable=True; all others are False."""
        mock_kite.VARIETY_REGULAR = "regular"

        order = {
            "exchange": "NFO",
            "symbol": "NIFTY2390718000CE",
            "side": "BUY",
            "quantity": 50,
        }

        # TokenException -> not retryable
        mock_kite.place_order.side_effect = kite_exceptions.TokenException("expired")
        assert worker.place_order(order)["retryable"] is False

        # NetworkException -> retryable
        mock_kite.place_order.side_effect = kite_exceptions.NetworkException("timeout")
        assert worker.place_order(order)["retryable"] is True

        # OrderException -> not retryable
        mock_kite.place_order.side_effect = kite_exceptions.OrderException("rejected")
        assert worker.place_order(order)["retryable"] is False

        # InputException -> not retryable
        mock_kite.place_order.side_effect = kite_exceptions.InputException("bad input")
        assert worker.place_order(order)["retryable"] is False

        # GeneralException -> not retryable
        mock_kite.place_order.side_effect = kite_exceptions.GeneralException("general")
        assert worker.place_order(order)["retryable"] is False

        # Unknown Exception -> not retryable
        mock_kite.place_order.side_effect = ValueError("some value error")
        assert worker.place_order(order)["retryable"] is False


# ============================================================
# Execute With Retry Tests
# ============================================================


class TestExecuteWithRetry:
    """Tests for ExecutionWorker.execute_with_retry().

    Requirements covered:
    - 1.3.5: Retry failed orders up to 3 times with exponential backoff
    - 2.3.6: Handle broker API failures with retries
    """

    def _make_order(self):
        """Helper to create a standard test order."""
        return {
            "exchange": "NSE",
            "symbol": "NIFTY",
            "side": "BUY",
            "quantity": 50,
            "order_type": "MARKET",
        }

    def _success_result(self, order_id="12345"):
        """Helper to create a successful placement result."""
        return {
            "success": True,
            "order_id": order_id,
            "message": "Order placed successfully",
            "error_type": None,
            "retryable": False,
        }

    def _retryable_failure(self, msg="Network error: timeout"):
        """Helper to create a retryable failure result."""
        return {
            "success": False,
            "order_id": None,
            "message": msg,
            "error_type": "NetworkException",
            "retryable": True,
        }

    def _non_retryable_failure(self, msg="Token error: expired"):
        """Helper to create a non-retryable failure result."""
        return {
            "success": False,
            "order_id": None,
            "message": msg,
            "error_type": "TokenException",
            "retryable": False,
        }

    @patch("src.workers.execution_worker.time.sleep", return_value=None)
    def test_success_on_first_attempt(self, mock_sleep, worker):
        """Returns success immediately without retrying when first attempt succeeds."""
        order = self._make_order()
        worker.place_order = MagicMock(return_value=self._success_result())

        result = worker.execute_with_retry(order)

        assert result["success"] is True
        assert result["order_id"] == "12345"
        assert result["attempts"] == 1
        worker.place_order.assert_called_once_with(order)
        mock_sleep.assert_not_called()

    @patch("src.workers.execution_worker.time.sleep", return_value=None)
    def test_success_on_second_attempt(self, mock_sleep, worker):
        """Returns success after one retry when second attempt succeeds."""
        order = self._make_order()
        worker.place_order = MagicMock(
            side_effect=[self._retryable_failure(), self._success_result()]
        )

        result = worker.execute_with_retry(order)

        assert result["success"] is True
        assert result["order_id"] == "12345"
        assert result["attempts"] == 2
        assert worker.place_order.call_count == 2
        mock_sleep.assert_called_once_with(1.0)  # backoff * 1

    @patch("src.workers.execution_worker.time.sleep", return_value=None)
    def test_success_on_third_attempt(self, mock_sleep, worker):
        """Returns success after two retries when third attempt succeeds."""
        order = self._make_order()
        worker.place_order = MagicMock(
            side_effect=[
                self._retryable_failure(),
                self._retryable_failure(),
                self._success_result(),
            ]
        )

        result = worker.execute_with_retry(order)

        assert result["success"] is True
        assert result["attempts"] == 3
        assert worker.place_order.call_count == 3
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1.0)  # backoff * 1
        mock_sleep.assert_any_call(2.0)  # backoff * 2

    @patch("src.workers.execution_worker.time.sleep", return_value=None)
    def test_non_retryable_failure_no_retry(self, mock_sleep, worker):
        """Returns failure immediately without retrying for non-retryable errors."""
        order = self._make_order()
        worker.place_order = MagicMock(return_value=self._non_retryable_failure())

        result = worker.execute_with_retry(order)

        assert result["success"] is False
        assert result["error_type"] == "TokenException"
        assert result["attempts"] == 1
        worker.place_order.assert_called_once_with(order)
        mock_sleep.assert_not_called()

    @patch("src.workers.execution_worker.time.sleep", return_value=None)
    def test_max_retries_exhausted(self, mock_sleep, worker):
        """Returns failure with max-retries message after exhausting all retries."""
        order = self._make_order()
        worker.place_order = MagicMock(return_value=self._retryable_failure())

        result = worker.execute_with_retry(order)

        assert result["success"] is False
        assert result["attempts"] == 4  # 1 initial + 3 retries
        assert "Max retries (3) exhausted" in result["message"]
        assert worker.place_order.call_count == 4  # 1 initial + 3 retries
        assert mock_sleep.call_count == 3

    @patch("src.workers.execution_worker.time.sleep", return_value=None)
    def test_retry_backoff_timing(self, mock_sleep, worker):
        """Verifies exponential backoff timing: backoff * attempt_number."""
        order = self._make_order()
        worker.place_order = MagicMock(return_value=self._retryable_failure())

        worker.execute_with_retry(order)

        # Backoff should be: 1*1=1, 1*2=2, 1*3=3 seconds
        expected_calls = [
            ((1.0,),),
            ((2.0,),),
            ((3.0,),),
        ]
        assert mock_sleep.call_args_list == [
            ((1.0,),),
            ((2.0,),),
            ((3.0,),),
        ]

    @patch("src.workers.execution_worker.time.sleep", return_value=None)
    def test_retry_stops_on_non_retryable_during_retries(self, mock_sleep, worker):
        """Stops retrying if a retry attempt returns a non-retryable error."""
        order = self._make_order()
        worker.place_order = MagicMock(
            side_effect=[
                self._retryable_failure(),
                self._non_retryable_failure("Token error: auth revoked"),
            ]
        )

        result = worker.execute_with_retry(order)

        assert result["success"] is False
        assert result["error_type"] == "TokenException"
        assert result["attempts"] == 2
        assert worker.place_order.call_count == 2
        mock_sleep.assert_called_once_with(1.0)

    @patch("src.workers.execution_worker.time.sleep", return_value=None)
    def test_custom_retry_backoff(self, mock_sleep, mock_kite, mock_redis, mock_db_session):
        """Respects custom retry_backoff value."""
        worker = ExecutionWorker(
            user_id=1,
            kite_client=mock_kite,
            redis_client=mock_redis,
            db_session=mock_db_session,
        )
        worker.retry_backoff = 2.0
        order = {
            "exchange": "NSE",
            "symbol": "NIFTY",
            "side": "BUY",
            "quantity": 50,
            "order_type": "MARKET",
        }
        worker.place_order = MagicMock(
            return_value={
                "success": False,
                "order_id": None,
                "message": "Network error",
                "error_type": "NetworkException",
                "retryable": True,
            }
        )

        worker.execute_with_retry(order)

        # Backoff should be: 2*1=2, 2*2=4, 2*3=6 seconds
        assert mock_sleep.call_args_list == [
            ((2.0,),),
            ((4.0,),),
            ((6.0,),),
        ]

    @patch("src.workers.execution_worker.time.sleep", return_value=None)
    def test_logs_retry_attempts(self, mock_sleep, worker, caplog):
        """Logs a warning for each retry attempt."""
        order = self._make_order()
        worker.place_order = MagicMock(return_value=self._retryable_failure())

        with caplog.at_level(logging.WARNING):
            worker.execute_with_retry(order)

        assert "Retrying order for user 1, attempt 1/3" in caplog.text
        assert "Retrying order for user 1, attempt 2/3" in caplog.text
        assert "Retrying order for user 1, attempt 3/3" in caplog.text

    @patch("src.workers.execution_worker.time.sleep", return_value=None)
    def test_logs_error_on_max_retries_exhausted(self, mock_sleep, worker, caplog):
        """Logs an error when max retries are exhausted."""
        order = self._make_order()
        worker.place_order = MagicMock(return_value=self._retryable_failure())

        with caplog.at_level(logging.ERROR):
            worker.execute_with_retry(order)

        assert "Max retries exhausted" in caplog.text


# ============================================================
# Check Order Status Tests
# ============================================================


class TestCheckOrderStatus:
    """Tests for ExecutionWorker.check_order_status().

    Verifies that the method correctly queries broker order history
    and returns the order's current status, handling errors gracefully.

    Requirements covered:
    - 1.3.5: Retry failed orders up to 3 times with exponential backoff
    """

    def test_returns_complete_status_when_order_filled(self, worker, mock_kite):
        """Returns status='COMPLETE' and filled=True when order is complete."""
        mock_kite.order_history.return_value = [
            {"status": "OPEN"},
            {"status": "COMPLETE"},
        ]

        result = worker.check_order_status("220901000012345")

        assert result == {"status": "COMPLETE", "filled": True}
        mock_kite.order_history.assert_called_once_with("220901000012345")

    def test_returns_pending_status_when_order_open(self, worker, mock_kite):
        """Returns status='OPEN' and filled=False when order is still open."""
        mock_kite.order_history.return_value = [
            {"status": "OPEN"},
        ]

        result = worker.check_order_status("220901000012345")

        assert result == {"status": "OPEN", "filled": False}

    def test_returns_rejected_status(self, worker, mock_kite):
        """Returns status='REJECTED' and filled=False when order is rejected."""
        mock_kite.order_history.return_value = [
            {"status": "OPEN"},
            {"status": "REJECTED"},
        ]

        result = worker.check_order_status("220901000012345")

        assert result == {"status": "REJECTED", "filled": False}

    def test_returns_unknown_on_exception(self, worker, mock_kite):
        """Returns status='UNKNOWN' and filled=False when an exception occurs."""
        mock_kite.order_history.side_effect = Exception("Connection timeout")

        result = worker.check_order_status("220901000012345")

        assert result == {"status": "UNKNOWN", "filled": False}

    def test_returns_unknown_on_network_exception(self, worker, mock_kite):
        """Returns UNKNOWN status on NetworkException (can't determine real status)."""
        mock_kite.order_history.side_effect = kite_exceptions.NetworkException(
            "Connection timed out"
        )

        result = worker.check_order_status("220901000012345")

        assert result == {"status": "UNKNOWN", "filled": False}

    def test_returns_unknown_on_empty_history(self, worker, mock_kite):
        """Returns UNKNOWN status when order history is empty."""
        mock_kite.order_history.return_value = []

        result = worker.check_order_status("220901000012345")

        assert result == {"status": "UNKNOWN", "filled": False}

    def test_returns_unknown_on_none_history(self, worker, mock_kite):
        """Returns UNKNOWN status when order history is None."""
        mock_kite.order_history.return_value = None

        result = worker.check_order_status("220901000012345")

        assert result == {"status": "UNKNOWN", "filled": False}

    def test_uses_latest_status_entry(self, worker, mock_kite):
        """Uses the last entry in order_history (most recent status)."""
        mock_kite.order_history.return_value = [
            {"status": "OPEN"},
            {"status": "PENDING"},
            {"status": "COMPLETE"},
        ]

        result = worker.check_order_status("220901000012345")

        assert result["status"] == "COMPLETE"
        assert result["filled"] is True

    def test_handles_missing_status_key(self, worker, mock_kite):
        """Returns UNKNOWN when status key is missing from order history entry."""
        mock_kite.order_history.return_value = [
            {"order_id": "123", "quantity": 50},
        ]

        result = worker.check_order_status("220901000012345")

        assert result == {"status": "UNKNOWN", "filled": False}

    def test_logs_warning_on_exception(self, worker, mock_kite, caplog):
        """Logs a warning when an exception occurs during status check."""
        mock_kite.order_history.side_effect = Exception("API timeout")

        with caplog.at_level(logging.WARNING):
            worker.check_order_status("220901000012345")

        assert "Error checking order status" in caplog.text


# ============================================================
# Execute With Retry - Order Status Check Tests
# ============================================================


class TestExecuteWithRetryOrderStatusCheck:
    """Tests for execute_with_retry order status check before retry.

    Verifies that the method checks order status before retrying to
    prevent duplicate order placement when the previous attempt's order
    was actually filled despite the network error.

    Requirements covered:
    - 1.3.5: Retry failed orders up to 3 times with exponential backoff
    """

    def _make_order(self):
        """Helper to create a standard test order."""
        return {
            "exchange": "NSE",
            "symbol": "NIFTY",
            "side": "BUY",
            "quantity": 50,
            "order_type": "MARKET",
        }

    @patch("src.workers.execution_worker.time.sleep", return_value=None)
    def test_skips_retry_when_previous_order_was_filled(self, mock_sleep, worker):
        """Returns success without retrying when previous order was actually filled."""
        order = self._make_order()

        # First attempt: network error but order_id was returned (rare but possible)
        first_result = {
            "success": False,
            "order_id": "220901000012345",
            "message": "Network error: timeout",
            "error_type": "NetworkException",
            "retryable": True,
        }
        worker.place_order = MagicMock(return_value=first_result)

        # Order status check reveals the order was filled
        worker.check_order_status = MagicMock(
            return_value={"status": "COMPLETE", "filled": True}
        )

        result = worker.execute_with_retry(order)

        assert result["success"] is True
        assert result["order_id"] == "220901000012345"
        assert result["message"] == "Order already filled (confirmed before retry)"
        # place_order called once (initial attempt), no retry happened
        worker.place_order.assert_called_once_with(order)
        worker.check_order_status.assert_called_once_with("220901000012345")

    @patch("src.workers.execution_worker.time.sleep", return_value=None)
    def test_proceeds_with_retry_when_status_unknown(self, mock_sleep, worker):
        """Proceeds with retry when order status check returns UNKNOWN."""
        order = self._make_order()

        # First attempt: network error with an order_id
        first_result = {
            "success": False,
            "order_id": "220901000012345",
            "message": "Network error: timeout",
            "error_type": "NetworkException",
            "retryable": True,
        }
        success_result = {
            "success": True,
            "order_id": "220901000099999",
            "message": "Order placed successfully",
            "error_type": None,
            "retryable": False,
        }
        worker.place_order = MagicMock(side_effect=[first_result, success_result])

        # Order status check returns UNKNOWN (can't determine, proceed with retry)
        worker.check_order_status = MagicMock(
            return_value={"status": "UNKNOWN", "filled": False}
        )

        result = worker.execute_with_retry(order)

        assert result["success"] is True
        assert result["order_id"] == "220901000099999"
        assert result["attempts"] == 2
        worker.check_order_status.assert_called_once_with("220901000012345")

    @patch("src.workers.execution_worker.time.sleep", return_value=None)
    def test_proceeds_with_retry_when_no_order_id(self, mock_sleep, worker):
        """Proceeds with retry normally when failed attempt has no order_id."""
        order = self._make_order()

        # First attempt: network error with no order_id (typical for network errors)
        first_result = {
            "success": False,
            "order_id": None,
            "message": "Network error: timeout",
            "error_type": "NetworkException",
            "retryable": True,
        }
        success_result = {
            "success": True,
            "order_id": "220901000099999",
            "message": "Order placed successfully",
            "error_type": None,
            "retryable": False,
        }
        worker.place_order = MagicMock(side_effect=[first_result, success_result])

        # check_order_status should NOT be called since there's no order_id
        worker.check_order_status = MagicMock()

        result = worker.execute_with_retry(order)

        assert result["success"] is True
        assert result["order_id"] == "220901000099999"
        assert result["attempts"] == 2
        worker.check_order_status.assert_not_called()

    @patch("src.workers.execution_worker.time.sleep", return_value=None)
    def test_proceeds_with_retry_when_order_pending(self, mock_sleep, worker):
        """Proceeds with retry when previous order is still PENDING."""
        order = self._make_order()

        first_result = {
            "success": False,
            "order_id": "220901000012345",
            "message": "Network error: timeout",
            "error_type": "NetworkException",
            "retryable": True,
        }
        success_result = {
            "success": True,
            "order_id": "220901000099999",
            "message": "Order placed successfully",
            "error_type": None,
            "retryable": False,
        }
        worker.place_order = MagicMock(side_effect=[first_result, success_result])

        # Order is still pending — not filled, should proceed with retry
        worker.check_order_status = MagicMock(
            return_value={"status": "PENDING", "filled": False}
        )

        result = worker.execute_with_retry(order)

        assert result["success"] is True
        assert result["order_id"] == "220901000099999"
        assert result["attempts"] == 2
        worker.check_order_status.assert_called_once_with("220901000012345")


# ============================================================
# Confirm Fill Tests
# ============================================================


class TestConfirmFill:
    """Tests for ExecutionWorker.confirm_fill().

    Requirements covered:
    - 1.3.6: Wait up to 30 seconds for order fill confirmation
    """

    def test_immediate_fill_on_first_poll(self, worker, mock_kite):
        """Returns fill details immediately when order is COMPLETE on first poll."""
        mock_kite.order_history.return_value = [
            {"status": "COMPLETE", "filled_quantity": 50, "average_price": 100.5}
        ]

        result = worker.confirm_fill("order123")

        assert result == {"filled": True, "quantity": 50, "price": 100.5}
        mock_kite.order_history.assert_called_once_with("order123")

    @patch("src.workers.execution_worker.time.sleep")
    @patch("src.workers.execution_worker.time.time")
    def test_fill_after_several_polls(self, mock_time, mock_sleep, worker, mock_kite):
        """Returns fill details after polling several times before COMPLETE."""
        # Simulate time progressing: start=0, then 1, 2, 3, 4 (for each loop check)
        mock_time.side_effect = [0, 1, 2, 3, 4]

        mock_kite.order_history.side_effect = [
            [{"status": "OPEN", "filled_quantity": 0, "average_price": 0}],
            [{"status": "OPEN", "filled_quantity": 0, "average_price": 0}],
            [{"status": "COMPLETE", "filled_quantity": 75, "average_price": 250.25}],
        ]

        result = worker.confirm_fill("order456")

        assert result == {"filled": True, "quantity": 75, "price": 250.25}
        assert mock_kite.order_history.call_count == 3
        assert mock_sleep.call_count == 2

    @patch("src.workers.execution_worker.time.sleep")
    def test_rejected_order_stops_polling(self, mock_sleep, worker, mock_kite):
        """Returns immediately with reason when order is REJECTED."""
        mock_kite.order_history.return_value = [
            {"status": "REJECTED", "status_message": "Insufficient funds"}
        ]

        result = worker.confirm_fill("order789")

        assert result == {"filled": False, "reason": "Insufficient funds"}
        mock_kite.order_history.assert_called_once_with("order789")
        mock_sleep.assert_not_called()

    @patch("src.workers.execution_worker.time.sleep")
    def test_cancelled_order_stops_polling(self, mock_sleep, worker, mock_kite):
        """Returns immediately with reason when order is CANCELLED."""
        mock_kite.order_history.return_value = [
            {"status": "CANCELLED", "status_message": "User cancelled"}
        ]

        result = worker.confirm_fill("order_cancel")

        assert result == {"filled": False, "reason": "User cancelled"}
        mock_kite.order_history.assert_called_once_with("order_cancel")
        mock_sleep.assert_not_called()

    @patch("src.workers.execution_worker.time.sleep")
    def test_rejected_without_status_message_uses_default(self, mock_sleep, worker, mock_kite):
        """Uses 'Order rejected' as default reason when status_message is missing."""
        mock_kite.order_history.return_value = [
            {"status": "REJECTED"}
        ]

        result = worker.confirm_fill("order_no_msg")

        assert result == {"filled": False, "reason": "Order rejected"}

    @patch("src.workers.execution_worker.time.sleep")
    @patch("src.workers.execution_worker.time.time")
    def test_timeout_after_30_seconds(self, mock_time, mock_sleep, worker, mock_kite):
        """Returns timeout reason after 30 seconds of polling without fill."""
        # Simulate time: start=0, then increments past timeout
        time_values = [0.0]  # initial call
        for i in range(1, 32):
            time_values.append(float(i))
        mock_time.side_effect = time_values

        # Always return OPEN status
        mock_kite.order_history.return_value = [
            {"status": "OPEN", "filled_quantity": 0, "average_price": 0}
        ]

        result = worker.confirm_fill("order_timeout", timeout=30)

        assert result == {"filled": False, "reason": "Timeout waiting for fill"}

    @patch("src.workers.execution_worker.time.sleep")
    @patch("src.workers.execution_worker.time.time")
    def test_exception_during_polling_continues(self, mock_time, mock_sleep, worker, mock_kite):
        """Exceptions during polling are handled gracefully and polling continues."""
        # Time: start=0, then 1, 2, 3
        mock_time.side_effect = [0, 1, 2, 3]

        mock_kite.order_history.side_effect = [
            Exception("Network error"),
            [{"status": "COMPLETE", "filled_quantity": 10, "average_price": 500.0}],
        ]

        result = worker.confirm_fill("order_error")

        assert result == {"filled": True, "quantity": 10, "price": 500.0}
        assert mock_kite.order_history.call_count == 2
        # sleep called once after the exception
        assert mock_sleep.call_count == 1

    def test_correct_fill_details_returned(self, worker, mock_kite):
        """Returns correct quantity and price from the order history."""
        mock_kite.order_history.return_value = [
            {"status": "PENDING", "filled_quantity": 0, "average_price": 0},
            {"status": "COMPLETE", "filled_quantity": 200, "average_price": 1234.56},
        ]

        result = worker.confirm_fill("order_details")

        # The method takes the last entry in order_history
        assert result == {"filled": True, "quantity": 200, "price": 1234.56}

    @patch("src.workers.execution_worker.time.sleep")
    @patch("src.workers.execution_worker.time.time")
    def test_custom_timeout_respected(self, mock_time, mock_sleep, worker, mock_kite):
        """Custom timeout value is respected."""
        # With timeout=5, time goes 0, 1, 2, 3, 4, 5 (exits on 5 >= 5)
        mock_time.side_effect = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
        mock_kite.order_history.return_value = [
            {"status": "OPEN", "filled_quantity": 0, "average_price": 0}
        ]

        result = worker.confirm_fill("order_custom_timeout", timeout=5)

        assert result == {"filled": False, "reason": "Timeout waiting for fill"}

    @patch("src.workers.execution_worker.time.sleep")
    @patch("src.workers.execution_worker.time.time")
    def test_polls_every_1_second(self, mock_time, mock_sleep, worker, mock_kite):
        """Verifies that time.sleep(1) is called between polls."""
        # Time: start=0, then 1, 2
        mock_time.side_effect = [0, 1, 2]

        mock_kite.order_history.side_effect = [
            [{"status": "OPEN", "filled_quantity": 0, "average_price": 0}],
            [{"status": "COMPLETE", "filled_quantity": 25, "average_price": 300.0}],
        ]

        worker.confirm_fill("order_sleep")

        # Sleep should be called with 1 second between polls
        mock_sleep.assert_called_with(1)


# ============================================================
# Store Trade Tests
# ============================================================


class TestStoreTrade:
    """Tests for ExecutionWorker.store_trade().

    Requirements covered:
    - 1.1: Store order and trade records
    - 7.1: Order record tracking
    """

    def test_stores_order_record_on_success(self, worker, mock_db_session):
        """Stores an Order record with correct fields when order is successful."""
        order = {
            "symbol": "NIFTY",
            "exchange": "NFO",
            "quantity": 50,
            "side": "BUY",
        }
        result = {
            "success": True,
            "order_id": "broker_123",
            "price": 18500.0,
            "status": "COMPLETE",
            "filled": False,
            "attempts": 1,
        }

        success = worker.store_trade(order, result)

        assert success is True
        # Should have called add once (order only, no trade since filled=False)
        assert mock_db_session.add.call_count == 1
        mock_db_session.commit.assert_called_once()

        # Verify the Order record fields
        order_record = mock_db_session.add.call_args_list[0][0][0]
        assert order_record.user_id == 1
        assert order_record.broker_order_id == "broker_123"
        assert order_record.symbol == "NIFTY"
        assert order_record.qty == 50
        assert order_record.price == 18500.0
        assert order_record.status == "COMPLETE"
        assert order_record.retries == 0
        assert order_record.error_message is None

    def test_stores_trade_record_when_filled(self, worker, mock_db_session):
        """Stores both Order and Trade records when order is filled."""
        order = {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "quantity": 100,
            "side": "BUY",
        }
        result = {
            "success": True,
            "order_id": "broker_456",
            "price": 2450.75,
            "status": "COMPLETE",
            "filled": True,
            "attempts": 1,
        }

        success = worker.store_trade(order, result)

        assert success is True
        # Should have called add twice (order + trade)
        assert mock_db_session.add.call_count == 2
        mock_db_session.commit.assert_called_once()

        # Verify the Trade record fields
        trade_record = mock_db_session.add.call_args_list[1][0][0]
        assert trade_record.user_id == 1
        assert trade_record.symbol == "RELIANCE"
        assert trade_record.exchange == "NSE"
        assert trade_record.qty == 100  # BUY -> positive qty
        assert trade_record.side == "BUY"
        assert trade_record.entry_price == 2450.75
        assert trade_record.status == "OPEN"

    def test_sell_order_has_negative_qty_in_trade(self, worker, mock_db_session):
        """SELL orders result in negative qty in the Trade record."""
        order = {
            "symbol": "INFY",
            "exchange": "NSE",
            "quantity": 25,
            "side": "SELL",
        }
        result = {
            "success": True,
            "order_id": "broker_789",
            "price": 1500.0,
            "status": "COMPLETE",
            "filled": True,
            "attempts": 1,
        }

        worker.store_trade(order, result)

        trade_record = mock_db_session.add.call_args_list[1][0][0]
        assert trade_record.qty == -25  # SELL -> negative qty

    def test_no_trade_record_when_not_filled(self, worker, mock_db_session):
        """Does not create a Trade record when result['filled'] is False."""
        order = {
            "symbol": "NIFTY",
            "exchange": "NFO",
            "quantity": 50,
            "side": "BUY",
        }
        result = {
            "success": True,
            "order_id": "broker_100",
            "price": 18000.0,
            "status": "COMPLETE",
            "filled": False,
            "attempts": 1,
        }

        worker.store_trade(order, result)

        # Only one add call (order only)
        assert mock_db_session.add.call_count == 1
        order_record = mock_db_session.add.call_args_list[0][0][0]
        assert isinstance(order_record, Order)

    def test_no_trade_record_when_filled_key_missing(self, worker, mock_db_session):
        """Does not create a Trade record when 'filled' key is absent from result."""
        order = {
            "symbol": "NIFTY",
            "exchange": "NFO",
            "quantity": 50,
            "side": "BUY",
        }
        result = {
            "success": True,
            "order_id": "broker_200",
            "price": 18000.0,
            "status": "COMPLETE",
            "attempts": 1,
        }

        worker.store_trade(order, result)

        # Only one add call (order only)
        assert mock_db_session.add.call_count == 1

    def test_retries_calculated_from_attempts(self, worker, mock_db_session):
        """retries = attempts - 1 in the Order record."""
        order = {
            "symbol": "NIFTY",
            "exchange": "NFO",
            "quantity": 50,
            "side": "BUY",
        }
        result = {
            "success": True,
            "order_id": "broker_300",
            "price": 18000.0,
            "status": "COMPLETE",
            "filled": False,
            "attempts": 3,
        }

        worker.store_trade(order, result)

        order_record = mock_db_session.add.call_args_list[0][0][0]
        assert order_record.retries == 2  # attempts(3) - 1

    def test_error_message_stored_on_failure(self, worker, mock_db_session):
        """Stores error_message when result indicates failure."""
        order = {
            "symbol": "NIFTY",
            "exchange": "NFO",
            "quantity": 50,
            "side": "BUY",
        }
        result = {
            "success": False,
            "order_id": None,
            "price": None,
            "status": "REJECTED",
            "filled": False,
            "attempts": 1,
            "message": "Order rejected by exchange",
        }

        worker.store_trade(order, result)

        order_record = mock_db_session.add.call_args_list[0][0][0]
        assert order_record.error_message == "Order rejected by exchange"
        assert order_record.status == "REJECTED"

    def test_no_error_message_on_success(self, worker, mock_db_session):
        """error_message is None when the order was successful."""
        order = {
            "symbol": "NIFTY",
            "exchange": "NFO",
            "quantity": 50,
            "side": "BUY",
        }
        result = {
            "success": True,
            "order_id": "broker_500",
            "price": 18000.0,
            "status": "COMPLETE",
            "filled": False,
            "attempts": 1,
            "message": "Order placed successfully",
        }

        worker.store_trade(order, result)

        order_record = mock_db_session.add.call_args_list[0][0][0]
        assert order_record.error_message is None

    def test_default_status_is_complete(self, worker, mock_db_session):
        """Defaults to 'COMPLETE' status when not provided in result."""
        order = {
            "symbol": "NIFTY",
            "exchange": "NFO",
            "quantity": 50,
            "side": "BUY",
        }
        result = {
            "success": True,
            "order_id": "broker_600",
            "price": 18000.0,
            "filled": False,
            "attempts": 1,
        }

        worker.store_trade(order, result)

        order_record = mock_db_session.add.call_args_list[0][0][0]
        assert order_record.status == "COMPLETE"

    def test_default_attempts_is_1(self, worker, mock_db_session):
        """Defaults to 1 attempt (0 retries) when 'attempts' not in result."""
        order = {
            "symbol": "NIFTY",
            "exchange": "NFO",
            "quantity": 50,
            "side": "BUY",
        }
        result = {
            "success": True,
            "order_id": "broker_700",
            "price": 18000.0,
            "status": "COMPLETE",
            "filled": False,
        }

        worker.store_trade(order, result)

        order_record = mock_db_session.add.call_args_list[0][0][0]
        assert order_record.retries == 0  # attempts(1) - 1

    def test_database_error_returns_false(self, worker, mock_db_session):
        """Returns False and rolls back on SQLAlchemy error."""
        order = {
            "symbol": "NIFTY",
            "exchange": "NFO",
            "quantity": 50,
            "side": "BUY",
        }
        result = {
            "success": True,
            "order_id": "broker_800",
            "price": 18000.0,
            "status": "COMPLETE",
            "filled": False,
            "attempts": 1,
        }
        mock_db_session.commit.side_effect = SQLAlchemyError("Connection lost")

        success = worker.store_trade(order, result)

        assert success is False
        mock_db_session.rollback.assert_called_once()

    def test_unexpected_error_returns_false(self, worker, mock_db_session):
        """Returns False and rolls back on unexpected exceptions."""
        order = {
            "symbol": "NIFTY",
            "exchange": "NFO",
            "quantity": 50,
            "side": "BUY",
        }
        result = {
            "success": True,
            "order_id": "broker_900",
            "price": 18000.0,
            "status": "COMPLETE",
            "filled": False,
            "attempts": 1,
        }
        mock_db_session.commit.side_effect = RuntimeError("Unexpected")

        success = worker.store_trade(order, result)

        assert success is False
        mock_db_session.rollback.assert_called_once()

    def test_database_error_logs_error(self, worker, mock_db_session, caplog):
        """Logs error on database failure."""
        order = {
            "symbol": "NIFTY",
            "exchange": "NFO",
            "quantity": 50,
            "side": "BUY",
        }
        result = {
            "success": True,
            "order_id": "broker_err",
            "price": 18000.0,
            "status": "COMPLETE",
            "filled": False,
            "attempts": 1,
        }
        mock_db_session.commit.side_effect = SQLAlchemyError("DB error")

        with caplog.at_level(logging.ERROR):
            worker.store_trade(order, result)

        assert "Database error storing trade" in caplog.text

    def test_correct_field_mapping_for_order(self, worker, mock_db_session):
        """Verifies all Order fields are mapped correctly from input dicts."""
        order = {
            "symbol": "BANKNIFTY",
            "exchange": "NFO",
            "quantity": 75,
            "side": "SELL",
        }
        result = {
            "success": False,
            "order_id": "brok_42",
            "price": 43000.5,
            "status": "REJECTED",
            "filled": False,
            "attempts": 4,
            "message": "Margin insufficient",
        }

        worker.store_trade(order, result)

        order_record = mock_db_session.add.call_args_list[0][0][0]
        assert order_record.user_id == 1
        assert order_record.broker_order_id == "brok_42"
        assert order_record.symbol == "BANKNIFTY"
        assert order_record.qty == 75
        assert order_record.price == 43000.5
        assert order_record.status == "REJECTED"
        assert order_record.retries == 3  # 4 - 1
        assert order_record.error_message == "Margin insufficient"

    def test_correct_field_mapping_for_trade(self, worker, mock_db_session):
        """Verifies all Trade fields are mapped correctly from input dicts."""
        order = {
            "symbol": "TATASTEEL",
            "exchange": "NSE",
            "quantity": 200,
            "side": "BUY",
        }
        result = {
            "success": True,
            "order_id": "brok_99",
            "price": 125.50,
            "status": "COMPLETE",
            "filled": True,
            "attempts": 2,
        }

        worker.store_trade(order, result)

        trade_record = mock_db_session.add.call_args_list[1][0][0]
        assert trade_record.user_id == 1
        assert trade_record.symbol == "TATASTEEL"
        assert trade_record.exchange == "NSE"
        assert trade_record.qty == 200
        assert trade_record.side == "BUY"
        assert trade_record.entry_price == 125.50
        assert trade_record.status == "OPEN"
        assert trade_record.timestamp is not None


# ============================================================
# Update Position Cache Tests
# ============================================================


class TestUpdatePositionCache:
    """Tests for ExecutionWorker.update_position_cache().

    After an order is executed and trade is stored, the execution worker
    triggers a risk engine update and invalidates stale cache entries.

    Requirements covered:
    - 1.4: Risk engine metrics update after trade execution
    """

    @pytest.fixture
    def sample_order(self):
        """Sample order dictionary for testing."""
        return {
            "symbol": "NIFTY",
            "exchange": "NSE",
            "side": "BUY",
            "quantity": 50,
        }

    @pytest.fixture
    def sample_result(self):
        """Sample execution result dictionary for testing."""
        return {
            "success": True,
            "order_id": "broker_123",
            "price": 19500.0,
            "filled": True,
            "attempts": 1,
        }

    # --- Task 7.7.1: Trigger risk engine update ---

    @patch("src.workers.execution_worker.celery_app")
    def test_triggers_risk_engine_task(
        self, mock_celery, worker, mock_redis, sample_order, sample_result
    ):
        """Sends 'run_risk_engine' Celery task with user_id."""
        worker.update_position_cache(sample_order, sample_result)

        mock_celery.send_task.assert_called_once_with(
            'run_risk_engine', args=[1]
        )

    @patch("src.workers.execution_worker.celery_app")
    def test_risk_engine_task_uses_correct_user_id(
        self, mock_celery, mock_kite, mock_redis, mock_db_session, sample_order, sample_result
    ):
        """Risk engine task is called with the correct user_id."""
        worker = ExecutionWorker(
            user_id=42,
            kite_client=mock_kite,
            redis_client=mock_redis,
            db_session=mock_db_session,
        )

        worker.update_position_cache(sample_order, sample_result)

        mock_celery.send_task.assert_called_once_with(
            'run_risk_engine', args=[42]
        )

    @patch("src.workers.execution_worker.celery_app")
    def test_celery_error_does_not_raise(
        self, mock_celery, worker, mock_redis, sample_order, sample_result
    ):
        """Error in Celery task dispatch doesn't raise an exception."""
        mock_celery.send_task.side_effect = Exception("Broker connection failed")

        # Should not raise
        worker.update_position_cache(sample_order, sample_result)

    @patch("src.workers.execution_worker.celery_app")
    def test_celery_error_logs_error(
        self, mock_celery, worker, mock_redis, sample_order, sample_result, caplog
    ):
        """Logs error when Celery task dispatch fails."""
        mock_celery.send_task.side_effect = Exception("Broker connection failed")

        with caplog.at_level(logging.ERROR):
            worker.update_position_cache(sample_order, sample_result)

        assert "Failed to trigger risk engine update" in caplog.text

    # --- Task 7.7.2: Invalidate stale cache ---

    @patch("src.workers.execution_worker.celery_app")
    def test_invalidates_risk_cache_key(
        self, mock_celery, worker, mock_redis, sample_order, sample_result
    ):
        """Deletes the user's risk cache key in Redis."""
        worker.update_position_cache(sample_order, sample_result)

        expected_key = "user:1:risk"
        mock_redis.delete.assert_called_once_with(expected_key)

    @patch("src.workers.execution_worker.celery_app")
    def test_invalidates_correct_user_risk_key(
        self, mock_celery, mock_kite, mock_redis, mock_db_session, sample_order, sample_result
    ):
        """Invalidates the correct user-specific risk key."""
        worker = ExecutionWorker(
            user_id=99,
            kite_client=mock_kite,
            redis_client=mock_redis,
            db_session=mock_db_session,
        )

        worker.update_position_cache(sample_order, sample_result)

        expected_key = "user:99:risk"
        mock_redis.delete.assert_called_once_with(expected_key)

    @patch("src.workers.execution_worker.celery_app")
    def test_redis_error_does_not_raise(
        self, mock_celery, worker, mock_redis, sample_order, sample_result
    ):
        """Error in Redis cache invalidation doesn't raise an exception."""
        mock_redis.delete.side_effect = redis.ConnectionError("Connection refused")

        # Should not raise
        worker.update_position_cache(sample_order, sample_result)

    @patch("src.workers.execution_worker.celery_app")
    def test_redis_error_logs_error(
        self, mock_celery, worker, mock_redis, sample_order, sample_result, caplog
    ):
        """Logs error when Redis cache invalidation fails."""
        mock_redis.delete.side_effect = redis.ConnectionError("Connection refused")

        with caplog.at_level(logging.ERROR):
            worker.update_position_cache(sample_order, sample_result)

        assert "Failed to invalidate risk cache" in caplog.text

    @patch("src.workers.execution_worker.celery_app")
    def test_celery_failure_still_attempts_cache_invalidation(
        self, mock_celery, worker, mock_redis, sample_order, sample_result
    ):
        """Cache invalidation still runs even if Celery task dispatch fails."""
        mock_celery.send_task.side_effect = Exception("Celery down")

        worker.update_position_cache(sample_order, sample_result)

        # Redis delete should still be called despite Celery failure
        expected_key = "user:1:risk"
        mock_redis.delete.assert_called_once_with(expected_key)

    @patch("src.workers.execution_worker.celery_app")
    def test_logs_info_on_successful_task_dispatch(
        self, mock_celery, worker, mock_redis, sample_order, sample_result, caplog
    ):
        """Logs info message on successful risk engine task dispatch."""
        with caplog.at_level(logging.INFO):
            worker.update_position_cache(sample_order, sample_result)

        assert "Triggered risk engine update" in caplog.text

    @patch("src.workers.execution_worker.celery_app")
    def test_logs_info_on_successful_cache_invalidation(
        self, mock_celery, worker, mock_redis, sample_order, sample_result, caplog
    ):
        """Logs info message on successful cache invalidation."""
        with caplog.at_level(logging.INFO):
            worker.update_position_cache(sample_order, sample_result)

        assert "Invalidated stale risk cache" in caplog.text
