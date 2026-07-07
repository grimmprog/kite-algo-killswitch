"""Tests for SignalService — signal lifecycle management.

Tests Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call

import pytest

from src.services.signal_service import SignalService, _signal_expiry_key


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    """Create a mock SQLAlchemy Session."""
    db = MagicMock()
    return db


@pytest.fixture
def mock_redis():
    """Create a mock RedisClient."""
    redis = MagicMock()
    redis.set.return_value = True
    redis.delete.return_value = 1
    redis.ttl.return_value = 45
    return redis


@pytest.fixture
def service(mock_db, mock_redis):
    """Create a SignalService with mocked dependencies."""
    return SignalService(db=mock_db, redis_client=mock_redis)


@pytest.fixture
def sample_signal_data():
    """Valid scan signal data dictionary."""
    return {
        "signal_type": "trend_pullback",
        "symbol": "NIFTY24500CE",
        "confidence_score": 75.0,
        "entry_price": 250.0,
        "stop_loss": 230.0,
        "target_price": 290.0,
        "max_potential_loss": 2000.0,
        "ai_quality_rating": "Strong Setup",
        "ai_warnings": ["Near resistance"],
        "ai_explanation": "Good momentum with volume confirmation.",
        "metadata": {"trend_direction": "bullish"},
    }


# ---------------------------------------------------------------------------
# Initialization tests
# ---------------------------------------------------------------------------


class TestSignalServiceInit:
    """Test SignalService initialization validation."""

    def test_raises_on_none_db(self, mock_redis):
        """Should raise ValueError if db is None."""
        with pytest.raises(ValueError, match="db cannot be None"):
            SignalService(db=None, redis_client=mock_redis)

    def test_raises_on_none_redis(self, mock_db):
        """Should raise ValueError if redis_client is None."""
        with pytest.raises(ValueError, match="redis_client cannot be None"):
            SignalService(db=mock_db, redis_client=None)

    def test_successful_init(self, mock_db, mock_redis):
        """Should initialize successfully with valid dependencies."""
        svc = SignalService(db=mock_db, redis_client=mock_redis)
        assert svc.db is mock_db
        assert svc.redis is mock_redis


# ---------------------------------------------------------------------------
# create_signal tests
# ---------------------------------------------------------------------------


class TestCreateSignal:
    """Test signal creation with countdown timer."""

    def test_creates_signal_in_db(self, service, mock_db, sample_signal_data):
        """Should add a ScanSignal to the DB session and commit."""
        service.create_signal(user_id=1, scan_signal_data=sample_signal_data)

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

    def test_sets_redis_ttl_key(self, service, mock_db, mock_redis, sample_signal_data):
        """Should set a Redis key with TTL for countdown tracking."""
        # Make refresh set an id on the signal
        def set_id(signal):
            signal.id = 42

        mock_db.refresh.side_effect = set_id

        service.create_signal(
            user_id=1, scan_signal_data=sample_signal_data, countdown_seconds=30
        )

        mock_redis.set.assert_called_once_with("signal_expiry:42", "42", ttl=30)

    def test_signal_has_pending_status(self, service, mock_db, sample_signal_data):
        """Created signal should have status='pending'."""
        service.create_signal(user_id=1, scan_signal_data=sample_signal_data)

        # Check the signal passed to db.add
        added_signal = mock_db.add.call_args[0][0]
        assert added_signal.status == "pending"

    def test_signal_has_correct_expires_at(self, service, mock_db, sample_signal_data):
        """Created signal should have expires_at set to now + countdown_seconds."""
        service.create_signal(
            user_id=1, scan_signal_data=sample_signal_data, countdown_seconds=90
        )

        added_signal = mock_db.add.call_args[0][0]
        assert added_signal.expires_at is not None
        assert added_signal.countdown_seconds == 90

    def test_uses_default_countdown(self, service, mock_db, sample_signal_data):
        """Default countdown should be 60 seconds."""
        service.create_signal(user_id=1, scan_signal_data=sample_signal_data)

        added_signal = mock_db.add.call_args[0][0]
        assert added_signal.countdown_seconds == 60

    def test_maps_all_fields_from_data(self, service, mock_db, sample_signal_data):
        """All fields from scan_signal_data should be mapped to the model."""
        service.create_signal(user_id=1, scan_signal_data=sample_signal_data)

        added_signal = mock_db.add.call_args[0][0]
        assert added_signal.symbol == "NIFTY24500CE"
        assert added_signal.signal_type == "trend_pullback"
        assert added_signal.confidence_score == 75.0
        assert added_signal.entry_price == 250.0
        assert added_signal.stop_loss == 230.0
        assert added_signal.target_price == 290.0
        assert added_signal.max_potential_loss == 2000.0
        assert added_signal.ai_quality_rating == "Strong Setup"
        assert added_signal.ai_warnings == ["Near resistance"]
        assert added_signal.ai_explanation == "Good momentum with volume confirmation."
        assert added_signal.metadata_json == {"trend_direction": "bullish"}


# ---------------------------------------------------------------------------
# approve_signal tests
# ---------------------------------------------------------------------------


class TestApproveSignal:
    """Test signal approval flow."""

    def _mock_pending_signal(self, mock_db, signal_id=1, user_id=1):
        """Set up a mock pending signal in the DB."""
        signal = MagicMock()
        signal.id = signal_id
        signal.user_id = user_id
        signal.status = "pending"
        signal.symbol = "NIFTY24500CE"
        signal.entry_price = 250.0
        signal.stop_loss = 230.0
        signal.target_price = 290.0
        signal.signal_type = "trend_pullback"
        signal.confidence_score = 75.0
        mock_db.query.return_value.filter.return_value.first.return_value = signal
        return signal

    def test_approves_pending_signal(self, service, mock_db, mock_redis):
        """Should update status to 'approved' and commit."""
        signal = self._mock_pending_signal(mock_db)

        result = service.approve_signal(signal_id=1, user_id=1)

        assert signal.status == "approved"
        mock_db.commit.assert_called_once()
        assert result["signal_id"] == 1
        assert result["symbol"] == "NIFTY24500CE"

    def test_deletes_redis_key_on_approve(self, service, mock_db, mock_redis):
        """Should delete the Redis TTL key after approval."""
        self._mock_pending_signal(mock_db)

        service.approve_signal(signal_id=1, user_id=1)

        mock_redis.delete.assert_called_once_with("signal_expiry:1")

    def test_returns_trade_execution_data(self, service, mock_db, mock_redis):
        """Should return dict with trade execution fields."""
        self._mock_pending_signal(mock_db)

        result = service.approve_signal(signal_id=1, user_id=1)

        assert result == {
            "signal_id": 1,
            "symbol": "NIFTY24500CE",
            "entry_price": 250.0,
            "stop_loss": 230.0,
            "target_price": 290.0,
            "signal_type": "trend_pullback",
            "confidence_score": 75.0,
        }

    def test_raises_if_signal_not_found(self, service, mock_db):
        """Should raise ValueError if signal doesn't exist."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(ValueError, match="not found"):
            service.approve_signal(signal_id=99, user_id=1)

    def test_raises_if_wrong_user(self, service, mock_db):
        """Should raise ValueError if signal belongs to different user."""
        self._mock_pending_signal(mock_db, user_id=2)

        with pytest.raises(ValueError, match="does not belong to user"):
            service.approve_signal(signal_id=1, user_id=1)

    def test_raises_if_not_pending(self, service, mock_db):
        """Should raise ValueError if signal is not in pending state."""
        signal = self._mock_pending_signal(mock_db)
        signal.status = "expired"

        with pytest.raises(ValueError, match="not pending"):
            service.approve_signal(signal_id=1, user_id=1)


