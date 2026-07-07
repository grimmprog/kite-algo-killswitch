"""Tests for TradeJournalService — journal entry creation on trade exit.

Tests the end-to-end flow:
1. Position monitor triggers auto-exit
2. TradeJournalService creates a journal entry with metadata
3. Related signal data (setup_type, confidence_score, trend_direction) is populated

Requirements: 14.5, 7.3-7.6
"""

import json
from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

from src.services.trade_journal_service import TradeJournalService


class TestTradeJournalServiceInit:
    """Tests for TradeJournalService initialization."""

    def test_raises_on_none_db(self):
        """Should raise ValueError when db is None."""
        with pytest.raises(ValueError, match="db cannot be None"):
            TradeJournalService(db=None)

    def test_creates_with_valid_session(self):
        """Should create service with valid db session."""
        mock_db = MagicMock()
        service = TradeJournalService(db=mock_db)
        assert service.db is mock_db


class TestCreateJournalEntryOnExit:
    """Tests for creating journal entries when a trade is exited."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        db = MagicMock()
        return db

    @pytest.fixture
    def service(self, mock_db):
        """Create a TradeJournalService instance."""
        return TradeJournalService(db=mock_db)

    @pytest.fixture
    def mock_trade(self):
        """Create a mock Trade object."""
        trade = MagicMock()
        trade.id = 1
        trade.user_id = 42
        trade.symbol = "NIFTY23DEC19000CE"
        trade.entry_price = 100.0
        trade.qty = 25
        trade.side = "BUY"
        trade.status = "CLOSED"
        return trade

    @pytest.fixture
    def mock_signal(self):
        """Create a mock ScanSignal object."""
        signal = MagicMock()
        signal.signal_type = "trend_pullback"
        signal.confidence_score = 78.5
        signal.metadata_json = {"trend_direction": "bullish"}
        return signal

    def test_creates_entry_with_sl_hit(self, service, mock_db, mock_trade, mock_signal):
        """Should create journal entry with correct data on SL hit exit."""
        # Mock: no existing journal entry
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            None,  # no existing journal entry
            mock_trade,  # trade lookup
        ]
        # Mock: signal lookup returns the mock signal
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = mock_signal

        result = service.create_journal_entry_on_exit(
            trade_id=1,
            user_id=42,
            exit_reason="sl_hit",
            exit_price=90.0,
        )

        # Should have called db.add with a journal entry
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_skips_if_journal_entry_already_exists(self, service, mock_db, mock_trade):
        """Should not create duplicate journal entry for same trade."""
        existing_entry = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = existing_entry

        result = service.create_journal_entry_on_exit(
            trade_id=1,
            user_id=42,
            exit_reason="sl_hit",
            exit_price=90.0,
        )

        assert result is existing_entry
        mock_db.add.assert_not_called()

    def test_returns_none_if_trade_not_found(self, service, mock_db):
        """Should return None if the trade doesn't exist."""
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            None,  # no existing journal entry
            None,  # trade not found
        ]

        result = service.create_journal_entry_on_exit(
            trade_id=999,
            user_id=42,
            exit_reason="target_hit",
            exit_price=120.0,
        )

        assert result is None
        mock_db.add.assert_not_called()

    def test_includes_ai_grade_when_provided(self, service, mock_db, mock_trade):
        """Should include AI grade in journal entry when provided."""
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            None,  # no existing journal entry
            mock_trade,  # trade lookup
        ]
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        service.create_journal_entry_on_exit(
            trade_id=1,
            user_id=42,
            exit_reason="target_hit",
            exit_price=120.0,
            ai_grade="A",
        )

        mock_db.add.assert_called_once()
        added_entry = mock_db.add.call_args[0][0]
        assert added_entry.ai_grade == "A"

    def test_handles_db_error_gracefully(self, service, mock_db, mock_trade):
        """Should return None and rollback on database error."""
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            None,  # no existing journal entry
            mock_trade,  # trade lookup
        ]
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        mock_db.commit.side_effect = Exception("DB error")

        result = service.create_journal_entry_on_exit(
            trade_id=1,
            user_id=42,
            exit_reason="sl_hit",
            exit_price=90.0,
        )

        assert result is None
        mock_db.rollback.assert_called_once()


