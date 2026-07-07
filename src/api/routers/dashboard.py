"""Dashboard API endpoints.

Requirements covered:
- 1.4.5: Cache risk metrics in Redis with timestamp
- 1.7.1: Dashboard showing positions, P&L, Greeks, kill switch status

Endpoints:
- GET /api/v1/dashboard — Composite dashboard data (risk + positions + kill switch)
- GET /api/v1/positions — Open positions with current prices and P&L
- GET /api/v1/risk — Real-time risk metrics (Redis first, DB fallback)
- GET /api/v1/trades/history — Paginated trade history
"""

import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.api.dependencies import get_db, get_redis, get_current_user
from src.api.schemas import (
    DashboardResponse,
    RiskMetricsResponse,
    PositionResponse,
    TradeHistoryResponse,
)
from src.cache.redis_client import RedisClient
from src.cache.redis_keys import RedisKeys
from src.database.models.position import Position
from src.database.models.trade import Trade

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["dashboard"])


# --------------------------------------------------------------------------
# Helper functions
# --------------------------------------------------------------------------


def _parse_risk_from_redis(risk_data: dict) -> RiskMetricsResponse:
    """Parse Redis risk hash into a RiskMetricsResponse.

    Args:
        risk_data: Raw dict from Redis HGETALL.

    Returns:
        RiskMetricsResponse with parsed float values.
    """
    return RiskMetricsResponse(
        daily_loss_pct=float(risk_data.get("daily_loss_pct", "0.0")),
        capital_used_pct=float(risk_data.get("capital_used_pct", "0.0")),
        margin_used_pct=float(risk_data.get("margin_used_pct", "0.0")),
        killswitch_active=risk_data.get("killswitch_active", "false").lower() == "true",
        net_delta=float(risk_data.get("net_delta", "0.0")),
        net_gamma=float(risk_data.get("net_gamma", "0.0")),
        net_vega=float(risk_data.get("net_vega", "0.0")),
        unrealized_pnl=float(risk_data.get("pnl", "0.0")),
    )


def _default_risk_metrics() -> RiskMetricsResponse:
    """Return default (zeroed) risk metrics when no data is available."""
    return RiskMetricsResponse(
        daily_loss_pct=0.0,
        capital_used_pct=0.0,
        margin_used_pct=0.0,
        killswitch_active=False,
        net_delta=0.0,
        net_gamma=0.0,
        net_vega=0.0,
        unrealized_pnl=0.0,
    )


def _risk_from_position(position: Position, killswitch_active: bool) -> RiskMetricsResponse:
    """Build risk metrics from database Position model as a fallback.

    Args:
        position: The user's Position record from DB.
        killswitch_active: Whether the kill switch is currently active.

    Returns:
        RiskMetricsResponse derived from the position record.
    """
    return RiskMetricsResponse(
        daily_loss_pct=0.0,
        capital_used_pct=0.0,
        margin_used_pct=0.0,
        killswitch_active=killswitch_active,
        net_delta=position.net_delta,
        net_gamma=position.net_gamma,
        net_vega=position.net_vega,
        unrealized_pnl=position.unrealized_pnl,
    )


def _is_stale(risk_data: dict, max_age_seconds: int = 60) -> bool:
    """Check if risk data is stale based on the updated_at timestamp.

    Args:
        risk_data: Redis hash data containing an 'updated_at' field.
        max_age_seconds: Maximum acceptable age in seconds.

    Returns:
        True if data is stale or missing timestamp, False otherwise.
    """
    updated_at_str = risk_data.get("updated_at")
    if not updated_at_str:
        return True
    try:
        updated_at = datetime.fromisoformat(updated_at_str)
        # Make timezone-aware if naive
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        age = (now - updated_at).total_seconds()
        return age > max_age_seconds
    except (ValueError, TypeError):
        return True