# ---------------------------------------------------------------------------
# reject_signal tests
# ---------------------------------------------------------------------------


class TestRejectSignal:
    """Test signal rejection flow."""

    def _mock_pending_signal(self, mock_db, signal_id=1, user_id=1):
        signal = MagicMock()
        signal.id = signal_id
        signal.user_id = user_id
        signal.status = "pending"
        mock_db.query.return_value.filter.return_value.first.return_value = signal
        return signal

    def test_rejects_pending_signal(self, service, mock_db, mock_redis):
        """Should update status to 'rejected' and commit."""
        signal = self._mock_pending_signal(mock_db)

        result = service.reject_signal(signal_id=1, user_id=1)

        assert signal.status == "rejected"
        mock_db.commit.assert_called_once()
        assert result == {"signal_id": 1, "status": "rejected"}

    def test_deletes_redis_key_on_reject(self, service, mock_db, mock_redis):
        """Should delete the Redis TTL key after rejection."""
        self._mock_pending_signal(mock_db)

        service.reject_signal(signal_id=1, user_id=1)

        mock_redis.delete.assert_called_once_with("signal_expiry:1")

    def test_raises_if_signal_not_found(self, service, mock_db):
        """Should raise ValueError if signal doesn't exist."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(ValueError, match="not found"):
            service.reject_signal(signal_id=99, user_id=1)

    def test_raises_if_wrong_user(self, service, mock_db):
        """Should raise ValueError if signal belongs to different user."""
        self._mock_pending_signal(mock_db, user_id=2)

        with pytest.raises(ValueError, match="does not belong to user"):
            service.reject_signal(signal_id=1, user_id=1)

    def test_raises_if_not_pending(self, service, mock_db):
        """Should raise ValueError if signal is already rejected/approved."""
        signal = self._mock_pending_signal(mock_db)
        signal.status = "approved"

        with pytest.raises(ValueError, match="not pending"):
            service.reject_signal(signal_id=1, user_id=1)


# ---------------------------------------------------------------------------
# expire_signal tests
# ---------------------------------------------------------------------------


class TestExpireSignal:
    """Test signal expiry (background worker flow)."""

    def _mock_pending_signal(self, mock_db, signal_id=1):
        signal = MagicMock()
        signal.id = signal_id
        signal.status = "pending"
        mock_db.query.return_value.filter.return_value.first.return_value = signal
        return signal

    def test_expires_pending_signal(self, service, mock_db, mock_redis):
        """Should update status to 'expired' and commit."""
        signal = self._mock_pending_signal(mock_db)

        result = service.expire_signal(signal_id=1)

        assert signal.status == "expired"
        mock_db.commit.assert_called_once()
        assert result == {"signal_id": 1, "status": "expired"}

    def test_deletes_redis_key_defensively(self, service, mock_db, mock_redis):
        """Should attempt to delete Redis key (even if already expired)."""
        self._mock_pending_signal(mock_db)

        service.expire_signal(signal_id=1)

        mock_redis.delete.assert_called_once_with("signal_expiry:1")

    def test_raises_if_signal_not_found(self, service, mock_db):
        """Should raise ValueError if signal doesn't exist."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(ValueError, match="not found"):
            service.expire_signal(signal_id=99)

    def test_raises_if_not_pending(self, service, mock_db):
        """Should raise ValueError if signal is already expired."""
        signal = self._mock_pending_signal(mock_db)
        signal.status = "expired"

        with pytest.raises(ValueError, match="not pending"):
            service.expire_signal(signal_id=1)


