"""Trade Journal API endpoints.

Requirements covered:
- 14.1: Display completed trades with date, symbol, entry/exit, P&L, setup_type, confidence, trend, exit_reason
- 14.2: Filter by date range, setup type, profit/loss, symbol
- 14.3: Sort by any column in ascending or descending order
- 14.4: Aggregate statistics: total trades, win rate, avg profit, avg loss, profit factor, best/worst trade
- 14.5: Auto-record trades with metadata on completion

Endpoints:
- GET /api/v1/journal       — Get journal entries with optional filters and sorting
- GET /api/v1/journal/stats — Get aggregate trade statistics
"""

import logging
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import asc, desc
from sqlalchemy.orm import Session

from src.api.dependencies import get_db, get_current_user
from src.database.models.trade_journal import TradeJournalEntry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["journal"])


# --------------------------------------------------------------------------
# Response schemas
# --------------------------------------------------------------------------


class JournalEntryResponse(BaseModel):
    """A single trade journal entry."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    trade_id: int
    symbol: str
    entry_price: float
    exit_price: Optional[float] = None
    pnl: Optional[float] = None
    setup_type: Optional[str] = None
    confidence_score: Optional[float] = None
    trend_direction: Optional[str] = None
    exit_reason: Optional[str] = None
    ai_grade: Optional[str] = None
    ai_entry_feedback: Optional[str] = None
    ai_exit_feedback: Optional[str] = None
    ai_sizing_feedback: Optional[str] = None
    ai_risk_feedback: Optional[str] = None
    ai_patterns: Optional[list] = None
    trade_date: date
    created_at: datetime


class JournalStatsResponse(BaseModel):
    """Aggregate trade journal statistics."""

    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_profit: float
    avg_loss: float
    profit_factor: float
    best_trade_pnl: Optional[float] = None
    worst_trade_pnl: Optional[float] = None
    total_pnl: float


# --------------------------------------------------------------------------
# Allowed sort columns mapping
# --------------------------------------------------------------------------

SORT_COLUMNS = {
    "trade_date": TradeJournalEntry.trade_date,
    "symbol": TradeJournalEntry.symbol,
    "entry_price": TradeJournalEntry.entry_price,
    "exit_price": TradeJournalEntry.exit_price,
    "pnl": TradeJournalEntry.pnl,
    "setup_type": TradeJournalEntry.setup_type,
    "confidence_score": TradeJournalEntry.confidence_score,
    "trend_direction": TradeJournalEntry.trend_direction,
    "exit_reason": TradeJournalEntry.exit_reason,
    "ai_grade": TradeJournalEntry.ai_grade,
    "created_at": TradeJournalEntry.created_at,
}


# --------------------------------------------------------------------------
# GET /api/v1/journal
# --------------------------------------------------------------------------


@router.get("/journal", response_model=List[JournalEntryResponse])
async def get_journal_entries(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
    # Filters
    date_from: Optional[date] = Query(None, description="Filter from date (inclusive)"),
    date_to: Optional[date] = Query(None, description="Filter to date (inclusive)"),
    setup_type: Optional[str] = Query(None, description="Filter by setup type"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    profit_loss: Optional[str] = Query(
        None,
        pattern=r"^(profit|loss)$",
        description="Filter by profit or loss trades",
    ),
    # Sorting
    sort_by: Optional[str] = Query(
        "trade_date",
        description="Column to sort by",
    ),
    sort_order: Optional[str] = Query(
        "desc",
        pattern=r"^(asc|desc)$",
        description="Sort order: asc or desc",
    ),
    # Pagination
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
):
    """Get trade journal entries with optional filters, sorting, and pagination.

    14.1: Returns all trade metadata including AI grade and feedback.
    14.2: Supports filtering by date range, setup type, profit/loss, symbol.
    14.3: Supports sorting by any column in ascending or descending order.
    """
    query = db.query(TradeJournalEntry).filter(
        TradeJournalEntry.user_id == user_id
    )

    # Apply filters
    if date_from:
        query = query.filter(TradeJournalEntry.trade_date >= date_from)
    if date_to:
        query = query.filter(TradeJournalEntry.trade_date <= date_to)
    if setup_type:
        query = query.filter(TradeJournalEntry.setup_type == setup_type)
    if symbol:
        query = query.filter(TradeJournalEntry.symbol == symbol)
    if profit_loss == "profit":
        query = query.filter(TradeJournalEntry.pnl > 0)
    elif profit_loss == "loss":
        query = query.filter(TradeJournalEntry.pnl < 0)

    # Apply sorting
    sort_column = SORT_COLUMNS.get(sort_by, TradeJournalEntry.trade_date)
    if sort_order == "asc":
        query = query.order_by(asc(sort_column))
    else:
        query = query.order_by(desc(sort_column))

    # Apply pagination
    offset = (page - 1) * page_size
    entries = query.offset(offset).limit(page_size).all()

    return [JournalEntryResponse.model_validate(entry) for entry in entries]


# --------------------------------------------------------------------------
# GET /api/v1/journal/stats
# --------------------------------------------------------------------------


@router.get("/journal/stats", response_model=JournalStatsResponse)
async def get_journal_stats(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get aggregate trade journal statistics.

    14.4: Returns total trades, win rate, avg profit, avg loss,
    profit factor, and best/worst trade.
    """
    entries = (
        db.query(TradeJournalEntry)
        .filter(TradeJournalEntry.user_id == user_id)
        .all()
    )

    if not entries:
        return JournalStatsResponse(
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0.0,
            avg_profit=0.0,
            avg_loss=0.0,
            profit_factor=0.0,
            best_trade_pnl=None,
            worst_trade_pnl=None,
            total_pnl=0.0,
        )

    total_trades = len(entries)
    pnl_values = [e.pnl for e in entries if e.pnl is not None]

    winning_trades = [p for p in pnl_values if p > 0]
    losing_trades = [p for p in pnl_values if p < 0]

    win_count = len(winning_trades)
    loss_count = len(losing_trades)
    win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0.0

    avg_profit = (sum(winning_trades) / win_count) if win_count > 0 else 0.0
    avg_loss = (sum(losing_trades) / loss_count) if loss_count > 0 else 0.0

    total_profit = sum(winning_trades) if winning_trades else 0.0
    total_loss = abs(sum(losing_trades)) if losing_trades else 0.0
    profit_factor = (total_profit / total_loss) if total_loss > 0 else 0.0

    best_trade = max(pnl_values) if pnl_values else None
    worst_trade = min(pnl_values) if pnl_values else None

    total_pnl = sum(pnl_values) if pnl_values else 0.0

    return JournalStatsResponse(
        total_trades=total_trades,
        winning_trades=win_count,
        losing_trades=loss_count,
        win_rate=round(win_rate, 2),
        avg_profit=round(avg_profit, 2),
        avg_loss=round(avg_loss, 2),
        profit_factor=round(profit_factor, 2),
        best_trade_pnl=best_trade,
        worst_trade_pnl=worst_trade,
        total_pnl=round(total_pnl, 2),
    )