class TestEnrichWithAIReview:
    """Tests for enriching journal entries with AI review data."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    @pytest.fixture
    def service(self, mock_db):
        return TradeJournalService(db=mock_db)

    def test_enriches_entry_with_ai_data(self, service, mock_db):
        """Should update journal entry with AI grade and feedback."""
        mock_entry = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_entry

        result = service.enrich_with_ai_review(
            journal_entry_id=1,
            ai_grade="B",
            ai_entry_feedback="Good entry timing",
            ai_exit_feedback="Exit was late",
        )

        assert mock_entry.ai_grade == "B"
        assert mock_entry.ai_entry_feedback == "Good entry timing"
        assert mock_entry.ai_exit_feedback == "Exit was late"
        mock_db.commit.assert_called_once()

    def test_returns_none_if_entry_not_found(self, service, mock_db):
        """Should return None if journal entry doesn't exist."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = service.enrich_with_ai_review(
            journal_entry_id=999,
            ai_grade="C",
        )

        assert result is None
        mock_db.commit.assert_not_called()


class TestCreateJournalEntryOnExitHelper:
    """Tests for the _create_journal_entry_on_exit helper in position_monitor_worker."""

    def test_creates_entry_on_auto_exit(self):
        """Should call TradeJournalService when all params are provided."""
        from src.workers.position_monitor_worker import _create_journal_entry_on_exit

        mock_db = MagicMock()
        mock_redis = MagicMock()
        mock_redis.get.return_value = None  # No cached AI data

        with patch(
            "src.workers.position_monitor_worker.TradeJournalService"
        ) as MockService:
            _create_journal_entry_on_exit(
                db_session=mock_db,
                user_id=42,
                trade_id=1,
                exit_reason="sl_hit",
                exit_price=90.0,
                redis_client=mock_redis,
            )

            MockService.assert_called_once_with(db=mock_db)
            MockService.return_value.create_journal_entry_on_exit.assert_called_once_with(
                trade_id=1,
                user_id=42,
                exit_reason="sl_hit",
                exit_price=90.0,
                ai_grade=None,
            )

    def test_skips_when_db_session_is_none(self):
        """Should skip journal creation when db_session is None."""
        from src.workers.position_monitor_worker import _create_journal_entry_on_exit

        with patch(
            "src.workers.position_monitor_worker.TradeJournalService"
        ) as MockService:
            _create_journal_entry_on_exit(
                db_session=None,
                user_id=42,
                trade_id=1,
                exit_reason="sl_hit",
                exit_price=90.0,
            )

            MockService.assert_not_called()

    def test_skips_when_trade_id_is_none(self):
        """Should skip journal creation when trade_id is None."""
        from src.workers.position_monitor_worker import _create_journal_entry_on_exit

        mock_db = MagicMock()

        with patch(
            "src.workers.position_monitor_worker.TradeJournalService"
        ) as MockService:
            _create_journal_entry_on_exit(
                db_session=mock_db,
                user_id=42,
                trade_id=None,
                exit_reason="sl_hit",
                exit_price=90.0,
            )

            MockService.assert_not_called()

    def test_includes_ai_grade_from_redis_cache(self):
        """Should fetch AI grade from Redis and pass to journal service."""
        from src.workers.position_monitor_worker import _create_journal_entry_on_exit

        mock_db = MagicMock()
        mock_redis = MagicMock()
        mock_redis.get.return_value = json.dumps({"grade": "B"})

        with patch(
            "src.workers.position_monitor_worker.TradeJournalService"
        ) as MockService:
            _create_journal_entry_on_exit(
                db_session=mock_db,
                user_id=42,
                trade_id=1,
                exit_reason="target_hit",
                exit_price=120.0,
                redis_client=mock_redis,
            )

            MockService.return_value.create_journal_entry_on_exit.assert_called_once_with(
                trade_id=1,
                user_id=42,
                exit_reason="target_hit",
                exit_price=120.0,
                ai_grade="B",
            )

    def test_handles_exception_gracefully(self):
        """Should catch exceptions and not propagate them."""
        from src.workers.position_monitor_worker import _create_journal_entry_on_exit

        mock_db = MagicMock()
        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        with patch(
            "src.workers.position_monitor_worker.TradeJournalService"
        ) as MockService:
            MockService.side_effect = Exception("Unexpected error")

            # Should not raise
            _create_journal_entry_on_exit(
                db_session=mock_db,
                user_id=42,
                trade_id=1,
                exit_reason="sl_hit",
                exit_price=90.0,
                redis_client=mock_redis,
            )