# ---------------------------------------------------------------------------
# get_pending_signals tests
# ---------------------------------------------------------------------------


class TestGetPendingSignals:
    """Test fetching pending signals with remaining countdown."""

    def _make_mock_signal(self, signal_id, symbol="NIFTY24500CE"):
        """Create a mock ScanSignal object."""
        signal = MagicMock()
        signal.id = signal_id
        signal.symbol = symbol
        signal.signal_type = "trend_pullback"
        signal.confidence_score = 80.0
        signal.entry_price = 250.0
        signal.stop_loss = 230.0
        signal.target_price = 290.0
        signal.max_potential_loss = 2000.0
        signal.status = "pending"
        signal.countdown_seconds = 60
        signal.expires_at = datetime(2024, 1, 1, 10, 1, 0, tzinfo=timezone.utc)
        signal.created_at = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        signal.ai_quality_rating = "Strong Setup"
        signal.ai_warnings = None
        signal.ai_explanation = None
        return signal

    def test_returns_list_with_remaining_seconds(self, service, mock_db, mock_redis):
        """Should return signals with remaining_seconds from Redis TTL."""
        signals = [self._make_mock_signal(1), self._make_mock_signal(2)]
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = signals

        # TTL returns different values for each key
        mock_redis.ttl.side_effect = [45, 20]

        result = service.get_pending_signals(user_id=1)

        assert len(result) == 2
        assert result[0]["remaining_seconds"] == 45
        assert result[1]["remaining_seconds"] == 20

    def test_returns_zero_remaining_when_ttl_expired(
        self, service, mock_db, mock_redis
    ):
        """Should return remaining_seconds=0 when Redis key is gone."""
        signals = [self._make_mock_signal(1)]
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = signals

        # TTL of -2 means key doesn't exist
        mock_redis.ttl.return_value = -2

        result = service.get_pending_signals(user_id=1)

        assert result[0]["remaining_seconds"] == 0

    def test_returns_empty_list_when_no_pending(self, service, mock_db, mock_redis):
        """Should return empty list if no pending signals exist."""
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

        result = service.get_pending_signals(user_id=1)

        assert result == []

    def test_includes_all_signal_fields(self, service, mock_db, mock_redis):
        """Should include all expected fields in each result dict."""
        signals = [self._make_mock_signal(1)]
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = signals
        mock_redis.ttl.return_value = 30

        result = service.get_pending_signals(user_id=1)

        item = result[0]
        assert item["id"] == 1
        assert item["symbol"] == "NIFTY24500CE"
        assert item["signal_type"] == "trend_pullback"
        assert item["confidence_score"] == 80.0
        assert item["entry_price"] == 250.0
        assert item["stop_loss"] == 230.0
        assert item["target_price"] == 290.0
        assert item["max_potential_loss"] == 2000.0
        assert item["status"] == "pending"
        assert item["countdown_seconds"] == 60
        assert item["remaining_seconds"] == 30
        assert item["ai_quality_rating"] == "Strong Setup"


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestSignalExpiryKey:
    """Test the Redis key builder."""

    def test_builds_correct_key(self):
        """Should return 'signal_expiry:{id}' format."""
        assert _signal_expiry_key(42) == "signal_expiry:42"
        assert _signal_expiry_key(1) == "signal_expiry:1"
