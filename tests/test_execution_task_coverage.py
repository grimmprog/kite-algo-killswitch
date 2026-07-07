"""Additional tests for execution_task.py to cover remaining untested paths.

Tests cover:
- _get_session_factory: lazy singleton pattern
- get_db_session: session creation
- get_user_kite_client: client creation with broker token
- _execute_order_flow: additional error paths
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch

import pytest

from src.workers import execution_task


# ============================================================
# Tests for _get_session_factory
# ============================================================


class TestSessionFactory:
    """Tests for the lazy session factory in execution_task."""

    @patch("src.workers.execution_task.create_engine")
    @patch("src.workers.execution_task.sessionmaker")
    def test_creates_engine_on_first_call(self, mock_sessionmaker, mock_create_engine):
        """Creates engine and sessionmaker on first call."""
        # Reset module-level state
        execution_task._engine = None
        execution_task._SessionFactory = None

        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine
        mock_factory = MagicMock()
        mock_sessionmaker.return_value = mock_factory

        result = execution_task._get_session_factory()

        mock_create_engine.assert_called_once()
        mock_sessionmaker.assert_called_once_with(bind=mock_engine)
        assert result == mock_factory

        # Clean up
        execution_task._engine = None
        execution_task._SessionFactory = None

    @patch("src.workers.execution_task.create_engine")
    @patch("src.workers.execution_task.sessionmaker")
    def test_reuses_factory_on_subsequent_calls(self, mock_sessionmaker, mock_create_engine):
        """Returns cached factory on second call."""
        execution_task._engine = None
        execution_task._SessionFactory = None

        mock_create_engine.return_value = MagicMock()
        mock_factory = MagicMock()
        mock_sessionmaker.return_value = mock_factory

        result1 = execution_task._get_session_factory()
        result2 = execution_task._get_session_factory()

        assert mock_create_engine.call_count == 1
        assert result1 == result2

        execution_task._engine = None
        execution_task._SessionFactory = None


# ============================================================
# Tests for get_db_session
# ============================================================


class TestGetDbSession:
    """Tests for database session creation."""

    @patch("src.workers.execution_task._get_session_factory")
    def test_returns_new_session(self, mock_factory):
        """get_db_session returns a new session from the factory."""
        mock_session = MagicMock()
        mock_factory.return_value = MagicMock(return_value=mock_session)

        session = execution_task.get_db_session()

        assert session == mock_session


# ============================================================
# Tests for get_user_kite_client
# ============================================================


class TestGetUserKiteClient:
    """Tests for Kite client creation."""

    @patch.dict(os.environ, {"KITE_API_KEY": "test_api_key"})
    def test_creates_kite_client_with_token(self):
        """Creates KiteConnect client with user's access token."""
        mock_db = MagicMock()
        mock_user = MagicMock()
        mock_user.broker_access_token = "user_token_123"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        mock_kite = MagicMock()
        mock_kite_cls = MagicMock(return_value=mock_kite)
        mock_kite_module = MagicMock()
        mock_kite_module.KiteConnect = mock_kite_cls

        with patch.dict("sys.modules", {"kiteconnect": mock_kite_module}):
            result = execution_task.get_user_kite_client(1, mock_db)

        mock_kite_cls.assert_called_once_with(api_key="test_api_key")
        mock_kite.set_access_token.assert_called_once_with("user_token_123")

    @patch.dict(os.environ, {}, clear=True)
    def test_raises_on_missing_api_key(self):
        """Raises RuntimeError when KITE_API_KEY is not set."""
        # Remove the env var if it exists
        os.environ.pop("KITE_API_KEY", None)
        mock_db = MagicMock()

        # Patch the kiteconnect import to avoid OpenSSL issues
        mock_kite_module = MagicMock()
        with patch.dict("sys.modules", {"kiteconnect": mock_kite_module}):
            with pytest.raises(RuntimeError, match="KITE_API_KEY"):
                execution_task.get_user_kite_client(1, mock_db)

    @patch.dict(os.environ, {"KITE_API_KEY": "test_api_key"})
    def test_raises_on_missing_user(self):
        """Raises RuntimeError when user has no broker token."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        mock_kite_module = MagicMock()
        with patch.dict("sys.modules", {"kiteconnect": mock_kite_module}):
            with pytest.raises(RuntimeError, match="no valid broker"):
                execution_task.get_user_kite_client(1, mock_db)

    @patch.dict(os.environ, {"KITE_API_KEY": "test_api_key"})
    def test_raises_on_empty_broker_token(self):
        """Raises RuntimeError when user's broker_access_token is None."""
        mock_db = MagicMock()
        mock_user = MagicMock()
        mock_user.broker_access_token = None
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        mock_kite_module = MagicMock()
        with patch.dict("sys.modules", {"kiteconnect": mock_kite_module}):
            with pytest.raises(RuntimeError, match="no valid broker"):
                execution_task.get_user_kite_client(1, mock_db)


# ============================================================
# Tests for additional _execute_order_flow paths
# ============================================================


class TestExecuteOrderFlowAdditional:
    """Additional tests for uncovered flow paths."""

    @patch("src.workers.execution_task.get_redis_client")
    @patch("src.workers.execution_task.get_db_session")
    @patch("src.workers.execution_task.get_user_kite_client")
    @patch("src.workers.execution_worker.ExecutionWorker", autospec=False)
    def test_fill_not_confirmed_returns_pending(
        self, mock_worker_cls, mock_get_kite, mock_get_db, mock_get_redis
    ):
        """When fill is not confirmed, returns filled=False."""
        mock_get_redis.return_value = MagicMock()
        mock_db_session = MagicMock()
        mock_get_db.return_value = mock_db_session
        mock_get_kite.return_value = MagicMock()

        mock_worker = MagicMock()
        mock_worker.validate_order.return_value = (True, "Valid")
        mock_worker.execute_with_retry.return_value = {
            "success": True,
            "order_id": "ORD456",
            "message": "Placed",
        }
        mock_worker.confirm_fill.return_value = {
            "filled": False,
            "quantity": None,
            "price": None,
        }
        mock_worker_cls.return_value = mock_worker

        from src.workers.execution_task import _execute_order_flow

        result = _execute_order_flow({"user_id": 1, "symbol": "NIFTY", "side": "BUY", "quantity": 10})

        assert result["success"] is True
        assert result["filled"] is False
        assert result["fill_price"] is None
        mock_db_session.close.assert_called_once()

    @patch("src.workers.execution_task.get_redis_client")
    @patch("src.workers.execution_task.get_db_session")
    @patch("src.workers.execution_task.get_user_kite_client")
    @patch("src.workers.execution_worker.ExecutionWorker", autospec=False)
    def test_exception_during_flow_returns_error(
        self, mock_worker_cls, mock_get_kite, mock_get_db, mock_get_redis
    ):
        """Unexpected exception in worker flow returns error result."""
        mock_get_redis.return_value = MagicMock()
        mock_db_session = MagicMock()
        mock_get_db.return_value = mock_db_session
        mock_get_kite.return_value = MagicMock()

        mock_worker = MagicMock()
        mock_worker.validate_order.side_effect = RuntimeError("Unexpected crash")
        mock_worker_cls.return_value = mock_worker

        from src.workers.execution_task import _execute_order_flow

        result = _execute_order_flow({"user_id": 1, "symbol": "NIFTY", "side": "BUY", "quantity": 10})

        assert result["success"] is False
        assert "RuntimeError" in result["message"]
        mock_db_session.close.assert_called_once()
