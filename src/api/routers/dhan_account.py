"""Dhan Account Dashboard API endpoint.

Provides live account data from Dhan APIs:
- Profile information
- Fund limits (margins)
- Positions (open positions with P&L)
- Today's trades
- P&L summary
- Today's orders

Endpoint:
- GET /api/v1/dashboard/dhan-account — Full account dashboard data from Dhan
"""

import logging
import os
from typing import List

import requests as http_requests
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_user, get_db
from src.api.routers.account import (
    AccountDashboardResponse,
    MarginsResponse,
    OrderItem,
    OrdersTodayResponse,
    PnLSummaryResponse,
    PositionItem,
    ProfileResponse,
    TradeItem,
    TradesTodayResponse,
)
from src.broker.token_encryption import TokenEncryption, TokenEncryptionError
from src.database.models.broker_connection import BrokerConnection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/dashboard", tags=["dhan-account-dashboard"])

DHAN_API_BASE = "https://api.dhan.co/v2"


# ---------------------------------------------------------------------------
# Dhan token helper
# ---------------------------------------------------------------------------


def _get_dhan_credentials(db: Session, user_id: int) -> tuple[str, str]:
    """Resolve Dhan access token and client ID for the given user.

    Looks up the broker_connections table for broker_type='dhan',
    decrypts the stored credentials.

    Returns:
        Tuple of (access_token, client_id).

    Raises:
        HTTPException 503: If Dhan is not connected.
    """
    encryption_key = os.environ.get("ENCRYPTION_KEY", "")
    if not encryption_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dhan not connected",
        )

    try:
        connection = (
            db.query(BrokerConnection)
            .filter(
                BrokerConnection.user_id == user_id,
                BrokerConnection.broker_type == "dhan",
                BrokerConnection.access_token_encrypted.isnot(None),
            )
            .first()
        )

        if not connection:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Dhan not connected",
            )

        encryptor = TokenEncryption(encryption_key=encryption_key)
        access_token = encryptor.decrypt(connection.access_token_encrypted)
        # client_id is stored in client_id_encrypted field
        client_id = encryptor.decrypt(connection.client_id_encrypted) if connection.client_id_encrypted else ""

        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Dhan not connected",
            )

        return access_token, client_id

    except HTTPException:
        raise
    except TokenEncryptionError as e:
        logger.error("Failed to decrypt Dhan token for user %d: %s", user_id, e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dhan not connected",
        )
    except Exception as e:
        logger.error("Dhan token lookup failed for user %d: %s", user_id, e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dhan not connected",
        )


def _dhan_headers(access_token: str, client_id: str = "") -> dict:
    """Build headers for Dhan API requests."""
    headers = {
        "access-token": access_token,
        "Content-Type": "application/json",
    }
    if client_id:
        headers["dhanClientId"] = client_id
    return headers


# ---------------------------------------------------------------------------
# GET /api/v1/dashboard/dhan-account
# ---------------------------------------------------------------------------


