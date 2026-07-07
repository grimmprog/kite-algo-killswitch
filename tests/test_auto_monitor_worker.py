"""Tests for the Auto-Monitor Worker — background P&L tracking and threshold alerts.

Tests cover:
- AutoMonitorWorker: P&L monitoring, threshold distance computation, proximity warnings
- Celery tasks: run_pnl_monitor, schedule_pnl_monitoring
- Redis state management: activate/deactivate monitoring
- Redis PubSub publishing: status and warning channels

Requirements covered:
- 10.2: Start backend P&L monitoring process on toggle
- 10.3: Stop backend P&L monitoring process on toggle
- 10.4: Push warning notification when P&L within 10% of threshold
- 10.5: Display current P&L value and distance to nearest threshold
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
from unittest.mock import MagicMock, patch, call

import pytest

from src.workers.auto_monitor_worker import (
    AutoMonitorWorker,
    _monitor_state_key,
    _threshold_warning_channel,
    _status_channel,
)
from src.workers.auto_monitor_task import (
    run_pnl_monitor,
    schedule_pnl_monitoring,
    get_monitored_user_ids,
    _execute_pnl_monitor,
    _execute_schedule_pnl_monitoring,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def mock_redis_client():
    """Create a mock RedisClient with basic methods."""
    client = MagicMock()
    client.get.return_value = None
    client.set.return_value = True
    client.hget.return_value = None
    client.client = MagicMock()
    client.client.publish.return_value = 1
    client.client.scan.return_value = (0, [])
    return client


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    return MagicMock()


@pytest.fixture
def worker(mock_redis_client):
    """Create an AutoMonitorWorker instance for user_id=1."""
    return AutoMonitorWorker(user_id=1, redis_client=mock_redis_client)


@pytest.fixture
def sample_thresholds():
    """Sample kill switch thresholds."""
    return {
        "daily_loss": 5000.0,  # ₹5000 daily loss limit
        "profit_target": 10000.0,  # ₹10000 profit target
        "drawdown": 3000.0,  # ₹3000 drawdown limit
        "capital": 100000.0,
    }


# ============================================================
# Tests for Redis key helpers
# ============================================================


class TestRedisKeyHelpers:
    """Test Redis key/channel name construction."""

    def test_monitor_state_key(self):
        assert _monitor_state_key(1) == "user:1:monitor:active"
        assert _monitor_state_key(42) == "user:42:monitor:active"

    def test_threshold_warning_channel(self):
        assert _threshold_warning_channel(1) == "monitor:threshold_warning:1"
        assert _threshold_warning_channel(99) == "monitor:threshold_warning:99"

    def test_status_channel(self):
        assert _status_channel(1) == "monitor:status:1"
        assert _status_channel(99) == "monitor:status:99"


# ============================================================
# Tests for AutoMonitorWorker initialization
# ============================================================


class TestWorkerInit:
    """Test AutoMonitorWorker constructor validation."""

    def test_valid_init(self, mock_redis_client):
        worker = AutoMonitorWorker(user_id=1, redis_client=mock_redis_client)
        assert worker.user_id == 1
        assert worker.redis is mock_redis_client

    def test_invalid_user_id_zero(self, mock_redis_client):
        with pytest.raises(ValueError, match="user_id must be a positive integer"):
            AutoMonitorWorker(user_id=0, redis_client=mock_redis_client)

    def test_invalid_user_id_negative(self, mock_redis_client):
        with pytest.raises(ValueError, match="user_id must be a positive integer"):
            AutoMonitorWorker(user_id=-1, redis_client=mock_redis_client)

    def test_none_redis_client(self):
        with pytest.raises(ValueError, match="redis_client cannot be None"):
            AutoMonitorWorker(user_id=1, redis_client=None)


# ============================================================
# Tests for monitoring state management
# ============================================================


class TestMonitoringState:
    """Test activate/deactivate monitoring state in Redis."""

    def test_is_monitoring_active_true(self, worker, mock_redis_client):
        mock_redis_client.get.return_value = "true"
        assert worker.is_monitoring_active() is True
        mock_redis_client.get.assert_called_with("user:1:monitor:active")

    def test_is_monitoring_active_false(self, worker, mock_redis_client):
        mock_redis_client.get.return_value = "false"
        assert worker.is_monitoring_active() is False

    def test_is_monitoring_active_none(self, worker, mock_redis_client):
        mock_redis_client.get.return_value = None
        assert worker.is_monitoring_active() is False

    def test_activate_monitoring(self, mock_redis_client):
        AutoMonitorWorker.activate_monitoring(1, mock_redis_client)
        mock_redis_client.set.assert_called_with("user:1:monitor:active", "true")

    def test_deactivate_monitoring(self, mock_redis_client):
        AutoMonitorWorker.deactivate_monitoring(1, mock_redis_client)
        mock_redis_client.set.assert_called_with("user:1:monitor:active", "false")


# ============================================================
# Tests for P&L fetching from Redis cache
# ============================================================


class TestGetCurrentPnl:
    """Test P&L retrieval from Redis risk cache."""

    def test_returns_pnl_value(self, worker, mock_redis_client):
        mock_redis_client.hget.return_value = "-2500.50"
        result = worker.get_current_pnl()
        assert result == -2500.50
        mock_redis_client.hget.assert_called_with("user:1:risk", "pnl")

    def test_returns_positive_pnl(self, worker, mock_redis_client):
        mock_redis_client.hget.return_value = "7500.0"
        result = worker.get_current_pnl()
        assert result == 7500.0

    def test_returns_none_when_no_cache(self, worker, mock_redis_client):
        mock_redis_client.hget.return_value = None
        result = worker.get_current_pnl()
        assert result is None

    def test_returns_none_for_invalid_value(self, worker, mock_redis_client):
        mock_redis_client.hget.return_value = "not_a_number"
        result = worker.get_current_pnl()
        assert result is None


# ============================================================
# Tests for threshold distance computation
# ============================================================


class TestComputeDistanceToThresholds:
    """Test distance calculation from P&L to thresholds."""

    def test_no_loss_full_distance(self, worker, sample_thresholds):
        """When P&L is 0, distance to all thresholds is 100%."""
        distances = worker.compute_distance_to_thresholds(0.0, sample_thresholds)

        assert distances["daily_loss"]["distance_pct"] == 100.0
        assert distances["profit_target"]["distance_pct"] == 100.0
        assert distances["drawdown"]["distance_pct"] == 100.0

    def test_loss_reduces_distance(self, worker, sample_thresholds):
        """When P&L is negative, distance to loss thresholds decreases."""
        # Loss of 2500 out of 5000 threshold = 50% distance remaining
        distances = worker.compute_distance_to_thresholds(-2500.0, sample_thresholds)

        assert distances["daily_loss"]["current_distance"] == 2500.0
        assert distances["daily_loss"]["distance_pct"] == 50.0
        assert distances["daily_loss"]["is_approaching"] is True

    def test_profit_approaching_target(self, worker, sample_thresholds):
        """When P&L is positive, distance to profit target decreases."""
        # Profit of 8000 out of 10000 target = 20% distance remaining
        distances = worker.compute_distance_to_thresholds(8000.0, sample_thresholds)

        assert distances["profit_target"]["current_distance"] == 2000.0
        assert distances["profit_target"]["distance_pct"] == 20.0
        assert distances["profit_target"]["is_approaching"] is True

    def test_profit_not_approaching_loss_thresholds(self, worker, sample_thresholds):
        """When P&L is positive, loss thresholds are not being approached."""
        distances = worker.compute_distance_to_thresholds(5000.0, sample_thresholds)

        assert distances["daily_loss"]["is_approaching"] is False
        assert distances["drawdown"]["is_approaching"] is False

    def test_zero_thresholds_skipped(self, worker):
        """Thresholds with value 0 are not included in distances."""
        thresholds = {
            "daily_loss": 0,
            "profit_target": 0,
            "drawdown": 0,
            "capital": 100000.0,
        }
        distances = worker.compute_distance_to_thresholds(-1000.0, thresholds)
        assert distances == {}


# ============================================================
# Tests for nearest threshold finding
# ============================================================


class TestFindNearestThreshold:
    """Test finding the closest approaching threshold."""

    def test_finds_nearest_approaching(self, worker):
        distances = {
            "daily_loss": {
                "threshold_value": 5000,
                "current_distance": 500,
                "distance_pct": 10.0,
                "is_approaching": True,
            },
            "drawdown": {
                "threshold_value": 3000,
                "current_distance": 1000,
                "distance_pct": 33.3,
                "is_approaching": True,
            },
        }
        name, pct = worker.find_nearest_threshold(distances)
        assert name == "daily_loss"
        assert pct == 10.0

    def test_empty_distances(self, worker):
        name, pct = worker.find_nearest_threshold({})
        assert name == "none"
        assert pct == 100.0

    def test_none_approaching_picks_smallest_distance(self, worker):
        distances = {
            "daily_loss": {
                "threshold_value": 5000,
                "current_distance": 4000,
                "distance_pct": 80.0,
                "is_approaching": False,
            },
            "profit_target": {
                "threshold_value": 10000,
                "current_distance": 5000,
                "distance_pct": 50.0,
                "is_approaching": False,
            },
        }
        name, pct = worker.find_nearest_threshold(distances)
        assert name == "profit_target"
        assert pct == 50.0


# ============================================================
# Tests for proximity warning checks
# ============================================================


class TestCheckProximityWarnings:
    """Test 10% proximity threshold warning detection."""

    def test_no_warning_when_far_from_threshold(self, worker, sample_thresholds):
        """No warning when P&L is well below 90% of threshold."""
        # Loss of 1000 out of 5000 = only 20% consumed, far from 90%
        warnings = worker.check_proximity_warnings(-1000.0, sample_thresholds)
        assert warnings == []

    def test_warning_when_loss_within_10_percent(self, worker, sample_thresholds):
        """Warning when loss exceeds 90% of daily_loss threshold."""
        # Loss of 4600 out of 5000 = 92% consumed, within 10% of threshold
        warnings = worker.check_proximity_warnings(-4600.0, sample_thresholds)

        loss_warnings = [w for w in warnings if w["threshold_name"] == "daily_loss"]
        assert len(loss_warnings) == 1
        assert loss_warnings[0]["threshold_value"] == 5000.0
        assert loss_warnings[0]["current_value"] == 4600.0

    def test_warning_when_profit_within_10_percent(self, worker, sample_thresholds):
        """Warning when profit exceeds 90% of profit_target threshold."""
        # Profit of 9200 out of 10000 = 92% of target, within 10%
        warnings = worker.check_proximity_warnings(9200.0, sample_thresholds)

        profit_warnings = [w for w in warnings if w["threshold_name"] == "profit_target"]
        assert len(profit_warnings) == 1
        assert profit_warnings[0]["threshold_value"] == 10000.0
        assert profit_warnings[0]["current_value"] == 9200.0

    def test_drawdown_warning(self, worker, sample_thresholds):
        """Warning when loss exceeds 90% of drawdown threshold."""
        # Loss of 2800 out of 3000 drawdown = 93.3%, within 10%
        warnings = worker.check_proximity_warnings(-2800.0, sample_thresholds)

        drawdown_warnings = [w for w in warnings if w["threshold_name"] == "drawdown"]
        assert len(drawdown_warnings) == 1

    def test_multiple_warnings_possible(self, worker):
        """Can trigger warnings on multiple thresholds simultaneously."""
        thresholds = {
            "daily_loss": 3000.0,
            "profit_target": 10000.0,
            "drawdown": 2500.0,  # lower than daily_loss
            "capital": 100000.0,
        }
        # Loss of 2800 triggers both daily_loss (93.3%) and drawdown warnings
        warnings = worker.check_proximity_warnings(-2800.0, thresholds)

        names = [w["threshold_name"] for w in warnings]
        assert "daily_loss" in names
        assert "drawdown" in names

    def test_no_warning_for_positive_pnl_on_loss_thresholds(self, worker, sample_thresholds):
        """Positive P&L should not trigger loss threshold warnings."""
        warnings = worker.check_proximity_warnings(4500.0, sample_thresholds)

        loss_warnings = [
            w for w in warnings
            if w["threshold_name"] in ("daily_loss", "drawdown")
        ]
        assert loss_warnings == []


# ============================================================
# Tests for Redis PubSub publishing
# ============================================================


class TestPublishStatus:
    """Test monitor status publishing via Redis PubSub."""

    def test_publishes_to_correct_channel(self, worker, mock_redis_client):
        distances = {
            "daily_loss": {
                "threshold_value": 5000,
                "current_distance": 2000,
                "distance_pct": 40.0,
            },
        }
        worker.publish_status(-3000.0, distances, "daily_loss", 40.0)

        mock_redis_client.client.publish.assert_called_once()
        args = mock_redis_client.client.publish.call_args
        assert args[0][0] == "monitor:status:1"

        payload = json.loads(args[0][1])
        assert payload["user_id"] == 1
        assert payload["current_pnl"] == -3000.0
        assert payload["nearest_threshold"] == "daily_loss"
        assert payload["monitoring_active"] is True

    def test_publish_returns_true_on_success(self, worker, mock_redis_client):
        result = worker.publish_status(0.0, {}, "none", 100.0)
        assert result is True

    def test_publish_returns_false_on_error(self, worker, mock_redis_client):
        mock_redis_client.client.publish.side_effect = Exception("Redis down")
        result = worker.publish_status(0.0, {}, "none", 100.0)
        assert result is False


class TestPublishThresholdWarning:
    """Test threshold warning publishing via Redis PubSub."""

    def test_publishes_warnings(self, worker, mock_redis_client):
        warnings = [
            {
                "threshold_name": "daily_loss",
                "threshold_value": 5000.0,
                "current_value": 4600.0,
                "distance_pct": 8.0,
            }
        ]
        result = worker.publish_threshold_warning(warnings)
        assert result is True

        args = mock_redis_client.client.publish.call_args
        assert args[0][0] == "monitor:threshold_warning:1"
        payload = json.loads(args[0][1])
        assert len(payload["warnings"]) == 1
        assert payload["warnings"][0]["threshold_name"] == "daily_loss"

    def test_no_publish_when_empty_warnings(self, worker, mock_redis_client):
        result = worker.publish_threshold_warning([])
        assert result is True
        mock_redis_client.client.publish.assert_not_called()


# ============================================================
# Tests for full monitor cycle
# ============================================================


class TestRunMonitorCycle:
    """Test the full run_monitor_cycle method."""

    def test_skips_when_inactive(self, worker, mock_redis_client, mock_db_session):
        mock_redis_client.get.return_value = "false"
        result = worker.run_monitor_cycle(mock_db_session)
        assert result["status"] == "skipped"
        assert result["reason"] == "Monitoring inactive"

    def test_skips_when_no_pnl_data(self, worker, mock_redis_client, mock_db_session):
        mock_redis_client.get.return_value = "true"
        mock_redis_client.hget.return_value = None
        result = worker.run_monitor_cycle(mock_db_session)
        assert result["status"] == "skipped"
        assert "No P&L data" in result["reason"]

    @patch("src.workers.auto_monitor_worker.AutoMonitorWorker.get_thresholds")
    def test_error_when_thresholds_fail(
        self, mock_get_thresholds, worker, mock_redis_client, mock_db_session
    ):
        mock_redis_client.get.return_value = "true"
        mock_redis_client.hget.return_value = "-2000.0"
        mock_get_thresholds.return_value = None

        result = worker.run_monitor_cycle(mock_db_session)
        assert result["status"] == "error"
        assert "thresholds" in result["reason"].lower()

    @patch("src.workers.auto_monitor_worker.AutoMonitorWorker.get_thresholds")
    def test_successful_cycle_no_warnings(
        self, mock_get_thresholds, worker, mock_redis_client, mock_db_session
    ):
        mock_redis_client.get.return_value = "true"
        mock_redis_client.hget.return_value = "-1000.0"
        mock_get_thresholds.return_value = {
            "daily_loss": 5000.0,
            "profit_target": 10000.0,
            "drawdown": 3000.0,
            "capital": 100000.0,
        }

        result = worker.run_monitor_cycle(mock_db_session)
        assert result["status"] == "success"
        assert result["warnings_count"] == 0
        assert result["current_pnl"] == -1000.0

    @patch("src.workers.auto_monitor_worker.AutoMonitorWorker.get_thresholds")
    def test_successful_cycle_with_warnings(
        self, mock_get_thresholds, worker, mock_redis_client, mock_db_session
    ):
        mock_redis_client.get.return_value = "true"
        mock_redis_client.hget.return_value = "-4700.0"  # 94% of 5000
        mock_get_thresholds.return_value = {
            "daily_loss": 5000.0,
            "profit_target": 10000.0,
            "drawdown": 3000.0,
            "capital": 100000.0,
        }

        result = worker.run_monitor_cycle(mock_db_session)
        assert result["status"] == "success"
        assert result["warnings_count"] >= 1  # at least daily_loss warning

        # Verify publish was called (status + warning)
        assert mock_redis_client.client.publish.call_count >= 2


# ============================================================
# Tests for Celery task functions
# ============================================================


class TestGetMonitoredUserIds:
    """Test getting user IDs with active monitoring from Redis."""

    def test_returns_empty_when_no_keys(self, mock_redis_client):
        mock_redis_client.client.scan.return_value = (0, [])
        result = get_monitored_user_ids(mock_redis_client)
        assert result == []

    def test_returns_active_user_ids(self, mock_redis_client):
        mock_redis_client.client.scan.return_value = (
            0,
            ["user:1:monitor:active", "user:2:monitor:active"],
        )
        mock_redis_client.get.side_effect = lambda k: (
            "true" if k == "user:1:monitor:active" else "false"
        )

        result = get_monitored_user_ids(mock_redis_client)
        assert 1 in result
        assert 2 not in result

    def test_handles_scan_error(self, mock_redis_client):
        mock_redis_client.client.scan.side_effect = Exception("Redis error")
        result = get_monitored_user_ids(mock_redis_client)
        assert result == []


class TestRunPnlMonitorTask:
    """Test the run_pnl_monitor Celery task."""

    @patch("src.workers.auto_monitor_task.get_redis_client")
    def test_skips_inactive_user(self, mock_get_redis):
        mock_redis = MagicMock()
        mock_redis.get.return_value = "false"
        mock_get_redis.return_value = mock_redis

        result = _execute_pnl_monitor(1)
        assert result["status"] == "skipped"
        assert result["reason"] == "Monitoring inactive"

    @patch("src.workers.auto_monitor_task.get_db_session")
    @patch("src.workers.auto_monitor_task.get_redis_client")
    def test_handles_exceptions(self, mock_get_redis, mock_get_session):
        mock_redis = MagicMock()
        mock_redis.get.return_value = "true"
        mock_redis.hget.return_value = None
        mock_get_redis.return_value = mock_redis
        mock_get_session.return_value = MagicMock()

        result = _execute_pnl_monitor(1)
        # Should be "skipped" because no P&L data
        assert result["status"] == "skipped"


class TestSchedulePnlMonitoring:
    """Test the schedule_pnl_monitoring Celery beat task."""

    @patch("src.workers.auto_monitor_task.run_pnl_monitor")
    @patch("src.workers.auto_monitor_task.get_redis_client")
    def test_dispatches_for_active_users(self, mock_get_redis, mock_task):
        mock_redis = MagicMock()
        mock_redis.client.scan.return_value = (
            0,
            ["user:1:monitor:active", "user:2:monitor:active"],
        )
        mock_redis.get.return_value = "true"
        mock_get_redis.return_value = mock_redis

        result = _execute_schedule_pnl_monitoring()
        assert result["status"] == "success"
        assert result["users_dispatched"] == 2
        assert mock_task.delay.call_count == 2

    @patch("src.workers.auto_monitor_task.get_redis_client")
    def test_returns_zero_when_no_users(self, mock_get_redis):
        mock_redis = MagicMock()
        mock_redis.client.scan.return_value = (0, [])
        mock_get_redis.return_value = mock_redis

        result = _execute_schedule_pnl_monitoring()
        assert result["status"] == "success"
        assert result["users_dispatched"] == 0
