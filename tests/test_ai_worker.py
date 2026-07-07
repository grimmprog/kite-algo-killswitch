"""Tests for the AI Analysis Worker — Celery tasks for async AI-powered trade analysis.

Tests cover:
- analyze_signal_quality: Signal analysis with 5-second timeout
- evaluate_exit_ai: Exit recommendation with graceful degradation
- generate_market_narrative: Market narrative with caching
- detect_risk_anomalies: Risk warning detection
- Redis PubSub publishing for WebSocket delivery
- Timeout handling (SoftTimeLimitExceeded)
- Graceful degradation when AI is unavailable

Requirements covered:
- 18.6: AI signal analysis completes within 5 seconds
- 21.1: AI exit evaluation runs on 30-second cycles
- 22.2: AI market narrative updates at scheduled intervals
- 24.1: AI risk anomaly detection for behavioral patterns
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
from datetime import datetime
from unittest.mock import MagicMock, patch, call

import pytest
from celery.exceptions import SoftTimeLimitExceeded

from src.workers.ai_worker import (
    analyze_signal_quality,
    evaluate_exit_ai,
    generate_market_narrative,
    detect_risk_anomalies,
    _get_ai_service,
    _publish_result,
    _unavailable_result,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def mock_redis_client():
    """Create a mock RedisClient with PubSub support."""
    client = MagicMock()
    client.client = MagicMock()
    client.client.publish = MagicMock(return_value=1)
    client.setex = MagicMock(return_value=True)
    return client


@pytest.fixture
def mock_ai_service():
    """Create a mock AITradingService."""
    service = MagicMock()
    service.analyze_signal.return_value = {
        "quality_rating": "Strong Setup",
        "warnings": [],
        "explanation": "Strong bullish setup with good volume confirmation.",
    }
    service.evaluate_exit.return_value = {
        "action": "hold",
        "reasoning": "Trend remains intact, momentum building.",
        "confidence": 85.0,
        "warnings": [],
    }
    service.generate_narrative.return_value = {
        "session_type": "morning_brief",
        "key_points": ["Market opened flat", "NIFTY holding 22000 support"],
        "bias": "bullish",
        "expected_range": {"low": 21900.0, "high": 22200.0},
        "key_levels": {"support": [21900.0], "resistance": [22200.0]},
    }
    service.detect_risk_anomalies.return_value = {
        "warnings": [
            {
                "severity": "warning",
                "message": "3 consecutive losses detected — consider a break",
                "category": "behavioral",
                "requires_acknowledgment": False,
            }
        ]
    }
    return service


@pytest.fixture
def sample_signal_context():
    """Sample signal context for testing."""
    return {
        "symbol": "NIFTY",
        "timeframe": "5min",
        "indicators": {"ema_20": 22050.0, "vwap": 22030.0, "rsi": 62.5},
        "price_action_pattern": "trend_pullback",
        "volume_profile": {"current": 1200, "average": 1000},
        "recent_candles": [{"open": 22000, "high": 22100, "low": 21980, "close": 22080}],
    }


@pytest.fixture
def sample_position():
    """Sample position data for testing."""
    return {
        "position_id": 42,
        "symbol": "NIFTY 22100 CE",
        "entry_price": 150.0,
        "current_price": 165.0,
        "stop_loss": 135.0,
        "target": 200.0,
        "unrealized_pnl": 750.0,
        "time_held_minutes": 25,
        "quantity": 50,
        "option_type": "CE",
    }


@pytest.fixture
def sample_market_data():
    """Sample market data for testing."""
    return {
        "macd": {"signal": 0.5, "histogram": 0.3},
        "momentum": 65.0,
        "volume": 1.2,
        "trend": "bullish",
        "key_levels": {"support": [21900.0], "resistance": [22200.0]},
        "ema_20": 22050.0,
        "vwap": 22030.0,
    }


@pytest.fixture
def sample_user_state():
    """Sample user trading state for risk detection."""
    return {
        "consecutive_losses": 3,
        "trades_today": 5,
        "last_trade_time": "2024-01-15T10:30:00",
        "last_trade_pnl": -500.0,
        "last_trade_symbol": "NIFTY",
    }


# ============================================================
# Tests for _get_ai_service
# ============================================================


class TestGetAIService:
    """Tests for the _get_ai_service helper."""

    @patch.dict(os.environ, {"AI_PROVIDER": "gemini", "AI_GEMINI_API_KEY": "test-key"})
    def test_creates_service_with_gemini(self):
        """Should create an AITradingService with Gemini provider."""
        service = _get_ai_service()
        assert service is not None
        assert service.provider.value == "gemini"

    @patch.dict(os.environ, {"AI_PROVIDER": "claude", "AI_CLAUDE_API_KEY": "test-key"})
    def test_creates_service_with_claude(self):
        """Should create an AITradingService with Claude provider."""
        service = _get_ai_service()
        assert service is not None
        assert service.provider.value == "claude"

    @patch.dict(os.environ, {"AI_PROVIDER": "gemini", "AI_API_KEY": "fallback-key"}, clear=True)
    def test_uses_fallback_api_key(self):
        """Should use AI_API_KEY as fallback when provider-specific key is missing."""
        service = _get_ai_service()
        assert service is not None

    @patch.dict(os.environ, {"AI_PROVIDER": "gemini"}, clear=True)
    def test_raises_when_no_api_key(self):
        """Should raise RuntimeError when no API key is configured."""
        # Clear any existing keys
        os.environ.pop("AI_GEMINI_API_KEY", None)
        os.environ.pop("AI_API_KEY", None)
        with pytest.raises(RuntimeError, match="No AI API key configured"):
            _get_ai_service()


# ============================================================
# Tests for _publish_result
# ============================================================


class TestPublishResult:
    """Tests for the _publish_result helper."""

    @patch("src.workers.ai_worker.get_redis_client")
    def test_publishes_json_to_channel(self, mock_get_redis):
        """Should publish JSON-serialized data to the specified channel."""
        mock_client = MagicMock()
        mock_client.client.publish = MagicMock(return_value=1)
        mock_get_redis.return_value = mock_client

        data = {"status": "success", "task_type": "signal_analysis"}
        result = _publish_result("ai:signal_analysis:1", data)

        assert result is True
        mock_client.client.publish.assert_called_once()
        channel_arg = mock_client.client.publish.call_args[0][0]
        assert channel_arg == "ai:signal_analysis:1"

    @patch("src.workers.ai_worker.get_redis_client")
    def test_returns_false_on_error(self, mock_get_redis):
        """Should return False when Redis publish fails."""
        mock_client = MagicMock()
        mock_client.client.publish.side_effect = Exception("Connection refused")
        mock_get_redis.return_value = mock_client

        result = _publish_result("ai:test:1", {"data": "test"})
        assert result is False


# ============================================================
# Tests for _unavailable_result
# ============================================================


class TestUnavailableResult:
    """Tests for the _unavailable_result helper."""

    def test_builds_degraded_response(self):
        """Should build a proper unavailability response."""
        result = _unavailable_result("signal_analysis", "API key missing")

        assert result["status"] == "unavailable"
        assert result["task_type"] == "signal_analysis"
        assert result["message"] == "API key missing"
        assert "timestamp" in result

    def test_default_reason(self):
        """Should use default reason when none provided."""
        result = _unavailable_result("exit_recommendation")
        assert result["message"] == "AI unavailable"


# ============================================================
# Tests for analyze_signal_quality
# ============================================================


class TestAnalyzeSignalQuality:
    """Tests for the analyze_signal_quality Celery task."""

    @patch("src.workers.ai_worker._is_ai_feature_enabled", return_value=True)
    @patch("src.workers.ai_worker._publish_result")
    @patch("src.workers.ai_worker._get_ai_service")
    def test_successful_analysis(self, mock_get_service, mock_publish, mock_feature, mock_ai_service, sample_signal_context):
        """Should analyze signal and publish result to Redis PubSub."""
        mock_get_service.return_value = mock_ai_service

        result = analyze_signal_quality(user_id=1, signal_context=sample_signal_context)

        assert result["status"] == "success"
        assert result["task_type"] == "signal_analysis"
        assert result["user_id"] == 1
        assert result["data"]["quality_rating"] == "Strong Setup"

        # Verify publish was called with correct channel
        mock_publish.assert_called_once()
        channel_arg = mock_publish.call_args[0][0]
        assert channel_arg == "ai:signal_analysis:1"

    @patch("src.workers.ai_worker._is_ai_feature_enabled", return_value=True)
    @patch("src.workers.ai_worker._publish_result")
    @patch("src.workers.ai_worker._get_ai_service")
    def test_handles_ai_unavailable(self, mock_get_service, mock_publish, mock_feature, sample_signal_context):
        """Should gracefully degrade when AI service raises RuntimeError."""
        mock_get_service.side_effect = RuntimeError("No AI API key configured")

        result = analyze_signal_quality(user_id=1, signal_context=sample_signal_context)

        assert result["status"] == "unavailable"
        assert "No AI API key" in result["message"]
        mock_publish.assert_called_once()

    @patch("src.workers.ai_worker._is_ai_feature_enabled", return_value=True)
    @patch("src.workers.ai_worker._publish_result")
    @patch("src.workers.ai_worker._get_ai_service")
    def test_handles_timeout(self, mock_get_service, mock_publish, mock_feature, sample_signal_context):
        """Should handle SoftTimeLimitExceeded and return unavailable status."""
        mock_service = MagicMock()
        mock_service.analyze_signal.side_effect = SoftTimeLimitExceeded()
        mock_get_service.return_value = mock_service

        result = analyze_signal_quality(user_id=1, signal_context=sample_signal_context)

        assert result["status"] == "unavailable"
        assert "timed out" in result["message"]
        assert result["user_id"] == 1
        mock_publish.assert_called_once()

    @patch("src.workers.ai_worker._is_ai_feature_enabled", return_value=True)
    @patch("src.workers.ai_worker._publish_result")
    @patch("src.workers.ai_worker._get_ai_service")
    def test_handles_unexpected_exception(self, mock_get_service, mock_publish, mock_feature, sample_signal_context):
        """Should handle unexpected exceptions and return unavailable status."""
        mock_service = MagicMock()
        mock_service.analyze_signal.side_effect = ValueError("Unexpected error")
        mock_get_service.return_value = mock_service

        result = analyze_signal_quality(user_id=1, signal_context=sample_signal_context)

        assert result["status"] == "unavailable"
        assert result["user_id"] == 1
        mock_publish.assert_called_once()

    @patch("src.workers.ai_worker._is_ai_feature_enabled", return_value=True)
    @patch("src.workers.ai_worker._publish_result")
    @patch("src.workers.ai_worker._get_ai_service")
    def test_handles_service_degradation_response(self, mock_get_service, mock_publish, mock_feature, sample_signal_context):
        """Should detect when AI service itself returns a degraded response."""
        mock_service = MagicMock()
        mock_service.analyze_signal.return_value = {
            "error": True,
            "message": "AI rate limit exceeded",
            "available": False,
        }
        mock_get_service.return_value = mock_service

        result = analyze_signal_quality(user_id=1, signal_context=sample_signal_context)

        assert result["status"] == "unavailable"
        assert "rate limit" in result["message"]

    @patch("src.workers.ai_worker._is_ai_feature_enabled", return_value=False)
    @patch("src.workers.ai_worker._publish_result")
    def test_skips_when_feature_disabled(self, mock_publish, mock_feature, sample_signal_context):
        """Should return unavailable when signal analysis is disabled in settings."""
        result = analyze_signal_quality(user_id=1, signal_context=sample_signal_context)

        assert result["status"] == "unavailable"
        assert "disabled" in result["message"]
        mock_publish.assert_called_once()


# ============================================================
# Tests for evaluate_exit_ai
# ============================================================


class TestEvaluateExitAI:
    """Tests for the evaluate_exit_ai Celery task."""

    @patch("src.workers.ai_worker._is_ai_feature_enabled", return_value=True)
    @patch("src.workers.ai_worker._publish_result")
    @patch("src.workers.ai_worker._get_ai_service")
    def test_successful_evaluation(self, mock_get_service, mock_publish, mock_feature, mock_ai_service, sample_position, sample_market_data):
        """Should evaluate exit and publish result to Redis PubSub."""
        mock_get_service.return_value = mock_ai_service

        result = evaluate_exit_ai(user_id=1, position=sample_position, market_data=sample_market_data)

        assert result["status"] == "success"
        assert result["task_type"] == "exit_recommendation"
        assert result["user_id"] == 1
        assert result["position_id"] == 42
        assert result["data"]["action"] == "hold"

        # Verify correct PubSub channel
        mock_publish.assert_called_once()
        channel_arg = mock_publish.call_args[0][0]
        assert channel_arg == "ai:exit_recommendation:1"

    @patch("src.workers.ai_worker._is_ai_feature_enabled", return_value=True)
    @patch("src.workers.ai_worker._publish_result")
    @patch("src.workers.ai_worker._get_ai_service")
    def test_handles_ai_unavailable(self, mock_get_service, mock_publish, mock_feature, sample_position, sample_market_data):
        """Should gracefully degrade when AI service is not configured."""
        mock_get_service.side_effect = RuntimeError("No AI API key configured")

        result = evaluate_exit_ai(user_id=1, position=sample_position, market_data=sample_market_data)

        assert result["status"] == "unavailable"
        mock_publish.assert_called_once()

    @patch("src.workers.ai_worker._is_ai_feature_enabled", return_value=True)
    @patch("src.workers.ai_worker._publish_result")
    @patch("src.workers.ai_worker._get_ai_service")
    def test_handles_timeout(self, mock_get_service, mock_publish, mock_feature, sample_position, sample_market_data):
        """Should handle SoftTimeLimitExceeded gracefully."""
        mock_service = MagicMock()
        mock_service.evaluate_exit.side_effect = SoftTimeLimitExceeded()
        mock_get_service.return_value = mock_service

        result = evaluate_exit_ai(user_id=1, position=sample_position, market_data=sample_market_data)

        assert result["status"] == "unavailable"
        assert "timed out" in result["message"]
        assert result["position_id"] == 42

    @patch("src.workers.ai_worker._is_ai_feature_enabled", return_value=True)
    @patch("src.workers.ai_worker._publish_result")
    @patch("src.workers.ai_worker._get_ai_service")
    def test_handles_unexpected_exception(self, mock_get_service, mock_publish, mock_feature, sample_position, sample_market_data):
        """Should handle unexpected exceptions gracefully."""
        mock_service = MagicMock()
        mock_service.evaluate_exit.side_effect = Exception("Network error")
        mock_get_service.return_value = mock_service

        result = evaluate_exit_ai(user_id=1, position=sample_position, market_data=sample_market_data)

        assert result["status"] == "unavailable"
        assert result["user_id"] == 1

    @patch("src.workers.ai_worker._is_ai_feature_enabled", return_value=False)
    @patch("src.workers.ai_worker._publish_result")
    def test_skips_when_feature_disabled(self, mock_publish, mock_feature, sample_position, sample_market_data):
        """Should return unavailable when exit recommendations are disabled in settings."""
        result = evaluate_exit_ai(user_id=1, position=sample_position, market_data=sample_market_data)

        assert result["status"] == "unavailable"
        assert "disabled" in result["message"]
        mock_publish.assert_called_once()


# ============================================================
# Tests for generate_market_narrative
# ============================================================


class TestGenerateMarketNarrative:
    """Tests for the generate_market_narrative Celery task."""

    @patch("src.workers.ai_worker._is_ai_feature_enabled", return_value=True)
    @patch("src.workers.ai_worker.get_redis_client")
    @patch("src.workers.ai_worker._publish_result")
    @patch("src.workers.ai_worker._get_ai_service")
    def test_successful_narrative(self, mock_get_service, mock_publish, mock_get_redis, mock_feature, mock_ai_service, mock_redis_client):
        """Should generate narrative, cache it, and publish via PubSub."""
        mock_get_service.return_value = mock_ai_service
        mock_get_redis.return_value = mock_redis_client

        result = generate_market_narrative(
            user_id=1,
            session_type="morning_brief",
            market_data={"vix": 14.5},
        )

        assert result["status"] == "success"
        assert result["task_type"] == "market_narrative"
        assert result["session_type"] == "morning_brief"
        assert result["data"]["bias"] == "bullish"

        # Verify PubSub publish
        mock_publish.assert_called_once()
        channel_arg = mock_publish.call_args[0][0]
        assert channel_arg == "ai:market_narrative:1"

        # Verify caching
        mock_redis_client.setex.assert_called_once()
        cache_key = mock_redis_client.setex.call_args[0][0]
        assert cache_key == "ai:narrative:morning_brief"

    @patch("src.workers.ai_worker._is_ai_feature_enabled", return_value=True)
    @patch("src.workers.ai_worker._publish_result")
    @patch("src.workers.ai_worker._get_ai_service")
    def test_handles_ai_unavailable(self, mock_get_service, mock_publish, mock_feature):
        """Should gracefully degrade when AI service is not configured."""
        mock_get_service.side_effect = RuntimeError("No AI API key configured")

        result = generate_market_narrative(
            user_id=1,
            session_type="morning_brief",
            market_data={},
        )

        assert result["status"] == "unavailable"
        mock_publish.assert_called_once()

    @patch("src.workers.ai_worker._is_ai_feature_enabled", return_value=True)
    @patch("src.workers.ai_worker._publish_result")
    @patch("src.workers.ai_worker._get_ai_service")
    def test_handles_timeout(self, mock_get_service, mock_publish, mock_feature):
        """Should handle SoftTimeLimitExceeded gracefully."""
        mock_service = MagicMock()
        mock_service.generate_narrative.side_effect = SoftTimeLimitExceeded()
        mock_get_service.return_value = mock_service

        result = generate_market_narrative(
            user_id=1,
            session_type="lunch",
            market_data={},
        )

        assert result["status"] == "unavailable"
        assert "timed out" in result["message"]
        assert result["session_type"] == "lunch"

    @patch("src.workers.ai_worker._is_ai_feature_enabled", return_value=True)
    @patch("src.workers.ai_worker.get_redis_client")
    @patch("src.workers.ai_worker._publish_result")
    @patch("src.workers.ai_worker._get_ai_service")
    def test_handles_cache_failure_gracefully(self, mock_get_service, mock_publish, mock_get_redis, mock_feature, mock_ai_service):
        """Should still succeed even if caching fails."""
        mock_get_service.return_value = mock_ai_service
        mock_client = MagicMock()
        mock_client.setex.side_effect = Exception("Redis connection lost")
        mock_get_redis.return_value = mock_client

        result = generate_market_narrative(
            user_id=1,
            session_type="morning_brief",
            market_data={},
        )

        # Task should still succeed even if caching fails
        assert result["status"] == "success"

    @patch("src.workers.ai_worker._is_ai_feature_enabled", return_value=False)
    @patch("src.workers.ai_worker._publish_result")
    def test_skips_when_feature_disabled(self, mock_publish, mock_feature):
        """Should return unavailable when market narrative is disabled in settings."""
        result = generate_market_narrative(
            user_id=1,
            session_type="morning_brief",
            market_data={},
        )

        assert result["status"] == "unavailable"
        assert "disabled" in result["message"]
        mock_publish.assert_called_once()


# ============================================================
# Tests for detect_risk_anomalies
# ============================================================


class TestDetectRiskAnomalies:
    """Tests for the detect_risk_anomalies Celery task."""

    @patch("src.workers.ai_worker._is_ai_feature_enabled", return_value=True)
    @patch("src.workers.ai_worker._publish_result")
    @patch("src.workers.ai_worker._get_ai_service")
    def test_successful_detection(self, mock_get_service, mock_publish, mock_feature, mock_ai_service, sample_user_state, sample_market_data):
        """Should detect risk anomalies and publish to PubSub."""
        mock_get_service.return_value = mock_ai_service

        result = detect_risk_anomalies(
            user_id=1,
            user_state=sample_user_state,
            market_data=sample_market_data,
        )

        assert result["status"] == "success"
        assert result["task_type"] == "risk_anomaly_detection"
        assert result["user_id"] == 1
        assert "warnings" in result["data"]

        # Verify correct PubSub channel
        mock_publish.assert_called_once()
        channel_arg = mock_publish.call_args[0][0]
        assert channel_arg == "ai:risk_warnings:1"

    @patch("src.workers.ai_worker._is_ai_feature_enabled", return_value=True)
    @patch("src.workers.ai_worker._publish_result")
    @patch("src.workers.ai_worker._get_ai_service")
    def test_handles_ai_unavailable(self, mock_get_service, mock_publish, mock_feature, sample_user_state, sample_market_data):
        """Should gracefully degrade when AI service is not configured."""
        mock_get_service.side_effect = RuntimeError("No AI API key configured")

        result = detect_risk_anomalies(
            user_id=1,
            user_state=sample_user_state,
            market_data=sample_market_data,
        )

        assert result["status"] == "unavailable"
        mock_publish.assert_called_once()

    @patch("src.workers.ai_worker._is_ai_feature_enabled", return_value=True)
    @patch("src.workers.ai_worker._publish_result")
    @patch("src.workers.ai_worker._get_ai_service")
    def test_handles_timeout(self, mock_get_service, mock_publish, mock_feature, sample_user_state, sample_market_data):
        """Should handle SoftTimeLimitExceeded gracefully."""
        mock_service = MagicMock()
        mock_service.detect_risk_anomalies.side_effect = SoftTimeLimitExceeded()
        mock_get_service.return_value = mock_service

        result = detect_risk_anomalies(
            user_id=1,
            user_state=sample_user_state,
            market_data=sample_market_data,
        )

        assert result["status"] == "unavailable"
        assert "timed out" in result["message"]

    @patch("src.workers.ai_worker._is_ai_feature_enabled", return_value=False)
    @patch("src.workers.ai_worker._publish_result")
    def test_skips_when_feature_disabled(self, mock_publish, mock_feature, sample_user_state, sample_market_data):
        """Should return unavailable when risk warnings are disabled in settings."""
        result = detect_risk_anomalies(
            user_id=1,
            user_state=sample_user_state,
            market_data=sample_market_data,
        )

        assert result["status"] == "unavailable"
        assert "disabled" in result["message"]
        mock_publish.assert_called_once()

    @patch("src.workers.ai_worker._publish_result")
    @patch("src.workers.ai_worker._get_ai_service")
    def test_handles_unexpected_exception(self, mock_get_service, mock_publish, sample_user_state, sample_market_data):
        """Should handle unexpected exceptions gracefully."""
        mock_service = MagicMock()
        mock_service.detect_risk_anomalies.side_effect = TypeError("Bad data")
        mock_get_service.return_value = mock_service

        result = detect_risk_anomalies(
            user_id=1,
            user_state=sample_user_state,
            market_data=sample_market_data,
        )

        assert result["status"] == "unavailable"
        assert result["user_id"] == 1


# ============================================================
# Tests for task configuration
# ============================================================


class TestTaskConfiguration:
    """Tests for Celery task configuration (timeouts, retries)."""

    def test_signal_analysis_has_5s_soft_limit(self):
        """Signal analysis task should have 5-second soft_time_limit (Req 18.6)."""
        assert analyze_signal_quality.soft_time_limit == 5

    def test_signal_analysis_has_10s_hard_limit(self):
        """Signal analysis task should have 10-second hard time_limit."""
        assert analyze_signal_quality.time_limit == 10

    def test_exit_evaluation_has_10s_soft_limit(self):
        """Exit evaluation task should have 10-second soft_time_limit."""
        assert evaluate_exit_ai.soft_time_limit == 10

    def test_narrative_has_15s_soft_limit(self):
        """Narrative task should have 15-second soft_time_limit."""
        assert generate_market_narrative.soft_time_limit == 15

    def test_risk_detection_has_10s_soft_limit(self):
        """Risk detection task should have 10-second soft_time_limit."""
        assert detect_risk_anomalies.soft_time_limit == 10

    def test_signal_analysis_no_retries(self):
        """Signal analysis should not retry (time-sensitive)."""
        assert analyze_signal_quality.max_retries == 0

    def test_narrative_has_retry(self):
        """Narrative generation can retry once (not time-critical)."""
        assert generate_market_narrative.max_retries == 1
