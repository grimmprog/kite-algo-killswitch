"""Kill Switch API endpoints for the Admin Testing UI.

Provides endpoints to activate and deactivate the kill switch per user
via Redis key operations.

Requirements covered:
- 5.1: Display kill switch status
- 5.2: Activate kill switch (set Redis key to "true")
- 5.3: Deactivate kill switch (delete Redis key)
- 5.6: Log activation with timestamp
- 9.7: POST activate/deactivate endpoints
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.admin.dependencies import get_redis
from src.cache.redis_client import RedisClient
from src.cache.redis_keys import RedisKeys

logger = logging.getLogger(__name__)

router = APIRouter()


class KillSwitchStatusResponse(BaseModel):
    """Response model for kill switch status."""

    user_id: int
    status: str  # "active" or "inactive"


class KillSwitchActivateResponse(BaseModel):
    """Response model for kill switch activation."""

    user_id: int
    status: str
    activated_at: str


class KillSwitchDeactivateResponse(BaseModel):
    """Response model for kill switch deactivation."""

    user_id: int
    status: str


@router.post(
    "/api/killswitch/{user_id}/activate",
    response_model=KillSwitchActivateResponse,
)
async def activate_killswitch(
    user_id: int,
    redis: RedisClient = Depends(get_redis),
) -> KillSwitchActivateResponse:
    """Activate the kill switch for a user.

    Sets the Redis key user:{user_id}:killswitch to "true" and
    logs the activation with a timestamp.
    """
    try:
        key = RedisKeys.user_killswitch(user_id)
        redis.set(key, "true")
        activated_at = datetime.now().isoformat()
        logger.info(
            "Kill switch activated for user %d at %s", user_id, activated_at
        )
        return KillSwitchActivateResponse(
            user_id=user_id,
            status="active",
            activated_at=activated_at,
        )
    except Exception as e:
        logger.error("Failed to activate kill switch for user %d: %s", user_id, e)
        raise HTTPException(
            status_code=500, detail="Failed to activate kill switch"
        )


@router.post(
    "/api/killswitch/{user_id}/deactivate",
    response_model=KillSwitchDeactivateResponse,
)
async def deactivate_killswitch(
    user_id: int,
    redis: RedisClient = Depends(get_redis),
) -> KillSwitchDeactivateResponse:
    """Deactivate the kill switch for a user.

    Deletes the Redis key user:{user_id}:killswitch.
    """
    try:
        key = RedisKeys.user_killswitch(user_id)
        redis.delete(key)
        logger.info("Kill switch deactivated for user %d", user_id)
        return KillSwitchDeactivateResponse(
            user_id=user_id,
            status="inactive",
        )
    except Exception as e:
        logger.error("Failed to deactivate kill switch for user %d: %s", user_id, e)
        raise HTTPException(
            status_code=500, detail="Failed to deactivate kill switch"
        )


@router.get(
    "/api/killswitch/{user_id}/status",
    response_model=KillSwitchStatusResponse,
)
async def get_killswitch_status(
    user_id: int,
    redis: RedisClient = Depends(get_redis),
) -> KillSwitchStatusResponse:
    """Get the current kill switch status for a user.

    Reads the Redis key and returns active/inactive.
    """
    try:
        key = RedisKeys.user_killswitch(user_id)
        value = redis.get(key)
        status = "active" if value == "true" else "inactive"
        return KillSwitchStatusResponse(user_id=user_id, status=status)
    except Exception as e:
        logger.error("Failed to read kill switch status for user %d: %s", user_id, e)
        raise HTTPException(
            status_code=500, detail="Failed to read kill switch status"
        )
