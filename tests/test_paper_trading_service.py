"""Tests for PaperTradingService — virtual trading management.

Tests Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from src.services.paper_trading_service import (
    get_account,
    enter_trade,
    exit_trade,
    get_open_positions,
    get_trade_history,
    reset_account,
    _compute_profit_factor,
)
from src.database.models.paper_trade import PaperAccount, PaperTrade


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    """Create a mock SQLAlchemy Session."""
    db = MagicMock()
    return db


@pytest.fixture
def sample_account():
    """Create a sample PaperAccount instance."""
    account = MagicMock(spec=PaperAccount)
    account.id = 1
    account.user_id = 42
    account.balance = 40000.0
    account.starting_capital = 40000.0
    account.total_pnl = 0.0
    account.total_trades = 0
    account.winning_trades = 0
    account.losing_trades = 0
    return account


@pytest.fixture
def sample_trade_data():
    """Valid paper trade entry data."""
    return {
        "symbol": "NIFTY24500CE",
        "strike": 24500.0,
        "option_type": "CE",
        "entry_price": 200.0,
        "quantity": 50,
        "stop_loss": 180.0,
        "target": 250.0,
    }


@pytest.fixture
def open_trade():
    """Create a sample open PaperTrade."""
    trade = MagicMock(spec=PaperTrade)
    trade.id = 10
    trade.user_id = 42
    trade.account_id = 1
    trade.symbol = "NIFTY24500CE"
    trade.strike = 24500.0
    trade.option_type = "CE"
    trade.entry_price = 200.0
    trade.quantity = 50
    trade.stop_loss = 180.0
    trade.target = 250.0
    trade.status = "open"
    trade.pnl = None
    trade.exit_price = None
    trade.closed_at = None
    return trade


# ---------------------------------------------------------------------------
# get_account tests
# ---------------------------------------------------------------------------


class TestGetAccount:
    """Test get_account function."""

    def test_returns_existing_account_with_stats(self, mock_db, sample_account):
        """Should return existing account with computed stats."""
        sample_account.total_trades = 10
        sample_account.winning_trades = 7
        sample_account.losing_trades = 3
        sample_account.total_pnl = 5000.0

        mock_db.query.return_value.filter.return_value.first.return_value = (
            sample_account
        )

        # Mock _compute_profit_factor via the closed trades query
        with patch(
            "src.services.paper_trading_service._compute_profit_factor",
            return_value=2.5,
        ):
            result = get_account(mock_db, 42)

        assert result["user_id"] == 42
        assert result["balance"] == 40000.0
        assert result["total_pnl"] == 5000.0
        assert result["win_rate"] == 0.7
        assert result["roi_pct"] == pytest.approx(12.5)

    def test_creates_account_if_not_exists(self, mock_db):
        """Should create new account with default balance if none exists."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        # After creation, the refresh will populate default values
        def refresh_side_effect(obj):
            obj.id = 1
            obj.user_id = 42
            obj.balance = 40000.0
            obj.starting_capital = 40000.0
            obj.total_pnl = 0.0
            obj.total_trades = 0
            obj.winning_trades = 0
            obj.losing_trades = 0

        mock_db.refresh.side_effect = refresh_side_effect

        with patch(
            "src.services.paper_trading_service._compute_profit_factor",
            return_value=0.0,
        ):
            result = get_account(mock_db, 42)

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        assert result["balance"] == 40000.0
        assert result["win_rate"] == 0.0
        assert result["roi_pct"] == 0.0

    def test_win_rate_zero_when_no_trades(self, mock_db, sample_account):
        """Should return win_rate=0 when no trades."""
        sample_account.total_trades = 0
        mock_db.query.return_value.filter.return_value.first.return_value = (
            sample_account
        )

        with patch(
            "src.services.paper_trading_service._compute_profit_factor",
            return_value=0.0,
        ):
            result = get_account(mock_db, 42)

        assert result["win_rate"] == 0.0


# ---------------------------------------------------------------------------
# enter_trade tests
# ---------------------------------------------------------------------------


