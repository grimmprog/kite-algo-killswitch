"""Tests for the Risk Engine Task - Celery task for per-user risk monitoring.

Tests cover:
- schedule_risk_monitoring(): Dispatches risk engine tasks for active users
- run_risk_engine(): Full risk cycle for a single user
- get_active_users(): Queries active users from database
- get_user_kite_client(): Gets configured Kite client for a user

Requirements covered:
- 1.4.1: Monitor each user's P&L every 2-3 seconds
- 1.8.5: Maintain separate execution queue for each user
- 2.3.8: Continue processing other users when one user's operation fails
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import logging
from unittest.mock import MagicMock, patch, call

import pytest

from src.workers.risk_engine_task import (
    schedule_risk_monitoring,
    run_risk_engine,
    get_active_users,
    get_user_kite_client,
    _execute_risk_engine,
    _execute_schedule_risk_monitoring,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    return MagicMock()


@pytest.fixture
def mock_redis_client():
    """Create a mock RedisClient."""
    client = MagicMock()
    client.get.return_value = None  # No killswitch by default
    return client


@pytest.fixture
def mock_user():
    """Create a mock User object with broker token."""
    user = MagicMock()
    user.id = 1
    user.capital = 100000.0
    user.daily_loss_limit_percent = 2.0
    user.is_active = True
    user.broker_access_token = "valid_token_123"
    return user


@pytest.fixture
def mock_user_no_token():
    """Create a mock User object without broker token."""
    user = MagicMock()
    user.id = 2
    user.capital = 50000.0
    user.daily_loss_limit_percent = 3.0
    user.is_active = True
    user.broker_access_token = None
    return user


# ============================================================
# Tests for get_active_users
# ============================================================


class TestGetActiveUsers:
    """Tests for querying active users from the database."""

    def test_returns_active_users_with_tokens(self, mock_db_session):
        """Returns users that are active and have broker tokens."""
        user1 = MagicMock()
        user1.id = 1
        user1.capital = 100000.0
        user1.daily_loss_limit_percent = 2.0
        user1.is_active = True
        user1.broker_access_token = "token_1"

        user2 = MagicMock()
        user2.id = 2
        user2.capital = 200000.0
        user2.daily_loss_limit_percent = 3.0
        user2.is_active = True
        user2.broker_access_token = "token_2"

        mock_query = MagicMock()
        mock_db_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [user1, user2]

        result = get_active_users(mock_db_session)

        assert len(result) == 2
        assert result[0] == {
            "user_id": 1,
            "capital": 100000.0,
            "daily_loss_limit_percent": 2.0,
        }
        assert result[1] == {
            "user_id": 2,
            "capital": 200000.0,
            "daily_loss_limit_percent": 3.0,
        }

    def test_returns_empty_list_when_no_active_users(self, mock_db_session):
        """Returns empty list when no active users exist."""
        mock_query = MagicMock()
        mock_db_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []

        result = get_active_users(mock_db_session)

        assert result == []

    def test_handles_database_error_gracefully(self, mock_db_session):
        """Returns empty list on database error without crashing."""
        mock_db_session.query.side_effect = Exception("DB connection lost")

        result = get_active_users(mock_db_session)

        assert result == []


# ============================================================
# Tests for get_user_kite_client
# ============================================================


class TestGetUserKiteClient:
    """Tests for getting a configured Kite client for a user."""

    @patch("src.workers.risk_engine_task.os.environ.get")
    def test_raises_when_no_api_key(self, mock_env_get, mock_db_session):
        """Raises RuntimeError when KITE_API_KEY is not set."""
        mock_env_get.return_value = None

        with pytest.raises(RuntimeError, match="KITE_API_KEY"):
            get_user_kite_client(1, mock_db_session)

    @patch("src.workers.risk_engine_task.os.environ.get")
    def test_raises_when_user_has_no_token(self, mock_env_get, mock_db_session):
        """Raises RuntimeError when user has no broker access token."""
        mock_env_get.return_value = "test_api_key"

        mock_query = MagicMock()
        mock_db_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        with pytest.raises(RuntimeError, match="no valid broker access token"):
            get_user_kite_client(1, mock_db_session)

    @patch("src.workers.risk_engine_task.os.environ.get")
    @patch("kiteconnect.KiteConnect")
    def test_returns_configured_kite_client(
        self, mock_kite_class, mock_env_get, mock_db_session, mock_user
    ):
        """Returns a KiteConnect instance configured with user's token."""
        mock_env_get.return_value = "test_api_key"

        mock_query = MagicMock()
        mock_db_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_user

        mock_kite_instance = MagicMock()
        mock_kite_class.return_value = mock_kite_instance

        result = get_user_kite_client(1, mock_db_session)

        mock_kite_class.assert_called_once_with(api_key="test_api_key")
        mock_kite_instance.set_access_token.assert_called_once_with("valid_token_123")
        assert result is mock_kite_instance


# ============================================================
# Tests for schedule_risk_monitoring
# ============================================================


