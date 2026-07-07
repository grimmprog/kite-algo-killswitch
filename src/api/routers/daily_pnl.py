"""Daily P&L API — Store and retrieve daily trading performance.

Endpoints:
- GET  /api/v1/trades/daily-summary       — Get today's P&L summary (live from broker)
- POST /api/v1/trades/daily-summary/save   — Save today's P&L snapshot to DB
- GET  /api/v1/trades/daily-history        — Get historical daily P&L records
"""

import json
import logging
import os
from datetime import date, datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_user, get_db
from src.broker.token_encryption import TokenEncryption
from src.database.models.broker_connection import BrokerConnection
from src.database.models.daily_pnl import DailyPnLSnapshot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/trades", tags=["daily-pnl"])


# --- Response Models ---

class DailySummaryResponse(BaseModel):
    trade_date: str
    gross_pnl: float
    total_charges: float
    net_pnl: float
    opening_capital: float
    closing_capital: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    max_profit_trade: float
    max_loss_trade: float
    brokerage: float
    stt: float
    exchange_charges: float
    gst: float
    instruments_traded: List[str]
    win_rate: float
    capital_change_pct: float


class DailyHistoryItem(BaseModel):
    trade_date: str
    net_pnl: float
    gross_pnl: float
    total_charges: float
    total_trades: int
    win_rate: float
    closing_capital: float
    ai_grade: Optional[str] = None
    notes: Optional[str] = None


# --- Helpers ---

def _get_kite_client(db: Session, user_id: int):
    """Get authenticated KiteConnect client for the user."""
    from kiteconnect import KiteConnect

    encryption_key = os.environ.get("ENCRYPTION_KEY", "")
    api_key = os.environ.get("KITE_API_KEY", "")

    connection = (
        db.query(BrokerConnection)
        .filter(
            BrokerConnection.user_id == user_id,
            BrokerConnection.broker_type == "kite",
            BrokerConnection.access_token_encrypted.isnot(None),
        )
        .first()
    )

    if not connection:
        raise HTTPException(status_code=503, detail="Kite not connected")

    enc = TokenEncryption(encryption_key=encryption_key)
    token = enc.decrypt(connection.access_token_encrypted)

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(token)
    return kite


def _compute_daily_summary(kite, user_id: int) -> Dict:
    """Fetch today's trades from Kite and compute P&L summary."""
    trades = kite.trades()
    orders = kite.orders()
    positions = kite.positions()
    margins = kite.margins(segment="equity")

    # Capital
    available = margins.get("available", {})
    net_capital = float(margins.get("net", available.get("cash", 0)))

    # P&L from positions
    day_positions = positions.get("day", [])
    net_positions = positions.get("net", [])

    total_pnl = 0.0
    winning = 0
    losing = 0
    max_profit = 0.0
    max_loss = 0.0
    symbols = set()

    for pos in (day_positions or net_positions):
        pnl = float(pos.get("pnl", 0))
        total_pnl += pnl
        symbol = pos.get("tradingsymbol", "")
        if symbol:
            symbols.add(symbol)
        if pnl > 0:
            winning += 1
            max_profit = max(max_profit, pnl)
        elif pnl < 0:
            losing += 1
            max_loss = min(max_loss, pnl)

    # Charges calculation
    executed_orders = [o for o in orders if o.get("status") == "COMPLETE"]
    num_orders = len(executed_orders)
    brokerage = num_orders * 20.0

    sell_turnover = 0.0
    total_turnover = 0.0
    for trade in trades:
        qty = int(trade.get("filled_quantity", trade.get("quantity", 0)))
        price = float(trade.get("average_price", 0))
        trade_value = qty * price
        total_turnover += trade_value
        if trade.get("transaction_type") == "SELL":
            sell_turnover += trade_value

    stt = sell_turnover * 0.0015
    exchange_charges = total_turnover * 0.00053
    gst = (brokerage + exchange_charges) * 0.18
    total_charges = round(brokerage + stt + exchange_charges + gst, 2)
    net_pnl = round(total_pnl - total_charges, 2)

    return {
        "trade_date": date.today().isoformat(),
        "gross_pnl": round(total_pnl, 2),
        "total_charges": total_charges,
        "net_pnl": net_pnl,
        "opening_capital": round(net_capital - net_pnl, 2),
        "closing_capital": round(net_capital, 2),
        "total_trades": num_orders,
        "winning_trades": winning,
        "losing_trades": losing,
        "max_profit_trade": round(max_profit, 2),
        "max_loss_trade": round(max_loss, 2),
        "brokerage": round(brokerage, 2),
        "stt": round(stt, 2),
        "exchange_charges": round(exchange_charges + total_turnover * 0.000001, 2),
        "gst": round(gst, 2),
        "instruments_traded": list(symbols),
        "win_rate": round(winning / max(winning + losing, 1) * 100, 1),
        "capital_change_pct": round(net_pnl / max(net_capital - net_pnl, 1) * 100, 2),
    }


