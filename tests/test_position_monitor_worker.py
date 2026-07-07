"""Unit tests for the position monitor worker.

Tests the Celery task module src/workers/position_monitor_worker.py:
- monitor_positions task: per-user position monitoring cycle
- schedule_position_monitoring task: beat scheduler for dispatching
- Helper functions: publish updates, fetch prices, process positions

Requirements covered: 7.2, 7.3, 7.4, 7.5, 7.6, 8.1-8.5
"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call

import pytest

from src.services.position_monitor_service import (
    ExitCondition,
    MarketData,
    MonitoredPosition,
)
from src.workers.position_monitor_worker import (
    CHANNEL_AUTO_EXIT,
    CHANNEL_EXIT_CONDITION,
    CHANNEL_POSITION_MONITOR,
    _execute_monitor_positions,
    _execute_schedule_position_monitoring,
    _process_single_position,
    cache_position_state,
    fetch_live_prices,
    get_users_with_open_positions,
    publish_auto_exit_triggered,
    publish_exit_condition_update,
    publish_position_update,
)


# --- Fixtures ---


@pytest.fixture
def mock_redis_client():
    """Create a mock RedisClient."""
    client = MagicMock()
    client.client = MagicMock()
    client.client.publish = MagicMock(return_value=1)
    client.get = MagicMock(return_value=None)
    client.set = MagicMock(return_value=True)
    return client


@pytest.fixture
def sample_position():
    """Create a sample MonitoredPosition for testing."""
    return MonitoredPosition(
        position_id=1,
        symbol="NIFTY23DEC21000CE",
        entry_price=200.0,
        current_price=210.0,
        quantity=50,
        stop_loss=190.0,
        target=230.0,
        trailing_stop_enabled=True,
        trailing_stop_level=205.0,
        trailing_stop_distance=2.5,
        unrealized_pnl=500.0,
        distance_to_sl_pct=9.52,
        distance_to_target_pct=9.52,
        status="active",
    )


@pytest.fixture
def sample_exit_conditions():
    """Create sample exit conditions."""
    return [
        ExitCondition(
            name="ema_cross",
            description="Close above 20 EMA",
            is_met=False,
            details="Price 210.00 <= EMA20 215.00",
        ),
        ExitCondition(
            name="vwap_touch",
            description="Price touches VWAP",
            is_met=False,
            details="Price 210.00 not at VWAP 212.00",
        ),
        ExitCondition(
            name="consecutive_green",
            description="2 consecutive green candles",
            is_met=True,
            details="3 consecutive green candle(s) detected",
        ),
        ExitCondition(
            name="time_based",
            description="Time-based exit (after 11:30 IST)",
            is_met=False,
            details="Current IST time 10:30 < 11:30",
        ),
    ]


# --- Tests for publish_position_update ---


class TestPublishPositionUpdate:
    """Tests for publish_position_update function."""

    def test_publishes_to_correct_channel(self, mock_redis_client, sample_position):
        """Should publish to position:monitor:{user_id} channel."""
        result = publish_position_update(mock_redis_client, 42, sample_position)

        assert result is True
        mock_redis_client.client.publish.assert_called_once()
        channel = mock_redis_client.client.publish.call_args[0][0]
        assert channel == "position:monitor:42"

    def test_payload_contains_position_data(self, mock_redis_client, sample_position):
        """Should include all position metrics in the payload."""
        publish_position_update(mock_redis_client, 1, sample_position)

        payload_str = mock_redis_client.client.publish.call_args[0][1]
        payload = json.loads(payload_str)

        assert payload["position_id"] == 1
        assert payload["symbol"] == "NIFTY23DEC21000CE"
        assert payload["entry_price"] == 200.0
        assert payload["current_price"] == 210.0
        assert payload["quantity"] == 50
        assert payload["stop_loss"] == 190.0
        assert payload["target"] == 230.0
        assert payload["trailing_stop_enabled"] is True
        assert payload["trailing_stop_level"] == 205.0
        assert payload["status"] == "active"
        assert "timestamp" in payload

    def test_returns_false_on_redis_error(self, mock_redis_client, sample_position):
        """Should return False when Redis publish fails."""
        mock_redis_client.client.publish.side_effect = Exception("Connection refused")

        result = publish_position_update(mock_redis_client, 1, sample_position)
        assert result is False


# --- Tests for publish_exit_condition_update ---


class TestPublishExitConditionUpdate:
    """Tests for publish_exit_condition_update function."""

    def test_publishes_to_correct_channel(
        self, mock_redis_client, sample_exit_conditions
    ):
        """Should publish to position:exit_condition:{user_id} channel."""
        result = publish_exit_condition_update(
            mock_redis_client, 42, 1, sample_exit_conditions
        )

        assert result is True
        channel = mock_redis_client.client.publish.call_args[0][0]
        assert channel == "position:exit_condition:42"

    def test_payload_includes_all_conditions(
        self, mock_redis_client, sample_exit_conditions
    ):
        """Should include all exit conditions with met/not-met status."""
        publish_exit_condition_update(mock_redis_client, 1, 5, sample_exit_conditions)

        payload = json.loads(mock_redis_client.client.publish.call_args[0][1])
        assert payload["position_id"] == 5
        assert len(payload["conditions"]) == 4
        assert payload["any_met"] is True  # consecutive_green is met
        assert "timestamp" in payload

    def test_any_met_false_when_none_met(self, mock_redis_client):
        """Should set any_met=False when no condition is met."""
        conditions = [
            ExitCondition(name="ema_cross", description="", is_met=False),
            ExitCondition(name="vwap_touch", description="", is_met=False),
        ]
        publish_exit_condition_update(mock_redis_client, 1, 1, conditions)

        payload = json.loads(mock_redis_client.client.publish.call_args[0][1])
        assert payload["any_met"] is False

    def test_returns_false_on_error(self, mock_redis_client):
        """Should return False when Redis publish fails."""
        mock_redis_client.client.publish.side_effect = Exception("Redis down")
        result = publish_exit_condition_update(mock_redis_client, 1, 1, [])
        assert result is False


# --- Tests for publish_auto_exit_triggered ---


class TestPublishAutoExitTriggered:
    """Tests for publish_auto_exit_triggered function."""

    def test_publishes_to_correct_channel(self, mock_redis_client):
        """Should publish to position:auto_exit:{user_id} channel."""
        exit_data = {
            "position_id": 1,
            "symbol": "NIFTY",
            "exit_reason": "sl_hit",
            "quantity": 50,
        }
        result = publish_auto_exit_triggered(mock_redis_client, 7, exit_data)

        assert result is True
        channel = mock_redis_client.client.publish.call_args[0][0]
        assert channel == "position:auto_exit:7"

    def test_payload_includes_exit_data_and_timestamp(self, mock_redis_client):
        """Should include exit data and a timestamp."""
        exit_data = {
            "position_id": 3,
            "symbol": "BANKNIFTY",
            "exit_reason": "target_hit",
        }
        publish_auto_exit_triggered(mock_redis_client, 1, exit_data)

        payload = json.loads(mock_redis_client.client.publish.call_args[0][1])
        assert payload["position_id"] == 3
        assert payload["exit_reason"] == "target_hit"
        assert "timestamp" in payload

    def test_returns_false_on_error(self, mock_redis_client):
        """Should return False when Redis publish fails."""
        mock_redis_client.client.publish.side_effect = Exception("Error")
        result = publish_auto_exit_triggered(mock_redis_client, 1, {})
        assert result is False


# --- Tests for cache_position_state ---


class TestCachePositionState:
    """Tests for cache_position_state function."""

    def test_caches_with_correct_key(self, mock_redis_client, sample_position):
        """Should cache position state with key position_monitor:{user_id}:{position_id}."""
        cache_position_state(mock_redis_client, 42, sample_position)

        mock_redis_client.set.assert_called_once()
        key = mock_redis_client.set.call_args[0][0]
        assert key == "position_monitor:42:1"

    def test_caches_with_ttl(self, mock_redis_client, sample_position):
        """Should set a TTL of 10 seconds on cached position state."""
        cache_position_state(mock_redis_client, 1, sample_position)

        call_kwargs = mock_redis_client.set.call_args
        assert call_kwargs[1]["ttl"] == 10

    def test_handles_redis_error_gracefully(self, mock_redis_client, sample_position):
        """Should not raise on Redis failure."""
        mock_redis_client.set.side_effect = Exception("Redis down")
        # Should not raise
        cache_position_state(mock_redis_client, 1, sample_position)


# --- Tests for fetch_live_prices ---


class TestFetchLivePrices:
    """Tests for fetch_live_prices function."""

    def test_returns_prices_from_kite(self):
        """Should map symbol to last_price from Kite LTP response."""
        mock_kite = MagicMock()
        mock_kite.ltp.return_value = {
            "NFO:NIFTY23DEC21000CE": {"last_price": 215.5},
            "NFO:BANKNIFTY23DEC48000PE": {"last_price": 180.0},
        }

        prices = fetch_live_prices(
            mock_kite, ["NIFTY23DEC21000CE", "BANKNIFTY23DEC48000PE"]
        )

        assert prices["NIFTY23DEC21000CE"] == 215.5
        assert prices["BANKNIFTY23DEC48000PE"] == 180.0

    def test_returns_empty_dict_for_empty_symbols(self):
        """Should return empty dict for empty symbol list."""
        mock_kite = MagicMock()
        result = fetch_live_prices(mock_kite, [])
        assert result == {}
        mock_kite.ltp.assert_not_called()

    def test_returns_empty_dict_on_error(self):
        """Should return empty dict on Kite API error."""
        mock_kite = MagicMock()
        mock_kite.ltp.side_effect = Exception("Network error")

        result = fetch_live_prices(mock_kite, ["NIFTY"])
        assert result == {}


# --- Tests for monitor_positions task ---


class TestMonitorPositions:
    """Tests for the _execute_monitor_positions function."""

    @patch("src.workers.position_monitor_worker.get_redis_client")
    @patch("src.workers.position_monitor_worker.get_db_session")
    def test_skips_when_killswitch_active(self, mock_get_db, mock_get_redis):
        """Should skip monitoring when kill switch is active."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = "true"
        mock_get_redis.return_value = mock_redis

        result = _execute_monitor_positions(user_id=1)

        assert result["status"] == "skipped"
        assert result["reason"] == "Kill switch active"
        mock_get_db.assert_not_called()

    @patch("src.workers.position_monitor_worker.get_redis_client")
    @patch("src.workers.position_monitor_worker.get_db_session")
    @patch("src.workers.position_monitor_worker.PositionMonitorService")
    def test_returns_success_with_no_positions(
        self, mock_service_cls, mock_get_db, mock_get_redis
    ):
        """Should return success with 0 positions when user has none."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None  # No killswitch
        mock_get_redis.return_value = mock_redis

        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_service = MagicMock()
        mock_service.get_monitored_positions.return_value = []
        mock_service_cls.return_value = mock_service

        result = _execute_monitor_positions(user_id=1)

        assert result["status"] == "success"
        assert result["positions_monitored"] == 0
        assert result["auto_exits_triggered"] == 0

    @patch("src.workers.position_monitor_worker.get_redis_client")
    @patch("src.workers.position_monitor_worker.get_db_session")
    @patch("src.workers.position_monitor_worker.PositionMonitorService")
    @patch("src.workers.position_monitor_worker.get_user_kite_client")
    @patch("src.workers.position_monitor_worker.fetch_live_prices")
    @patch("src.workers.position_monitor_worker._process_single_position")
    def test_processes_each_position(
        self,
        mock_process,
        mock_fetch_prices,
        mock_get_kite,
        mock_service_cls,
        mock_get_db,
        mock_get_redis,
    ):
        """Should process each active position and return counts."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        positions = [
            MonitoredPosition(
                position_id=1,
                symbol="NIFTY",
                entry_price=100.0,
                current_price=105.0,
                quantity=50,
                stop_loss=95.0,
                target=120.0,
                trailing_stop_enabled=False,
                unrealized_pnl=250.0,
                distance_to_sl_pct=9.5,
                distance_to_target_pct=14.3,
                status="active",
            ),
            MonitoredPosition(
                position_id=2,
                symbol="BANKNIFTY",
                entry_price=200.0,
                current_price=210.0,
                quantity=15,
                stop_loss=190.0,
                target=230.0,
                trailing_stop_enabled=True,
                trailing_stop_level=205.0,
                trailing_stop_distance=2.0,
                unrealized_pnl=150.0,
                distance_to_sl_pct=9.5,
                distance_to_target_pct=9.5,
                status="active",
            ),
        ]

        mock_service = MagicMock()
        mock_service.get_monitored_positions.return_value = positions
        mock_service_cls.return_value = mock_service

        mock_kite = MagicMock()
        mock_get_kite.return_value = mock_kite

        mock_fetch_prices.return_value = {"NIFTY": 106.0, "BANKNIFTY": 212.0}
        mock_process.return_value = {"auto_exit_triggered": False, "exit_reason": None}

        result = _execute_monitor_positions(user_id=1)

        assert result["status"] == "success"
        assert result["positions_monitored"] == 2
        assert result["auto_exits_triggered"] == 0
        assert mock_process.call_count == 2

    @patch("src.workers.position_monitor_worker.get_redis_client")
    @patch("src.workers.position_monitor_worker.get_db_session")
    @patch("src.workers.position_monitor_worker.PositionMonitorService")
    @patch("src.workers.position_monitor_worker.get_user_kite_client")
    def test_returns_error_when_kite_client_unavailable(
        self, mock_get_kite, mock_service_cls, mock_get_db, mock_get_redis
    ):
        """Should return error when Kite client cannot be obtained."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_service = MagicMock()
        mock_service.get_monitored_positions.return_value = [MagicMock()]
        mock_service_cls.return_value = mock_service

        mock_get_kite.side_effect = RuntimeError("No access token")

        result = _execute_monitor_positions(user_id=1)

        assert result["status"] == "error"
        assert "Kite client error" in result["reason"]


# --- Tests for schedule_position_monitoring task ---


class TestSchedulePositionMonitoring:
    """Tests for the _execute_schedule_position_monitoring function."""

    @patch("src.workers.position_monitor_worker.get_db_session")
    @patch("src.workers.position_monitor_worker.get_users_with_open_positions")
    @patch("src.workers.position_monitor_worker.monitor_positions")
    def test_dispatches_tasks_for_each_user(
        self, mock_monitor, mock_get_users, mock_get_db
    ):
        """Should dispatch a monitor_positions task for each user."""
        mock_get_users.return_value = [1, 2, 3]
        mock_get_db.return_value = MagicMock()

        result = _execute_schedule_position_monitoring()

        assert result["status"] == "success"
        assert result["users_dispatched"] == 3
        assert mock_monitor.delay.call_count == 3
        mock_monitor.delay.assert_any_call(1)
        mock_monitor.delay.assert_any_call(2)
        mock_monitor.delay.assert_any_call(3)

    @patch("src.workers.position_monitor_worker.get_db_session")
    @patch("src.workers.position_monitor_worker.get_users_with_open_positions")
    def test_returns_zero_when_no_users(self, mock_get_users, mock_get_db):
        """Should return 0 users dispatched when no active positions."""
        mock_get_users.return_value = []
        mock_get_db.return_value = MagicMock()

        result = _execute_schedule_position_monitoring()

        assert result["status"] == "success"
        assert result["users_dispatched"] == 0

    @patch("src.workers.position_monitor_worker.get_db_session")
    @patch("src.workers.position_monitor_worker.get_users_with_open_positions")
    @patch("src.workers.position_monitor_worker.monitor_positions")
    def test_continues_on_dispatch_failure(
        self, mock_monitor, mock_get_users, mock_get_db
    ):
        """Should continue dispatching even if one user fails."""
        mock_get_users.return_value = [1, 2, 3]
        mock_get_db.return_value = MagicMock()

        # Second dispatch fails
        mock_monitor.delay.side_effect = [None, Exception("Queue full"), None]

        result = _execute_schedule_position_monitoring()

        assert result["status"] == "success"
        assert result["users_dispatched"] == 2


# --- Tests for _process_single_position ---


class TestProcessSinglePosition:
    """Tests for _process_single_position function."""

    def test_triggers_auto_exit_on_sl_hit(self, mock_redis_client, sample_position):
        """Should trigger auto-exit when SL is hit."""
        # Set current price below SL
        live_prices = {sample_position.symbol: 185.0}  # Below SL of 190

        mock_service = MagicMock()
        mock_service.update_trailing_stop.return_value = None
        mock_service.check_sl_target.return_value = "sl_hit"
        mock_service.trigger_auto_exit.return_value = {
            "position_id": 1,
            "symbol": sample_position.symbol,
            "exit_reason": "sl_hit",
            "entry_price": 200.0,
            "current_price": 185.0,
            "quantity": 50,
            "trade_id": 10,
        }

        mock_kite = MagicMock()

        result = _process_single_position(
            service=mock_service,
            kite_client=mock_kite,
            redis_client=mock_redis_client,
            user_id=1,
            position=sample_position,
            live_prices=live_prices,
        )

        assert result["auto_exit_triggered"] is True
        # Verify auto_exit event was published
        publish_calls = [
            c for c in mock_redis_client.client.publish.call_args_list
            if "auto_exit" in c[0][0]
        ]
        assert len(publish_calls) == 1

    def test_triggers_auto_exit_on_target_hit(self, mock_redis_client, sample_position):
        """Should trigger auto-exit when target is hit."""
        live_prices = {sample_position.symbol: 235.0}  # Above target of 230

        mock_service = MagicMock()
        mock_service.update_trailing_stop.return_value = None
        mock_service.check_sl_target.return_value = "target_hit"
        mock_service.trigger_auto_exit.return_value = {
            "position_id": 1,
            "symbol": sample_position.symbol,
            "exit_reason": "target_hit",
            "entry_price": 200.0,
            "current_price": 235.0,
            "quantity": 50,
            "trade_id": 10,
        }

        result = _process_single_position(
            service=mock_service,
            kite_client=MagicMock(),
            redis_client=mock_redis_client,
            user_id=1,
            position=sample_position,
            live_prices=live_prices,
        )

        assert result["auto_exit_triggered"] is True

    def test_publishes_position_update_every_cycle(
        self, mock_redis_client, sample_position
    ):
        """Should always publish position_monitor_update even without exit."""
        live_prices = {sample_position.symbol: 210.0}

        mock_service = MagicMock()
        mock_service.update_trailing_stop.return_value = None
        mock_service.check_sl_target.return_value = None  # No SL/Target hit

        # No exit conditions met
        mock_service.evaluate_exit_conditions.return_value = [
            ExitCondition(name="ema_cross", description="", is_met=False),
        ]

        # Mock market data fetch
        with patch(
            "src.workers.position_monitor_worker.fetch_market_data_for_position"
        ) as mock_fetch_md:
            mock_fetch_md.return_value = MarketData(
                current_price=210.0,
                ema20=215.0,
                vwap=212.0,
                candles=[],
                current_time=datetime.now(timezone.utc),
            )

            result = _process_single_position(
                service=mock_service,
                kite_client=MagicMock(),
                redis_client=mock_redis_client,
                user_id=1,
                position=sample_position,
                live_prices=live_prices,
            )

        assert result["auto_exit_triggered"] is False

        # Verify position:monitor publish happened
        monitor_calls = [
            c for c in mock_redis_client.client.publish.call_args_list
            if "position:monitor:" in c[0][0]
        ]
        assert len(monitor_calls) >= 1

    def test_updates_trailing_stop(self, mock_redis_client, sample_position):
        """Should update trailing stop when price moves favorably."""
        live_prices = {sample_position.symbol: 220.0}  # Price moved up

        mock_service = MagicMock()
        mock_service.update_trailing_stop.return_value = 214.5  # New trailing level
        mock_service.check_sl_target.return_value = None

        with patch(
            "src.workers.position_monitor_worker.fetch_market_data_for_position"
        ) as mock_fetch_md:
            mock_fetch_md.return_value = MarketData(
                current_price=220.0,
                ema20=215.0,
                vwap=218.0,
                candles=[],
                current_time=datetime.now(timezone.utc),
            )
            mock_service.evaluate_exit_conditions.return_value = []

            _process_single_position(
                service=mock_service,
                kite_client=MagicMock(),
                redis_client=mock_redis_client,
                user_id=1,
                position=sample_position,
                live_prices=live_prices,
            )

        # Trailing stop should have been called
        mock_service.update_trailing_stop.assert_called_once()