class TestScheduleRiskMonitoring:
    """Tests for the Celery beat task that dispatches per-user risk tasks."""

    @patch("src.workers.risk_engine_task.run_risk_engine")
    @patch("src.workers.risk_engine_task.get_active_users")
    @patch("src.workers.risk_engine_task.get_db_session")
    def test_dispatches_task_for_each_active_user(
        self, mock_get_session, mock_get_active, mock_run_risk
    ):
        """Dispatches run_risk_engine.delay for each active user."""
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        mock_get_active.return_value = [
            {"user_id": 1, "capital": 100000.0, "daily_loss_limit_percent": 2.0},
            {"user_id": 2, "capital": 200000.0, "daily_loss_limit_percent": 3.0},
        ]

        result = _execute_schedule_risk_monitoring()

        assert result["status"] == "success"
        assert result["users_dispatched"] == 2
        mock_run_risk.delay.assert_any_call(1)
        mock_run_risk.delay.assert_any_call(2)
        mock_session.close.assert_called_once()

    @patch("src.workers.risk_engine_task.get_active_users")
    @patch("src.workers.risk_engine_task.get_db_session")
    def test_returns_zero_when_no_active_users(
        self, mock_get_session, mock_get_active
    ):
        """Returns success with 0 dispatched when no active users exist."""
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        mock_get_active.return_value = []

        result = _execute_schedule_risk_monitoring()

        assert result["status"] == "success"
        assert result["users_dispatched"] == 0
        assert "No active users" in result["reason"]
        mock_session.close.assert_called_once()

    @patch("src.workers.risk_engine_task.run_risk_engine")
    @patch("src.workers.risk_engine_task.get_active_users")
    @patch("src.workers.risk_engine_task.get_db_session")
    def test_continues_dispatching_if_one_user_fails(
        self, mock_get_session, mock_get_active, mock_run_risk
    ):
        """Continues dispatching tasks even if one dispatch fails (Req 2.3.8)."""
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        mock_get_active.return_value = [
            {"user_id": 1, "capital": 100000.0, "daily_loss_limit_percent": 2.0},
            {"user_id": 2, "capital": 200000.0, "daily_loss_limit_percent": 3.0},
            {"user_id": 3, "capital": 150000.0, "daily_loss_limit_percent": 2.5},
        ]

        # User 2 dispatch fails
        mock_run_risk.delay.side_effect = [None, Exception("Broker error"), None]

        result = _execute_schedule_risk_monitoring()

        assert result["status"] == "success"
        assert result["users_dispatched"] == 2  # 1 and 3 succeeded
        mock_session.close.assert_called_once()

    @patch("src.workers.risk_engine_task._execute_schedule_risk_monitoring")
    def test_top_level_catches_unexpected_errors(self, mock_execute):
        """Top-level schedule_risk_monitoring catches unexpected errors."""
        mock_execute.side_effect = RuntimeError("Unexpected crash")

        result = schedule_risk_monitoring()

        assert result["status"] == "error"
        assert result["users_dispatched"] == 0
        assert "Unexpected error" in result["reason"]


# ============================================================
# Tests for run_risk_engine
# ============================================================