def _get_killswitch_status(redis_client: RedisClient, user_id: int) -> bool:
    """Get the kill switch status from Redis.

    Args:
        redis_client: The Redis client instance.
        user_id: The user's ID.

    Returns:
        True if kill switch is active, False otherwise.
    """
    ks_value = redis_client.get(RedisKeys.user_killswitch(user_id))
    return ks_value is not None and ks_value.lower() == "true"


def _build_position_response(trade: Trade, redis_client: RedisClient) -> PositionResponse:
    """Build a PositionResponse from an open trade, enriching with current price.

    Args:
        trade: An open Trade record.
        redis_client: Redis client for fetching market data.

    Returns:
        PositionResponse with current price and computed P&L.
    """
    current_price = None
    # Try to get current market price from Redis
    market_data_str = redis_client.get(RedisKeys.market_data(trade.symbol))
    if market_data_str:
        try:
            market_data = json.loads(market_data_str)
            current_price = market_data.get("spot")
        except (json.JSONDecodeError, TypeError):
            pass

    # Compute P&L based on current price if available
    if current_price is not None:
        if trade.side == "BUY":
            pnl = (current_price - trade.entry_price) * trade.qty
        else:
            pnl = (trade.entry_price - current_price) * trade.qty
    else:
        pnl = trade.pnl

    return PositionResponse(
        symbol=trade.symbol,
        quantity=trade.qty,
        entry_price=trade.entry_price,
        current_price=current_price,
        pnl=pnl,
        margin_used=trade.margin_used or 0.0,
    )


# --------------------------------------------------------------------------
# 10.1: GET /api/v1/dashboard
# --------------------------------------------------------------------------


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """Get dashboard data: risk metrics, positions, kill switch status.

    10.1.1: Fetch risk metrics from Redis
    10.1.2: Fetch positions from database
    10.1.3: Compute summary stats
    10.1.4: Return DashboardResponse
    """
    # 10.1.1: Fetch risk metrics from Redis
    risk_data = redis.hgetall(RedisKeys.user_risk(user_id))
    if risk_data:
        risk_metrics = _parse_risk_from_redis(risk_data)
    else:
        risk_metrics = _default_risk_metrics()

    # 10.1.2: Fetch open positions (trades with status OPEN)
    open_trades = (
        db.query(Trade)
        .filter(Trade.user_id == user_id, Trade.status == "OPEN")
        .all()
    )

    positions = [_build_position_response(t, redis) for t in open_trades]

    # 10.1.3: Get kill switch status
    killswitch_active = _get_killswitch_status(redis, user_id)

    # 10.1.4: Return composite response
    return DashboardResponse(
        risk_metrics=risk_metrics,
        positions=positions,
        killswitch_active=killswitch_active,
    )


# --------------------------------------------------------------------------
# 10.2: GET /api/v1/positions
# --------------------------------------------------------------------------


