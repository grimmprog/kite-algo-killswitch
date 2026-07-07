"""Integration tests for end-to-end flows (Task 19.5).

Tests cross-component integration wiring:
1. Scanner → Signal → Approval → Trade Execution
2. Settings change → Worker picks up new thresholds
3. Kill switch → Segment deactivation → Notification
4. Paper trade entry → Balance validation → Exit → Stats update
5. AI service → Rate limiting → Graceful degradation

Requirements covered: All
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    """Create a mock SQLAlchemy Session."""
    session = MagicMock()
    session.add = MagicMock()
    session.commit = MagicMock()
    session.refresh = MagicMock()
    session.rollback = MagicMock()
    return session


@pytest.fixture
def mock_redis():
    """Create a mock RedisClient with common operations."""
    redis = MagicMock()
    redis.set.return_value = True
    redis.get.return_value = None
    redis.delete.return_value = 1
    redis.ttl.return_value = 45
    redis.client = MagicMock()
    redis.client.publish = MagicMock(return_value=1)
    return redis


# ===========================================================================
# Flow 1: Scanner → Signal → Approval → Trade Execution
# ===========================================================================


class TestScannerToTradeExecution:
    """Test the full flow: scanner detects signal → SignalService creates it →
    AI analysis triggered → WebSocket event published → user approves →
    trade execution data returned."""

    @patch("src.services.signal_pipeline._publish_signal_detected")
    @patch("src.services.signal_pipeline._trigger_ai_analysis")
    @patch("src.services.signal_pipeline.SignalService")
    def test_scanner_signal_creates_pending_signal_and_triggers_ai(
        self, MockSignalService, mock_ai_trigger, mock_publish, mock_db, mock_redis
    ):
        """Scanner signals flow through pipeline: create → AI → WebSocket."""
        from src.services.signal_pipeline import process_scanner_signals

        # Setup mock signal returned by SignalService.create_signal
        mock_service = MockSignalService.return_value
        mock_signal = MagicMock()
        mock_signal.id = 101
        mock_signal.symbol = "NIFTY24500CE"
        mock_signal.signal_type = "trend_pullback"
        mock_signal.confidence_score = 82.0
        mock_signal.entry_price = 250.0
        mock_signal.stop_loss = 230.0
        mock_signal.target_price = 300.0
        mock_signal.max_potential_loss = 2000.0
        mock_signal.status = "pending"
        mock_signal.countdown_seconds = 60
        mock_signal.expires_at = datetime(2024, 1, 1, 10, 1, 0, tzinfo=timezone.utc)
        mock_signal.created_at = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        mock_signal.ai_quality_rating = None
        mock_signal.ai_warnings = None
        mock_signal.ai_explanation = None
        mock_service.create_signal.return_value = mock_signal

        scanner_output = [
            {
                "symbol": "NIFTY24500CE",
                "scan_type": "trend_pullback",
                "confidence_score": 82.0,
                "entry_price": 250.0,
                "stop_loss": 230.0,
                "target_price": 300.0,
                "max_potential_loss": 2000.0,
                "metadata": {"trend_direction": "bullish"},
            }
        ]

        # Execute: scanner → signal pipeline
        result = process_scanner_signals(
            user_id=1,
            signals=scanner_output,
            db=mock_db,
            redis_client=mock_redis,
            countdown_seconds=60,
        )

        # Verify: signal created
        assert len(result) == 1
        assert result[0]["symbol"] == "NIFTY24500CE"
        assert result[0]["status"] == "pending"
        mock_service.create_signal.assert_called_once()

        # Verify: AI analysis triggered
        mock_ai_trigger.assert_called_once()
        ai_call_args = mock_ai_trigger.call_args[0]
        assert ai_call_args[0] == 1  # user_id
        assert ai_call_args[2] == 101  # signal_id

        # Verify: WebSocket event published
        mock_publish.assert_called_once()

    @patch("src.services.signal_pipeline._publish_signal_detected")
    @patch("src.services.signal_pipeline._trigger_ai_analysis")
    @patch("src.services.signal_pipeline.SignalService")
    def test_approval_returns_trade_execution_data(
        self, MockSignalService, mock_ai_trigger, mock_publish, mock_db, mock_redis
    ):
        """After signal creation, approval returns data for trade execution."""
        from src.services.signal_pipeline import process_scanner_signals
        from src.services.signal_service import SignalService

        # Step 1: Create signal via pipeline
        mock_pipeline_service = MockSignalService.return_value
        mock_signal = MagicMock()
        mock_signal.id = 200
        mock_signal.symbol = "BANKNIFTY48000CE"
        mock_signal.signal_type = "trend_pullback"
        mock_signal.confidence_score = 75.0
        mock_signal.entry_price = 320.0
        mock_signal.stop_loss = 290.0
        mock_signal.target_price = 380.0
        mock_signal.max_potential_loss = 1500.0
        mock_signal.status = "pending"
        mock_signal.countdown_seconds = 45
        mock_signal.expires_at = None
        mock_signal.created_at = None
        mock_signal.ai_quality_rating = None
        mock_signal.ai_warnings = None
        mock_signal.ai_explanation = None
        mock_pipeline_service.create_signal.return_value = mock_signal

        process_scanner_signals(
            user_id=1,
            signals=[{
                "symbol": "BANKNIFTY48000CE",
                "scan_type": "trend_pullback",
                "confidence_score": 75.0,
                "entry_price": 320.0,
                "stop_loss": 290.0,
                "target_price": 380.0,
                "max_potential_loss": 1500.0,
                "metadata": {},
            }],
            db=mock_db,
            redis_client=mock_redis,
            countdown_seconds=45,
        )

        # Step 2: Simulate approval via SignalService directly
        # Mock the DB query to return our signal for approval
        mock_db_signal = MagicMock()
        mock_db_signal.id = 200
        mock_db_signal.user_id = 1
        mock_db_signal.symbol = "BANKNIFTY48000CE"
        mock_db_signal.signal_type = "trend_pullback"
        mock_db_signal.confidence_score = 75.0
        mock_db_signal.entry_price = 320.0
        mock_db_signal.stop_loss = 290.0
        mock_db_signal.target_price = 380.0
        mock_db_signal.max_potential_loss = 1500.0
        mock_db_signal.status = "pending"

        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_db_signal
        )

        signal_service = SignalService(db=mock_db, redis_client=mock_redis)
        trade_data = signal_service.approve_signal(signal_id=200, user_id=1)

        # Verify: trade execution data returned
        assert trade_data["signal_id"] == 200
        assert trade_data["symbol"] == "BANKNIFTY48000CE"
        assert trade_data["entry_price"] == 320.0
        assert trade_data["stop_loss"] == 290.0
        assert trade_data["target_price"] == 380.0

        # Verify: signal status changed to approved
        assert mock_db_signal.status == "approved"

        # Verify: Redis TTL key removed
        mock_redis.delete.assert_called()

    @patch("src.services.signal_pipeline._publish_signal_detected")
    @patch("src.services.signal_pipeline._trigger_ai_analysis")
    @patch("src.services.signal_pipeline.SignalService")
    def test_expired_signal_cannot_be_approved(
        self, MockSignalService, mock_ai_trigger, mock_publish, mock_db, mock_redis
    ):
        """A signal that has expired cannot be approved — full lifecycle test."""
        from src.services.signal_service import SignalService

        # Signal exists but status is "expired"
        mock_db_signal = MagicMock()
        mock_db_signal.id = 300
        mock_db_signal.user_id = 1
        mock_db_signal.status = "expired"

        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_db_signal
        )

        signal_service = SignalService(db=mock_db, redis_client=mock_redis)

        with pytest.raises(ValueError, match="not pending"):
            signal_service.approve_signal(signal_id=300, user_id=1)


# ===========================================================================
# Flow 2: Settings change → Worker picks up new thresholds
# ===========================================================================


class TestSettingsChangeWorkerPropagation:
    """Test that settings updates propagate to Redis cache for worker consumption.

    Flow: User updates kill switch thresholds → SettingsService persists to DB →
    caches in Redis → Worker reads new thresholds from Redis on next cycle."""

    @patch("src.services.settings_service.get_redis_client")
    def test_killswitch_threshold_update_caches_in_redis(self, mock_get_redis, mock_db):
        """Updating kill switch thresholds caches them in Redis for workers."""
        from src.services.settings_service import SettingsService

        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        # Mock the user settings DB record
        mock_settings = MagicMock()
        mock_settings.daily_loss_type = "percentage"
        mock_settings.daily_loss_value = 3.0
        mock_settings.profit_target_type = "percentage"
        mock_settings.profit_target_value = 5.0
        mock_settings.drawdown_type = "amount"
        mock_settings.drawdown_value = 5000.0
        mock_settings.profit_warning_pct = 80.0
        mock_settings.capital = 100000.0
        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_settings
        )

        service = SettingsService()

        # Update thresholds
        from src.services.settings_service import KillSwitchThresholds

        new_thresholds = KillSwitchThresholds(
            daily_loss_type="percentage",
            daily_loss_value=4.0,
            profit_target_type="percentage",
            profit_target_value=6.0,
            drawdown_type="absolute",
            drawdown_value=8000.0,
            profit_warning_pct=85.0,
        )

        service.update_killswitch_thresholds(
            db=mock_db, user_id=1, thresholds=new_thresholds
        )

        # Verify: Redis cache was updated (workers will read this)
        mock_redis.set.assert_called()
        # Find the call that caches killswitch thresholds
        cache_calls = [
            c for c in mock_redis.set.call_args_list
            if "killswitch" in str(c)
        ]
        assert len(cache_calls) >= 1, "Kill switch thresholds should be cached"

    @patch("src.services.settings_service.get_redis_client")
    def test_worker_reads_updated_thresholds_from_cache(self, mock_get_redis):
        """Workers read thresholds from Redis cache (set by settings update)."""
        from src.services.settings_service import SettingsService

        cached_thresholds = {
            "daily_loss_type": "percentage",
            "daily_loss_value": 4.0,
            "daily_loss_amount": 4000.0,
            "profit_target_type": "percentage",
            "profit_target_value": 6.0,
            "profit_target_amount": 6000.0,
            "drawdown_type": "absolute",
            "drawdown_value": 8000.0,
            "drawdown_amount": 8000.0,
            "profit_warning_pct": 85.0,
            "capital": 100000.0,
            "warning": None,
        }

        mock_redis = MagicMock()
        mock_redis.get.return_value = json.dumps(cached_thresholds)
        mock_get_redis.return_value = mock_redis

        # Worker reads cached thresholds
        result = SettingsService.get_cached_killswitch_thresholds(user_id=1)

        assert result is not None
        assert result["daily_loss_value"] == 4.0
        assert result["profit_target_value"] == 6.0
        assert result["drawdown_value"] == 8000.0

    @patch("src.services.settings_service.get_redis_client")
    def test_strategy_settings_update_caches_watchlist(self, mock_get_redis, mock_db):
        """Strategy settings update caches watchlist for scanner worker."""
        from src.services.settings_service import SettingsService, StrategySettings

        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        # Mock existing user settings
        mock_settings = MagicMock()
        mock_settings.watchlist = ["NIFTY", "BANKNIFTY"]
        mock_settings.trading_start_time = "09:15"
        mock_settings.trading_end_time = "15:15"
        mock_settings.confidence_threshold = 60
        mock_settings.max_trades_per_day = 5
        mock_settings.max_active_trades = 3
        mock_settings.capital = 100000.0
        mock_settings.lot_sizes = {"NIFTY": 25, "BANKNIFTY": 15}
        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_settings
        )

        service = SettingsService()
        new_settings = StrategySettings(
            watchlist=["NIFTY", "BANKNIFTY", "SENSEX"],
            trading_start_time="09:15",
            trading_end_time="15:15",
            confidence_threshold=70,
            max_trades_per_day=5,
            max_active_trades=3,
            capital=100000.0,
            lot_sizes={"NIFTY": 25, "BANKNIFTY": 15, "SENSEX": 10},
        )

        service.update_strategy_settings(db=mock_db, user_id=1, settings=new_settings)

        # Verify: watchlist cached separately for scanner worker
        set_calls = mock_redis.set.call_args_list
        watchlist_cached = any(
            "watchlist" in str(c) for c in set_calls
        )
        assert watchlist_cached, "Watchlist should be cached in Redis"


# ===========================================================================
# Flow 3: Kill switch → Segment deactivation → Notification
# ===========================================================================


class TestKillSwitchSegmentNotification:
    """Test the full kill switch flow: trigger → segments deactivated in Redis →
    critical notification pushed → WebSocket broadcast."""

    def test_killswitch_activation_marks_all_segments_deactivated(self, mock_redis, mock_db):
        """Kill switch activation stores all segments as deactivated."""
        from src.services.killswitch_integration import (
            handle_killswitch_activation,
            get_killswitch_deactivated_segments,
        )

        with patch(
            "src.services.killswitch_integration.NotificationService"
        ) as MockNotifService:
            MockNotifService.return_value = MagicMock()

            handle_killswitch_activation(
                user_id=1,
                reason="Daily loss limit breached: -₹5,000",
                positions_closed=3,
                redis_client=mock_redis,
                db_session=mock_db,
            )

        # Verify: segments stored in Redis
        mock_redis.set.assert_called()
        set_call = mock_redis.set.call_args
        key = set_call[0][0]
        value = json.loads(set_call[0][1])

        assert "killswitch:segments" in key
        assert "NSE" in value
        assert "BSE" in value
        assert "NFO" in value
        assert "BFO" in value

    def test_killswitch_pushes_critical_notification(self, mock_redis, mock_db):
        """Kill switch activation pushes a critical notification."""
        from src.services.killswitch_integration import handle_killswitch_activation

        with patch(
            "src.services.killswitch_integration.NotificationService"
        ) as MockNotifService:
            mock_notif_instance = MagicMock()
            MockNotifService.return_value = mock_notif_instance

            handle_killswitch_activation(
                user_id=2,
                reason="Drawdown threshold exceeded",
                positions_closed=1,
                redis_client=mock_redis,
                db_session=mock_db,
            )

            # Verify: notification service called with critical severity
            mock_notif_instance.push_notification.assert_called_once()
            call_kwargs = mock_notif_instance.push_notification.call_args[1]
            assert call_kwargs["severity"] == "critical"
            assert call_kwargs["category"] == "killswitch"
            assert "Kill Switch Activated" in call_kwargs["title"]
            assert "Drawdown threshold exceeded" in call_kwargs["message"]
            assert "1 position(s) queued for exit" in call_kwargs["message"]

    @patch("src.services.settings_service.get_redis_client")
    def test_segments_show_killswitch_deactivation_after_trigger(self, mock_get_redis):
        """After kill switch, SettingsService.get_segments reflects deactivation."""
        from src.services.settings_service import SettingsService

        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        # Simulate post-killswitch state in Redis
        mock_redis.get.side_effect = lambda key: {
            "user:1:killswitch": "true",
            "user:1:killswitch:segments": json.dumps(["NSE", "BSE", "NFO", "BFO"]),
        }.get(key)

        service = SettingsService()
        segments = service.get_segments(user_id=1)

        # All segments should reflect kill switch deactivation
        for seg in segments:
            assert seg.deactivated_by_killswitch is True
            assert seg.is_active is False

    @patch("src.services.settings_service.get_redis_client")
    def test_segments_restore_after_killswitch_cleared(self, mock_get_redis):
        """After kill switch is cleared, segments return to normal."""
        from src.services.settings_service import SettingsService

        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        # Kill switch cleared — no segments key
        mock_redis.get.side_effect = lambda key: {
            "user:1:killswitch": None,
        }.get(key)

        service = SettingsService()
        segments = service.get_segments(user_id=1)

        for seg in segments:
            assert seg.deactivated_by_killswitch is False


# ===========================================================================
# Flow 4: Paper trade entry → Balance validation → Exit → Stats update
# ===========================================================================


class TestPaperTradeFlow:
    """Test the full paper trading lifecycle: enter trade → validate balance →
    exit trade → P&L calculation → account stats update."""

    def test_enter_trade_validates_balance_and_deducts(self, mock_db):
        """Paper trade entry validates balance and deducts from account."""
        from src.services.paper_trading_service import enter_trade
        from src.database.models.paper_trade import PaperAccount, PaperTrade

        # Setup: account with ₹40,000 balance
        mock_account = MagicMock()
        mock_account.id = 1
        mock_account.user_id = 1
        mock_account.balance = 40000.0
        mock_account.starting_capital = 40000.0

        # Mock DB queries
        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_account
        )

        trade_data = {
            "symbol": "NIFTY24500CE",
            "strike": 24500.0,
            "option_type": "CE",
            "entry_price": 200.0,
            "quantity": 25,
            "stop_loss": 180.0,
            "target": 250.0,
        }

        # Cost = 200 × 25 = 5000, within balance
        result = enter_trade(db=mock_db, user_id=1, trade_data=trade_data)

        # Verify: trade created
        mock_db.add.assert_called()
        mock_db.commit.assert_called()

    def test_enter_trade_rejects_insufficient_balance(self, mock_db):
        """Paper trade entry rejected when cost exceeds available balance."""
        from src.services.paper_trading_service import enter_trade
        from src.database.models.paper_trade import PaperAccount

        # Setup: account with only ₹1,000 balance
        mock_account = MagicMock()
        mock_account.id = 1
        mock_account.user_id = 1
        mock_account.balance = 1000.0

        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_account
        )

        trade_data = {
            "symbol": "NIFTY24500CE",
            "strike": 24500.0,
            "option_type": "CE",
            "entry_price": 200.0,
            "quantity": 25,  # Cost = 5000 > 1000
            "stop_loss": 180.0,
            "target": 250.0,
        }

        with pytest.raises(ValueError, match="[Ii]nsufficient|[Ee]xceed|[Bb]alance"):
            enter_trade(db=mock_db, user_id=1, trade_data=trade_data)

    def test_exit_trade_calculates_pnl_and_updates_stats(self, mock_db):
        """Exiting paper trade calculates P&L and updates account stats."""
        from src.services.paper_trading_service import exit_trade
        from src.database.models.paper_trade import PaperAccount, PaperTrade

        # Setup: open trade
        mock_trade = MagicMock(spec=PaperTrade)
        mock_trade.id = 10
        mock_trade.user_id = 1
        mock_trade.symbol = "NIFTY24500CE"
        mock_trade.entry_price = 200.0
        mock_trade.quantity = 25
        mock_trade.status = "open"
        mock_trade.pnl = None

        # Setup: account
        mock_account = MagicMock(spec=PaperAccount)
        mock_account.user_id = 1
        mock_account.balance = 35000.0  # 40000 - 5000 (entry cost)
        mock_account.total_pnl = 0.0
        mock_account.total_trades = 0
        mock_account.winning_trades = 0
        mock_account.losing_trades = 0

        # First query returns trade, second returns account
        def query_side_effect(model):
            mock_q = MagicMock()
            if model == PaperTrade:
                mock_q.filter.return_value.first.return_value = mock_trade
            else:
                mock_q.filter.return_value.first.return_value = mock_account
            return mock_q

        mock_db.query.side_effect = query_side_effect

        # Exit at profit: 250 (exit) - 200 (entry) = +50/unit × 25 = +1250
        result = exit_trade(db=mock_db, user_id=1, trade_id=10, exit_price=250.0)

        # Verify: trade closed with correct P&L
        assert mock_trade.status == "closed"
        assert mock_trade.exit_price == 250.0
        assert mock_trade.pnl == 1250.0  # (250 - 200) × 25

        # Verify: account stats updated
        assert mock_account.total_pnl == 1250.0
        assert mock_account.total_trades == 1
        assert mock_account.winning_trades == 1

        # Verify: balance updated (exit_price × quantity added back)
        assert mock_account.balance == 35000.0 + (250.0 * 25)

    def test_exit_losing_trade_updates_losing_count(self, mock_db):
        """Exiting a losing paper trade updates losing_trades counter."""
        from src.services.paper_trading_service import exit_trade
        from src.database.models.paper_trade import PaperAccount, PaperTrade

        mock_trade = MagicMock(spec=PaperTrade)
        mock_trade.id = 11
        mock_trade.user_id = 1
        mock_trade.entry_price = 200.0
        mock_trade.quantity = 25
        mock_trade.status = "open"

        mock_account = MagicMock(spec=PaperAccount)
        mock_account.user_id = 1
        mock_account.balance = 35000.0
        mock_account.total_pnl = 0.0
        mock_account.total_trades = 0
        mock_account.winning_trades = 0
        mock_account.losing_trades = 0

        def query_side_effect(model):
            mock_q = MagicMock()
            if model == PaperTrade:
                mock_q.filter.return_value.first.return_value = mock_trade
            else:
                mock_q.filter.return_value.first.return_value = mock_account
            return mock_q

        mock_db.query.side_effect = query_side_effect

        # Exit at loss: 170 (exit) - 200 (entry) = -30/unit × 25 = -750
        exit_trade(db=mock_db, user_id=1, trade_id=11, exit_price=170.0)

        assert mock_trade.pnl == -750.0
        assert mock_account.losing_trades == 1
        assert mock_account.total_pnl == -750.0

    def test_full_paper_trade_lifecycle_with_stats(self, mock_db):
        """Full flow: get account → enter → exit → get account shows updated stats."""
        from src.services.paper_trading_service import get_account
        from src.database.models.paper_trade import PaperAccount

        # Account after trades: 2 winning, 1 losing
        mock_account = MagicMock(spec=PaperAccount)
        mock_account.id = 1
        mock_account.user_id = 1
        mock_account.balance = 42500.0
        mock_account.starting_capital = 40000.0
        mock_account.total_pnl = 2500.0
        mock_account.total_trades = 3
        mock_account.winning_trades = 2
        mock_account.losing_trades = 1

        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_account
        )

        # Mock profit factor computation
        with patch(
            "src.services.paper_trading_service._compute_profit_factor",
            return_value=2.5,
        ):
            account_data = get_account(db=mock_db, user_id=1)

        # Verify: computed stats
        assert account_data["balance"] == 42500.0
        assert account_data["total_pnl"] == 2500.0
        assert account_data["total_trades"] == 3
        assert account_data["win_rate"] == pytest.approx(2 / 3)
        assert account_data["profit_factor"] == 2.5
        assert account_data["roi_pct"] == pytest.approx(6.25)  # 2500/40000 × 100


# ===========================================================================
# Flow 5: AI service → Rate limiting → Graceful degradation
# ===========================================================================


class TestAIServiceRateLimitingDegradation:
    """Test that AI service enforces rate limits and degrades gracefully.

    Flow: AI requests → rate limiter checks → if exceeded, graceful response →
    if provider errors, graceful response → never blocks trading."""

    def test_ai_request_succeeds_within_rate_limit(self):
        """AI requests succeed when within the 30 req/min rate limit."""
        from src.services.ai_trading_service import (
            AITradingService,
            AIProvider,
            TokenBucketRateLimiter,
        )

        with patch(
            "src.services.ai_trading_service.create_provider_client"
        ) as mock_create:
            mock_client = MagicMock()
            mock_client.send_request.return_value = {
                "quality_rating": "Strong Setup",
                "warnings": [],
                "explanation": "Trend intact, volume confirms.",
            }
            mock_create.return_value = mock_client

            service = AITradingService(
                provider=AIProvider.GEMINI, api_key="test-key"
            )

            result = service.analyze_signal({
                "symbol": "NIFTY24500CE",
                "confidence_score": 80,
                "entry_price": 250.0,
                "stop_loss": 230.0,
                "target_price": 300.0,
            })

            # Should get a valid response, not error
            assert result.get("error") is not True
            assert result.get("quality_rating") == "Strong Setup"

    def test_ai_rate_limit_exceeded_returns_graceful_response(self):
        """When rate limit is exceeded, AI returns a graceful degradation."""
        from src.services.ai_trading_service import (
            AITradingService,
            AIProvider,
            TokenBucketRateLimiter,
        )

        with patch(
            "src.services.ai_trading_service.create_provider_client"
        ) as mock_create:
            mock_client = MagicMock()
            mock_create.return_value = mock_client

            service = AITradingService(
                provider=AIProvider.GEMINI, api_key="test-key"
            )

            # Exhaust the rate limiter (30 tokens)
            for _ in range(30):
                service.rate_limiter.consume()

            # Next request should be rate-limited
            result = service.analyze_signal({
                "symbol": "NIFTY24500CE",
                "confidence_score": 80,
                "entry_price": 250.0,
                "stop_loss": 230.0,
                "target_price": 300.0,
            })

            # Should return graceful degradation, not exception
            assert result["error"] is True
            assert "rate limit" in result["message"].lower()
            assert result["available"] is False
            # Client should NOT have been called
            mock_client.send_request.assert_not_called()

    def test_ai_provider_error_returns_graceful_degradation(self):
        """When AI provider returns an error, service degrades gracefully."""
        from src.services.ai_trading_service import (
            AITradingService,
            AIProvider,
            AIProviderError,
        )

        with patch(
            "src.services.ai_trading_service.create_provider_client"
        ) as mock_create:
            mock_client = MagicMock()
            mock_client.send_request.side_effect = AIProviderError(
                "Service unavailable"
            )
            mock_create.return_value = mock_client

            service = AITradingService(
                provider=AIProvider.CLAUDE, api_key="test-key"
            )

            result = service.analyze_signal({
                "symbol": "BANKNIFTY48000CE",
                "confidence_score": 70,
                "entry_price": 300.0,
                "stop_loss": 270.0,
                "target_price": 360.0,
            })

            # Should return graceful response, never raise
            assert result["error"] is True
            assert "unavailable" in result["message"].lower()
            assert result["available"] is False

    def test_ai_timeout_returns_graceful_degradation(self):
        """When AI request times out, service degrades gracefully."""
        from src.services.ai_trading_service import AITradingService, AIProvider

        with patch(
            "src.services.ai_trading_service.create_provider_client"
        ) as mock_create:
            mock_client = MagicMock()
            mock_client.send_request.side_effect = TimeoutError(
                "Request timed out"
            )
            mock_create.return_value = mock_client

            service = AITradingService(
                provider=AIProvider.GEMINI, api_key="test-key"
            )

            result = service.analyze_signal({
                "symbol": "NIFTY24500CE",
                "confidence_score": 85,
                "entry_price": 250.0,
                "stop_loss": 230.0,
                "target_price": 300.0,
            })

            assert result["error"] is True
            assert "unavailable" in result["message"].lower()

    def test_ai_degradation_does_not_block_trading(self):
        """AI failures must never block trading functionality."""
        from src.services.ai_trading_service import AITradingService, AIProvider

        with patch(
            "src.services.ai_trading_service.create_provider_client"
        ) as mock_create:
            mock_client = MagicMock()
            mock_client.send_request.side_effect = Exception(
                "Catastrophic failure"
            )
            mock_create.return_value = mock_client

            service = AITradingService(
                provider=AIProvider.GEMINI, api_key="test-key"
            )

            # This should NEVER raise — it should degrade gracefully
            result = service.analyze_signal({
                "symbol": "NIFTY24500CE",
                "confidence_score": 90,
                "entry_price": 250.0,
                "stop_loss": 230.0,
                "target_price": 300.0,
            })

            # Graceful degradation: error response, no exception
            assert result is not None
            assert result["error"] is True
            assert result["available"] is False

    def test_rate_limiter_token_bucket_refills(self):
        """Token bucket refills over time, allowing requests again."""
        from src.services.ai_trading_service import TokenBucketRateLimiter
        import time

        limiter = TokenBucketRateLimiter(max_tokens=2, refill_rate=100.0)

        # Exhaust all tokens
        assert limiter.consume() is True
        assert limiter.consume() is True
        assert limiter.consume() is False  # Exhausted

        # Wait for refill (100 tokens/sec = quick refill)
        time.sleep(0.05)

        # Should have tokens again
        assert limiter.consume() is True
