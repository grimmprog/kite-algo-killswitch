"""Risk Metrics API endpoints for the Admin Testing UI.

Provides GET /admin/api/risk/{user_id} to read per-user risk metrics
from Redis and compute derived fields (margin_percent, threshold_warning).

Requirements covered:
- 4.1: Display user risk metrics from Redis
- 4.3: Show updated_at timestamp
- 4.4: Show "No risk data" when unavailable
- 4.5: Show margin as absolute and percentage
- 4.6: Risk threshold flagging
- 9.6: GET /admin/api/risk/{user_id} endpoint
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.admin.dependencies import get_db, get_redis
from src.cache.redis_client import RedisClient
from src.cache.redis_keys import RedisKeys, RiskMetrics
from src.database.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


class RiskMetricsResponse(BaseModel):
    """Response model for user risk metrics."""

    pnl: float
    net_delta: float
    net_gamma: float
    net_vega: float
    margin_used: float
    margin_percent: float
    updated_at: str
    threshold_warning: bool


@router.get("/api/risk/{user_id}", response_model=RiskMetricsResponse)
async def get_risk(
    user_id: int,
    redis: RedisClient = Depends(get_redis),
    db: Session = Depends(get_db),
) -> RiskMetricsResponse:
    """Get risk metrics for a user.

    Reads the Redis hash at user:{user_id}:risk, parses the fields,
    computes margin_percent and threshold_warning, and returns the result.

    Returns HTTP 404 when the risk hash is empty (no data available).
    """
    try:
        # Read risk hash from Redis
        key = RedisKeys.user_risk(user_id)
        raw = redis.hgetall(key)

        if not raw:
            raise HTTPException(status_code=404, detail="No risk data")

        # Parse fields — handle both bytes and string keys
        metrics = RiskMetrics.from_redis_hash(raw)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Redis error reading risk for user %d: %s", user_id, e)
        raise HTTPException(status_code=500, detail="Failed to read risk data from Redis")

    try:
        # Get user's capital from DB
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        capital = user.capital
        daily_loss_limit_percent = user.daily_loss_limit_percent

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Database error reading user %d: %s", user_id, e)
        raise HTTPException(status_code=500, detail="Database unavailable")

    # Compute margin_percent = (margin_used / capital) * 100
    margin_percent = (metrics.margin_used / capital * 100) if capital > 0 else 0.0

    # Compute threshold_warning: true when abs(pnl)/capital*100 > 0.5 * daily_loss_limit_percent
    pnl_loss_percent = (abs(metrics.pnl) / capital * 100) if capital > 0 else 0.0
    threshold_warning = pnl_loss_percent > (0.5 * daily_loss_limit_percent)

    return RiskMetricsResponse(
        pnl=metrics.pnl,
        net_delta=metrics.net_delta,
        net_gamma=metrics.net_gamma,
        net_vega=metrics.net_vega,
        margin_used=metrics.margin_used,
        margin_percent=round(margin_percent, 2),
        updated_at=metrics.updated_at,
        threshold_warning=threshold_warning,
    )
