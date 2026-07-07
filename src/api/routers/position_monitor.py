"""Position Monitor API endpoints.

Requirements covered:
- 7.1-7.7: Position Monitor with SL/Target Tracking
- 8.1-8.5: Exit Strategy Rules Display
- 10.1-10.5: Auto-Monitor Toggle

Endpoints:
- GET /api/v1/positions/monitor — Get all monitored positions with SL/Target status
- GET /api/v1/positions/{id}/exit-rules — Get exit conditions for a specific position
- POST /api/v1/positions/{id}/exit — Trigger manual exit for a position
- PUT /api/v1/monitor/toggle — Start/stop background auto-monitor
"""

import json
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.dependencies import get_db, get_redis, get_current_user
from src.cache.redis_client import RedisClient
from src.database.models.position_monitor import PositionMonitorState
from src.services.position_monitor_service import (
    ExitCondition,
    MarketData,
    MonitoredPosition,
    PositionMonitorService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["position_monitor"])

# Redis key for auto-monitor toggle state
MONITOR_TOGGLE_KEY = "user:{user_id}:auto_monitor"


# --------------------------------------------------------------------------
# Request/Response models
# --------------------------------------------------------------------------


class ManualExitRequest(BaseModel):
    """Request body for triggering a manual position exit."""

    reason: str = "manual_exit"


class ManualExitResponse(BaseModel):
    """Response after triggering a manual exit."""

    position_id: int
    symbol: str
    entry_price: float
    current_price: float
    quantity: int
    exit_reason: str
    trade_id: int


class MonitorToggleRequest(BaseModel):
    """Request body for toggling the auto-monitor."""

    active: bool


class MonitorToggleResponse(BaseModel):
    """Response after toggling the auto-monitor state."""

    active: bool
    message: str


# --------------------------------------------------------------------------
# GET /api/v1/positions/monitor
# --------------------------------------------------------------------------


@router.get("/positions/monitor", response_model=List[MonitoredPosition])
async def get_monitored_positions(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all monitored positions with SL/Target status and computed metrics.

    Returns positions with:
    - Current price, entry price, stop-loss, target
    - Unrealized P&L
    - Distance to SL/Target as percentage
    - Trailing stop level (if enabled)

    Requirements: 7.1
    """
    service = PositionMonitorService(db=db)
    positions = service.get_monitored_positions(user_id=user_id)
    return positions


# --------------------------------------------------------------------------
# GET /api/v1/positions/{id}/exit-rules
# --------------------------------------------------------------------------


@router.get("/positions/{position_id}/exit-rules", response_model=List[ExitCondition])
async def get_exit_rules(
    position_id: int,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """Get exit conditions for a specific position.

    Evaluates all exit rules (EMA cross, VWAP touch, consecutive green
    candles, time-based) against current market data.

    Requirements: 8.1-8.5
    """
    # Verify position belongs to user
    position_state = (
        db.query(PositionMonitorState)
        .filter(
            PositionMonitorState.id == position_id,
            PositionMonitorState.user_id == user_id,
        )
        .first()
    )

    if position_state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Position {position_id} not found",
        )

    service = PositionMonitorService(db=db)

    # Build MonitoredPosition from DB record
    current_price = position_state.current_price or position_state.entry_price
    quantity = position_state.trade.qty if position_state.trade else 1

    if current_price > 0:
        distance_to_sl_pct = (current_price - position_state.stop_loss) / current_price * 100
        distance_to_target_pct = (position_state.target - current_price) / current_price * 100
    else:
        distance_to_sl_pct = 0.0
        distance_to_target_pct = 0.0

    monitored_position = MonitoredPosition(
        position_id=position_state.id,
        symbol=position_state.symbol,
        entry_price=position_state.entry_price,
        current_price=current_price,
        quantity=quantity,
        stop_loss=position_state.stop_loss,
        target=position_state.target,
        trailing_stop_enabled=position_state.trailing_stop_enabled,
        trailing_stop_level=position_state.trailing_stop_level,
        trailing_stop_distance=position_state.trailing_stop_distance,
        unrealized_pnl=(current_price - position_state.entry_price) * quantity,
        distance_to_sl_pct=distance_to_sl_pct,
        distance_to_target_pct=distance_to_target_pct,
        status=position_state.status,
    )

    # Get market data from Redis for exit condition evaluation
    market_data = _get_market_data_from_redis(redis, position_state.symbol, current_price)

    conditions = service.evaluate_exit_conditions(
        position=monitored_position,
        market_data=market_data,
    )

    return conditions


# --------------------------------------------------------------------------
# POST /api/v1/positions/{id}/exit
# --------------------------------------------------------------------------


@router.post("/positions/{position_id}/exit", response_model=ManualExitResponse)
async def trigger_manual_exit(
    position_id: int,
    body: ManualExitRequest,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Trigger a manual exit for a position.

    Accepts a reason in the body (defaults to "manual_exit") and triggers
    the auto-exit flow for the given position.

    Requirements: 7.7
    """
    # Verify position belongs to user
    position_state = (
        db.query(PositionMonitorState)
        .filter(
            PositionMonitorState.id == position_id,
            PositionMonitorState.user_id == user_id,
        )
        .first()
    )

    if position_state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Position {position_id} not found",
        )

    if position_state.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Position {position_id} is not active (current status: {position_state.status})",
        )

    service = PositionMonitorService(db=db)

    # Map manual exit reason to a valid reason for trigger_auto_exit
    reason = "closed"

    try:
        result = service.trigger_auto_exit(position_id=position_id, reason=reason)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return ManualExitResponse(
        position_id=result["position_id"],
        symbol=result["symbol"],
        entry_price=result["entry_price"],
        current_price=result["current_price"],
        quantity=result["quantity"],
        exit_reason=body.reason,
        trade_id=result["trade_id"],
    )


