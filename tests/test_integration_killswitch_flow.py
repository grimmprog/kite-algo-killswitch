"""Integration tests for kill switch activation flow (Task 22.2).

Tests the end-to-end kill switch activation flow:
1. Threshold breach detection
2. Flag setting (Redis NX)
3. Position closure (exit orders queued)
4. Database logging (KillSwitchLog record)
5. User notification (Redis pub/sub)

Requirements covered:
- 6.2.2: Integration tests for kill switch activation
- 1.5.1: Set kill switch flag in Redis atomically
- 1.5.4: Close all open positions via market orders
- 1.5.5: Log kill switch activation to database
- 1.5.6: Notify user via all channels
- 1.5.8: Prevent kill switch from triggering multiple times for same event
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import pytest
from unittest.mock import MagicMock, patch, call
from datetime import datetime

from src.workers.risk_engine_worker import RiskEngineWorker
from src.cache.redis_keys import RedisKeys
from src.database.models.killswitch_log import KillSwitchLog


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def mock_kite():
    """Create a mock KiteConnect client with sample positions."""
    kite = MagicMock()
    kite.positions.return_value = {
        "net": [
            {
                "tradingsymbol": "NIFTY23DEC21000CE",
                "exchange": "NFO",
                "product": "NRML",
                "quantity": 50,
                "average_price": 150.0,
                "last_price": 120.0,
                "pnl": -1500.0,
                "unrealised": -1500.0,
                "realised": 0.0,
                "buy_quantity": 50,
                "sell_quantity": 0,
            },
            {
                "tradingsymbol": "NIFTY23DEC21000PE",
                "exchange": "NFO",
                "product": "NRML",
                "quantity": -25,
                "average_price": 100.0,
                "last_price": 180.0,
                "pnl": -2000.0,
                "unrealised": -2000.0,
                "realised": 0.0,
                "buy_quantity": 0,
                "sell_quantity": 25,
            },
        ],
        "day": [],
    }
    return kite


@pytest.fixture
def mock_redis_client():
    """Create a mock Redis client for integration testing."""
    redis = MagicMock()
    # Default: kill switch flag NOT set (first activation)
    redis.set.return_value = True  # NX succeeds
    redis.publish.return_value = 1  # pub/sub returns subscriber count
    return redis


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    db = MagicMock()
    db.add.return_value = None
    db.commit.return_value = None
    return db


@pytest.fixture
def worker(mock_kite, mock_redis_client, mock_db):
    """Create a RiskEngineWorker for integration testing."""
    return RiskEngineWorker(
        user_id=1,
        kite_client=mock_kite,
        redis_client=mock_redis_client,
        db_session=mock_db,
    )


# ============================================================
# 22.2.1: Threshold Breach Detection
# ============================================================


class TestThresholdBreachDetection:
    """Test that check_thresholds correctly detects when daily loss limit is breached."""

    def test_daily_loss_limit_breached(self, worker):
        """check_thresholds returns True when loss exceeds daily limit."""
        # User has 500k capital, 2% daily loss limit = 10k max loss
        # Current P&L is -15000 which is -3%, exceeding the 2% limit
        breached, reason = worker.check_thresholds(
            pnl=-15000.0,
            capital=500000.0,
            daily_loss_limit_pct=2.0,
            margin_used=50000.0,
        )

        assert breached is True
        assert "Daily loss limit breached" in reason
        assert "-3.00%" in reason

    def test_daily_loss_exactly_at_limit(self, worker):
        """check_thresholds returns True when loss is exactly at the limit."""
        # 2% of 500k = 10k loss exactly at limit
        breached, reason = worker.check_thresholds(
            pnl=-10000.0,
            capital=500000.0,
            daily_loss_limit_pct=2.0,
            margin_used=50000.0,
        )

        assert breached is True
        assert "Daily loss limit breached" in reason

    def test_no_breach_within_limits(self, worker):
        """check_thresholds returns False when P&L is within daily loss limit."""
        breached, reason = worker.check_thresholds(
            pnl=-5000.0,
            capital=500000.0,
            daily_loss_limit_pct=2.0,
            margin_used=50000.0,
        )

        assert breached is False
        assert reason == "Within limits"

    def test_margin_limit_breach(self, worker):
        """check_thresholds detects margin usage above 90%."""
        breached, reason = worker.check_thresholds(
            pnl=-1000.0,
            capital=500000.0,
            daily_loss_limit_pct=2.0,
            margin_used=460000.0,  # 92% of capital
        )

        assert breached is True
        assert "Margin limit breached" in reason

    def test_end_to_end_positions_to_threshold_detection(
        self, worker, mock_kite
    ):
        """Full flow: fetch positions → compute P&L → check thresholds."""
        positions = worker.fetch_positions()
        pnl = worker.compute_live_pnl(positions)

        # P&L from positions: -1500 + -2000 = -3500
        breached, reason = worker.check_thresholds(
            pnl=pnl,
            capital=100000.0,  # With 100k capital, -3500 = -3.5%
            daily_loss_limit_pct=2.0,
            margin_used=20000.0,
        )

        assert breached is True
        assert "Daily loss limit breached" in reason


# ============================================================
# 22.2.2: Flag Setting
# ============================================================


class TestFlagSetting:
    """Test that trigger_killswitch sets Redis kill switch flag atomically via NX."""

    @patch("src.workers.risk_engine_worker.RiskEngineWorker._queue_exit_orders")
    @patch("src.workers.risk_engine_worker.RiskEngineWorker._log_killswitch_event")
    @patch("src.workers.risk_engine_worker.RiskEngineWorker._send_killswitch_notification")
    def test_sets_redis_flag_with_nx(
        self, mock_notify, mock_log, mock_exit, worker, mock_redis_client
    ):
        """trigger_killswitch sets Redis flag with NX (set-if-not-exists)."""
        mock_exit.return_value = 2

        worker.trigger_killswitch("Daily loss limit breached: -3.00%")

        expected_key = RedisKeys.user_killswitch(1)
        mock_redis_client.set.assert_called_once_with(expected_key, "true", nx=True)

    @patch("src.workers.risk_engine_worker.RiskEngineWorker._queue_exit_orders")
    @patch("src.workers.risk_engine_worker.RiskEngineWorker._log_killswitch_event")
    @patch("src.workers.risk_engine_worker.RiskEngineWorker._send_killswitch_notification")
    def test_returns_true_on_first_activation(
        self, mock_notify, mock_log, mock_exit, worker, mock_redis_client
    ):
        """trigger_killswitch returns True when flag is newly set."""
        mock_redis_client.set.return_value = True
        mock_exit.return_value = 2

        result = worker.trigger_killswitch("Daily loss limit breached")

        assert result is True

    @patch("src.workers.risk_engine_worker.RiskEngineWorker._queue_exit_orders")
    @patch("src.workers.risk_engine_worker.RiskEngineWorker._log_killswitch_event")
    @patch("src.workers.risk_engine_worker.RiskEngineWorker._send_killswitch_notification")
    def test_returns_false_on_duplicate_trigger(
        self, mock_notify, mock_log, mock_exit, worker, mock_redis_client
    ):
        """trigger_killswitch returns False when flag already exists (NX fails)."""
        mock_redis_client.set.return_value = False  # NX fails, flag already set

        result = worker.trigger_killswitch("Daily loss limit breached")

        assert result is False
        # Should NOT proceed with exit orders, logging, or notification
        mock_exit.assert_not_called()
        mock_log.assert_not_called()
        mock_notify.assert_not_called()

    @patch("src.workers.risk_engine_worker.RiskEngineWorker._queue_exit_orders")
    @patch("src.workers.risk_engine_worker.RiskEngineWorker._log_killswitch_event")
    @patch("src.workers.risk_engine_worker.RiskEngineWorker._send_killswitch_notification")
    def test_flag_key_is_user_specific(
        self, mock_notify, mock_log, mock_exit, mock_kite, mock_redis_client, mock_db
    ):
        """Each user gets their own kill switch flag key."""
        mock_redis_client.set.return_value = True
        mock_exit.return_value = 0

        worker_user1 = RiskEngineWorker(1, mock_kite, mock_redis_client, mock_db)
        worker_user1.trigger_killswitch("Loss breach")

        worker_user2 = RiskEngineWorker(2, mock_kite, mock_redis_client, mock_db)
        mock_redis_client.set.reset_mock()
        worker_user2.trigger_killswitch("Loss breach")

        expected_key = RedisKeys.user_killswitch(2)
        mock_redis_client.set.assert_called_once_with(expected_key, "true", nx=True)


# ============================================================
# 22.2.3: Position Closure
# ============================================================


class TestPositionClosure:
    """Test that trigger_killswitch queues exit orders for all open positions."""

    @patch("src.workers.celery_app.celery_app")
    def test_queues_exit_orders_for_all_positions(
        self, mock_celery, worker, mock_kite, mock_redis_client
    ):
        """trigger_killswitch queues exit orders for every open position."""
        mock_redis_client.set.return_value = True

        worker.trigger_killswitch("Daily loss limit breached")

        # Should have queued 2 exit orders (one SELL for long, one BUY for short)
        assert mock_celery.send_task.call_count == 2

    @patch("src.workers.celery_app.celery_app")
    def test_long_position_gets_sell_exit_order(
        self, mock_celery, worker, mock_kite, mock_redis_client
    ):
        """Long positions (qty > 0) get SELL exit orders."""
        mock_redis_client.set.return_value = True

        worker.trigger_killswitch("Daily loss limit breached")

        # Find the SELL order call
        sell_calls = [
            c for c in mock_celery.send_task.call_args_list
            if c[1].get("kwargs", {}).get("transaction_type") == "SELL"
            or (len(c) > 1 and isinstance(c[1], dict) and c[1].get("kwargs", {}).get("transaction_type") == "SELL")
        ]
        # Check via kwargs
        all_calls = mock_celery.send_task.call_args_list
        sell_found = False
        for c in all_calls:
            kwargs = c[1].get("kwargs", {}) if len(c) > 1 else c.kwargs.get("kwargs", {})
            if kwargs.get("transaction_type") == "SELL":
                assert kwargs["tradingsymbol"] == "NIFTY23DEC21000CE"
                assert kwargs["quantity"] == 50
                assert kwargs["order_type"] == "MARKET"
                sell_found = True
                break

        assert sell_found, "Expected a SELL exit order for the long position"

    @patch("src.workers.celery_app.celery_app")
    def test_short_position_gets_buy_exit_order(
        self, mock_celery, worker, mock_kite, mock_redis_client
    ):
        """Short positions (qty < 0) get BUY exit orders."""
        mock_redis_client.set.return_value = True

        worker.trigger_killswitch("Daily loss limit breached")

        all_calls = mock_celery.send_task.call_args_list
        buy_found = False
        for c in all_calls:
            kwargs = c[1].get("kwargs", {}) if len(c) > 1 else c.kwargs.get("kwargs", {})
            if kwargs.get("transaction_type") == "BUY":
                assert kwargs["tradingsymbol"] == "NIFTY23DEC21000PE"
                assert kwargs["quantity"] == 25
                assert kwargs["order_type"] == "MARKET"
                buy_found = True
                break

        assert buy_found, "Expected a BUY exit order for the short position"

    @patch("src.workers.celery_app.celery_app")
    def test_exit_orders_marked_as_killswitch_triggered(
        self, mock_celery, worker, mock_kite, mock_redis_client
    ):
        """All exit orders have trigger_reason='kill_switch'."""
        mock_redis_client.set.return_value = True

        worker.trigger_killswitch("Daily loss limit breached")

        for c in mock_celery.send_task.call_args_list:
            kwargs = c[1].get("kwargs", {}) if len(c) > 1 else c.kwargs.get("kwargs", {})
            assert kwargs.get("trigger_reason") == "kill_switch"

    @patch("src.workers.celery_app.celery_app")
    def test_no_exit_orders_when_no_positions(
        self, mock_celery, mock_redis_client, mock_db
    ):
        """No exit orders are queued when the user has no open positions."""
        kite = MagicMock()
        kite.positions.return_value = {"net": [], "day": []}
        mock_redis_client.set.return_value = True

        w = RiskEngineWorker(1, kite, mock_redis_client, mock_db)
        w.trigger_killswitch("Daily loss limit breached")

        mock_celery.send_task.assert_not_called()


# ============================================================
# 22.2.4: Database Logging
# ============================================================


class TestDatabaseLogging:
    """Test that trigger_killswitch creates a KillSwitchLog record in the database."""

    @patch("src.workers.celery_app.celery_app")
    def test_log_entry_created_in_database(
        self, mock_celery, worker, mock_redis_client, mock_db
    ):
        """trigger_killswitch creates a KillSwitchLog record."""
        mock_redis_client.set.return_value = True

        worker.trigger_killswitch("Daily loss limit breached: -3.00%", capital=500000.0)

        mock_db.add.assert_called_once()
        log_entry = mock_db.add.call_args[0][0]
        assert isinstance(log_entry, KillSwitchLog)

    @patch("src.workers.celery_app.celery_app")
    def test_log_entry_has_correct_user_id(
        self, mock_celery, worker, mock_redis_client, mock_db
    ):
        """KillSwitchLog record has the correct user_id."""
        mock_redis_client.set.return_value = True

        worker.trigger_killswitch("Daily loss limit breached", capital=500000.0)

        log_entry = mock_db.add.call_args[0][0]
        assert log_entry.user_id == 1

    @patch("src.workers.celery_app.celery_app")
    def test_log_entry_has_trigger_reason(
        self, mock_celery, worker, mock_redis_client, mock_db
    ):
        """KillSwitchLog record stores the trigger reason."""
        mock_redis_client.set.return_value = True
        reason = "Daily loss limit breached: -3.50%"

        worker.trigger_killswitch(reason, capital=500000.0)

        log_entry = mock_db.add.call_args[0][0]
        assert log_entry.trigger_reason == reason

    @patch("src.workers.celery_app.celery_app")
    def test_log_entry_has_positions_closed_count(
        self, mock_celery, worker, mock_redis_client, mock_db
    ):
        """KillSwitchLog record stores the number of positions queued for exit."""
        mock_redis_client.set.return_value = True

        worker.trigger_killswitch("Loss breach", capital=500000.0)

        log_entry = mock_db.add.call_args[0][0]
        assert log_entry.positions_closed_count == 2  # 2 positions from fixture

    @patch("src.workers.celery_app.celery_app")
    def test_log_entry_has_capital(
        self, mock_celery, worker, mock_redis_client, mock_db
    ):
        """KillSwitchLog record stores capital at time of trigger."""
        mock_redis_client.set.return_value = True

        worker.trigger_killswitch("Loss breach", capital=500000.0)

        log_entry = mock_db.add.call_args[0][0]
        assert log_entry.capital_at_trigger == 500000.0

    @patch("src.workers.celery_app.celery_app")
    def test_database_commit_called(
        self, mock_celery, worker, mock_redis_client, mock_db
    ):
        """Database session is committed after adding the log entry."""
        mock_redis_client.set.return_value = True

        worker.trigger_killswitch("Loss breach", capital=500000.0)

        mock_db.commit.assert_called()


# ============================================================
# 22.2.5: User Notification
# ============================================================


class TestUserNotification:
    """Test that trigger_killswitch sends notification via Redis pub/sub."""

    @patch("src.workers.celery_app.celery_app")
    def test_notification_published_to_user_channel(
        self, mock_celery, worker, mock_redis_client, mock_db
    ):
        """Notification is published to the user's Redis pub/sub channel."""
        mock_redis_client.set.return_value = True

        worker.trigger_killswitch("Daily loss limit breached")

        expected_channel = "user:1:notifications"
        mock_redis_client.publish.assert_called_once()
        actual_channel = mock_redis_client.publish.call_args[0][0]
        assert actual_channel == expected_channel

    @patch("src.workers.celery_app.celery_app")
    def test_notification_contains_killswitch_type(
        self, mock_celery, worker, mock_redis_client, mock_db
    ):
        """Notification message has type 'killswitch_activated'."""
        mock_redis_client.set.return_value = True

        worker.trigger_killswitch("Daily loss limit breached")

        message_json = mock_redis_client.publish.call_args[0][1]
        message = json.loads(message_json)
        assert message["type"] == "killswitch_activated"

    @patch("src.workers.celery_app.celery_app")
    def test_notification_contains_reason(
        self, mock_celery, worker, mock_redis_client, mock_db
    ):
        """Notification message includes the trigger reason."""
        mock_redis_client.set.return_value = True
        reason = "Daily loss limit breached: -3.50%"

        worker.trigger_killswitch(reason)

        message_json = mock_redis_client.publish.call_args[0][1]
        message = json.loads(message_json)
        assert message["reason"] == reason

    @patch("src.workers.celery_app.celery_app")
    def test_notification_contains_positions_closed(
        self, mock_celery, worker, mock_redis_client, mock_db
    ):
        """Notification message includes the number of positions closed."""
        mock_redis_client.set.return_value = True

        worker.trigger_killswitch("Loss breach")

        message_json = mock_redis_client.publish.call_args[0][1]
        message = json.loads(message_json)
        assert message["positions_closed"] == 2

    @patch("src.workers.celery_app.celery_app")
    def test_notification_contains_user_id(
        self, mock_celery, worker, mock_redis_client, mock_db
    ):
        """Notification message includes user_id."""
        mock_redis_client.set.return_value = True

        worker.trigger_killswitch("Loss breach")

        message_json = mock_redis_client.publish.call_args[0][1]
        message = json.loads(message_json)
        assert message["user_id"] == 1

    @patch("src.workers.celery_app.celery_app")
    def test_notification_contains_timestamp(
        self, mock_celery, worker, mock_redis_client, mock_db
    ):
        """Notification message includes a timestamp."""
        mock_redis_client.set.return_value = True

        worker.trigger_killswitch("Loss breach")

        message_json = mock_redis_client.publish.call_args[0][1]
        message = json.loads(message_json)
        assert "timestamp" in message


