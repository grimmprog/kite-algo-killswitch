"""Tests for signal_expiry_worker — periodic signal countdown expiry check.

Tests Requirements: 4.5, 4.6
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from src.workers.signal_expiry_worker import (
    check_signal_expiry,
    _execute_check_signal_expiry,
    _signal_expiry_key,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_redis():
    """Create a mock RedisClient."""
    redis = MagicMock()
    redis.ttl.return_value = -2  # Key doesn't exist (expired)
    redis.delete.return_value = 1
    return redis


@pytest.fixture
def make_pending_signal():
    """Factory for creating mock pending signal objects."""

    def _make(signal_id=1, user_id=1, symbol="NIFTY24500CE", expires_at=None):
        signal = MagicMock()
        signal.id = signal_id
        signal.user_id = user_id
        signal.symbol = symbol
        signal.status = "pending"
        signal.expires_at = expires_at or (
            datetime.now(timezone.utc) - timedelta(seconds=10)
        )
        signal.updated_at = datetime.now(timezone.utc)
        return signal

    return _make


# ---------------------------------------------------------------------------
# Helper tests
# ---------------------------------------------------------------------------


class TestSignalExpiryKey:
    """Test the Redis key construction helper."""

    def test_builds_correct_key(self):
        """Should build key with correct prefix and signal ID."""
        assert _signal_expiry_key(42) == "signal_expiry:42"

    def test_builds_key_for_id_1(self):
        """Should build key for signal ID 1."""
        assert _signal_expiry_key(1) == "signal_expiry:1"


# ---------------------------------------------------------------------------
# Core logic tests
# ---------------------------------------------------------------------------


class TestExecuteCheckSignalExpiry:
    """Test the internal _execute_check_signal_expiry logic."""

    @patch("src.workers.signal_expiry_worker._get_db_session")
    @patch("src.workers.signal_expiry_worker.get_redis_client")
    def test_no_pending_signals(self, mock_get_redis, mock_get_session):
        """Should return success with zero counts when no pending signals."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_get_session.return_value = mock_db
        mock_get_redis.return_value = MagicMock()

        result = _execute_check_signal_expiry()

        assert result["status"] == "success"
        assert result["expired_count"] == 0
        assert result["pending_checked"] == 0
        assert result["reason"] == "No pending signals"
        mock_db.close.assert_called_once()

    @patch("src.workers.signal_expiry_worker._get_db_session")
    @patch("src.workers.signal_expiry_worker.get_redis_client")
    def test_expires_signal_when_redis_key_gone(
        self, mock_get_redis, mock_get_session, make_pending_signal
    ):
        """Should expire signal when Redis TTL key no longer exists (ttl=-2)."""
        signal = make_pending_signal(signal_id=5, expires_at=datetime.now(timezone.utc) + timedelta(seconds=30))
        mock_redis = MagicMock()
        mock_redis.ttl.return_value = -2  # Key expired/gone

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [signal]
        mock_get_session.return_value = mock_db
        mock_get_redis.return_value = mock_redis

        result = _execute_check_signal_expiry()

        assert result["status"] == "success"
        assert result["expired_count"] == 1
        assert result["pending_checked"] == 1
        assert signal.status == "expired"
        mock_db.commit.assert_called_once()
        mock_db.close.assert_called_once()

    @patch("src.workers.signal_expiry_worker._get_db_session")
    @patch("src.workers.signal_expiry_worker.get_redis_client")
    def test_does_not_expire_signal_with_active_ttl(
        self, mock_get_redis, mock_get_session, make_pending_signal
    ):
        """Should not expire signal when Redis TTL key still has time remaining."""
        signal = make_pending_signal(
            signal_id=3,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=30),
        )
        mock_redis = MagicMock()
        mock_redis.ttl.return_value = 25  # Still 25 seconds remaining

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [signal]
        mock_get_session.return_value = mock_db
        mock_get_redis.return_value = mock_redis

        result = _execute_check_signal_expiry()

        assert result["status"] == "success"
        assert result["expired_count"] == 0
        assert result["pending_checked"] == 1
        assert signal.status == "pending"
        mock_db.commit.assert_not_called()
        mock_db.close.assert_called_once()

    @patch("src.workers.signal_expiry_worker._get_db_session")
    @patch("src.workers.signal_expiry_worker.get_redis_client")
    def test_expires_signal_via_timestamp_fallback(
        self, mock_get_redis, mock_get_session, make_pending_signal
    ):
        """Should expire signal via expires_at fallback when Redis key exists but time passed."""
        past_time = datetime.now(timezone.utc) - timedelta(seconds=10)
        signal = make_pending_signal(signal_id=7, expires_at=past_time)

        mock_redis = MagicMock()
        # Key exists with no TTL (unusual but possible after Redis restart)
        mock_redis.ttl.return_value = -1

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [signal]
        mock_get_session.return_value = mock_db
        mock_get_redis.return_value = mock_redis

        result = _execute_check_signal_expiry()

        assert result["status"] == "success"
        assert result["expired_count"] == 1
        assert signal.status == "expired"
        mock_db.commit.assert_called_once()

    @patch("src.workers.signal_expiry_worker._get_db_session")
    @patch("src.workers.signal_expiry_worker.get_redis_client")
    def test_multiple_signals_mixed_expiry(
        self, mock_get_redis, mock_get_session, make_pending_signal
    ):
        """Should correctly handle mix of expired and active signals."""
        expired_signal = make_pending_signal(signal_id=1)
        active_signal = make_pending_signal(
            signal_id=2,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=30),
        )

        mock_redis = MagicMock()
        # Signal 1: key gone (expired), Signal 2: key still has TTL
        mock_redis.ttl.side_effect = [-2, 20]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [
            expired_signal,
            active_signal,
        ]
        mock_get_session.return_value = mock_db
        mock_get_redis.return_value = mock_redis

        result = _execute_check_signal_expiry()

        assert result["status"] == "success"
        assert result["expired_count"] == 1
        assert result["pending_checked"] == 2
        assert expired_signal.status == "expired"
        assert active_signal.status == "pending"
        mock_db.commit.assert_called_once()

    @patch("src.workers.signal_expiry_worker._get_db_session")
    @patch("src.workers.signal_expiry_worker.get_redis_client")
    def test_cleans_up_redis_key_on_expiry(
        self, mock_get_redis, mock_get_session, make_pending_signal
    ):
        """Should defensively delete the Redis key when expiring a signal."""
        signal = make_pending_signal(signal_id=10)
        mock_redis = MagicMock()
        mock_redis.ttl.return_value = -2

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [signal]
        mock_get_session.return_value = mock_db
        mock_get_redis.return_value = mock_redis

        _execute_check_signal_expiry()

        mock_redis.delete.assert_called_once_with("signal_expiry:10")


