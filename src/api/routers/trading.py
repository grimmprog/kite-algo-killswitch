"""Trading API endpoints.

Requirements covered:
- 1.3.3: Validate trades before execution (kill switch check)
- 1.3.4: Place orders with broker via Kite API (async via Celery)
- 1.5.2: Block all new trades immediately when kill switch is active

Endpoints:
- POST /api/v1/trades/execute — Queue trade for async execution
- GET /api/v1/trades/status/{task_id} — Check async task status
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.dependencies import get_current_user, get_redis
from src.api.schemas import TradeRequest, TradeResponse
from src.cache.redis_client import RedisClient
from src.cache.redis_keys import RedisKeys

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/trades", tags=["trading"])


# --------------------------------------------------------------------------
# 11.1: POST /api/v1/trades/execute
# --------------------------------------------------------------------------


@router.post("/execute", response_model=TradeResponse)
async def execute_trade(
    request: TradeRequest,
    user_id: int = Depends(get_current_user),
    redis: RedisClient = Depends(get_redis),
):
    """Queue trade for execution. Check kill switch first.

    11.1.1: Validate trade request (handled by Pydantic schema)
    11.1.2: Check kill switch — block if active
    11.1.3: Queue execution task via Celery
    11.1.4: Return task ID
    """
    # 11.1.2: Check kill switch
    ks = redis.get(RedisKeys.user_killswitch(user_id))
    if ks and ks.lower() == "true":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Trading blocked: kill switch is active",
        )

    # 11.1.3: Queue Celery task
    from src.workers.celery_app import celery_app

    order_data = {
        "user_id": user_id,
        "symbol": request.symbol,
        "exchange": request.exchange,
        "quantity": request.quantity,
        "side": request.side,
        "order_type": request.order_type,
        "price": request.price,
    }

    task = celery_app.send_task("execute_order", args=[order_data])
    logger.info("Trade queued for user %d: task_id=%s, symbol=%s", user_id, task.id, request.symbol)

    # 11.1.4: Return task ID
    return TradeResponse(task_id=task.id, message="Order queued for execution")


# --------------------------------------------------------------------------
# 11.2: GET /api/v1/trades/status/{task_id}
# --------------------------------------------------------------------------


@router.get("/status/{task_id}")
async def get_trade_status(
    task_id: str,
    user_id: int = Depends(get_current_user),
):
    """Check async task status.

    11.2.1: Look up task by ID
    11.2.2: Return execution result if completed, else pending status
    """
    from src.workers.celery_app import celery_app

    result = celery_app.AsyncResult(task_id)

    if result.ready():
        return {"status": "completed", "result": result.get()}

    return {"status": "pending", "result": None}