@router.get("/positions", response_model=List[PositionResponse])
async def get_positions(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """Get user's open positions with current prices and P&L.

    10.2.1: Fetch open trades for user
    10.2.2: Include current prices from Redis market data
    10.2.3: Compute P&L per position
    10.2.4: Return list of positions
    """
    open_trades = (
        db.query(Trade)
        .filter(Trade.user_id == user_id, Trade.status == "OPEN")
        .all()
    )

    return [_build_position_response(t, redis) for t in open_trades]


# --------------------------------------------------------------------------
# 10.3: GET /api/v1/risk
# --------------------------------------------------------------------------


@router.get("/risk", response_model=RiskMetricsResponse)
async def get_risk_metrics(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """Get real-time risk metrics from Redis, fallback to database.

    10.3.1: Fetch from Redis cache
    10.3.2: Check freshness (stale if > 60s or no updated_at)
    10.3.3: Fall back to database Position if stale
    10.3.4: Return risk metrics
    """
    # 10.3.1: Try Redis first
    risk_data = redis.hgetall(RedisKeys.user_risk(user_id))

    # 10.3.2: Check if data exists and is fresh
    if risk_data and not _is_stale(risk_data):
        return _parse_risk_from_redis(risk_data)

    # 10.3.3: Fall back to database
    logger.info("Risk data stale or missing for user %d, falling back to DB", user_id)
    killswitch_active = _get_killswitch_status(redis, user_id)
    position = db.query(Position).filter(Position.user_id == user_id).first()

    if position:
        return _risk_from_position(position, killswitch_active)

    # No data anywhere — return defaults
    return _default_risk_metrics()


# --------------------------------------------------------------------------
# 10.4: GET /api/v1/trades/history
# --------------------------------------------------------------------------


@router.get("/trades/history")
async def get_trade_history(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    status: Optional[str] = Query(None),
):
    """Get trade/order history. Falls back to live Kite/Dhan API when DB is empty.

    Checks DB first; if no trades stored, fetches today's orders from broker API.
    """
    offset = (page - 1) * page_size

    # Try database first
    query = db.query(Trade).filter(Trade.user_id == user_id)
    if status and status != "ALL":
        query = query.filter(Trade.status == status)

    total_db = query.count()

    if total_db > 0:
        trades = (
            query.order_by(Trade.timestamp.desc())
            .offset(offset)
            .limit(page_size)
            .all()
        )
        return {
            "orders": [
                {
                    "id": t.id,
                    "symbol": t.symbol,
                    "exchange": t.exchange,
                    "qty": t.qty,
                    "side": t.side,
                    "price": t.entry_price or 0,
                    "status": t.status or "COMPLETE",
                    "timestamp": t.timestamp.isoformat() if t.timestamp else "",
                    "pnl": t.pnl or 0,
                }
                for t in trades
            ],
            "total": total_db,
        }

    # Fallback: fetch today's orders from Kite API
    try:
        import os
        from src.broker.token_encryption import TokenEncryption
        from src.database.models.broker_connection import BrokerConnection
        from kiteconnect import KiteConnect

        # Get Kite token
        encryption_key = os.environ.get("ENCRYPTION_KEY", "")
        access_token = None

        if encryption_key:
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
                encryptor = TokenEncryption(encryption_key=encryption_key)
                access_token = encryptor.decrypt(connection.access_token_encrypted)

        # Fallback to access_token.txt
        if not access_token:
            token_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
                "access_token.txt"
            )
            if os.path.exists(token_path):
                with open(token_path) as f:
                    access_token = f.read().strip()

        if not access_token:
            return {"orders": [], "total": 0}

        api_key = os.environ.get("KITE_API_KEY", "")
        kite = KiteConnect(api_key=api_key)
        kite.set_access_token(access_token)

        orders = kite.orders()

        # Filter by status if provided
        if status and status != "ALL":
            status_map = {"Completed": "COMPLETE", "Rejected": "REJECTED", "Pending": "OPEN"}
            kite_status = status_map.get(status, status.upper())
            orders = [o for o in orders if o.get("status", "").upper() == kite_status]

        total = len(orders)

        # Paginate
        paginated = orders[offset: offset + page_size]

        return {
            "orders": [
                {
                    "id": i + offset + 1,
                    "symbol": o.get("tradingsymbol", ""),
                    "exchange": o.get("exchange", "NFO"),
                    "qty": o.get("quantity", 0),
                    "side": o.get("transaction_type", ""),
                    "price": o.get("average_price", o.get("price", 0)),
                    "status": o.get("status", ""),
                    "timestamp": o.get("order_timestamp", "").isoformat() if hasattr(o.get("order_timestamp", ""), "isoformat") else str(o.get("order_timestamp", "")),
                    "pnl": 0,
                }
                for i, o in enumerate(paginated)
            ],
            "total": total,
        }

    except Exception as e:
        logger.warning("Failed to fetch orders from Kite for user %d: %s", user_id, e)
        return {"orders": [], "total": 0}