# ---------------------------------------------------------------------------
# Task wrapper tests
# ---------------------------------------------------------------------------


class TestCheckSignalExpiryTask:
    """Test the Celery task wrapper (check_signal_expiry)."""

    @patch("src.workers.signal_expiry_worker._execute_check_signal_expiry")
    def test_returns_result_on_success(self, mock_execute):
        """Should return the result from _execute_check_signal_expiry."""
        mock_execute.return_value = {
            "status": "success",
            "expired_count": 2,
            "pending_checked": 5,
            "reason": "Expired 2 signals",
        }

        result = check_signal_expiry()

        assert result["status"] == "success"
        assert result["expired_count"] == 2

    @patch("src.workers.signal_expiry_worker._execute_check_signal_expiry")
    def test_catches_unexpected_exceptions(self, mock_execute):
        """Should catch and return error on unexpected exception."""
        mock_execute.side_effect = RuntimeError("Database connection failed")

        result = check_signal_expiry()

        assert result["status"] == "error"
        assert result["expired_count"] == 0
        assert "RuntimeError" in result["reason"]


# ---------------------------------------------------------------------------
# Beat schedule integration test
# ---------------------------------------------------------------------------


class TestCeleryBeatSchedule:
    """Verify the signal expiry task is registered in Celery beat schedule."""

    def test_signal_expiry_in_beat_schedule(self):
        """Should have check-signal-expiry-every-5s in beat schedule."""
        from src.workers.celery_app import celery_app

        schedule = celery_app.conf.beat_schedule
        assert "check-signal-expiry-every-5s" in schedule

        entry = schedule["check-signal-expiry-every-5s"]
        assert entry["task"] == "src.workers.signal_expiry_worker.check_signal_expiry"
        assert entry["schedule"] == 5.0
