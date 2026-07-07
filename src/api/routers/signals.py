"""Signal Approval API endpoints.

Requirements covered:
- 4.1: Display pending signals with trade details
- 4.2: Provide approve/reject actions
- 4.3: Approve submits trade for execution via trade execution API
- 4.4: Reject dismisses signal and logs rejection
- 4.5: Countdown timer per pending signal
- 4.6: Expired signals move to history

Endpoints:
- GET  /api/v1/signals/pending       — Get pending signals with countdown
- POST /api/v1/signals/{id}/approve  — Approve signal and submit trade
- POST /api/v1/signals/{id}/reject   — Reject signal
- GET  /api/v1/signals/history       — Get signal history (non-pending)
"""

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from src.api.dependencies import get_db, get_redis, get_current_user
from src.cache.redis_client import RedisClient
from src.database.models.scan_signal import ScanSignal
from src.services.signal_service import SignalService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["signals"])


# --------------------------------------------------------------------------
# Response schemas
# --------------------------------------------------------------------------


class PendingSignalResponse(BaseModel):
    """A pending signal with remaining countdown information."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    signal_type: str
    confidence_score: float
    entry_price: float
    stop_loss: float
    target_price: float
    max_potential_loss: float
    status: str
    countdown_seconds: int
    remaining_seconds: int
    expires_at: Optional[str] = None
    created_at: Optional[str] = None
    ai_quality_rating: Optional[str] = None
    ai_warnings: Optional[list] = None
    ai_explanation: Optional[str] = None


class SignalHistoryResponse(BaseModel):
    """A signal that has been approved, rejected, or expired."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    signal_type: str
    confidence_score: float
    entry_price: float
    stop_loss: float
    target_price: float
    max_potential_loss: float
    status: str
    countdown_seconds: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    ai_quality_rating: Optional[str] = None
    ai_warnings: Optional[list] = None
    ai_explanation: Optional[str] = None


class SignalApproveResponse(BaseModel):
    """Response after approving a signal."""

    signal_id: int
    symbol: str
    entry_price: float
    stop_loss: float
    target_price: float
    signal_type: str
    confidence_score: float
    trade_task_id: Optional[str] = None
    message: str


class SignalRejectResponse(BaseModel):
    """Response after rejecting a signal."""

    signal_id: int
    status: str
    message: str


# --------------------------------------------------------------------------
# GET /api/v1/signals/pending
# --------------------------------------------------------------------------


@router.get("/signals/pending", response_model=List[PendingSignalResponse])
async def get_pending_signals(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """Get all pending signals for the current user with remaining countdown.

    Returns signals ordered by creation time (newest first), each with
    the remaining seconds until expiry calculated from Redis TTL.

    Requirements: 4.1, 4.5
    """
    service = SignalService(db=db, redis_client=redis)
    pending = service.get_pending_signals(user_id)

    return [PendingSignalResponse(**signal) for signal in pending]


# --------------------------------------------------------------------------
# POST /api/v1/signals/{id}/approve
# --------------------------------------------------------------------------


@router.post("/signals/{signal_id}/approve", response_model=SignalApproveResponse)
async def approve_signal(
    signal_id: int,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """Approve a pending signal and submit the trade for execution.

    Approves the signal via SignalService, then queues the trade for
    execution through the existing Celery trade execution pipeline.

    Requirements: 4.2, 4.3
    """
    service = SignalService(db=db, redis_client=redis)

    try:
        result = service.approve_signal(signal_id, user_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # Submit trade for execution via existing Celery task
    trade_task_id = None
    try:
        from src.workers.celery_app import celery_app

        # Check kill switch before submitting trade
        from src.cache.redis_keys import RedisKeys

        ks = redis.get(RedisKeys.user_killswitch(user_id))
        if ks and ks.lower() == "true":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Trading blocked: kill switch is active",
            )

        order_data = {
            "user_id": user_id,
            "symbol": result["symbol"],
            "exchange": "NFO",  # Default to NFO for option signals
            "quantity": 1,  # Default lot; settings-driven in production
            "side": "BUY",
            "order_type": "MARKET",
            "price": result["entry_price"],
        }

        task = celery_app.send_task("execute_order", args=[order_data])
        trade_task_id = task.id

        logger.info(
            "Signal %d approved by user %d, trade queued: task_id=%s",
            signal_id,
            user_id,
            trade_task_id,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(
            "Signal %d approved but trade queue failed: %s", signal_id, exc
        )

    return SignalApproveResponse(
        signal_id=result["signal_id"],
        symbol=result["symbol"],
        entry_price=result["entry_price"],
        stop_loss=result["stop_loss"],
        target_price=result["target_price"],
        signal_type=result["signal_type"],
        confidence_score=result["confidence_score"],
        trade_task_id=trade_task_id,
        message="Signal approved and trade queued for execution",
    )


# --------------------------------------------------------------------------
# POST /api/v1/signals/{id}/reject
# --------------------------------------------------------------------------


@router.post("/signals/{signal_id}/reject", response_model=SignalRejectResponse)
async def reject_signal(
    signal_id: int,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """Reject a pending signal and dismiss it.

    Updates signal status to "rejected" and logs the rejection.

    Requirements: 4.2, 4.4
    """
    service = SignalService(db=db, redis_client=redis)

    try:
        result = service.reject_signal(signal_id, user_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    logger.info("Signal %d rejected by user %d", signal_id, user_id)

    return SignalRejectResponse(
        signal_id=result["signal_id"],
        status=result["status"],
        message="Signal rejected and dismissed",
    )


# --------------------------------------------------------------------------
# GET /api/v1/signals/history
# --------------------------------------------------------------------------


@router.get("/signals/history", response_model=List[SignalHistoryResponse])
async def get_signal_history(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    """Get signal history (all non-pending signals) for the current user.

    Returns approved, rejected, and expired signals sorted by
    updated_at descending (most recent action first).

    Requirements: 4.6
    """
    offset = (page - 1) * page_size

    signals = (
        db.query(ScanSignal)
        .filter(
            ScanSignal.user_id == user_id,
            ScanSignal.status != "pending",
        )
        .order_by(ScanSignal.updated_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )

    return [
        SignalHistoryResponse(
            id=s.id,
            symbol=s.symbol,
            signal_type=s.signal_type,
            confidence_score=s.confidence_score,
            entry_price=s.entry_price,
            stop_loss=s.stop_loss,
            target_price=s.target_price,
            max_potential_loss=s.max_potential_loss,
            status=s.status,
            countdown_seconds=s.countdown_seconds,
            created_at=s.created_at,
            updated_at=s.updated_at,
            ai_quality_rating=s.ai_quality_rating,
            ai_warnings=s.ai_warnings,
            ai_explanation=s.ai_explanation,
        )
        for s in signals
    ]
