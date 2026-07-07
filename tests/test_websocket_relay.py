"""Tests for WebSocket relay (Redis PubSub → Socket.IO).

Covers:
- Channel parsing: extracting event prefix and user_id from channel names
- Event mapping: mapping channel prefixes to Socket.IO event names
- Message handling: relaying valid messages, ignoring invalid ones

Requirements covered: 2.4, 7.2, 11.2-11.5
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from src.api.websocket_relay import (
    CHANNEL_EVENT_MAP,
    CHANNEL_PATTERNS,
    get_event_name,
    parse_channel,
    _handle_message,
)


# --- Tests for parse_channel ---


class TestParseChannel:
    """Tests for parse_channel function."""

    def test_simple_channel_with_user_id(self):
        """notification:42 → ('notification', '42')"""
        result = parse_channel("notification:42")
        assert result == ("notification", "42")

    def test_two_part_prefix_with_user_id(self):
        """ai:signal_analysis:7 → ('ai:signal_analysis', '7')"""
        result = parse_channel("ai:signal_analysis:7")
        assert result == ("ai:signal_analysis", "7")

    def test_three_part_prefix_with_user_id(self):
        """position:auto_exit:100 → ('position:auto_exit', '100')"""
        result = parse_channel("position:auto_exit:100")
        assert result == ("position:auto_exit", "100")

    def test_monitor_threshold_warning(self):
        """monitor:threshold_warning:5 → ('monitor:threshold_warning', '5')"""
        result = parse_channel("monitor:threshold_warning:5")
        assert result == ("monitor:threshold_warning", "5")

    def test_scanner_signal(self):
        """scanner:signal:99 → ('scanner:signal', '99')"""
        result = parse_channel("scanner:signal:99")
        assert result == ("scanner:signal", "99")

    def test_empty_string_returns_none(self):
        """Empty string should return None."""
        result = parse_channel("")
        assert result is None

    def test_no_colon_returns_none(self):
        """Channel without colon delimiter should return None."""
        result = parse_channel("invalidchannel")
        assert result is None

    def test_non_numeric_user_id_returns_none(self):
        """Non-numeric user_id should return None."""
        result = parse_channel("ai:signal_analysis:abc")
        assert result is None

    def test_user_id_with_special_chars_returns_none(self):
        """User_id with special characters should return None."""
        result = parse_channel("scanner:signal:12a3")
        assert result is None

    def test_large_user_id(self):
        """Large user_id should be parsed correctly."""
        result = parse_channel("notification:999999")
        assert result == ("notification", "999999")

    def test_user_id_zero(self):
        """User_id of 0 should be parsed (isdigit returns True for '0')."""
        result = parse_channel("notification:0")
        assert result == ("notification", "0")


# --- Tests for get_event_name ---


class TestGetEventName:
    """Tests for get_event_name function."""

    def test_ai_signal_analysis(self):
        """ai:signal_analysis maps to ai_analysis_result."""
        assert get_event_name("ai:signal_analysis") == "ai_analysis_result"

    def test_ai_exit_recommendation(self):
        """ai:exit_recommendation maps to ai_analysis_result."""
        assert get_event_name("ai:exit_recommendation") == "ai_analysis_result"

    def test_ai_market_narrative(self):
        """ai:market_narrative maps to ai_market_update."""
        assert get_event_name("ai:market_narrative") == "ai_market_update"

    def test_ai_risk_warnings(self):
        """ai:risk_warnings maps to ai_risk_warning."""
        assert get_event_name("ai:risk_warnings") == "ai_risk_warning"

    def test_monitor_threshold_warning(self):
        """monitor:threshold_warning maps to threshold_warning."""
        assert get_event_name("monitor:threshold_warning") == "threshold_warning"

    def test_monitor_status(self):
        """monitor:status maps to monitor_status."""
        assert get_event_name("monitor:status") == "monitor_status"

    def test_scanner_signal(self):
        """scanner:signal maps to signal_detected."""
        assert get_event_name("scanner:signal") == "signal_detected"

    def test_scanner_consolidation(self):
        """scanner:consolidation maps to consolidation_update."""
        assert get_event_name("scanner:consolidation") == "consolidation_update"

    def test_position_monitor(self):
        """position:monitor maps to position_monitor_update."""
        assert get_event_name("position:monitor") == "position_monitor_update"

    def test_position_exit_condition(self):
        """position:exit_condition maps to exit_condition_update."""
        assert get_event_name("position:exit_condition") == "exit_condition_update"

    def test_position_auto_exit(self):
        """position:auto_exit maps to auto_exit_triggered."""
        assert get_event_name("position:auto_exit") == "auto_exit_triggered"

    def test_notification(self):
        """notification maps to notification."""
        assert get_event_name("notification") == "notification"

    def test_unknown_prefix_returns_none(self):
        """Unknown channel prefix returns None."""
        assert get_event_name("unknown:prefix") is None

    def test_empty_prefix_returns_none(self):
        """Empty prefix returns None."""
        assert get_event_name("") is None

    def test_all_map_entries_have_values(self):
        """All entries in the channel-event map have non-empty values."""
        for prefix, event in CHANNEL_EVENT_MAP.items():
            assert prefix, "Map key should not be empty"
            assert event, f"Map value for '{prefix}' should not be empty"


# --- Tests for _handle_message ---


class TestHandleMessage:
    """Tests for the _handle_message relay function."""

    @pytest.mark.asyncio
    async def test_relays_valid_scanner_signal(self):
        """Valid scanner signal message is relayed to correct room."""
        payload = {"symbol": "NIFTY", "confidence": 85}
        channel = "scanner:signal:42"

        with patch("src.api.websocket_relay.sio") as mock_sio:
            mock_sio.emit = AsyncMock()
            await _handle_message(channel, json.dumps(payload))

            mock_sio.emit.assert_called_once_with(
                "signal_detected", payload, room="user:42"
            )

    @pytest.mark.asyncio
    async def test_relays_valid_notification(self):
        """Valid notification message is relayed to correct room."""
        payload = {"title": "Trade Executed", "severity": "info"}
        channel = "notification:7"

        with patch("src.api.websocket_relay.sio") as mock_sio:
            mock_sio.emit = AsyncMock()
            await _handle_message(channel, json.dumps(payload))

            mock_sio.emit.assert_called_once_with(
                "notification", payload, room="user:7"
            )

    @pytest.mark.asyncio
    async def test_relays_ai_risk_warning(self):
        """AI risk warning is relayed with correct event name."""
        payload = {"severity": "critical", "message": "Revenge trading detected"}
        channel = "ai:risk_warnings:15"

        with patch("src.api.websocket_relay.sio") as mock_sio:
            mock_sio.emit = AsyncMock()
            await _handle_message(channel, json.dumps(payload))

            mock_sio.emit.assert_called_once_with(
                "ai_risk_warning", payload, room="user:15"
            )

    @pytest.mark.asyncio
    async def test_relays_position_monitor_update(self):
        """Position monitor update is relayed correctly."""
        payload = {"position_id": 1, "pnl": 500.0}
        channel = "position:monitor:3"

        with patch("src.api.websocket_relay.sio") as mock_sio:
            mock_sio.emit = AsyncMock()
            await _handle_message(channel, json.dumps(payload))

            mock_sio.emit.assert_called_once_with(
                "position_monitor_update", payload, room="user:3"
            )

    @pytest.mark.asyncio
    async def test_ignores_unrecognized_channel(self):
        """Unrecognized channel formats are silently ignored."""
        with patch("src.api.websocket_relay.sio") as mock_sio:
            mock_sio.emit = AsyncMock()
            await _handle_message("invalid", '{"data": 1}')

            mock_sio.emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_non_numeric_user_id(self):
        """Channels with non-numeric user_id are ignored."""
        with patch("src.api.websocket_relay.sio") as mock_sio:
            mock_sio.emit = AsyncMock()
            await _handle_message("scanner:signal:abc", '{"data": 1}')

            mock_sio.emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_invalid_json(self):
        """Invalid JSON payloads are ignored (not relayed)."""
        with patch("src.api.websocket_relay.sio") as mock_sio:
            mock_sio.emit = AsyncMock()
            await _handle_message("scanner:signal:1", "not-json{{{")

            mock_sio.emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_emit_error_gracefully(self):
        """If sio.emit raises, the error is logged but doesn't crash."""
        payload = {"data": "test"}
        channel = "notification:1"

        with patch("src.api.websocket_relay.sio") as mock_sio:
            mock_sio.emit = AsyncMock(side_effect=Exception("Connection lost"))
            # Should not raise
            await _handle_message(channel, json.dumps(payload))

    @pytest.mark.asyncio
    async def test_relays_monitor_threshold_warning(self):
        """Monitor threshold warning is relayed correctly."""
        payload = {"pnl": -4500, "threshold": -5000, "distance_pct": 10}
        channel = "monitor:threshold_warning:22"

        with patch("src.api.websocket_relay.sio") as mock_sio:
            mock_sio.emit = AsyncMock()
            await _handle_message(channel, json.dumps(payload))

            mock_sio.emit.assert_called_once_with(
                "threshold_warning", payload, room="user:22"
            )

    @pytest.mark.asyncio
    async def test_relays_auto_exit_triggered(self):
        """Auto exit triggered event is relayed correctly."""
        payload = {"position_id": 5, "reason": "sl_hit"}
        channel = "position:auto_exit:10"

        with patch("src.api.websocket_relay.sio") as mock_sio:
            mock_sio.emit = AsyncMock()
            await _handle_message(channel, json.dumps(payload))

            mock_sio.emit.assert_called_once_with(
                "auto_exit_triggered", payload, room="user:10"
            )


# --- Tests for channel patterns ---


class TestChannelPatterns:
    """Verify channel pattern configuration is correct."""

    def test_patterns_cover_all_domains(self):
        """All expected domain patterns are subscribed."""
        assert "ai:*" in CHANNEL_PATTERNS
        assert "monitor:*" in CHANNEL_PATTERNS
        assert "scanner:*" in CHANNEL_PATTERNS
        assert "position:*" in CHANNEL_PATTERNS
        assert "notification:*" in CHANNEL_PATTERNS

    def test_patterns_count(self):
        """We subscribe to exactly 5 pattern groups."""
        assert len(CHANNEL_PATTERNS) == 5
