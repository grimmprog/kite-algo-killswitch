"""Account Dashboard API endpoint.

Provides live account data from Kite Connect:
- Profile information
- Margins (available capital, used, net)
- Positions (open positions with P&L)
- Today's trades
- P&L summary
- Today's orders

Endpoint:
- GET /api/v1/dashboard/account — Full account dashboard data from Kite
"""

import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_user, get_db
from src.broker.token_encryption import TokenEncryption, TokenEncryptionError
from src.database.models.broker_connection import BrokerConnection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/dashboard", tags=["account-dashboard"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ProfileResponse(BaseModel):
    user_name: str
    user_id: str
    email: str
    broker: str


class MarginsResponse(BaseModel):
    available_capital: float
    net: float
    used: float


class PositionItem(BaseModel):
    symbol: str
    qty: int
    avg_price: float
    ltp: float
    pnl: float
    product: str


class TradeItem(BaseModel):
    symbol: str
    transaction_type: str
    qty: int
    price: float
    time: str


class TradesTodayResponse(BaseModel):
    count: int  # Number of executed orders (not fills)
    fills: int = 0  # Number of individual trade fills
    trades: List[TradeItem]


class PnLSummaryResponse(BaseModel):
    total_pnl: float
    realized_pnl: float
    unrealized_pnl: float
    brokerage: float = 0.0
    stt: float = 0.0
    exchange_charges: float = 0.0
    gst: float = 0.0
    total_charges: float = 0.0
    net_pnl: float = 0.0


class OrderItem(BaseModel):
    symbol: str
    status: str
    transaction_type: str
    qty: int
    price: float


class OrdersTodayResponse(BaseModel):
    count: int
    orders: List[OrderItem]


class AccountDashboardResponse(BaseModel):
    profile: ProfileResponse
    margins: MarginsResponse
    positions: List[PositionItem]
    trades_today: TradesTodayResponse
    pnl_summary: PnLSummaryResponse
    orders_today: OrdersTodayResponse


# ---------------------------------------------------------------------------
# Kite session helper
# ---------------------------------------------------------------------------


def _get_kite_access_token(db: Session, user_id: int) -> str:
    """Resolve Kite access token for the given user.

    Resolution order:
    1. Database (broker_connections table, encrypted, for the logged-in user)
    2. Fallback: access_token.txt file (shared)

    Args:
        db: Database session.
        user_id: The authenticated user's ID.

    Returns:
        The decrypted/plain access token string.

    Raises:
        HTTPException: 503 if no valid token is found.
    """
    # 1. Try database (encrypted token for this user)
    encryption_key = os.environ.get("ENCRYPTION_KEY", "")
    if encryption_key:
        try:
            connection = (
                db.query(BrokerConnection)
                .filter(
                    BrokerConnection.user_id == user_id,
                    BrokerConnection.broker_type == "kite",
                    BrokerConnection.access_token_encrypted.isnot(None),
                )
                .first()
            )

            if connection:
                # Check if token is expired
                if connection.token_expiry and connection.token_expiry.replace(
                    tzinfo=timezone.utc
                ) < datetime.now(timezone.utc):
                    logger.warning(
                        "Kite token expired for user %d (expiry: %s)",
                        user_id,
                        connection.token_expiry,
                    )
                else:
                    encryptor = TokenEncryption(encryption_key=encryption_key)
                    token = encryptor.decrypt(connection.access_token_encrypted)
                    if token:
                        return token
        except TokenEncryptionError as e:
            logger.error("Failed to decrypt token for user %d: %s", user_id, e)
        except Exception as e:
            logger.error("Database token lookup failed for user %d: %s", user_id, e)

    # 2. Fallback: access_token.txt file
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)
    ))))
    token_path = os.path.join(base_dir, "access_token.txt")

    if os.path.exists(token_path):
        try:
            with open(token_path, "r") as f:
                token = f.read().strip()
                if token:
                    return token
        except IOError as e:
            logger.error("Failed to read access_token.txt: %s", e)

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Kite session not available. Token expired or not configured. Please reconnect your broker.",
    )


