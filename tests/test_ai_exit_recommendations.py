"""Unit tests for AI Exit Recommendations — Task 7.7.

Tests the enhanced evaluate_exit method with local detection logic for:
- Momentum divergences
- Volume drying up
- Approaching key S/R levels
- Theta decay acceleration
- Broader market trend reversals

Also tests the 30-second evaluation cycle scheduling task.

Requirements covered: 21.1, 21.2, 21.3, 21.6
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.services.ai_trading_service import (
    AIProvider,
    AITradingService,
    EXIT_EVALUATION_INTERVAL,
    VALID_EXIT_ACTIONS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service():
    """Create an AITradingService instance for testing."""
    return AITradingService(provider=AIProvider.GEMINI, api_key="test-key")


@pytest.fixture
def base_position():
    """Base position data for CE option."""
    return {
        "entry_price": 100.0,
        "current_price": 110.0,
        "stop_loss": 95.0,
        "target": 120.0,
        "unrealized_pnl": 500.0,
        "time_held_minutes": 30,
        "symbol": "NIFTY",
        "quantity": 50,
        "option_type": "CE",
    }


@pytest.fixture
def base_market_data():
    """Base market data with all expected fields."""
    return {
        "macd": {"signal": 1.5, "histogram": 2.0, "prev_histogram": 2.5},
        "momentum": 5.0,
        "volume": 10000,
        "volume_avg": 12000,
        "trend": "bullish",
        "key_levels": {"support": [95.0, 90.0], "resistance": [115.0, 120.0]},
        "ema_20": 108.0,
        "vwap": 107.5,
        "days_to_expiry": 5,
    }


# ---------------------------------------------------------------------------
# Tests for EXIT_EVALUATION_INTERVAL constant
# ---------------------------------------------------------------------------


class TestExitEvaluationInterval:
    """Verify the 30-second evaluation cycle constant (Requirement 21.1)."""

    def test_interval_is_30_seconds(self):
        """EXIT_EVALUATION_INTERVAL must be 30 seconds per Requirement 21.1."""
        assert EXIT_EVALUATION_INTERVAL == 30


# ---------------------------------------------------------------------------
# Tests for _detect_exit_warnings
# ---------------------------------------------------------------------------


class TestDetectExitWarnings:
    """Tests for the local warning detection logic (Requirement 21.3)."""

    def test_momentum_divergence_ce_position(self, service):
        """Detects momentum divergence for CE position — price up but MACD declining."""
        position = {
            "entry_price": 100.0,
            "current_price": 110.0,
            "option_type": "CE",
        }
        market_data = {
            "macd": {"histogram": 1.0, "prev_histogram": 3.0},
        }
        warnings = service._detect_exit_warnings(position, market_data)
        assert any("Momentum divergence" in w for w in warnings)

    def test_no_momentum_divergence_when_macd_rising(self, service):
        """No divergence when both price and MACD are rising for CE."""
        position = {
            "entry_price": 100.0,
            "current_price": 110.0,
            "option_type": "CE",
        }
        market_data = {
            "macd": {"histogram": 3.0, "prev_histogram": 1.0},
        }
        warnings = service._detect_exit_warnings(position, market_data)
        assert not any("Momentum divergence" in w for w in warnings)

    def test_momentum_divergence_pe_position(self, service):
        """Detects momentum divergence for PE position — histogram rising."""
        position = {
            "entry_price": 100.0,
            "current_price": 110.0,
            "option_type": "PE",
        }
        market_data = {
            "macd": {"histogram": -0.5, "prev_histogram": -2.0},
        }
        warnings = service._detect_exit_warnings(position, market_data)
        assert any("Momentum divergence" in w for w in warnings)

    def test_volume_drying_up(self, service):
        """Detects volume below 50% of average."""
        position = {"entry_price": 100.0, "current_price": 105.0, "option_type": "CE"}
        market_data = {
            "volume": 400,
            "volume_avg": 1000,
        }
        warnings = service._detect_exit_warnings(position, market_data)
        assert any("Volume drying up" in w for w in warnings)

    def test_no_volume_warning_above_threshold(self, service):
        """No volume warning when volume is above 50% of average."""
        position = {"entry_price": 100.0, "current_price": 105.0, "option_type": "CE"}
        market_data = {
            "volume": 600,
            "volume_avg": 1000,
        }
        warnings = service._detect_exit_warnings(position, market_data)
        assert not any("Volume drying up" in w for w in warnings)

    def test_approaching_resistance_ce(self, service):
        """Detects approaching resistance for CE position (within 1%)."""
        position = {
            "entry_price": 100.0,
            "current_price": 119.5,
            "option_type": "CE",
        }
        market_data = {
            "key_levels": {"resistance": [120.0], "support": [100.0]},
        }
        warnings = service._detect_exit_warnings(position, market_data)
        assert any("resistance" in w.lower() for w in warnings)

    def test_approaching_support_pe(self, service):
        """Detects approaching support for PE position (within 1%)."""
        position = {
            "entry_price": 100.0,
            "current_price": 90.5,
            "option_type": "PE",
        }
        market_data = {
            "key_levels": {"resistance": [100.0], "support": [90.0]},
        }
        warnings = service._detect_exit_warnings(position, market_data)
        assert any("support" in w.lower() for w in warnings)

    def test_theta_decay_expiry_day(self, service):
        """Detects theta decay acceleration on expiry day."""
        position = {
            "entry_price": 100.0,
            "current_price": 105.0,
            "option_type": "CE",
            "time_held_minutes": 60,
        }
        market_data = {"days_to_expiry": 0}
        warnings = service._detect_exit_warnings(position, market_data)
        assert any("Theta decay" in w for w in warnings)

    def test_theta_decay_near_expiry(self, service):
        """Detects theta decay concern when near expiry with extended hold."""
        position = {
            "entry_price": 100.0,
            "current_price": 105.0,
            "option_type": "CE",
            "time_held_minutes": 150,
        }
        market_data = {"days_to_expiry": 2}
        warnings = service._detect_exit_warnings(position, market_data)
        assert any("Theta decay" in w for w in warnings)

    def test_no_theta_warning_far_from_expiry(self, service):
        """No theta warning when far from expiry."""
        position = {
            "entry_price": 100.0,
            "current_price": 105.0,
            "option_type": "CE",
            "time_held_minutes": 30,
        }
        market_data = {"days_to_expiry": 10}
        warnings = service._detect_exit_warnings(position, market_data)
        assert not any("Theta decay" in w for w in warnings)

    def test_broader_market_reversal_ce_bearish(self, service):
        """Detects market reversal for CE position when market turns bearish."""
        position = {
            "entry_price": 100.0,
            "current_price": 105.0,
            "option_type": "CE",
        }
        market_data = {"trend": "bearish"}
        warnings = service._detect_exit_warnings(position, market_data)
        assert any("market trend reversal" in w.lower() for w in warnings)

    def test_broader_market_reversal_pe_bullish(self, service):
        """Detects market reversal for PE position when market turns bullish."""
        position = {
            "entry_price": 100.0,
            "current_price": 105.0,
            "option_type": "PE",
        }
        market_data = {"trend": "bullish"}
        warnings = service._detect_exit_warnings(position, market_data)
        assert any("market trend reversal" in w.lower() for w in warnings)

    def test_no_warnings_when_conditions_normal(self, service, base_position, base_market_data):
        """No warnings when all conditions are normal."""
        # Reset to normal conditions
        base_market_data["macd"] = {"histogram": 3.0, "prev_histogram": 2.0}
        base_market_data["volume"] = 15000
        base_market_data["volume_avg"] = 12000
        base_market_data["trend"] = "bullish"
        base_market_data["days_to_expiry"] = 10
        base_market_data["key_levels"] = {"resistance": [200.0], "support": [50.0]}
        base_position["current_price"] = 110.0
        warnings = service._detect_exit_warnings(base_position, base_market_data)
        assert len(warnings) == 0


# ---------------------------------------------------------------------------
# Tests for local fallback recommendation
# ---------------------------------------------------------------------------


class TestLocalExitFallback:
    """Tests for _compute_local_exit_recommendation fallback."""

    def test_hold_when_no_warnings(self, service, base_position, base_market_data):
        """Recommends hold when no warnings are detected."""
        result = service._compute_local_exit_recommendation(
            base_position, base_market_data, warnings=[]
        )
        assert result["action"] == "hold"
        assert result["confidence"] == 60

    def test_exit_now_with_many_warnings(self, service, base_position, base_market_data):
        """Recommends exit_now when 3+ warnings are present."""
        warnings = [
            "Momentum divergence detected",
            "Volume drying up",
            "Broader market trend reversal",
        ]
        result = service._compute_local_exit_recommendation(
            base_position, base_market_data, warnings
        )
        assert result["action"] == "exit_now"
        assert result["confidence"] > 80

    def test_book_partial_in_profit_with_two_warnings(self, service):
        """Recommends book_partial when in profit with critical condition."""
        position = {
            "entry_price": 100.0,
            "current_price": 115.0,
            "option_type": "CE",
            "unrealized_pnl": 750.0,
        }
        # Single critical warning → book_partial because in profit
        warnings = [
            "Broader market trend reversal — market turning bearish against CE position",
        ]
        result = service._compute_local_exit_recommendation(position, {}, warnings)
        assert result["action"] == "book_partial"
        assert result["confidence"] >= 65

    def test_book_partial_in_profit_two_noncritical_warnings(self, service):
        """Recommends book_partial when in profit with two non-critical warnings."""
        position = {
            "entry_price": 100.0,
            "current_price": 115.0,
            "option_type": "CE",
            "unrealized_pnl": 750.0,
        }
        # Two non-critical warnings → book_partial since in profit
        warnings = [
            "Volume drying up — current volume below 50% of average",
            "Momentum divergence — price rising but MACD declining",
        ]
        result = service._compute_local_exit_recommendation(position, {}, warnings)
        assert result["action"] == "book_partial"
        assert result["confidence"] >= 65

    def test_tighten_stop_single_warning(self, service, base_position, base_market_data):
        """Recommends tighten_stop for a single warning."""
        warnings = ["Volume drying up"]
        result = service._compute_local_exit_recommendation(
            base_position, base_market_data, warnings
        )
        assert result["action"] == "tighten_stop"


# ---------------------------------------------------------------------------
# Tests for enhanced evaluate_exit
# ---------------------------------------------------------------------------


class TestEvaluateExit:
    """Tests for the enhanced evaluate_exit method."""

    def test_returns_llm_response_with_merged_warnings(self, service, base_position, base_market_data):
        """evaluate_exit merges local warnings into LLM response."""
        # Make market_data trigger a local warning (bearish trend for CE)
        base_market_data["trend"] = "bearish"

        mock_response = {
            "action": "tighten_stop",
            "reasoning": "Market showing signs of weakness.",
            "confidence": 70.0,
            "warnings": ["MACD crossover imminent"],
        }

        with patch.object(service, "_make_request", return_value=mock_response):
            result = service.evaluate_exit(base_position, base_market_data)

        assert result["action"] == "tighten_stop"
        assert result["confidence"] == 70.0
        # Should have both LLM warning and local warning
        assert len(result["warnings"]) >= 2
        assert any("MACD crossover" in w for w in result["warnings"])
        assert any("market trend reversal" in w.lower() for w in result["warnings"])

    def test_uses_local_fallback_on_llm_error(self, service, base_position, base_market_data):
        """evaluate_exit falls back to local recommendation when LLM fails."""
        # Set up conditions that trigger a local warning
        base_market_data["trend"] = "bearish"

        error_response = {
            "error": True,
            "message": "AI analysis unavailable",
            "available": False,
        }

        with patch.object(service, "_make_request", return_value=error_response):
            result = service.evaluate_exit(base_position, base_market_data)

        # Should get a valid recommendation from local fallback
        assert result["action"] in VALID_EXIT_ACTIONS
        assert "reasoning" in result
        assert "confidence" in result
        assert "warnings" in result
        # Should have detected the trend reversal warning
        assert any("market trend reversal" in w.lower() for w in result["warnings"])

    def test_validates_action_from_llm(self, service, base_position, base_market_data):
        """evaluate_exit defaults invalid action to 'hold'."""
        mock_response = {
            "action": "invalid_action",
            "reasoning": "Some reasoning",
            "confidence": 50.0,
            "warnings": [],
        }

        with patch.object(service, "_make_request", return_value=mock_response):
            result = service.evaluate_exit(base_position, base_market_data)

        assert result["action"] == "hold"

    def test_clamps_confidence_to_valid_range(self, service, base_position, base_market_data):
        """evaluate_exit clamps confidence to 0-100."""
        mock_response = {
            "action": "hold",
            "reasoning": "All good",
            "confidence": 150.0,  # Invalid, should be clamped
            "warnings": [],
        }

        with patch.object(service, "_make_request", return_value=mock_response):
            result = service.evaluate_exit(base_position, base_market_data)

        assert result["confidence"] == 100.0

    def test_never_places_orders(self, service, base_position, base_market_data):
        """evaluate_exit never contains execution-related fields (Requirement 21.6)."""
        mock_response = {
            "action": "exit_now",
            "reasoning": "Critical exit signal!",
            "confidence": 95.0,
            "warnings": ["Multiple concerns"],
        }

        with patch.object(service, "_make_request", return_value=mock_response):
            result = service.evaluate_exit(base_position, base_market_data)

        # No execution fields
        execution_fields = {
            "order_id", "execution_id", "executed", "filled",
            "order_placed", "trade_executed",
        }
        for field in execution_fields:
            assert field not in result

    def test_high_confidence_exit_now(self, service, base_position, base_market_data):
        """High-confidence exit_now recommendation sets confidence > 80."""
        # Trigger multiple warnings for high-confidence exit
        base_market_data["trend"] = "bearish"
        base_market_data["volume"] = 100
        base_market_data["volume_avg"] = 1000
        base_market_data["days_to_expiry"] = 0

        error_response = {
            "error": True,
            "message": "AI unavailable",
            "available": False,
        }

        with patch.object(service, "_make_request", return_value=error_response):
            result = service.evaluate_exit(base_position, base_market_data)

        # Multiple warnings should yield exit_now with high confidence
        assert result["action"] == "exit_now"
        assert result["confidence"] > 80


# ---------------------------------------------------------------------------
# Tests for schedule_exit_evaluations task
# ---------------------------------------------------------------------------


class TestScheduleExitEvaluations:
    """Tests for the 30-second periodic exit evaluation scheduler."""

    @patch("src.workers.ai_worker.get_redis_client")
    @patch("src.workers.ai_worker.evaluate_exit_ai")
    def test_dispatches_evaluations_for_active_positions(
        self, mock_eval_task, mock_redis
    ):
        """Schedules evaluate_exit_ai for each active position."""
        from src.workers.ai_worker import schedule_exit_evaluations

        mock_client = MagicMock()
        mock_redis.return_value.client = mock_client

        # Set up Redis keys for positions (format: position_monitor:{user_id}:{position_id})
        mock_client.keys.return_value = [
            b"position_monitor:1:101",
            b"position_monitor:1:102",
        ]

        def get_side_effect(key):
            key_str = key.decode("utf-8") if isinstance(key, bytes) else key
            if key_str == "position_monitor:1:101":
                return json.dumps(
                    {"position_id": 101, "symbol": "NIFTY", "status": "active"}
                ).encode()
            elif key_str == "position_monitor:1:102":
                return json.dumps(
                    {"position_id": 102, "symbol": "BANKNIFTY", "status": "active"}
                ).encode()
            elif key_str == "market_data:1":
                return json.dumps({"trend": "bullish"}).encode()
            return None

        mock_client.get.side_effect = get_side_effect

        result = schedule_exit_evaluations()

        assert result["status"] == "success"
        assert result["evaluations_dispatched"] == 2
        assert mock_eval_task.delay.call_count == 2

    @patch("src.workers.ai_worker.get_redis_client")
    def test_returns_zero_when_no_positions(self, mock_redis):
        """Returns 0 evaluations when no active positions."""
        from src.workers.ai_worker import schedule_exit_evaluations

        mock_client = MagicMock()
        mock_redis.return_value.client = mock_client
        mock_client.keys.return_value = []

        result = schedule_exit_evaluations()

        assert result["status"] == "success"
        assert result["evaluations_dispatched"] == 0

    @patch("src.workers.ai_worker.get_redis_client")
    def test_skips_non_active_positions(self, mock_redis):
        """Skips positions that are not in 'active' status."""
        from src.workers.ai_worker import schedule_exit_evaluations

        mock_client = MagicMock()
        mock_redis.return_value.client = mock_client

        mock_client.keys.return_value = [b"position_monitor:1:101"]

        def get_side_effect(key):
            key_str = key.decode("utf-8") if isinstance(key, bytes) else key
            if key_str == "position_monitor:1:101":
                return json.dumps(
                    {"position_id": 101, "symbol": "NIFTY", "status": "closed"}
                ).encode()
            return None

        mock_client.get.side_effect = get_side_effect

        result = schedule_exit_evaluations()

        assert result["status"] == "success"
        assert result["evaluations_dispatched"] == 0

    @patch("src.workers.ai_worker.get_redis_client")
    def test_handles_redis_error_gracefully(self, mock_redis):
        """Returns error status when Redis is unavailable."""
        from src.workers.ai_worker import schedule_exit_evaluations

        mock_redis.return_value.client.keys.side_effect = Exception("Redis down")

        result = schedule_exit_evaluations()

        assert result["status"] == "error"
        assert result["evaluations_dispatched"] == 0


# ---------------------------------------------------------------------------
# Tests for beat schedule configuration
# ---------------------------------------------------------------------------


class TestBeatScheduleConfiguration:
    """Tests that the 30-second cycle is configured in Celery beat."""

    def test_exit_evaluation_in_beat_schedule(self):
        """Verify exit evaluation task is scheduled every 30 seconds."""
        from src.workers.celery_app import celery_app

        schedule = celery_app.conf.beat_schedule
        assert "evaluate-exit-recommendations-every-30s" in schedule

        task_config = schedule["evaluate-exit-recommendations-every-30s"]
        assert task_config["task"] == "src.workers.ai_worker.schedule_exit_evaluations"
        assert task_config["schedule"] == 30.0
