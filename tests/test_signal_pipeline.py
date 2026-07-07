"""Tests for Signal Pipeline — Scanner → Signal → AI → WebSocket flow.

Tests the integration wiring that connects:
1. Scanner signals → SignalService.create_signal (persistence)
2. Signal creation → AI signal analysis trigger
3. Signal creation → Redis PubSub signal_detected event
4. Signal expiry → Redis PubSub signal_expired event

Requirements covered: 1.1, 4.1-4.7, 18.1
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call

import pytest

from src.services.signal_pipeline import (
    process_scanner_signals,
    publish_signal_expired,
    _normalize_signal_data,
    _trigger_ai_analysis,
    _publish_signal_detected,
    SIGNAL_DETECTED_CHANNEL,
    SIGNAL_EXPIRED_CHANNEL,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    """Create a mock SQLAlchemy Session."""
    return MagicMock()


@pytest.fixture
def mock_redis():
    """Create a mock RedisClient."""
    redis = MagicMock()
    redis.set.return_value = True
    redis.delete.return_value = 1
    redis.ttl.return_value = 45
    redis.client = MagicMock()
    redis.client.publish.return_value = 1
    return redis


@pytest.fixture
def sample_signals():
    """Sample scanner output signals."""
    return [
        {
            "symbol": "NIFTY24500CE",
            "scan_type": "trend_pullback",
            "confidence_score": 78.5,
            "entry_price": 250.0,
            "stop_loss": 230.0,
            "target_price": 290.0,
            "max_potential_loss": 2000.0,
            "metadata": {"trend_direction": "bullish"},
        },
        {
            "symbol": "BANKNIFTY24800PE",
            "scan_type": "trend_pullback",
            "confidence_score": 65.0,
            "entry_price": 180.0,
            "stop_loss": 200.0,
            "target_price": 140.0,
            "max_potential_loss": 1500.0,
            "metadata": {"trend_direction": "bearish"},
        },
    ]


# ---------------------------------------------------------------------------
# _normalize_signal_data tests
# ---------------------------------------------------------------------------


class TestNormalizeSignalData:
    """Test signal data normalization."""

    def test_maps_scan_type_to_signal_type(self):
        """Should use scan_type as signal_type when signal_type is absent."""
        data = {
            "symbol": "NIFTY",
            "scan_type": "consolidation_breakout",
            "confidence_score": 70.0,
            "entry_price": 100.0,
            "stop_loss": 90.0,
            "target_price": 120.0,
            "max_potential_loss": 500.0,
        }
        result = _normalize_signal_data(data)
        assert result["signal_type"] == "consolidation_breakout"

    def test_prefers_signal_type_over_scan_type(self):
        """Should prefer signal_type if both are present."""
        data = {
            "symbol": "NIFTY",
            "signal_type": "trend_pullback",
            "scan_type": "consolidation_breakout",
            "confidence_score": 70.0,
            "entry_price": 100.0,
            "stop_loss": 90.0,
            "target_price": 120.0,
            "max_potential_loss": 500.0,
        }
        result = _normalize_signal_data(data)
        assert result["signal_type"] == "trend_pullback"

    def test_maps_max_loss_alias(self):
        """Should use max_loss as fallback for max_potential_loss."""
        data = {
            "symbol": "NIFTY",
            "scan_type": "trend_pullback",
            "confidence_score": 70.0,
            "entry_price": 100.0,
            "stop_loss": 90.0,
            "target_price": 120.0,
            "max_loss": 750.0,
        }
        result = _normalize_signal_data(data)
        assert result["max_potential_loss"] == 750.0

    def test_includes_optional_ai_fields(self):
        """Should pass through AI-related fields."""
        data = {
            "symbol": "NIFTY",
            "scan_type": "trend_pullback",
            "confidence_score": 70.0,
            "entry_price": 100.0,
            "stop_loss": 90.0,
            "target_price": 120.0,
            "max_potential_loss": 500.0,
            "ai_quality_rating": "Strong Setup",
            "ai_warnings": ["Near resistance"],
            "ai_explanation": "Good trade.",
        }
        result = _normalize_signal_data(data)
        assert result["ai_quality_rating"] == "Strong Setup"
        assert result["ai_warnings"] == ["Near resistance"]
        assert result["ai_explanation"] == "Good trade."


# ---------------------------------------------------------------------------
# process_scanner_signals tests
# ---------------------------------------------------------------------------


class TestProcessScannerSignals:
    """Test the full signal processing pipeline."""

    @patch("src.services.signal_pipeline._publish_signal_detected")
    @patch("src.services.signal_pipeline._trigger_ai_analysis")
    @patch("src.services.signal_pipeline.SignalService")
    def test_creates_signals_via_signal_service(
        self, MockSignalService, mock_ai_trigger, mock_publish, mock_db, mock_redis, sample_signals
    ):
        """Should call SignalService.create_signal for each signal."""
        mock_service = MockSignalService.return_value
        mock_signal = MagicMock()
        mock_signal.id = 1
        mock_signal.symbol = "NIFTY24500CE"
        mock_signal.signal_type = "trend_pullback"
        mock_signal.confidence_score = 78.5
        mock_signal.entry_price = 250.0
        mock_signal.stop_loss = 230.0
        mock_signal.target_price = 290.0
        mock_signal.max_potential_loss = 2000.0
        mock_signal.status = "pending"
        mock_signal.countdown_seconds = 60
        mock_signal.expires_at = datetime(2024, 1, 1, 10, 1, 0, tzinfo=timezone.utc)
        mock_signal.created_at = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        mock_signal.ai_quality_rating = None
        mock_signal.ai_warnings = None
        mock_signal.ai_explanation = None
        mock_service.create_signal.return_value = mock_signal

        result = process_scanner_signals(
            user_id=1,
            signals=sample_signals,
            db=mock_db,
            redis_client=mock_redis,
            countdown_seconds=60,
        )

        assert mock_service.create_signal.call_count == 2
        assert len(result) == 2

    @patch("src.services.signal_pipeline._publish_signal_detected")
    @patch("src.services.signal_pipeline._trigger_ai_analysis")
    @patch("src.services.signal_pipeline.SignalService")
    def test_triggers_ai_analysis_for_each_signal(
        self, MockSignalService, mock_ai_trigger, mock_publish, mock_db, mock_redis, sample_signals
    ):
        """Should call _trigger_ai_analysis for each created signal."""
        mock_service = MockSignalService.return_value
        mock_signal = MagicMock()
        mock_signal.id = 42
        mock_signal.symbol = "NIFTY24500CE"
        mock_signal.signal_type = "trend_pullback"
        mock_signal.confidence_score = 78.5
        mock_signal.entry_price = 250.0
        mock_signal.stop_loss = 230.0
        mock_signal.target_price = 290.0
        mock_signal.max_potential_loss = 2000.0
        mock_signal.status = "pending"
        mock_signal.countdown_seconds = 60
        mock_signal.expires_at = None
        mock_signal.created_at = None
        mock_signal.ai_quality_rating = None
        mock_signal.ai_warnings = None
        mock_signal.ai_explanation = None
        mock_service.create_signal.return_value = mock_signal

        process_scanner_signals(
            user_id=1,
            signals=sample_signals,
            db=mock_db,
            redis_client=mock_redis,
        )

        assert mock_ai_trigger.call_count == 2
        # First call should include signal_id=42
        call_args = mock_ai_trigger.call_args_list[0]
        assert call_args[0][0] == 1  # user_id
        assert call_args[0][2] == 42  # signal_id

    @patch("src.services.signal_pipeline._publish_signal_detected")
    @patch("src.services.signal_pipeline._trigger_ai_analysis")
    @patch("src.services.signal_pipeline.SignalService")
    def test_publishes_signal_detected_event(
        self, MockSignalService, mock_ai_trigger, mock_publish, mock_db, mock_redis, sample_signals
    ):
        """Should publish signal_detected to Redis PubSub for each signal."""
        mock_service = MockSignalService.return_value
        mock_signal = MagicMock()
        mock_signal.id = 1
        mock_signal.symbol = "NIFTY24500CE"
        mock_signal.signal_type = "trend_pullback"
        mock_signal.confidence_score = 78.5
        mock_signal.entry_price = 250.0
        mock_signal.stop_loss = 230.0
        mock_signal.target_price = 290.0
        mock_signal.max_potential_loss = 2000.0
        mock_signal.status = "pending"
        mock_signal.countdown_seconds = 60
        mock_signal.expires_at = None
        mock_signal.created_at = None
        mock_signal.ai_quality_rating = None
        mock_signal.ai_warnings = None
        mock_signal.ai_explanation = None
        mock_service.create_signal.return_value = mock_signal

        process_scanner_signals(
            user_id=1,
            signals=sample_signals,
            db=mock_db,
            redis_client=mock_redis,
        )

        assert mock_publish.call_count == 2

    @patch("src.services.signal_pipeline._publish_signal_detected")
    @patch("src.services.signal_pipeline._trigger_ai_analysis")
    @patch("src.services.signal_pipeline.SignalService")
    def test_skips_ai_analysis_when_disabled(
        self, MockSignalService, mock_ai_trigger, mock_publish, mock_db, mock_redis, sample_signals
    ):
        """Should skip AI analysis when trigger_ai_analysis=False."""
        mock_service = MockSignalService.return_value
        mock_signal = MagicMock()
        mock_signal.id = 1
        mock_signal.symbol = "NIFTY24500CE"
        mock_signal.signal_type = "trend_pullback"
        mock_signal.confidence_score = 78.5
        mock_signal.entry_price = 250.0
        mock_signal.stop_loss = 230.0
        mock_signal.target_price = 290.0
        mock_signal.max_potential_loss = 2000.0
        mock_signal.status = "pending"
        mock_signal.countdown_seconds = 60
        mock_signal.expires_at = None
        mock_signal.created_at = None
        mock_signal.ai_quality_rating = None
        mock_signal.ai_warnings = None
        mock_signal.ai_explanation = None
        mock_service.create_signal.return_value = mock_signal

        process_scanner_signals(
            user_id=1,
            signals=sample_signals,
            db=mock_db,
            redis_client=mock_redis,
            trigger_ai_analysis=False,
        )

        mock_ai_trigger.assert_not_called()

    @patch("src.services.signal_pipeline._publish_signal_detected")
    @patch("src.services.signal_pipeline._trigger_ai_analysis")
    @patch("src.services.signal_pipeline.SignalService")
    def test_continues_on_individual_signal_error(
        self, MockSignalService, mock_ai_trigger, mock_publish, mock_db, mock_redis, sample_signals
    ):
        """Should continue processing if one signal fails."""
        mock_service = MockSignalService.return_value
        mock_signal = MagicMock()
        mock_signal.id = 2
        mock_signal.symbol = "BANKNIFTY24800PE"
        mock_signal.signal_type = "trend_pullback"
        mock_signal.confidence_score = 65.0
        mock_signal.entry_price = 180.0
        mock_signal.stop_loss = 200.0
        mock_signal.target_price = 140.0
        mock_signal.max_potential_loss = 1500.0
        mock_signal.status = "pending"
        mock_signal.countdown_seconds = 60
        mock_signal.expires_at = None
        mock_signal.created_at = None
        mock_signal.ai_quality_rating = None
        mock_signal.ai_warnings = None
        mock_signal.ai_explanation = None

        # First signal fails, second succeeds
        mock_service.create_signal.side_effect = [
            ValueError("DB error"),
            mock_signal,
        ]

        result = process_scanner_signals(
            user_id=1,
            signals=sample_signals,
            db=mock_db,
            redis_client=mock_redis,
        )

        assert len(result) == 1
        assert result[0]["symbol"] == "BANKNIFTY24800PE"

    def test_returns_empty_list_for_empty_signals(self, mock_db, mock_redis):
        """Should return empty list when no signals provided."""
        result = process_scanner_signals(
            user_id=1,
            signals=[],
            db=mock_db,
            redis_client=mock_redis,
        )
        assert result == []


# ---------------------------------------------------------------------------
# _trigger_ai_analysis tests
# ---------------------------------------------------------------------------


class TestTriggerAIAnalysis:
    """Test AI analysis task dispatch."""

    @patch("src.workers.celery_app.celery_app")
    def test_queues_celery_task(self, mock_celery):
        """Should send the analyze_signal_quality task via Celery."""
        mock_task = MagicMock()
        mock_task.id = "task-123"
        mock_celery.send_task.return_value = mock_task

        result = _trigger_ai_analysis(
            user_id=1,
            signal_data={"symbol": "NIFTY", "confidence_score": 80},
            signal_id=42,
        )

        assert result == "task-123"
        mock_celery.send_task.assert_called_once_with(
            "src.workers.ai_worker.analyze_signal_quality",
            args=[1, {
                "signal_id": 42,
                "symbol": "NIFTY",
                "scan_type": None,
                "confidence_score": 80,
                "entry_price": None,
                "stop_loss": None,
                "target_price": None,
                "metadata": {},
            }],
        )

    @patch("src.workers.celery_app.celery_app")
    def test_returns_none_on_failure(self, mock_celery):
        """Should return None and not raise if Celery fails."""
        mock_celery.send_task.side_effect = Exception("Celery down")

        result = _trigger_ai_analysis(user_id=1, signal_data={}, signal_id=1)

        assert result is None


# ---------------------------------------------------------------------------
# _publish_signal_detected tests
# ---------------------------------------------------------------------------


class TestPublishSignalDetected:
    """Test signal_detected event publishing."""

    @patch("src.services.signal_pipeline.get_redis_client")
    def test_publishes_to_correct_channel(self, mock_get_redis):
        """Should publish to scanner:signal:{user_id} channel."""
        mock_redis = MagicMock()
        mock_redis.client.publish.return_value = 1
        mock_get_redis.return_value = mock_redis

        signal_data = {"id": 1, "symbol": "NIFTY", "status": "pending"}
        result = _publish_signal_detected(user_id=7, signal_data=signal_data)

        assert result is True
        call_args = mock_redis.client.publish.call_args
        assert call_args[0][0] == "scanner:signal:7"

    @patch("src.services.signal_pipeline.get_redis_client")
    def test_payload_contains_signal_data(self, mock_get_redis):
        """Should include signal data in the published payload."""
        mock_redis = MagicMock()
        mock_redis.client.publish.return_value = 1
        mock_get_redis.return_value = mock_redis

        signal_data = {"id": 1, "symbol": "NIFTY"}
        _publish_signal_detected(user_id=5, signal_data=signal_data)

        call_args = mock_redis.client.publish.call_args
        payload = json.loads(call_args[0][1])
        assert payload["user_id"] == 5
        assert payload["signal"]["id"] == 1
        assert payload["signal"]["symbol"] == "NIFTY"
        assert "timestamp" in payload

    @patch("src.services.signal_pipeline.get_redis_client")
    def test_returns_false_on_publish_error(self, mock_get_redis):
        """Should return False on Redis publish failure."""
        mock_redis = MagicMock()
        mock_redis.client.publish.side_effect = Exception("Connection error")
        mock_get_redis.return_value = mock_redis

        result = _publish_signal_detected(user_id=1, signal_data={})
        assert result is False


# ---------------------------------------------------------------------------
# publish_signal_expired tests
# ---------------------------------------------------------------------------


class TestPublishSignalExpired:
    """Test signal_expired event publishing."""

    @patch("src.services.signal_pipeline.get_redis_client")
    def test_publishes_to_correct_channel(self, mock_get_redis):
        """Should publish to scanner:signal_expired:{user_id} channel."""
        mock_redis = MagicMock()
        mock_redis.client.publish.return_value = 1
        mock_get_redis.return_value = mock_redis

        result = publish_signal_expired(user_id=3, signal_id=42, symbol="NIFTY24500CE")

        assert result is True
        call_args = mock_redis.client.publish.call_args
        assert call_args[0][0] == "scanner:signal_expired:3"

    @patch("src.services.signal_pipeline.get_redis_client")
    def test_payload_contains_expiry_data(self, mock_get_redis):
        """Should include signal_id, symbol, and status in payload."""
        mock_redis = MagicMock()
        mock_redis.client.publish.return_value = 1
        mock_get_redis.return_value = mock_redis

        publish_signal_expired(user_id=3, signal_id=42, symbol="NIFTY24500CE")

        call_args = mock_redis.client.publish.call_args
        payload = json.loads(call_args[0][1])
        assert payload["signal_id"] == 42
        assert payload["user_id"] == 3
        assert payload["symbol"] == "NIFTY24500CE"
        assert payload["status"] == "expired"
        assert "expired_at" in payload

    @patch("src.services.signal_pipeline.get_redis_client")
    def test_returns_false_on_error(self, mock_get_redis):
        """Should return False on Redis failure."""
        mock_redis = MagicMock()
        mock_redis.client.publish.side_effect = Exception("Connection error")
        mock_get_redis.return_value = mock_redis

        result = publish_signal_expired(user_id=1, signal_id=1, symbol="NIFTY")
        assert result is False


# ---------------------------------------------------------------------------
# WebSocket relay channel mapping tests
# ---------------------------------------------------------------------------


class TestChannelMapping:
    """Verify that signal pipeline channels match websocket_relay mappings."""

    def test_signal_detected_channel_format(self):
        """SIGNAL_DETECTED_CHANNEL should match relay's scanner:signal prefix."""
        # The relay maps "scanner:signal" → "signal_detected"
        channel = SIGNAL_DETECTED_CHANNEL.format(user_id=42)
        assert channel == "scanner:signal:42"
        # Prefix before the last ":" should be "scanner:signal"
        prefix = ":".join(channel.split(":")[:-1])
        assert prefix == "scanner:signal"

    def test_signal_expired_channel_format(self):
        """SIGNAL_EXPIRED_CHANNEL should match relay's scanner:signal_expired prefix."""
        channel = SIGNAL_EXPIRED_CHANNEL.format(user_id=7)
        assert channel == "scanner:signal_expired:7"
        prefix = ":".join(channel.split(":")[:-1])
        assert prefix == "scanner:signal_expired"