# ============================================================
# End-to-End: Complete Kill Switch Activation Flow
# ============================================================


class TestCompleteKillSwitchFlow:
    """Test the complete end-to-end kill switch activation flow."""

    @patch("src.workers.celery_app.celery_app")
    def test_full_flow_positions_to_killswitch(
        self, mock_celery, worker, mock_kite, mock_redis_client, mock_db
    ):
        """Complete flow: positions → P&L → threshold check → kill switch trigger.

        This test exercises the entire kill switch activation path:
        1. Fetch positions from broker
        2. Compute live P&L
        3. Check thresholds (breach detected)
        4. Trigger kill switch
        5. Verify all side effects (flag, orders, log, notification)
        """
        # Step 1: Fetch positions
        positions = worker.fetch_positions()
        assert len(positions) == 2

        # Step 2: Compute P&L
        pnl = worker.compute_live_pnl(positions)
        # P&L = sum of unrealised: -1500 + -2000 = -3500
        assert pnl == -3500.0

        # Step 3: Check thresholds
        capital = 100000.0
        breached, reason = worker.check_thresholds(
            pnl=pnl,
            capital=capital,
            daily_loss_limit_pct=2.0,  # 2% of 100k = 2000; loss is 3500
            margin_used=20000.0,
        )
        assert breached is True
        assert "Daily loss limit breached" in reason

        # Step 4: Trigger kill switch
        result = worker.trigger_killswitch(reason, capital=capital)
        assert result is True

        # Step 5a: Verify flag was set
        expected_key = RedisKeys.user_killswitch(1)
        mock_redis_client.set.assert_called_with(expected_key, "true", nx=True)

        # Step 5b: Verify exit orders were queued
        assert mock_celery.send_task.call_count == 2

        # Step 5c: Verify database log was created
        mock_db.add.assert_called_once()
        log_entry = mock_db.add.call_args[0][0]
        assert isinstance(log_entry, KillSwitchLog)
        assert log_entry.user_id == 1
        assert log_entry.positions_closed_count == 2
        mock_db.commit.assert_called()

        # Step 5d: Verify notification was sent
        mock_redis_client.publish.assert_called_once()
        channel = mock_redis_client.publish.call_args[0][0]
        assert channel == "user:1:notifications"
        message = json.loads(mock_redis_client.publish.call_args[0][1])
        assert message["type"] == "killswitch_activated"
        assert message["positions_closed"] == 2

    @patch("src.workers.celery_app.celery_app")
    def test_duplicate_trigger_prevented(
        self, mock_celery, worker, mock_redis_client, mock_db
    ):
        """Second trigger is blocked by Redis NX (idempotency)."""
        # First trigger succeeds
        mock_redis_client.set.return_value = True
        result1 = worker.trigger_killswitch("First breach")
        assert result1 is True

        # Second trigger blocked (NX returns False)
        mock_redis_client.set.return_value = False
        result2 = worker.trigger_killswitch("Second breach")
        assert result2 is False

    @patch("src.workers.celery_app.celery_app")
    def test_no_trigger_when_within_limits(
        self, mock_celery, worker, mock_kite, mock_redis_client, mock_db
    ):
        """No kill switch triggered when P&L is within acceptable limits."""
        positions = worker.fetch_positions()
        pnl = worker.compute_live_pnl(positions)

        # Use large capital so loss percentage is small
        breached, reason = worker.check_thresholds(
            pnl=pnl,
            capital=10000000.0,  # 10M capital, -3500 is tiny
            daily_loss_limit_pct=2.0,
            margin_used=100000.0,
        )
        assert breached is False
        assert reason == "Within limits"

        # Kill switch should NOT be triggered
        mock_redis_client.set.assert_not_called()
        mock_celery.send_task.assert_not_called()
        mock_db.add.assert_not_called()