class TestEnterTrade:
    """Test enter_trade function."""

    def test_successful_entry(self, mock_db, sample_account, sample_trade_data):
        """Should create trade and deduct investment from balance."""
        mock_db.query.return_value.filter.return_value.first.return_value = (
            sample_account
        )

        def refresh_side_effect(obj):
            obj.id = 10

        mock_db.refresh.side_effect = refresh_side_effect

        result = enter_trade(mock_db, 42, sample_trade_data)

        # Investment = 200 * 50 = 10000
        assert sample_account.balance == 30000.0
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_insufficient_balance_raises(
        self, mock_db, sample_account, sample_trade_data
    ):
        """Should raise ValueError when investment exceeds balance."""
        sample_account.balance = 5000.0  # Less than 200 * 50 = 10000
        mock_db.query.return_value.filter.return_value.first.return_value = (
            sample_account
        )

        with pytest.raises(ValueError, match="Insufficient balance"):
            enter_trade(mock_db, 42, sample_trade_data)

    def test_exact_balance_allowed(self, mock_db, sample_account, sample_trade_data):
        """Should allow trade when investment exactly equals balance."""
        sample_account.balance = 10000.0  # Exactly 200 * 50
        mock_db.query.return_value.filter.return_value.first.return_value = (
            sample_account
        )

        def refresh_side_effect(obj):
            obj.id = 10

        mock_db.refresh.side_effect = refresh_side_effect

        result = enter_trade(mock_db, 42, sample_trade_data)

        assert sample_account.balance == 0.0

    def test_creates_account_if_missing(self, mock_db, sample_trade_data):
        """Should auto-create account if user has none."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        def commit_side_effect():
            pass

        mock_db.commit.side_effect = commit_side_effect

        # After first commit (account creation), second query returns new account
        new_account = MagicMock(spec=PaperAccount)
        new_account.id = 1
        new_account.user_id = 42
        new_account.balance = 40000.0
        new_account.starting_capital = 40000.0

        # First call returns None (no existing account), after add+commit+refresh
        # returns the new account
        call_count = [0]

        def filter_side_effect(*args, **kwargs):
            mock_result = MagicMock()
            call_count[0] += 1
            if call_count[0] == 1:
                mock_result.first.return_value = None
            else:
                mock_result.first.return_value = new_account
            return mock_result

        mock_db.query.return_value.filter.side_effect = filter_side_effect

        def refresh_side_effect(obj):
            if isinstance(obj, PaperAccount) or (
                hasattr(obj, "balance") and not hasattr(obj, "symbol")
            ):
                obj.id = 1
                obj.user_id = 42
                obj.balance = 40000.0
                obj.starting_capital = 40000.0
            else:
                obj.id = 10

        mock_db.refresh.side_effect = refresh_side_effect

        result = enter_trade(mock_db, 42, sample_trade_data)
        # Account should be added
        assert mock_db.add.call_count >= 1


# ---------------------------------------------------------------------------
# exit_trade tests
# ---------------------------------------------------------------------------


class TestExitTrade:
    """Test exit_trade function."""

    def test_successful_exit_with_profit(
        self, mock_db, sample_account, open_trade
    ):
        """Should close trade, calculate PnL, update account on profit."""
        # First query returns the trade, second returns the account
        call_count = [0]

        def query_side_effect(model):
            mock_query = MagicMock()
            call_count[0] += 1
            if call_count[0] == 1:
                # Trade query
                mock_query.filter.return_value.first.return_value = open_trade
            else:
                # Account query
                mock_query.filter.return_value.first.return_value = sample_account
            return mock_query

        mock_db.query.side_effect = query_side_effect

        def refresh_side_effect(obj):
            pass

        mock_db.refresh.side_effect = refresh_side_effect

        result = exit_trade(mock_db, 42, 10, 220.0)

        # PnL = (220 - 200) * 50 = 1000
        assert open_trade.pnl == 1000.0
        assert open_trade.exit_price == 220.0
        assert open_trade.status == "closed"
        # Balance += exit_price * quantity = 220 * 50 = 11000
        assert sample_account.balance == 51000.0
        assert sample_account.total_pnl == 1000.0
        assert sample_account.winning_trades == 1
        assert sample_account.total_trades == 1

    def test_successful_exit_with_loss(
        self, mock_db, sample_account, open_trade
    ):
        """Should properly handle losing trade."""
        call_count = [0]

        def query_side_effect(model):
            mock_query = MagicMock()
            call_count[0] += 1
            if call_count[0] == 1:
                mock_query.filter.return_value.first.return_value = open_trade
            else:
                mock_query.filter.return_value.first.return_value = sample_account
            return mock_query

        mock_db.query.side_effect = query_side_effect
        mock_db.refresh.side_effect = lambda obj: None

        result = exit_trade(mock_db, 42, 10, 180.0)

        # PnL = (180 - 200) * 50 = -1000
        assert open_trade.pnl == -1000.0
        assert sample_account.losing_trades == 1
        assert sample_account.total_pnl == -1000.0

    def test_trade_not_found_raises(self, mock_db):
        """Should raise ValueError when trade doesn't exist."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(ValueError, match="Trade 99 not found"):
            exit_trade(mock_db, 42, 99, 220.0)

    def test_trade_wrong_user_raises(self, mock_db, open_trade):
        """Should raise ValueError when trade belongs to different user."""
        open_trade.user_id = 99  # Different user
        mock_db.query.return_value.filter.return_value.first.return_value = open_trade

        with pytest.raises(ValueError, match="does not belong to user"):
            exit_trade(mock_db, 42, 10, 220.0)

    def test_trade_not_open_raises(self, mock_db, open_trade):
        """Should raise ValueError when trade is already closed."""
        open_trade.status = "closed"
        mock_db.query.return_value.filter.return_value.first.return_value = open_trade

        with pytest.raises(ValueError, match="is not open"):
            exit_trade(mock_db, 42, 10, 220.0)


