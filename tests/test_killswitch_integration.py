"""Tests for kill switch → segment deactivation → notification integration.

Validates Requirements 12.4 and 11.4:
- 12.4: When kill switch activates, indicate which segments were deactivated
- 11.4: When kill switch triggers, push critical notification with trigger reason
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.services.killswitch_integration import (
    _killswitch_segments_key,
    _mark_segments_deactivated,
    _push_killswitch_notification,
    clear_killswitch_segments,
    get_killswitch_deactivated_segments,
    handle_killswitch_activation,
)


@pytest.fixture
def mock_redis():
    """Create a mock RedisClient with common operations."""
    redis = MagicMock()
    redis.get.return_value = None
    redis.set.return_value = True
    redis.delete.return_value = 1
    redis.client = MagicMock()
    redis.client.publish = MagicMock()
    return redis


@pytest.fixture
def mock_db_session():
    """Create a mock SQLAlchemy session."""
    session = MagicMock()
    session.add = MagicMock()
    session.commit = MagicMock()
    session.refresh = MagicMock()
    return session


class TestKillswitchSegmentsKey:
    """Test Redis key generation for kill switch segments."""

    def test_key_format(self):
        assert _killswitch_segments_key(42) == "user:42:killswitch:segments"

    def test_key_different_users(self):
        assert _killswitch_segments_key(1) != _killswitch_segments_key(2)


class TestMarkSegmentsDeactivated:
    """Test segment deactivation state storage."""

    def test_stores_segments_as_json(self, mock_redis):
        result = _mark_segments_deactivated(
            user_id=1,
            segments=["NSE", "BSE", "NFO"],
            redis_client=mock_redis,
        )

        assert result is True
        mock_redis.set.assert_called_once_with(
            "user:1:killswitch:segments",
            json.dumps(["NSE", "BSE", "NFO"]),
        )

    def test_stores_all_default_segments(self, mock_redis):
        result = _mark_segments_deactivated(
            user_id=5,
            segments=["NSE", "BSE", "NFO", "BFO"],
            redis_client=mock_redis,
        )

        assert result is True
        key = "user:5:killswitch:segments"
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args[0][0] == key
        stored = json.loads(call_args[0][1])
        assert "NSE" in stored
        assert "BFO" in stored

    def test_handles_redis_error(self, mock_redis):
        mock_redis.set.side_effect = Exception("Redis connection lost")

        result = _mark_segments_deactivated(
            user_id=1,
            segments=["NSE"],
            redis_client=mock_redis,
        )

        assert result is False


class TestGetKillswitchDeactivatedSegments:
    """Test reading kill switch deactivated segments from Redis."""

    def test_returns_empty_when_no_data(self, mock_redis):
        mock_redis.get.return_value = None

        result = get_killswitch_deactivated_segments(1, mock_redis)
        assert result == []

    def test_returns_stored_segments(self, mock_redis):
        mock_redis.get.return_value = json.dumps(["NSE", "NFO"])

        result = get_killswitch_deactivated_segments(1, mock_redis)
        assert result == ["NSE", "NFO"]

    def test_handles_invalid_json(self, mock_redis):
        mock_redis.get.return_value = "not-json{"

        result = get_killswitch_deactivated_segments(1, mock_redis)
        assert result == []

    def test_handles_non_list_json(self, mock_redis):
        mock_redis.get.return_value = json.dumps({"segments": ["NSE"]})

        result = get_killswitch_deactivated_segments(1, mock_redis)
        assert result == []

    def test_handles_redis_error(self, mock_redis):
        mock_redis.get.side_effect = Exception("Connection refused")

        result = get_killswitch_deactivated_segments(1, mock_redis)
        assert result == []


class TestClearKillswitchSegments:
    """Test clearing kill switch segment state."""

    def test_deletes_redis_key(self, mock_redis):
        result = clear_killswitch_segments(1, mock_redis)

        assert result is True
        mock_redis.delete.assert_called_once_with("user:1:killswitch:segments")

    def test_handles_error(self, mock_redis):
        mock_redis.delete.side_effect = Exception("Redis error")

        result = clear_killswitch_segments(1, mock_redis)
        assert result is False


class TestPushKillswitchNotification:
    """Test critical notification push on kill switch activation."""

    @patch("src.services.killswitch_integration.NotificationService")
    def test_pushes_critical_notification(self, MockNotifService, mock_redis, mock_db_session):
        mock_service_instance = MagicMock()
        MockNotifService.return_value = mock_service_instance

        result = _push_killswitch_notification(
            user_id=1,
            reason="Daily loss limit breached: -3.50%",
            positions_closed=2,
            redis_client=mock_redis,
            db_session=mock_db_session,
        )

        assert result is True
        MockNotifService.assert_called_once_with(db=mock_db_session, redis_client=mock_redis)
        mock_service_instance.push_notification.assert_called_once()

        call_kwargs = mock_service_instance.push_notification.call_args[1]
        assert call_kwargs["user_id"] == 1
        assert call_kwargs["severity"] == "critical"
        assert call_kwargs["category"] == "killswitch"
        assert "Kill Switch Activated" in call_kwargs["title"]
        assert "Daily loss limit breached" in call_kwargs["message"]
        assert "2 position(s) queued for exit" in call_kwargs["message"]

    @patch("src.services.killswitch_integration.NotificationService")
    def test_includes_metadata(self, MockNotifService, mock_redis, mock_db_session):
        mock_service_instance = MagicMock()
        MockNotifService.return_value = mock_service_instance

        _push_killswitch_notification(
            user_id=1,
            reason="Margin limit breached",
            positions_closed=3,
            redis_client=mock_redis,
            db_session=mock_db_session,
        )

        call_kwargs = mock_service_instance.push_notification.call_args[1]
        metadata = call_kwargs["metadata"]
        assert metadata["reason"] == "Margin limit breached"
        assert metadata["positions_closed"] == 3
        assert "triggered_at" in metadata

    @patch("src.services.killswitch_integration.NotificationService")
    def test_handles_notification_error(self, MockNotifService, mock_redis, mock_db_session):
        MockNotifService.side_effect = Exception("DB connection error")

        result = _push_killswitch_notification(
            user_id=1,
            reason="test",
            positions_closed=0,
            redis_client=mock_redis,
            db_session=mock_db_session,
        )

        assert result is False


class TestHandleKillswitchActivation:
    """Test the full integration: notification + segment deactivation."""

    @patch("src.services.killswitch_integration._mark_segments_deactivated")
    @patch("src.services.killswitch_integration._push_killswitch_notification")
    def test_full_flow_success(
        self, mock_push_notif, mock_mark_segments, mock_redis, mock_db_session
    ):
        mock_push_notif.return_value = True
        mock_mark_segments.return_value = True

        result = handle_killswitch_activation(
            user_id=1,
            reason="Daily loss limit breached: -3.50%",
            positions_closed=2,
            redis_client=mock_redis,
            db_session=mock_db_session,
        )

        assert result is True
        mock_push_notif.assert_called_once_with(
            user_id=1,
            reason="Daily loss limit breached: -3.50%",
            positions_closed=2,
            redis_client=mock_redis,
            db_session=mock_db_session,
        )
        mock_mark_segments.assert_called_once_with(
            user_id=1,
            segments=["NSE", "BSE", "NFO", "BFO"],
            redis_client=mock_redis,
        )

    @patch("src.services.killswitch_integration._mark_segments_deactivated")
    @patch("src.services.killswitch_integration._push_killswitch_notification")
    def test_uses_custom_segments(
        self, mock_push_notif, mock_mark_segments, mock_redis, mock_db_session
    ):
        mock_push_notif.return_value = True
        mock_mark_segments.return_value = True

        handle_killswitch_activation(
            user_id=1,
            reason="test",
            positions_closed=0,
            redis_client=mock_redis,
            db_session=mock_db_session,
            deactivated_segments=["NFO", "BFO"],
        )

        mock_mark_segments.assert_called_once_with(
            user_id=1,
            segments=["NFO", "BFO"],
            redis_client=mock_redis,
        )

    @patch("src.services.killswitch_integration._mark_segments_deactivated")
    @patch("src.services.killswitch_integration._push_killswitch_notification")
    def test_returns_false_if_notification_fails(
        self, mock_push_notif, mock_mark_segments, mock_redis, mock_db_session
    ):
        mock_push_notif.return_value = False
        mock_mark_segments.return_value = True

        result = handle_killswitch_activation(
            user_id=1,
            reason="test",
            positions_closed=0,
            redis_client=mock_redis,
            db_session=mock_db_session,
        )

        # Partial failure: notification failed but segments were marked
        assert result is False

    @patch("src.services.killswitch_integration._mark_segments_deactivated")
    @patch("src.services.killswitch_integration._push_killswitch_notification")
    def test_returns_false_if_segments_fail(
        self, mock_push_notif, mock_mark_segments, mock_redis, mock_db_session
    ):
        mock_push_notif.return_value = True
        mock_mark_segments.return_value = False

        result = handle_killswitch_activation(
            user_id=1,
            reason="test",
            positions_closed=0,
            redis_client=mock_redis,
            db_session=mock_db_session,
        )

        # Partial failure: notification succeeded but segments failed
        assert result is False


class TestSettingsServiceSegmentsWithKillSwitch:
    """Test that SettingsService.get_segments reads kill switch state."""

    @patch("src.services.settings_service.get_redis_client")
    def test_segments_show_killswitch_deactivation(self, mock_get_redis):
        """When kill switch is active, segments should show deactivated_by_killswitch."""
        from src.services.settings_service import SettingsService

        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        # Kill switch is active
        mock_redis.get.side_effect = lambda key: {
            "user:1:killswitch": "true",
            "user:1:killswitch:segments": json.dumps(["NSE", "BSE", "NFO", "BFO"]),
        }.get(key)

        service = SettingsService()
        segments = service.get_segments(1)

        # All segments should show deactivated by kill switch
        for seg in segments:
            assert seg.deactivated_by_killswitch is True
            assert seg.is_active is False

    @patch("src.services.settings_service.get_redis_client")
    def test_segments_normal_when_killswitch_inactive(self, mock_get_redis):
        """When kill switch is not active, segments show normal status."""
        from src.services.settings_service import SettingsService

        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        # Kill switch is not active
        mock_redis.get.side_effect = lambda key: {
            "user:1:killswitch": None,
        }.get(key)

        service = SettingsService()
        segments = service.get_segments(1)

        # No segments should be deactivated by kill switch
        for seg in segments:
            assert seg.deactivated_by_killswitch is False

        # Default activity status
        nse = next(s for s in segments if s.segment == "NSE")
        bfo = next(s for s in segments if s.segment == "BFO")
        assert nse.is_active is True
        assert bfo.is_active is False  # BFO defaults to inactive

    @patch("src.services.settings_service.get_redis_client")
    def test_partial_segment_deactivation(self, mock_get_redis):
        """When only some segments deactivated by kill switch."""
        from src.services.settings_service import SettingsService

        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        # Kill switch active, only NFO deactivated
        mock_redis.get.side_effect = lambda key: {
            "user:1:killswitch": "true",
            "user:1:killswitch:segments": json.dumps(["NFO"]),
        }.get(key)

        service = SettingsService()
        segments = service.get_segments(1)

        nse = next(s for s in segments if s.segment == "NSE")
        nfo = next(s for s in segments if s.segment == "NFO")

        assert nse.deactivated_by_killswitch is False
        assert nse.is_active is True
        assert nfo.deactivated_by_killswitch is True
        assert nfo.is_active is False
