"""Property-based tests for PaperTradingService (Task 5.4).

Uses Hypothesis to verify:
- Property 10: Paper Trade Balance Integrity — Verify entry acceptance, balance change on exit, reset behavior
- Property 11: Paper Account Statistics Correctness — Verify win_rate, profit_factor, ROI formulas

**Validates: Requirements 9.1, 9.3, 9.5, 9.7**
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from hypothesis import given, strategies as st, settings, assume
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime, timezone

from src.services.paper_trading_service import (
    enter_trade,
    exit_trade,
    reset_account,
    get_account,
    _compute_profit_factor,
)


# ============================================================
# Helpers for mock setup
# ============================================================


def _make_mock_account(
    user_id=1,
    account_id=1,
    balance=40000.0,
    starting_capital=40000.0,
    total_pnl=0.0,
    total_trades=0,
    winning_trades=0,
    losing_trades=0,
):
    """Create a mock PaperAccount object."""
    account = MagicMock()
    account.id = account_id
    account.user_id = user_id
    account.balance = balance
    account.starting_capital = starting_capital
    account.total_pnl = total_pnl
    account.total_trades = total_trades
    account.winning_trades = winning_trades
    account.losing_trades = losing_trades
    account.updated_at = datetime.now(timezone.utc)
    return account


def _make_mock_trade(
    trade_id=1,
    user_id=1,
    account_id=1,
    entry_price=100.0,
    quantity=10,
    status="open",
    pnl=None,
    exit_price=None,
):
    """Create a mock PaperTrade object."""
    trade = MagicMock()
    trade.id = trade_id
    trade.user_id = user_id
    trade.account_id = account_id
    trade.entry_price = entry_price
    trade.quantity = quantity
    trade.status = status
    trade.pnl = pnl
    trade.exit_price = exit_price
    trade.symbol = "NIFTY"
    trade.option_type = "CE"
    trade.strike = 20000.0
    trade.stop_loss = 90.0
    trade.target = 120.0
    return trade


def _make_mock_db_session(account=None, trade=None, closed_trades=None):
    """Create a mock SQLAlchemy session."""
    db = MagicMock()

    # Set up query chain for account lookup
    query_mock = MagicMock()
    filter_mock = MagicMock()
    filter_mock.first.return_value = account

    query_mock.filter.return_value = filter_mock
    db.query.return_value = query_mock

    if trade is not None:
        # We need special handling when both account and trade queries happen
        pass

    return db


# ============================================================
# Property 10: Paper Trade Balance Integrity
# ============================================================


class TestPaperTradeBalanceIntegrity:
    """Property-based tests for paper trade balance correctness.

    **Validates: Requirements 9.1, 9.3, 9.5, 9.7**

    Core invariants:
    - Trade accepted iff entry_price × quantity <= available balance
    - After exit: balance changes by exit_price × quantity (credit back)
    - Reset: balance equals starting_capital
    """

    @given(
        entry_price=st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        quantity=st.integers(min_value=1, max_value=100),
        balance=st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100, deadline=None)
    def test_trade_accepted_iff_investment_within_balance(self, entry_price, quantity, balance):
        """Trade is accepted iff entry_price × quantity <= balance.

        **Validates: Requirements 9.3**

        Property: For any positive entry_price, quantity, and balance,
        enter_trade succeeds iff investment <= balance, and raises ValueError otherwise.
        """
        investment = entry_price * quantity
        account = _make_mock_account(balance=balance)

        db = MagicMock()
        # Setup query chain: first call for account lookup
        query_mock = MagicMock()
        filter_mock = MagicMock()
        filter_mock.first.return_value = account
        query_mock.filter.return_value = filter_mock
        db.query.return_value = query_mock

        trade_data = {
            "symbol": "NIFTY",
            "strike": 20000.0,
            "option_type": "CE",
            "entry_price": entry_price,
            "quantity": quantity,
            "stop_loss": entry_price * 0.9,
            "target": entry_price * 1.2,
        }

        if investment <= balance:
            # Should succeed — trade is accepted
            result = enter_trade(db, 1, trade_data)
            # Balance should be deducted by investment amount
            assert abs(account.balance - (balance - investment)) < 1e-6, (
                f"Expected balance={balance - investment}, got {account.balance}"
            )
        else:
            # Should raise ValueError for insufficient balance
            with pytest.raises(ValueError, match="Insufficient balance"):
                enter_trade(db, 1, trade_data)

    @given(
        entry_price=st.floats(min_value=1.0, max_value=500.0, allow_nan=False, allow_infinity=False),
        exit_price=st.floats(min_value=0.5, max_value=1000.0, allow_nan=False, allow_infinity=False),
        quantity=st.integers(min_value=1, max_value=50),
        initial_balance=st.floats(min_value=10000.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100, deadline=None)
    def test_balance_change_on_exit(self, entry_price, exit_price, quantity, initial_balance):
        """After exit: balance increases by exit_price × quantity.

        **Validates: Requirements 9.5**

        Property: When a trade is exited, the account balance increases by
        exit_price × quantity (the proceeds from closing the position).
        The PnL is (exit_price - entry_price) × quantity.
        """
        # Ensure the trade was affordable
        investment = entry_price * quantity
        assume(investment <= initial_balance)

        # Simulate balance after entry (deducted)
        balance_after_entry = initial_balance - investment

        # Create mock trade
        trade = _make_mock_trade(
            trade_id=1, user_id=1, entry_price=entry_price, quantity=quantity, status="open"
        )
        account = _make_mock_account(balance=balance_after_entry)

        db = MagicMock()

        # Setup: db.query(PaperTrade).filter(...).first() returns trade
        # Then: db.query(PaperAccount).filter(...).first() returns account
        call_count = [0]

        def mock_query(model):
            mock_q = MagicMock()
            mock_f = MagicMock()

            if call_count[0] == 0:
                # First query is for PaperTrade
                mock_f.first.return_value = trade
                call_count[0] += 1
            else:
                # Second query is for PaperAccount
                mock_f.first.return_value = account

            mock_q.filter.return_value = mock_f
            return mock_q

        db.query.side_effect = mock_query

        # Execute exit
        result = exit_trade(db, 1, 1, exit_price)

        # Verify balance change: balance should increase by exit_price × quantity
        expected_balance = balance_after_entry + (exit_price * quantity)
        assert abs(account.balance - expected_balance) < 1e-6, (
            f"Expected balance={expected_balance}, got {account.balance}. "
            f"entry={entry_price}, exit={exit_price}, qty={quantity}"
        )

        # Verify PnL calculation
        expected_pnl = (exit_price - entry_price) * quantity
        assert abs(trade.pnl - expected_pnl) < 1e-6, (
            f"Expected pnl={expected_pnl}, got {trade.pnl}"
        )

    @given(
        starting_capital=st.floats(min_value=1000.0, max_value=500000.0, allow_nan=False, allow_infinity=False),
        current_balance=st.floats(min_value=0.0, max_value=500000.0, allow_nan=False, allow_infinity=False),
        total_pnl=st.floats(min_value=-50000.0, max_value=50000.0, allow_nan=False, allow_infinity=False),
        total_trades=st.integers(min_value=0, max_value=100),
    )
    @settings(max_examples=100, deadline=None)
    def test_reset_restores_starting_capital(self, starting_capital, current_balance, total_pnl, total_trades):
        """Reset: balance equals starting_capital and stats are zeroed.

        **Validates: Requirements 9.7**

        Property: After reset_account, balance == starting_capital,
        total_pnl == 0, total_trades == 0, winning_trades == 0, losing_trades == 0.
        """
        account = _make_mock_account(
            balance=current_balance,
            starting_capital=starting_capital,
            total_pnl=total_pnl,
            total_trades=total_trades,
            winning_trades=total_trades // 2,
            losing_trades=total_trades - total_trades // 2,
        )

        db = MagicMock()
        query_mock = MagicMock()
        filter_mock = MagicMock()
        filter_mock.first.return_value = account
        # For the delete query
        filter_mock.delete.return_value = total_trades
        query_mock.filter.return_value = filter_mock
        db.query.return_value = query_mock

        result = reset_account(db, 1)

        # After reset, balance must equal starting_capital
        assert account.balance == starting_capital, (
            f"Expected balance={starting_capital}, got {account.balance}"
        )
        # All stats must be zeroed
        assert account.total_pnl == 0.0
        assert account.total_trades == 0
        assert account.winning_trades == 0
        assert account.losing_trades == 0


# ============================================================
# Property 11: Paper Account Statistics Correctness
# ============================================================


class TestPaperAccountStatisticsCorrectness:
    """Property-based tests for paper account statistics computation.

    **Validates: Requirements 9.1, 9.3**

    Core invariants:
    - win_rate = winning_trades / total_trades (0 if total_trades == 0)
    - profit_factor = sum_of_wins / abs(sum_of_losses) (0 if no losses)
    - ROI = total_pnl / starting_capital × 100
    """

    @given(
        winning_trades=st.integers(min_value=0, max_value=100),
        losing_trades=st.integers(min_value=0, max_value=100),
    )
    @settings(max_examples=100, deadline=None)
    def test_win_rate_formula(self, winning_trades, losing_trades):
        """win_rate = winning_trades / total_trades (0 if total_trades == 0).

        **Validates: Requirements 9.1**

        Property: For any combination of winning and losing trades,
        win_rate is correctly computed as winning_trades / total_trades.
        """
        total_trades = winning_trades + losing_trades

        account = _make_mock_account(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            starting_capital=40000.0,
            total_pnl=0.0,
        )

        db = MagicMock()
        query_mock = MagicMock()
        filter_mock = MagicMock()
        filter_mock.first.return_value = account
        filter_mock.all.return_value = []  # No closed trades for profit factor
        query_mock.filter.return_value = filter_mock
        db.query.return_value = query_mock

        result = get_account(db, 1)

        if total_trades == 0:
            expected_win_rate = 0.0
        else:
            expected_win_rate = winning_trades / total_trades

        assert abs(result["win_rate"] - expected_win_rate) < 1e-9, (
            f"Expected win_rate={expected_win_rate}, got {result['win_rate']}. "
            f"winning={winning_trades}, total={total_trades}"
        )

    @given(
        wins=st.lists(
            st.floats(min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False),
            min_size=0,
            max_size=20,
        ),
        losses=st.lists(
            st.floats(min_value=-10000.0, max_value=-0.01, allow_nan=False, allow_infinity=False),
            min_size=0,
            max_size=20,
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_profit_factor_formula(self, wins, losses):
        """profit_factor = sum_of_wins / abs(sum_of_losses) (0 if no losses).

        **Validates: Requirements 9.1**

        Property: For any sequence of winning and losing PnL values,
        profit_factor is correctly computed.
        """
        # Create mock closed trades
        closed_trades = []
        for w in wins:
            t = MagicMock()
            t.pnl = w
            closed_trades.append(t)
        for l_val in losses:
            t = MagicMock()
            t.pnl = l_val
            closed_trades.append(t)

        db = MagicMock()
        query_mock = MagicMock()
        filter_mock = MagicMock()
        filter_mock.all.return_value = closed_trades
        query_mock.filter.return_value = filter_mock
        db.query.return_value = query_mock

        result = _compute_profit_factor(db, account_id=1)

        total_wins = sum(wins)
        total_losses = sum(losses)

        if total_losses == 0:
            expected = 0.0
        else:
            expected = total_wins / abs(total_losses)

        assert abs(result - expected) < 1e-6, (
            f"Expected profit_factor={expected}, got {result}. "
            f"wins_sum={total_wins}, losses_sum={total_losses}"
        )

    @given(
        total_pnl=st.floats(min_value=-100000.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        starting_capital=st.floats(min_value=1000.0, max_value=500000.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100, deadline=None)
    def test_roi_formula(self, total_pnl, starting_capital):
        """ROI = total_pnl / starting_capital × 100.

        **Validates: Requirements 9.1**

        Property: For any total_pnl and starting_capital > 0,
        ROI is correctly computed as (total_pnl / starting_capital) × 100.
        """
        account = _make_mock_account(
            total_pnl=total_pnl,
            starting_capital=starting_capital,
            total_trades=5,
            winning_trades=3,
            losing_trades=2,
        )

        db = MagicMock()
        query_mock = MagicMock()
        filter_mock = MagicMock()
        filter_mock.first.return_value = account
        filter_mock.all.return_value = []  # No closed trades for profit factor
        query_mock.filter.return_value = filter_mock
        db.query.return_value = query_mock

        result = get_account(db, 1)

        expected_roi = (total_pnl / starting_capital) * 100
        assert abs(result["roi_pct"] - expected_roi) < 1e-6, (
            f"Expected roi_pct={expected_roi}, got {result['roi_pct']}. "
            f"total_pnl={total_pnl}, starting_capital={starting_capital}"
        )

    @given(
        total_pnl=st.floats(min_value=-100000.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        starting_capital=st.floats(min_value=1000.0, max_value=500000.0, allow_nan=False, allow_infinity=False),
        winning_trades=st.integers(min_value=0, max_value=50),
        losing_trades=st.integers(min_value=0, max_value=50),
    )
    @settings(max_examples=100, deadline=None)
    def test_get_account_stats_consistency(self, total_pnl, starting_capital, winning_trades, losing_trades):
        """All stats are internally consistent in get_account result.

        **Validates: Requirements 9.1**

        Property: The returned dictionary has correct win_rate and roi_pct
        given the account state, and all values are present.
        """
        total_trades = winning_trades + losing_trades

        account = _make_mock_account(
            total_pnl=total_pnl,
            starting_capital=starting_capital,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
        )

        db = MagicMock()
        query_mock = MagicMock()
        filter_mock = MagicMock()
        filter_mock.first.return_value = account
        filter_mock.all.return_value = []
        query_mock.filter.return_value = filter_mock
        db.query.return_value = query_mock

        result = get_account(db, 1)

        # Verify all expected keys are present
        assert "win_rate" in result
        assert "profit_factor" in result
        assert "roi_pct" in result
        assert "balance" in result
        assert "total_pnl" in result

        # Win rate
        if total_trades == 0:
            assert result["win_rate"] == 0.0
        else:
            expected_wr = winning_trades / total_trades
            assert abs(result["win_rate"] - expected_wr) < 1e-9

        # ROI
        expected_roi = (total_pnl / starting_capital) * 100
        assert abs(result["roi_pct"] - expected_roi) < 1e-6