@router.get("/dhan-account", response_model=AccountDashboardResponse)
async def get_dhan_account_dashboard(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get comprehensive account dashboard data from Dhan APIs.

    Returns profile, margins, positions, today's trades, P&L summary,
    and today's orders — all fetched live from the Dhan API.

    Raises:
        HTTPException 503: If Dhan is not connected or token is invalid.
        HTTPException 500: If Dhan API calls fail unexpectedly.
    """
    access_token, client_id = _get_dhan_credentials(db, user_id)
    headers = _dhan_headers(access_token, client_id)

    try:
        # Fetch all data from Dhan APIs
        profile_resp = http_requests.get(
            f"{DHAN_API_BASE}/profile", headers=headers, timeout=10
        )
        fund_resp = http_requests.get(
            f"{DHAN_API_BASE}/fundlimit", headers=headers, timeout=10
        )
        positions_resp = http_requests.get(
            f"{DHAN_API_BASE}/positions", headers=headers, timeout=10
        )
        orders_resp = http_requests.get(
            f"{DHAN_API_BASE}/orders", headers=headers, timeout=10
        )
        trades_resp = http_requests.get(
            f"{DHAN_API_BASE}/trades", headers=headers, timeout=10
        )
    except Exception as e:
        logger.error("Dhan API request failed for user %d: %s", user_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch account data from Dhan: {str(e)}",
        )

    # Check for auth errors
    if profile_resp.status_code == 401 or fund_resp.status_code == 401:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dhan session expired. Please reconnect your broker.",
        )

    # --- Build profile ---
    profile_data = profile_resp.json() if profile_resp.status_code == 200 else {}
    profile = ProfileResponse(
        user_name=profile_data.get("name", profile_data.get("dhanClientId", "")),
        user_id=profile_data.get("dhanClientId", client_id),
        email=profile_data.get("email", ""),
        broker="DHAN",
    )

    # --- Build margins ---
    fund_data = fund_resp.json() if fund_resp.status_code == 200 else {}
    # Dhan fund limit response has various fields
    available_balance = float(fund_data.get("availabelBalance", fund_data.get("availableBalance", 0)))
    utilized = float(fund_data.get("utilizedAmount", 0))
    sod_limit = float(fund_data.get("sodLimit", available_balance + utilized))

    margins = MarginsResponse(
        available_capital=available_balance,
        net=sod_limit,
        used=utilized,
    )

    # --- Build positions ---
    positions_data = positions_resp.json() if positions_resp.status_code == 200 else []
    positions_list: List[PositionItem] = []
    unrealized_pnl = 0.0
    realized_pnl = 0.0

    for pos in positions_data:
        qty = int(pos.get("netQty", pos.get("quantity", 0)))
        avg_price = float(pos.get("averagePrice", pos.get("costPrice", 0)))
        ltp = float(pos.get("ltp", pos.get("lastTradedPrice", 0)))
        pnl = float(pos.get("realizedProfit", 0)) + float(pos.get("unrealizedProfit", 0))
        day_pnl = float(pos.get("dayPnl", pnl))

        if qty == 0 and pnl == 0:
            continue

        if qty != 0:
            unrealized_pnl += float(pos.get("unrealizedProfit", 0))
        realized_pnl += float(pos.get("realizedProfit", 0))

        # Map Dhan product type
        product_type = pos.get("productType", "")

        positions_list.append(PositionItem(
            symbol=pos.get("tradingSymbol", pos.get("securityId", "")),
            qty=qty,
            avg_price=avg_price,
            ltp=ltp,
            pnl=round(day_pnl, 2),
            product=product_type,
        ))

    total_pnl = realized_pnl + unrealized_pnl

    # --- Build trades today ---
    trades_data = trades_resp.json() if trades_resp.status_code == 200 else []
    trade_items: List[TradeItem] = []

    for trade in trades_data:
        trade_time = trade.get("tradingTime", trade.get("exchangeTime", ""))
        if trade_time and "T" in str(trade_time):
            # Extract time portion from ISO format
            trade_time = str(trade_time).split("T")[-1][:8]

        trade_items.append(TradeItem(
            symbol=trade.get("tradingSymbol", trade.get("securityId", "")),
            transaction_type=trade.get("transactionType", ""),
            qty=int(trade.get("tradedQuantity", trade.get("quantity", 0))),
            price=float(trade.get("tradedPrice", trade.get("tradePrice", 0))),
            time=str(trade_time),
        ))

    trades_today = TradesTodayResponse(
        count=len(trade_items),
        trades=trade_items,
    )

    # --- Calculate brokerage and charges (Dhan same structure as Zerodha) ---
    num_orders = len([o for o in (orders_resp.json() if orders_resp.status_code == 200 else []) 
                      if o.get("orderStatus") in ("TRADED", "COMPLETE")])
    brokerage = num_orders * 20.0  # ₹20 per order

    sell_turnover = 0.0
    total_turnover = 0.0
    for trade in trades_data:
        qty = int(trade.get("tradedQuantity", trade.get("quantity", 0)))
        price = float(trade.get("tradedPrice", trade.get("tradePrice", 0)))
        trade_value = qty * price
        total_turnover += trade_value
        if trade.get("transactionType") == "SELL":
            sell_turnover += trade_value

    stt = sell_turnover * 0.0015  # 0.15% on sell side
    exchange_charges = total_turnover * 0.00053
    gst = (brokerage + exchange_charges) * 0.18
    sebi_charges = total_turnover * 0.000001
    stamp_duty = total_turnover * 0.00003

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
    orders_data = orders_resp.json() if orders_resp.status_code == 200 else []
    order_items: List[OrderItem] = []

    for order in orders_data:
        order_items.append(OrderItem(
            symbol=order.get("tradingSymbol", order.get("securityId", "")),
            status=order.get("orderStatus", ""),
            transaction_type=order.get("transactionType", ""),
            qty=int(order.get("quantity", 0)),
            price=float(order.get("price", order.get("averageTradedPrice", 0))),
        ))

    orders_today = OrdersTodayResponse(
        count=len(order_items),
        orders=order_items,
    )

    return AccountDashboardResponse(
        profile=profile,
        margins=margins,
        positions=positions_list,
        trades_today=trades_today,
        pnl_summary=pnl_summary,
        orders_today=orders_today,
    )
