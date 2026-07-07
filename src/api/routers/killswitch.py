"""Kill Switch API endpoints.

Requirements covered:
- 1.5.1: Atomically set kill switch flag in Redis
- 1.5.2: Block all new trades immediately when active
- 1.5.6: Log kill switch activations with timestamp and reason

Endpoints:
- POST /api/v1/killswitch/activate — Manually activate kill switch
- POST /api/v1/killswitch/deactivate — Deactivate kill switch
- GET /api/v1/killswitch/status — Get kill switch status
- GET /api/v1/killswitch/logs — Get kill switch activation history
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_user, get_db, get_redis
from src.api.schemas import KillSwitchStatusResponse
from src.cache.redis_client import RedisClient
from src.cache.redis_keys import RedisKeys

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/killswitch", tags=["killswitch"])


# --------------------------------------------------------------------------
# 12.1: POST /api/v1/killswitch/activate
# --------------------------------------------------------------------------


@router.post("/activate")
async def activate_killswitch(
    user_id: int = Depends(get_current_user),
    redis: RedisClient = Depends(get_redis),
    db: Session = Depends(get_db),
):
    """Manually activate kill switch.

    12.1.1: Validate auth (handled by get_current_user dependency)
    12.1.2: Set kill switch flag in Redis
    12.1.3: Log activation to database
    12.1.4: Return confirmation
    """
    # 12.1.2: Set kill switch flag atomically
    redis.set(RedisKeys.user_killswitch(user_id), "true")

    # 12.1.3: Log activation to database
    from src.database.models.killswitch_log import KillSwitchLog

    log = KillSwitchLog(user_id=user_id, trigger_reason="Manual activation")
    db.add(log)
    db.commit()

    logger.info("Kill switch activated for user %d (manual)", user_id)

    # 12.1.4: Return confirmation
    return {"message": "Kill switch activated", "active": True}


# --------------------------------------------------------------------------
# 12.2: POST /api/v1/killswitch/deactivate
# --------------------------------------------------------------------------


@router.post("/deactivate")
async def deactivate_killswitch(
    user_id: int = Depends(get_current_user),
    redis: RedisClient = Depends(get_redis),
):
    """Deactivate kill switch.

    12.2.1: Validate auth (handled by get_current_user dependency)
    12.2.2: Clear kill switch flag from Redis
    12.2.3: Return confirmation
    """
    # 12.2.2: Clear flag
    redis.delete(RedisKeys.user_killswitch(user_id))

    logger.info("Kill switch deactivated for user %d", user_id)

    # 12.2.3: Return confirmation
    return {"message": "Kill switch deactivated", "active": False}


# --------------------------------------------------------------------------
# 12.3: GET /api/v1/killswitch/status
# --------------------------------------------------------------------------


@router.get("/status", response_model=KillSwitchStatusResponse)
async def get_killswitch_status(
    user_id: int = Depends(get_current_user),
    redis: RedisClient = Depends(get_redis),
):
    """Get kill switch status.

    12.3.1: Check Redis flag
    12.3.2: Return status
    """
    ks = redis.get(RedisKeys.user_killswitch(user_id))
    active = ks is not None and ks.lower() == "true"

    return KillSwitchStatusResponse(active=active, user_id=user_id)


# --------------------------------------------------------------------------
# 12.4: GET /api/v1/killswitch/logs
# --------------------------------------------------------------------------


@router.get("/logs")
async def get_killswitch_logs(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get kill switch log history.

    12.4.1: Query logs for user
    12.4.2: Return history sorted by timestamp descending
    """
    from src.database.models.killswitch_log import KillSwitchLog

    logs = (
        db.query(KillSwitchLog)
        .filter(KillSwitchLog.user_id == user_id)
        .order_by(KillSwitchLog.timestamp.desc())
        .all()
    )

    return [
        {
            "id": log.id,
            "reason": log.trigger_reason,
            "timestamp": log.timestamp.isoformat(),
            "positions_closed": log.positions_closed_count,
        }
        for log in logs
    ]