# --------------------------------------------------------------------------
# PUT /api/v1/monitor/toggle
# --------------------------------------------------------------------------


@router.put("/monitor/toggle", response_model=MonitorToggleResponse)
async def toggle_auto_monitor(
    body: MonitorToggleRequest,
    user_id: int = Depends(get_current_user),
    redis: RedisClient = Depends(get_redis),
):
    """Start/stop background auto-monitor.

    Stores the monitor active state in Redis. When active, the background
    worker will track P&L and push threshold warnings.

    Requirements: 10.1-10.5
    """
    key = MONITOR_TOGGLE_KEY.format(user_id=user_id)
    redis.set(key, "true" if body.active else "false")

    if body.active:
        message = "Auto-monitor started"
        logger.info("Auto-monitor activated for user %d", user_id)
    else:
        message = "Auto-monitor stopped"
        logger.info("Auto-monitor deactivated for user %d", user_id)

    return MonitorToggleResponse(active=body.active, message=message)


# --------------------------------------------------------------------------
# Helper functions
# --------------------------------------------------------------------------


def _get_market_data_from_redis(
    redis: RedisClient, symbol: str, fallback_price: float
) -> MarketData:
    """Build MarketData from Redis cached market data.

    Falls back to defaults if Redis data is unavailable.

    Args:
        redis: Redis client instance.
        symbol: The trading symbol.
        fallback_price: Price to use if no market data available.

    Returns:
        MarketData instance with current indicators.
    """
    from src.cache.redis_keys import RedisKeys

    market_data_str = redis.get(RedisKeys.market_data(symbol))

    current_price = fallback_price
    ema20 = fallback_price
    vwap = fallback_price
    candles: List[dict] = []

    if market_data_str:
        try:
            data = json.loads(market_data_str)
            current_price = data.get("spot", fallback_price)
            vwap = data.get("vwap", fallback_price)
            ema20 = data.get("ema20", fallback_price)
            candles = data.get("candles", [])
        except (json.JSONDecodeError, TypeError):
            pass

    return MarketData(
        current_price=current_price,
        ema20=ema20,
        vwap=vwap,
        candles=candles,
    )
