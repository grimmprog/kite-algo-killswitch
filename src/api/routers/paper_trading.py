"""Paper Trading API endpoints.

Requirements covered:
- 9.1: Paper account with balance, P&L, win rate, profit factor, ROI
- 9.2: Enter paper trades with symbol, strike, option_type, entry_price, quantity, SL, target
- 9.3: Validate investment does not exceed available virtual capital
- 9.4: Display open paper positions
- 9.5: Exit paper trade at current simulated price
- 9.6: Trade history with entry/exit prices, P&L, exit reason, setup type
- 9.7: Reset account to starting capital and clear history

Endpoints:
- GET  /api/v1/paper/account         — Get paper account stats
- POST /api/v1/paper/trades          — Enter a new paper trade
- POST /api/v1/paper/trades/{id}/exit — Exit a paper trade
- GET  /api/v1/paper/positions       — Get open paper positions
- GET  /api/v1/paper/history         — Get completed paper trade history
- POST /api/v1/paper/reset           — Reset paper account
"""

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from src.api.dependencies import get_db, get_redis, get_current_user
from src.services import paper_trading_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["paper_trading"])


# --------------------------------------------------------------------------
# Request/Response schemas
# --------------------------------------------------------------------------


class PaperAccountResponse(BaseModel):
    """Paper trading account with performance statistics."""

    model_config = ConfigDict(from_attributes=True)

    user_id: int
    balance: float
    starting_capital: float
    total_pnl: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    profit_factor: float
    roi_pct: float


class PaperTradeEntryRequest(BaseModel):
    """Request body for entering a new paper trade."""

    symbol: str = Field(..., min_length=1, max_length=100)
    strike: float = Field(..., gt=0)
    option_type: str = Field(..., pattern=r"^(CE|PE)$")
    entry_price: float = Field(..., gt=0)
    quantity: int = Field(..., gt=0)
    stop_loss: float = Field(..., gt=0)
    target: float = Field(..., gt=0)
    setup_type: Optional[str] = Field(default=None, max_length=50)


class PaperTradeExitRequest(BaseModel):
    """Request body for exiting a paper trade."""

    exit_price: float = Field(..., gt=0)


class PaperTradeResponse(BaseModel):
    """Response model for a paper trade."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    strike: float
    option_type: str
    entry_price: float
    exit_price: Optional[float] = None
    quantity: int
    stop_loss: float
    target: float
    status: str
    pnl: Optional[float] = None
    exit_reason: Optional[str] = None
    setup_type: Optional[str] = None
    created_at: datetime
    closed_at: Optional[datetime] = None


# --------------------------------------------------------------------------
# GET /api/v1/paper/account
# --------------------------------------------------------------------------


@router.get("/paper/account", response_model=PaperAccountResponse)
async def get_paper_account(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get paper trading account with performance statistics.

    Returns virtual balance, total P&L, win rate, profit factor, and ROI.
    Creates a new account with default ₹40,000 balance if none exists.
    """
    account_data = paper_trading_service.get_account(db, user_id)
    return PaperAccountResponse(**account_data)


# --------------------------------------------------------------------------
# POST /api/v1/paper/trades
# --------------------------------------------------------------------------


@router.post(
    "/paper/trades",
    response_model=PaperTradeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def enter_paper_trade(
    trade_request: PaperTradeEntryRequest,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Enter a new paper trade.

    Validates that entry_price × quantity does not exceed available
    virtual capital. Creates the trade and deducts the investment
    from the account balance.
    """
    trade_data = trade_request.model_dump()

    try:
        trade = paper_trading_service.enter_trade(db, user_id, trade_data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return PaperTradeResponse.model_validate(trade)


# --------------------------------------------------------------------------
# POST /api/v1/paper/trades/{id}/exit
# --------------------------------------------------------------------------


@router.post("/paper/trades/{trade_id}/exit", response_model=PaperTradeResponse)
async def exit_paper_trade(
    trade_id: int,
    exit_request: PaperTradeExitRequest,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Exit an open paper trade at the specified price.

    Closes the position, calculates PnL, updates the account balance,
    and records the trade result.
    """
    try:
        trade = paper_trading_service.exit_trade(
            db, user_id, trade_id, exit_request.exit_price
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return PaperTradeResponse.model_validate(trade)


# --------------------------------------------------------------------------
# GET /api/v1/paper/positions
# --------------------------------------------------------------------------


@router.get("/paper/positions", response_model=List[PaperTradeResponse])
async def get_paper_positions(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all open paper positions for the current user."""
    positions = paper_trading_service.get_open_positions(db, user_id)
    return [PaperTradeResponse.model_validate(p) for p in positions]


# --------------------------------------------------------------------------
# GET /api/v1/paper/history
# --------------------------------------------------------------------------


@router.get("/paper/history", response_model=List[PaperTradeResponse])
async def get_paper_history(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get completed paper trade history, most recent first."""
    history = paper_trading_service.get_trade_history(db, user_id)
    return [PaperTradeResponse.model_validate(t) for t in history]


# --------------------------------------------------------------------------
# POST /api/v1/paper/reset
# --------------------------------------------------------------------------


@router.post("/paper/reset", response_model=PaperAccountResponse)
async def reset_paper_account(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reset paper account to starting capital and clear all trade history.

    Restores balance to the initial ₹40,000, resets all aggregate
    statistics, and deletes all paper trades.
    """
    try:
        account_data = paper_trading_service.reset_account(db, user_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return PaperAccountResponse(**account_data)