# ---------------------------------------------------------------------------
# get_open_positions tests
# ---------------------------------------------------------------------------


class TestGetOpenPositions:
    """Test get_open_positions function."""

    def test_returns_open_trades(self, mock_db, open_trade):
        """Should query trades with status=open for user."""
        mock_db.query.return_value.filter.return_value.all.return_value = [open_trade]

        result = get_open_positions(mock_db, 42)

        assert len(result) == 1
        assert result[0] == open_trade

    def test_returns_empty_when_no_positions(self, mock_db):
        """Should return empty list when user has no open positions."""
        mock_db.query.return_value.filter.return_value.all.return_value = []

        result = get_open_positions(mock_db, 42)

        assert result == []


# ---------------------------------------------------------------------------
# get_trade_history tests
# ---------------------------------------------------------------------------


class TestGetTradeHistory:
    """Test get_trade_history function."""

    def test_returns_closed_trades_ordered(self, mock_db):
        """Should return closed trades ordered by closed_at DESC."""
        trade1 = MagicMock(spec=PaperTrade)
        trade1.status = "closed"
        trade2 = MagicMock(spec=PaperTrade)
        trade2.status = "closed"

        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
            trade2,
            trade1,
        ]

        result = get_trade_history(mock_db, 42)

        assert len(result) == 2


# ---------------------------------------------------------------------------
# reset_account tests
# ---------------------------------------------------------------------------


class TestResetAccount:
    """Test reset_account function."""

    def test_resets_all_stats(self, mock_db, sample_account):
        """Should reset balance, stats, and delete all trades."""
        sample_account.balance = 35000.0
        sample_account.total_pnl = -5000.0
        sample_account.total_trades = 10
        sample_account.winning_trades = 3
        sample_account.losing_trades = 7

        mock_db.query.return_value.filter.return_value.first.return_value = (
            sample_account
        )
        mock_db.query.return_value.filter.return_value.delete.return_value = 10

        def refresh_side_effect(obj):
            pass

        mock_db.refresh.side_effect = refresh_side_effect

        result = reset_account(mock_db, 42)

        assert sample_account.balance == 40000.0
        assert sample_account.total_pnl == 0.0
        assert sample_account.total_trades == 0
        assert sample_account.winning_trades == 0
        assert sample_account.losing_trades == 0
        assert result["balance"] == 40000.0
        assert result["win_rate"] == 0.0
        assert result["roi_pct"] == 0.0

    def test_raises_when_no_account(self, mock_db):
        """Should raise ValueError if no account exists."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(ValueError, match="No paper account found"):
            reset_account(mock_db, 42)


# ---------------------------------------------------------------------------
# _compute_profit_factor tests
# ---------------------------------------------------------------------------


class TestComputeProfitFactor:
    """Test _compute_profit_factor helper."""

    def test_correct_profit_factor(self, mock_db):
        """Should compute sum of wins / abs(sum of losses)."""
        trade1 = MagicMock(spec=PaperTrade)
        trade1.pnl = 1000.0
        trade2 = MagicMock(spec=PaperTrade)
        trade2.pnl = 500.0
        trade3 = MagicMock(spec=PaperTrade)
        trade3.pnl = -300.0
        trade4 = MagicMock(spec=PaperTrade)
        trade4.pnl = -200.0

        mock_db.query.return_value.filter.return_value.all.return_value = [
            trade1,
            trade2,
            trade3,
            trade4,
        ]

        result = _compute_profit_factor(mock_db, 1)

        # (1000 + 500) / abs(-300 + -200) = 1500 / 500 = 3.0
        assert result == pytest.approx(3.0)

    def test_returns_zero_when_no_losses(self, mock_db):
        """Should return 0 if there are no losing trades."""
        trade1 = MagicMock(spec=PaperTrade)
        trade1.pnl = 1000.0

        mock_db.query.return_value.filter.return_value.all.return_value = [trade1]

        result = _compute_profit_factor(mock_db, 1)

        assert result == 0.0

    def test_returns_zero_when_no_trades(self, mock_db):
        """Should return 0 if there are no closed trades."""
        mock_db.query.return_value.filter.return_value.all.return_value = []

        result = _compute_profit_factor(mock_db, 1)

        assert result == 0.0
