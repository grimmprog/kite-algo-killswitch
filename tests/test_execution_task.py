"""Tests for the Execution Task - Celery task for order execution.

Tests cover:
- Successful full flow (validate → execute → confirm → store → return)
- Validation failure returns immediately
- Execution failure returns failure result
- Missing user_id returns failure
- Broker connection error returns failure

Requirements covered:
- 1.3.3: Validate trades before execution
- 1.3.5: Retry failed orders up to 3 times with exponential backoff
- 1.3.6: Wait up to 30 seconds for order fill confirmation
- 2.3.6: Handle broker API failures with retries
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch

import pytest

from src.workers.execution_task import execute_order, _execute_order_flow


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def valid_order_data():
    """Create valid order data for testing."""
    return {
        "user_id": 1,
        "symbol": "RELIANCE",
        "exchange": "NSE",
        "side": "BUY",
        "quantity": 10,
        "order_type": "MARKET",
    }


@pytest.fixture
def mock_worker():
    """Create a mock ExecutionWorker."""
    worker = MagicMock()
    worker.validate_order.return_value = (True, "Valid")
    worker.execute_with_retry.return_value = {
        "success": True,
        "order_id": "ORD123",
        "message": "Order placed successfully",
        "error_type": None,
        "retryable": False,
        "attempts": 1,
    }
    worker.confirm_fill.return_value = {
        "filled": True,
        "quantity": 10,
        "price": 2500.0,
    }
    worker.store_trade.return_value = True
    worker.mark_recent_order.return_value = None
    worker.update_position_cache.return_value = None
    return worker


# ============================================================
# Tests for successful full flow
# ============================================================


class TestExecuteOrderSuccess:
    """Tests for successful order execution flow."""

    @patch("src.workers.execution_task.get_redis_client")
    @patch("src.workers.execution_task.get_db_session")
    @patch("src.workers.execution_task.get_user_kite_client")
    @patch("src.workers.execution_worker.ExecutionWorker", autospec=False)
    def test_full_success_flow(
        self,
        mock_worker_cls,
        mock_get_kite,
        mock_get_db,
        mock_get_redis,
        valid_order_data,
        mock_worker,
    ):
        """Test successful execution: validate → execute → confirm → store → return."""
        mock_get_redis.return_value = MagicMock()
        mock_db_session = MagicMock()
        mock_get_db.return_value = mock_db_session
        mock_get_kite.return_value = MagicMock()
        mock_worker_cls.return_value = mock_worker

        result = _execute_order_flow(valid_order_data)

        assert result["success"] is True
        assert result["order_id"] == "ORD123"
        assert result["filled"] is True
        assert result["fill_price"] == 2500.0
        assert result["fill_quantity"] == 10
        assert result["message"] == "Order executed successfully"

    @patch("src.workers.execution_task.get_redis_client")
    @patch("src.workers.execution_task.get_db_session")
    @patch("src.workers.execution_task.get_user_kite_client")
    @patch("src.workers.execution_worker.ExecutionWorker", autospec=False)
    def test_full_flow_calls_all_worker_methods(
        self,
        mock_worker_cls,
        mock_get_kite,
        mock_get_db,
        mock_get_redis,
        valid_order_data,
        mock_worker,
    ):
        """Test that the full flow calls all worker methods in order."""
        mock_get_redis.return_value = MagicMock()
        mock_db_session = MagicMock()
        mock_get_db.return_value = mock_db_session
        mock_get_kite.return_value = MagicMock()
        mock_worker_cls.return_value = mock_worker

        _execute_order_flow(valid_order_data)

        # Verify all methods were called
        mock_worker.validate_order.assert_called_once_with(valid_order_data)
        mock_worker.execute_with_retry.assert_called_once_with(valid_order_data)
        mock_worker.confirm_fill.assert_called_once_with("ORD123")
        mock_worker.store_trade.assert_called_once()
        mock_worker.mark_recent_order.assert_called_once_with(valid_order_data)
        mock_worker.update_position_cache.assert_called_once()


# ============================================================
# Tests for validation failure
# ============================================================


class TestExecuteOrderValidationFailure:
    """Tests for order validation failures."""

    @patch("src.workers.execution_task.get_redis_client")
    @patch("src.workers.execution_task.get_db_session")
    @patch("src.workers.execution_task.get_user_kite_client")
    @patch("src.workers.execution_worker.ExecutionWorker", autospec=False)
    def test_validation_failure_returns_immediately(
        self,
        mock_worker_cls,
        mock_get_kite,
        mock_get_db,
        mock_get_redis,
        valid_order_data,
    ):
        """Test that validation failure returns immediately without executing."""
        mock_get_redis.return_value = MagicMock()
        mock_db_session = MagicMock()
        mock_get_db.return_value = mock_db_session
        mock_get_kite.return_value = MagicMock()

        mock_worker = MagicMock()
        mock_worker.validate_order.return_value = (False, "Kill switch is active")
        mock_worker_cls.return_value = mock_worker

        result = _execute_order_flow(valid_order_data)

        assert result["success"] is False
        assert result["message"] == "Kill switch is active"
        assert result["filled"] is False
        assert result["order_id"] is None
        # execute_with_retry should NOT have been called
        mock_worker.execute_with_retry.assert_not_called()

    @patch("src.workers.execution_task.get_redis_client")
    @patch("src.workers.execution_task.get_db_session")
    @patch("src.workers.execution_task.get_user_kite_client")
    @patch("src.workers.execution_worker.ExecutionWorker", autospec=False)
    def test_duplicate_order_returns_failure(
        self,
        mock_worker_cls,
        mock_get_kite,
        mock_get_db,
        mock_get_redis,
        valid_order_data,
    ):
        """Test that duplicate order detection returns failure."""
        mock_get_redis.return_value = MagicMock()
        mock_db_session = MagicMock()
        mock_get_db.return_value = mock_db_session
        mock_get_kite.return_value = MagicMock()

        mock_worker = MagicMock()
        mock_worker.validate_order.return_value = (False, "Duplicate order detected")
        mock_worker_cls.return_value = mock_worker

        result = _execute_order_flow(valid_order_data)

        assert result["success"] is False
        assert result["message"] == "Duplicate order detected"
        assert result["filled"] is False


# ============================================================
# Tests for execution failure
# ============================================================


class TestExecuteOrderExecutionFailure:
    """Tests for order execution failures."""

    @patch("src.workers.execution_task.get_redis_client")
    @patch("src.workers.execution_task.get_db_session")
    @patch("src.workers.execution_task.get_user_kite_client")
    @patch("src.workers.execution_worker.ExecutionWorker", autospec=False)
    def test_execution_failure_returns_failure_result(
        self,
        mock_worker_cls,
        mock_get_kite,
        mock_get_db,
        mock_get_redis,
        valid_order_data,
    ):
        """Test that execution failure (after retries) returns failure result."""
        mock_get_redis.return_value = MagicMock()
        mock_db_session = MagicMock()
        mock_get_db.return_value = mock_db_session
        mock_get_kite.return_value = MagicMock()

        mock_worker = MagicMock()
        mock_worker.validate_order.return_value = (True, "Valid")
        mock_worker.execute_with_retry.return_value = {
            "success": False,
            "order_id": None,
            "message": "Max retries (3) exhausted. Last error: NetworkException",
            "error_type": "NetworkException",
            "retryable": True,
            "attempts": 4,
        }
        mock_worker.store_trade.return_value = True
        mock_worker_cls.return_value = mock_worker

        result = _execute_order_flow(valid_order_data)

        assert result["success"] is False
        assert result["filled"] is False
        assert "Max retries" in result["message"]
        # Store trade should still be called to record the failed attempt
        mock_worker.store_trade.assert_called_once()
        # confirm_fill should NOT have been called
        mock_worker.confirm_fill.assert_not_called()

    @patch("src.workers.execution_task.get_redis_client")
    @patch("src.workers.execution_task.get_db_session")
    @patch("src.workers.execution_task.get_user_kite_client")
    @patch("src.workers.execution_worker.ExecutionWorker", autospec=False)
    def test_non_retryable_failure_returns_immediately(
        self,
        mock_worker_cls,
        mock_get_kite,
        mock_get_db,
        mock_get_redis,
        valid_order_data,
    ):
        """Test that non-retryable failure (e.g., TokenException) returns failure."""
        mock_get_redis.return_value = MagicMock()
        mock_db_session = MagicMock()
        mock_get_db.return_value = mock_db_session
        mock_get_kite.return_value = MagicMock()

        mock_worker = MagicMock()
        mock_worker.validate_order.return_value = (True, "Valid")
        mock_worker.execute_with_retry.return_value = {
            "success": False,
            "order_id": None,
            "message": "Token error: Session expired",
            "error_type": "TokenException",
            "retryable": False,
            "attempts": 1,
        }
        mock_worker.store_trade.return_value = True
        mock_worker_cls.return_value = mock_worker

        result = _execute_order_flow(valid_order_data)

        assert result["success"] is False
        assert result["filled"] is False
        assert "Token error" in result["message"]


# ============================================================
# Tests for edge cases
# ============================================================


class TestExecuteOrderEdgeCases:
    """Tests for edge cases and error handling."""

    def test_missing_user_id_returns_failure(self):
        """Test that missing user_id returns failure without crashing."""
        order_data = {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "side": "BUY",
            "quantity": 10,
        }
        result = _execute_order_flow(order_data)

        assert result["success"] is False
        assert "Missing user_id" in result["message"]

    @patch("src.workers.execution_task.get_redis_client")
    @patch("src.workers.execution_task.get_db_session")
    @patch("src.workers.execution_task.get_user_kite_client")
    def test_broker_connection_error_returns_failure(
        self,
        mock_get_kite,
        mock_get_db,
        mock_get_redis,
        valid_order_data,
    ):
        """Test that broker connection error returns failure."""
        mock_get_redis.return_value = MagicMock()
        mock_db_session = MagicMock()
        mock_get_db.return_value = mock_db_session
        mock_get_kite.side_effect = RuntimeError("User 1 has no valid broker access token")

        result = _execute_order_flow(valid_order_data)

        assert result["success"] is False
        assert "Broker connection error" in result["message"]
        assert result["filled"] is False
        mock_db_session.close.assert_called_once()

    def test_top_level_exception_caught_by_task(self):
        """Test that the Celery task wrapper catches unexpected errors."""
        with patch(
            "src.workers.execution_task._execute_order_flow",
            side_effect=Exception("Something went wrong"),
        ):
            result = execute_order({"user_id": 1})

        assert result["success"] is False
        assert "Unexpected error" in result["message"]
        assert result["filled"] is False
