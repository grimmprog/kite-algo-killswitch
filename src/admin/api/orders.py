"""Order Validation API endpoints for the Admin Testing UI.

Provides POST /admin/api/validate-order to submit mock orders
to the ExecutionWorker.validate_order() method and return results.

Requirements covered:
- 6.1: Form with symbol, side, quantity, reason
- 6.2: Call validate_order and return result
- 6.3: Green/red indicator for valid/invalid
- 6.4: Identify which check failed
- 9.8: POST /admin/api/validate-order endpoint
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.admin.dependencies import get_db, get_redis
from src.cache.redis_client import RedisClient
from src.workers.execution_worker import ExecutionWorker

logger = logging.getLogger(__name__)

router = APIRouter()


class OrderValidationRequest(BaseModel):
    """Request body for order validation."""

    user_id: int
    symbol: str
    side: str  # "BUY" or "SELL"
    quantity: int
    reason: Optional[str] = None


class OrderValidationResponse(BaseModel):
    """Response model for order validation result."""

    valid: bool
    message: str
    failed_check: Optional[str] = None  # "kill_switch", "margin", or "duplicate"


def _parse_failed_check(message: str) -> Optional[str]:
    """Parse the failure message to identify which check failed.

    Args:
        message: The failure message from validate_order.

    Returns:
        The check name: "kill_switch", "margin", or "duplicate", or None.
    """
    msg_lower = message.lower()
    if "kill switch" in msg_lower:
        return "kill_switch"
    if "margin" in msg_lower:
        return "margin"
    if "duplicate" in msg_lower:
        return "duplicate"
    return None


class _MockKiteClient:
    """A minimal mock Kite client for order validation.

    The validate_order method does not call any Kite API methods,
    so this mock is sufficient for running pre-trade checks.
    """

    pass


@router.post("/api/validate-order", response_model=OrderValidationResponse)
async def validate_order(
    body: OrderValidationRequest,
    redis: RedisClient = Depends(get_redis),
    db: Session = Depends(get_db),
) -> OrderValidationResponse:
    """Validate a mock order using ExecutionWorker.

    Instantiates an ExecutionWorker with the specified user_id,
    the Redis client, and a mock Kite client. Calls validate_order()
    and parses the result to identify which check failed (if any).
    """
    try:
        # Instantiate ExecutionWorker with mock Kite client
        worker = ExecutionWorker(
            user_id=body.user_id,
            kite_client=_MockKiteClient(),
            redis_client=redis,
            db_session=db,
        )

        # Build order dict
        order = {
            "symbol": body.symbol,
            "side": body.side,
            "quantity": body.quantity,
        }
        if body.reason:
            order["reason"] = body.reason

        # Run validation
        is_valid, message = worker.validate_order(order)

        # Parse failure reason
        failed_check = None if is_valid else _parse_failed_check(message)

        return OrderValidationResponse(
            valid=is_valid,
            message=message,
            failed_check=failed_check,
        )

    except ValueError as e:
        # ExecutionWorker raises ValueError for invalid user_id etc.
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("Order validation error: %s", e)
        raise HTTPException(status_code=500, detail="Order validation failed")