# --- Endpoints ---

@router.get("/daily-summary", response_model=DailySummaryResponse)
async def get_daily_summary(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get today's live P&L summary from broker.

    Fetches real-time data from Kite API and computes:
    - Gross/net P&L with charge breakdown
    - Win rate and trade count
    - Capital change percentage
    """
    kite = _get_kite_client(db, user_id)

    try:
        summary = _compute_daily_summary(kite, user_id)
        return DailySummaryResponse(**summary)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to compute daily summary for user %d: %s", user_id, str(e))
        raise HTTPException(status_code=500, detail=f"Failed to fetch daily summary: {str(e)}")


@router.post("/daily-summary/save")
async def save_daily_summary(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save today's P&L snapshot to the database.

    Creates or updates the DailyPnLSnapshot record for today.
    Call this at market close or manually to persist the data.
    """
    kite = _get_kite_client(db, user_id)

    try:
        summary = _compute_daily_summary(kite, user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compute summary: {str(e)}")

    today = date.today()

    # Upsert: check if today's record exists
    existing = (
        db.query(DailyPnLSnapshot)
        .filter(
            DailyPnLSnapshot.user_id == user_id,
            DailyPnLSnapshot.trade_date == today,
        )
        .first()
    )

    if existing:
        # Update
        existing.gross_pnl = summary["gross_pnl"]
        existing.total_charges = summary["total_charges"]
        existing.net_pnl = summary["net_pnl"]
        existing.opening_capital = summary["opening_capital"]
        existing.closing_capital = summary["closing_capital"]
        existing.total_trades = summary["total_trades"]
        existing.winning_trades = summary["winning_trades"]
        existing.losing_trades = summary["losing_trades"]
        existing.max_profit_trade = summary["max_profit_trade"]
        existing.max_loss_trade = summary["max_loss_trade"]
        existing.brokerage = summary["brokerage"]
        existing.stt = summary["stt"]
        existing.exchange_charges = summary["exchange_charges"]
        existing.gst = summary["gst"]
        existing.instruments_traded = json.dumps(summary["instruments_traded"])
    else:
        # Create
        snapshot = DailyPnLSnapshot(
            user_id=user_id,
            trade_date=today,
            gross_pnl=summary["gross_pnl"],
            total_charges=summary["total_charges"],
            net_pnl=summary["net_pnl"],
            opening_capital=summary["opening_capital"],
            closing_capital=summary["closing_capital"],
            total_trades=summary["total_trades"],
            winning_trades=summary["winning_trades"],
            losing_trades=summary["losing_trades"],
            max_profit_trade=summary["max_profit_trade"],
            max_loss_trade=summary["max_loss_trade"],
            brokerage=summary["brokerage"],
            stt=summary["stt"],
            exchange_charges=summary["exchange_charges"],
            gst=summary["gst"],
            instruments_traded=json.dumps(summary["instruments_traded"]),
        )
        db.add(snapshot)

    db.commit()
    logger.info("Saved daily P&L snapshot for user %d, date %s", user_id, today)

    return {"success": True, "message": f"Daily P&L saved for {today}", "net_pnl": summary["net_pnl"]}


@router.get("/daily-history", response_model=List[DailyHistoryItem])
async def get_daily_history(
    days: int = Query(default=30, ge=1, le=365),
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get historical daily P&L records for AI analysis and charting.

    Returns the last N days of saved P&L snapshots, ordered newest first.
    """
    records = (
        db.query(DailyPnLSnapshot)
        .filter(DailyPnLSnapshot.user_id == user_id)
        .order_by(desc(DailyPnLSnapshot.trade_date))
        .limit(days)
        .all()
    )

    result = []
    for r in records:
        win_rate = round(r.winning_trades / max(r.winning_trades + r.losing_trades, 1) * 100, 1)
        result.append(DailyHistoryItem(
            trade_date=r.trade_date.isoformat(),
            net_pnl=r.net_pnl,
            gross_pnl=r.gross_pnl,
            total_charges=r.total_charges,
            total_trades=r.total_trades,
            win_rate=win_rate,
            closing_capital=r.closing_capital,
            ai_grade=r.ai_grade,
            notes=r.notes,
        ))

    return result