def _get_kite_client(access_token: str):
    """Create an authenticated KiteConnect client.

    Args:
        access_token: Valid Kite access token.

    Returns:
        Authenticated KiteConnect instance.
    """
    from kiteconnect import KiteConnect

    api_key = os.environ.get("KITE_API_KEY", "")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="KITE_API_KEY not configured",
        )

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    return kite


# ---------------------------------------------------------------------------
# GET /api/v1/dashboard/account
# ---------------------------------------------------------------------------


@router.get("/account", response_model=AccountDashboardResponse)
async def get_account_dashboard(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get comprehensive account dashboard data from Kite Connect.

    Returns profile, margins, positions, today's trades, P&L summary,
    and today's orders — all fetched live from the Kite API.

    Raises:
        HTTPException 503: If Kite token is expired or invalid.
        HTTPException 500: If Kite API calls fail unexpectedly.
    """
    access_token = _get_kite_access_token(db, user_id)
    kite = _get_kite_client(access_token)

    try:
        # Fetch all data from Kite
        profile_data = kite.profile()
        margins_data = kite.margins(segment="equity")
        positions_data = kite.positions()
        trades_data = kite.trades()
        orders_data = kite.orders()
    except Exception as e:
        error_msg = str(e)
        # Kite returns specific error for expired tokens
        if "TokenException" in type(e).__name__ or "Invalid" in error_msg or "token" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Kite session expired. Please reconnect your broker.",
            )
        logger.error("Kite API error for user %d: %s", user_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch account data from Kite: {error_msg}",
        )

    # --- Build profile ---
    profile = ProfileResponse(
        user_name=profile_data.get("user_name", ""),
        user_id=profile_data.get("user_id", ""),
        email=profile_data.get("email", ""),
        broker=profile_data.get("broker", "ZERODHA"),
    )

    # --- Build margins ---
    available = margins_data.get("available", {})
    utilised = margins_data.get("utilised", {})

    available_capital = float(available.get("live_balance", 0))
    net = float(margins_data.get("net", available.get("cash", 0)))
    used = float(utilised.get("debits", 0))

    margins = MarginsResponse(
        available_capital=available_capital,
        net=net,
        used=used,
    )

    # --- Build positions ---
    net_positions = positions_data.get("net", [])
    day_positions = positions_data.get("day", [])

    # Use day positions if available (more relevant for today), else net
    active_positions = day_positions if day_positions else net_positions

    positions: List[PositionItem] = []
    unrealized_pnl = 0.0
    realized_pnl = 0.0

    for pos in active_positions:
        qty = int(pos.get("quantity", 0))
        if qty == 0 and float(pos.get("pnl", 0)) == 0:
            continue  # Skip fully closed positions with no P&L

        pnl = float(pos.get("pnl", 0))
        m2m = float(pos.get("m2m", 0))

        # Realized = P&L from closed quantity, Unrealized = from open quantity
        if qty != 0:
            unrealized_pnl += pnl
        else:
            realized_pnl += pnl

        positions.append(PositionItem(
            symbol=pos.get("tradingsymbol", ""),
            qty=qty,
            avg_price=float(pos.get("average_price", 0)),
            ltp=float(pos.get("last_price", 0)),
            pnl=pnl,
            product=pos.get("product", ""),
        ))

    # Also calculate realized from net positions that are fully closed
    for pos in net_positions:
        qty = int(pos.get("quantity", 0))
        if qty == 0:
            realized_pnl += float(pos.get("pnl", 0))

    # Avoid double-counting if we used day positions
    if day_positions:
        realized_pnl = 0.0
        unrealized_pnl = 0.0
        for pos in day_positions:
            qty = int(pos.get("quantity", 0))
            pnl = float(pos.get("pnl", 0))
            if qty != 0:
                unrealized_pnl += pnl
            else:
                realized_pnl += pnl

    total_pnl = realized_pnl + unrealized_pnl

    # --- Build trades today ---
    trade_items: List[TradeItem] = []
    for trade in trades_data:
        trade_time = trade.get("fill_timestamp", trade.get("order_timestamp", ""))
        if isinstance(trade_time, datetime):
            trade_time = trade_time.strftime("%H:%M:%S")
        else:
            trade_time = str(trade_time)

        trade_items.append(TradeItem(
            symbol=trade.get("tradingsymbol", ""),
            transaction_type=trade.get("transaction_type", ""),
            qty=int(trade.get("filled_quantity", trade.get("quantity", 0))),
            price=float(trade.get("average_price", 0)),
            time=trade_time,
        ))

    # Count executed orders (not fills)
    executed_orders = len([o for o in orders_data if o.get("status") == "COMPLETE"])

    trades_today = TradesTodayResponse(
        count=executed_orders,  # Orders executed
        fills=len(trade_items),  # Individual fills
        trades=trade_items,
    )

    # --- Calculate brokerage and charges ---
    # Zerodha/Dhan F&O charges (per SEBI regulations)
    # Brokerage: ₹20 per executed order (flat)
    # STT: 0.15% on sell side premium (options)
    # Exchange charges: 0.053% (NSE F&O)
    # GST: 18% on (brokerage + exchange charges)
    # SEBI charges: ₹10 per crore turnover
    
    num_orders = len([o for o in orders_data if o.get("status") == "COMPLETE"])
    brokerage = num_orders * 20.0  # ₹20 per order
    
    # Calculate sell-side turnover for STT (options: 0.15% on sell premium)
    sell_turnover = 0.0
    total_turnover = 0.0
    for trade in trades_data:
        qty = int(trade.get("filled_quantity", trade.get("quantity", 0)))
        price = float(trade.get("average_price", 0))
        trade_value = qty * price
        total_turnover += trade_value
        if trade.get("transaction_type") == "SELL":
            sell_turnover += trade_value
    
    stt = sell_turnover * 0.0015  # 0.15% on sell side
    exchange_charges = total_turnover * 0.00053  # 0.053% exchange txn charges
    gst = (brokerage + exchange_charges) * 0.18  # 18% GST
    sebi_charges = total_turnover * 0.000001  # ₹10 per crore = 0.0001%
    stamp_duty = total_turnover * 0.00003  # 0.003% (buy side only, approximated)
    
    total_charges = round(brokerage + stt + exchange_charges + gst + sebi_charges + stamp_duty, 2)
    net_pnl = round(total_pnl - total_charges, 2)

    # --- Build P&L summary ---
    pnl_summary = PnLSummaryResponse(
        total_pnl=round(total_pnl, 2),
        realized_pnl=round(realized_pnl, 2),
        unrealized_pnl=round(unrealized_pnl, 2),
        brokerage=round(brokerage, 2),
        stt=round(stt, 2),
        exchange_charges=round(exchange_charges + sebi_charges + stamp_duty, 2),
        gst=round(gst, 2),
        total_charges=total_charges,
        net_pnl=net_pnl,
    )

    # --- Build orders today ---
    order_items: List[OrderItem] = []
    for order in orders_data:
        order_items.append(OrderItem(
            symbol=order.get("tradingsymbol", ""),
            status=order.get("status", ""),
            transaction_type=order.get("transaction_type", ""),
            qty=int(order.get("quantity", 0)),
            price=float(order.get("average_price", order.get("price", 0))),
        ))

    orders_today = OrdersTodayResponse(
        count=len(order_items),
        orders=order_items,
    )

    return AccountDashboardResponse(
        profile=profile,
        margins=margins,
        positions=positions,
        trades_today=trades_today,
        pnl_summary=pnl_summary,
        orders_today=orders_today,
    )
