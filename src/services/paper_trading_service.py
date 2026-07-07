"""Paper Trading Service — manages virtual trading with simulated account.

Handles entering/exiting paper trades, balance management, performance
statistics (win rate, profit factor, ROI), and account reset.

No real orders are placed — all trades are simulated against the virtual balance.

Implements Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.database.models.paper_trade import PaperAccount, PaperTrade

logger = logging.getLogger(__name__)


def get_account(db: Session, user_id: int) -> Dict[str, Any]:
    """Get or create paper trading account with computed performance stats.

    Loads the user's PaperAccount. If none exists, creates one with
    the default starting capital of ₹40,000. Computes win_rate,
    profit_factor, and ROI from aggregate stats.

    Args:
        db: SQLAlchemy session.
        user_id: The user whose paper account to retrieve.

    Returns:
        Dictionary with account data and computed stats:
            - user_id (int)
            - balance (float)
            - starting_capital (float)
            - total_pnl (float)
            - total_trades (int)
            - winning_trades (int)
            - losing_trades (int)
            - win_rate (float): winning_trades / total_trades (0 if no trades)
            - profit_factor (float): sum of wins / abs(sum of losses) (0 if no losses)
            - roi_pct (float): total_pnl / starting_capital × 100
    """
    account = (
        db.query(PaperAccount)
        .filter(PaperAccount.user_id == user_id)
        .first()
    )

    if account is None:
        account = PaperAccount(
            user_id=user_id,
            balance=40000.0,
            starting_capital=40000.0,
            total_pnl=0.0,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
        )
        db.add(account)
        db.commit()
        db.refresh(account)
        logger.info("Created paper account for user %d", user_id)

    # Compute stats
    win_rate = (
        account.winning_trades / account.total_trades
        if account.total_trades > 0
        else 0.0
    )

    # Profit factor: sum of wins / abs(sum of losses)
    profit_factor = _compute_profit_factor(db, account.id)

    roi_pct = (
        (account.total_pnl / account.starting_capital) * 100
        if account.starting_capital > 0
        else 0.0
    )

    return {
        "user_id": account.user_id,
        "balance": account.balance,
        "starting_capital": account.starting_capital,
        "total_pnl": account.total_pnl,
        "total_trades": account.total_trades,
        "winning_trades": account.winning_trades,
        "losing_trades": account.losing_trades,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "roi_pct": roi_pct,
    }


def enter_trade(db: Session, user_id: int, trade_data: Dict[str, Any]) -> PaperTrade:
    """Enter a new paper trade after validating capital availability.

    Validates that entry_price × quantity does not exceed the available
    virtual balance. Creates a PaperTrade with status="open" and deducts
    the investment from the account balance.

    Args:
        db: SQLAlchemy session.
        user_id: The user entering the trade.
        trade_data: Dictionary with trade fields:
            - symbol (str): Trading symbol
            - strike (float): Strike price
            - option_type (str): "CE" or "PE"
            - entry_price (float): Entry price per unit
            - quantity (int): Number of units
            - stop_loss (float): Stop-loss level
            - target (float): Target price

    Returns:
        The created PaperTrade instance.

    Raises:
        ValueError: If insufficient balance or required fields missing.
    """
    account = (
        db.query(PaperAccount)
        .filter(PaperAccount.user_id == user_id)
        .first()
    )

    if account is None:
        # Auto-create account if it doesn't exist
        account = PaperAccount(
            user_id=user_id,
            balance=40000.0,
            starting_capital=40000.0,
            total_pnl=0.0,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
        )
        db.add(account)
        db.commit()
        db.refresh(account)

    entry_price = trade_data["entry_price"]
    quantity = trade_data["quantity"]
    investment = entry_price * quantity

    if investment > account.balance:
        raise ValueError(
            f"Insufficient balance. Required: {investment:.2f}, "
            f"Available: {account.balance:.2f}"
        )

    # Create the paper trade
    trade = PaperTrade(
        user_id=user_id,
        account_id=account.id,
        symbol=trade_data["symbol"],
        strike=trade_data["strike"],
        option_type=trade_data["option_type"],
        entry_price=entry_price,
        quantity=quantity,
        stop_loss=trade_data["stop_loss"],
        target=trade_data["target"],
        status="open",
        setup_type=trade_data.get("setup_type"),
    )

    # Deduct investment from balance
    account.balance -= investment
    account.updated_at = datetime.now(timezone.utc)

    db.add(trade)
    db.commit()
    db.refresh(trade)

    logger.info(
        "User %d entered paper trade %d: %s %s @ %.2f x %d (invested %.2f)",
        user_id,
        trade.id,
        trade.symbol,
        trade.option_type,
        entry_price,
        quantity,
        investment,
    )

    return trade


def exit_trade(
    db: Session, user_id: int, trade_id: int, exit_price: float
) -> PaperTrade:
    """Exit an open paper trade at the given price and update account stats.

    Verifies the trade belongs to the user and is in "open" status.
    Calculates PnL as (exit_price - entry_price) × quantity.
    Adds exit_price × quantity back to the account balance.
    Updates aggregate account statistics.

    Args:
        db: SQLAlchemy session.
        user_id: The user exiting the trade.
        trade_id: The ID of the trade to exit.
        exit_price: The price at which to close the position.

    Returns:
        The closed PaperTrade instance with pnl set.

    Raises:
        ValueError: If trade not found, not owned by user, or not open.
    """
    trade = db.query(PaperTrade).filter(PaperTrade.id == trade_id).first()

    if trade is None:
        raise ValueError(f"Trade {trade_id} not found")

    if trade.user_id != user_id:
        raise ValueError(f"Trade {trade_id} does not belong to user {user_id}")

    if trade.status != "open":
        raise ValueError(
            f"Trade {trade_id} is not open (current status: {trade.status})"
        )

    # Calculate PnL
    pnl = (exit_price - trade.entry_price) * trade.quantity

    # Update trade
    trade.exit_price = exit_price
    trade.pnl = pnl
    trade.status = "closed"
    trade.closed_at = datetime.now(timezone.utc)

    # Update account balance: add back exit_price × quantity
    account = (
        db.query(PaperAccount)
        .filter(PaperAccount.user_id == user_id)
        .first()
    )

    account.balance += exit_price * trade.quantity
    account.total_pnl += pnl
    account.total_trades += 1

    if pnl > 0:
        account.winning_trades += 1
    elif pnl < 0:
        account.losing_trades += 1

    account.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(trade)

    logger.info(
        "User %d exited paper trade %d: %s @ %.2f, PnL: %.2f",
        user_id,
        trade.id,
        trade.symbol,
        exit_price,
        pnl,
    )

    return trade


def get_open_positions(db: Session, user_id: int) -> List[PaperTrade]:
    """Get all open paper positions for a user.

    Args:
        db: SQLAlchemy session.
        user_id: The user whose open positions to fetch.

    Returns:
        List of PaperTrade instances with status="open".
    """
    return (
        db.query(PaperTrade)
        .filter(
            PaperTrade.user_id == user_id,
            PaperTrade.status == "open",
        )
        .all()
    )


def get_trade_history(db: Session, user_id: int) -> List[PaperTrade]:
    """Get completed paper trade history for a user, most recent first.

    Args:
        db: SQLAlchemy session.
        user_id: The user whose trade history to fetch.

    Returns:
        List of PaperTrade instances with status="closed",
        ordered by closed_at descending.
    """
    return (
        db.query(PaperTrade)
        .filter(
            PaperTrade.user_id == user_id,
            PaperTrade.status == "closed",
        )
        .order_by(PaperTrade.closed_at.desc())
        .all()
    )


def reset_account(db: Session, user_id: int) -> Dict[str, Any]:
    """Reset paper account to starting capital and clear all trade history.

    Sets balance back to starting_capital, resets all aggregate stats
    to zero, and deletes all paper trades for the user.

    Args:
        db: SQLAlchemy session.
        user_id: The user whose account to reset.

    Returns:
        Dictionary with the reset account data (same format as get_account).

    Raises:
        ValueError: If no paper account exists for the user.
    """
    account = (
        db.query(PaperAccount)
        .filter(PaperAccount.user_id == user_id)
        .first()
    )

    if account is None:
        raise ValueError(f"No paper account found for user {user_id}")

    # Reset account stats
    account.balance = account.starting_capital
    account.total_pnl = 0.0
    account.total_trades = 0
    account.winning_trades = 0
    account.losing_trades = 0
    account.updated_at = datetime.now(timezone.utc)

    # Delete all paper trades for the user
    db.query(PaperTrade).filter(PaperTrade.user_id == user_id).delete()

    db.commit()
    db.refresh(account)

    logger.info(
        "User %d paper account reset to starting capital %.2f",
        user_id,
        account.starting_capital,
    )

    return {
        "user_id": account.user_id,
        "balance": account.balance,
        "starting_capital": account.starting_capital,
        "total_pnl": account.total_pnl,
        "total_trades": account.total_trades,
        "winning_trades": account.winning_trades,
        "losing_trades": account.losing_trades,
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "roi_pct": 0.0,
    }


def _compute_profit_factor(db: Session, account_id: int) -> float:
    """Compute profit factor: sum of winning PnLs / abs(sum of losing PnLs).

    Args:
        db: SQLAlchemy session.
        account_id: The paper account ID.

    Returns:
        Profit factor as a float. Returns 0.0 if there are no losing trades.
    """
    closed_trades = (
        db.query(PaperTrade)
        .filter(
            PaperTrade.account_id == account_id,
            PaperTrade.status == "closed",
        )
        .all()
    )

    total_wins = sum(t.pnl for t in closed_trades if t.pnl is not None and t.pnl > 0)
    total_losses = sum(
        t.pnl for t in closed_trades if t.pnl is not None and t.pnl < 0
    )

    if total_losses == 0:
        return 0.0

    return total_wins / abs(total_losses)