class TestRunRiskEngine:
    """Tests for the per-user risk engine Celery task."""

    @patch("src.workers.risk_engine_task.get_db_session")
    @patch("src.workers.risk_engine_task.get_redis_client")
    def test_skips_when_killswitch_active(self, mock_get_redis, mock_get_session):
        """Skips risk engine when kill switch is already active for user."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = "true"
        mock_get_redis.return_value = mock_redis

        result = _execute_risk_engine(user_id=1)

        assert result["status"] == "skipped"
        assert result["user_id"] == 1
        assert "Kill switch already active" in result["reason"]

    @patch("src.workers.risk_engine_task.get_user_kite_client")
    @patch("src.workers.risk_engine_task.get_db_session")
    @patch("src.workers.risk_engine_task.get_redis_client")
    def test_error_when_kite_client_unavailable(
        self, mock_get_redis, mock_get_session, mock_get_kite
    ):
        """Returns error status when Kite client cannot be obtained."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        mock_get_kite.side_effect = RuntimeError("No broker token")

        result = _execute_risk_engine(user_id=1)

        assert result["status"] == "error"
        assert result["user_id"] == 1
        assert "Kite client error" in result["reason"]
        mock_session.close.assert_called_once()

    @patch("src.workers.risk_engine_worker.RiskEngineWorker", autospec=True)
    @patch("src.workers.risk_engine_task.get_user_kite_client")
    @patch("src.workers.risk_engine_task.get_db_session")
    @patch("src.workers.risk_engine_task.get_redis_client")
    def test_successful_risk_check_no_breach(
        self, mock_get_redis, mock_get_session, mock_get_kite, mock_worker_cls
    ):
        """Completes risk check successfully with no threshold breach."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        mock_session = MagicMock()
        mock_get_session.return_value = mock_session

        mock_kite = MagicMock()
        mock_get_kite.return_value = mock_kite

        # Mock user lookup
        mock_user = MagicMock()
        mock_user.capital = 100000.0
        mock_user.daily_loss_limit_percent = 2.0
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_user

        # Mock worker
        mock_worker_instance = MagicMock()
        mock_worker_cls.return_value = mock_worker_instance
        mock_worker_instance.fetch_positions_safe.return_value = [
            {"tradingsymbol": "NIFTY", "quantity": 50, "pnl": -500}
        ]
        mock_worker_instance.compute_live_pnl.return_value = -500.0
        mock_worker_instance.compute_greeks.return_value = {
            "net_delta": 0.5, "net_gamma": 0.01, "net_vega": 0.1
        }
        mock_worker_instance.compute_margin_used.return_value = 25000.0
        mock_worker_instance.check_thresholds.return_value = (False, "Within limits")

        result = _execute_risk_engine(user_id=1)

        assert result["status"] == "success"
        assert result["user_id"] == 1
        assert "Risk check completed" in result["reason"]
        mock_worker_instance.update_redis_cache.assert_called_once()
        mock_worker_instance.trigger_killswitch.assert_not_called()
        mock_session.close.assert_called_once()

    @patch("src.workers.risk_engine_worker.RiskEngineWorker", autospec=True)
    @patch("src.workers.risk_engine_task.get_user_kite_client")
    @patch("src.workers.risk_engine_task.get_db_session")
    @patch("src.workers.risk_engine_task.get_redis_client")
    def test_triggers_killswitch_on_breach(
        self, mock_get_redis, mock_get_session, mock_get_kite, mock_worker_cls
    ):
        """Triggers kill switch when threshold is breached."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        mock_session = MagicMock()
        mock_get_session.return_value = mock_session

        mock_kite = MagicMock()
        mock_get_kite.return_value = mock_kite

        # Mock user lookup
        mock_user = MagicMock()
        mock_user.capital = 100000.0
        mock_user.daily_loss_limit_percent = 2.0
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_user

        # Mock worker with threshold breach
        mock_worker_instance = MagicMock()
        mock_worker_cls.return_value = mock_worker_instance
        mock_worker_instance.fetch_positions_safe.return_value = [
            {"tradingsymbol": "NIFTY", "quantity": 50, "pnl": -5000}
        ]
        mock_worker_instance.compute_live_pnl.return_value = -5000.0
        mock_worker_instance.compute_greeks.return_value = {
            "net_delta": 0.5, "net_gamma": 0.01, "net_vega": 0.1
        }
        mock_worker_instance.compute_margin_used.return_value = 25000.0
        mock_worker_instance.check_thresholds.return_value = (
            True, "Daily loss limit breached: -5.00%"
        )

        result = _execute_risk_engine(user_id=1)

        assert result["status"] == "success"
        assert "Kill switch triggered" in result["reason"]
        mock_worker_instance.trigger_killswitch.assert_called_once_with(
            "Daily loss limit breached: -5.00%", 100000.0
        )
        mock_session.close.assert_called_once()

    @patch("src.workers.risk_engine_task._execute_risk_engine")
    def test_top_level_catches_unexpected_errors(self, mock_execute):
        """Top-level run_risk_engine catches unexpected errors."""
        mock_execute.side_effect = RuntimeError("Segfault")

        result = run_risk_engine(user_id=42)

        assert result["status"] == "error"
        assert result["user_id"] == 42
        assert "Unexpected error" in result["reason"]

    @patch("src.workers.risk_engine_task.get_db_session")
    @patch("src.workers.risk_engine_task.get_redis_client")
    def test_session_closed_even_on_error(self, mock_get_redis, mock_get_session):
        """Database session is closed even when an error occurs."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        mock_session = MagicMock()
        mock_get_session.return_value = mock_session

        # Make get_user_kite_client raise
        with patch(
            "src.workers.risk_engine_task.get_user_kite_client",
            side_effect=RuntimeError("Token expired"),
        ):
            _execute_risk_engine(user_id=1)

        mock_session.close.assert_called_once()


# ============================================================
# Tests for Celery Beat Schedule Integration
# ============================================================


class TestCeleryBeatSchedule:
    """Tests verifying the Celery beat schedule is configured correctly."""

    def test_beat_schedule_includes_risk_monitoring(self):
        """The Celery beat schedule has the risk monitoring entry."""
        from src.workers.celery_app import celery_app

        schedule = celery_app.conf.beat_schedule
        assert "schedule-risk-monitoring-every-3s" in schedule

    def test_beat_schedule_interval_is_3_seconds(self):
        """Risk monitoring is scheduled every 3 seconds (Req 1.4.1)."""
        from src.workers.celery_app import celery_app

        entry = celery_app.conf.beat_schedule["schedule-risk-monitoring-every-3s"]
        assert entry["schedule"] == 3.0

    def test_beat_schedule_targets_correct_task(self):
        """Beat schedule targets the schedule_risk_monitoring task."""
        from src.workers.celery_app import celery_app

        entry = celery_app.conf.beat_schedule["schedule-risk-monitoring-every-3s"]
        assert entry["task"] == "src.workers.risk_engine_task.schedule_risk_monitoring"
