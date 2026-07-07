"""System Status and Capital API endpoints.

Requirements covered:
- 13.1: Capital display on Dashboard (available balance, configured capital, used/available margin)
- 13.2: Fetch latest margin data from Zerodha API
- 13.3: Margin breakdown by segment (equity, commodity, F&O)
- 13.4: Refresh margin data every 60 seconds (frontend responsibility, API serves fresh data)
- 16.1: Market hours countdown (time to open or close)
- 16.2: Zerodha session status (connected/disconnected/expired)
- 16.3: Background worker status (scanner, position monitor, kill switch monitor)
- 16.4: Warning indicator for non-running workers
- 16.5: Refresh every 30 seconds (frontend responsibility, API serves current data)

Endpoints:
- GET /api/v1/status/system — Market hours, session status, worker statuses
- GET /api/v1/status/capital — Capital, margin, and segment breakdown
"""

import json
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from src.api.dependencies import get_redis, get_current_user
from src.cache.redis_client import RedisClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["status"])

# IST offset: UTC+5:30
IST_OFFSET = timedelta(hours=5, minutes=30)

# Market hours (IST)
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 15
MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MINUTE = 30

# Worker heartbeat threshold (seconds)
WORKER_HEARTBEAT_MAX_AGE = 60

# Known worker names
KNOWN_WORKERS = ["scanner_worker", "position_monitor_worker", "killswitch_monitor"]


# --------------------------------------------------------------------------
# Response Models
# --------------------------------------------------------------------------


class WorkerStatus(BaseModel):
    """Status of a single background worker."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    status: str  # "running" or "stopped"


class SystemStatusResponse(BaseModel):
    """System status including market hours, session, and workers."""

    model_config = ConfigDict(from_attributes=True)

    market_status: str  # "pre_market", "open", "closed"
    countdown_seconds: int  # seconds to open or close
    session_status: str  # "connected", "disconnected", "expired"
    workers: List[WorkerStatus]


class CapitalResponse(BaseModel):
    """Capital and margin breakdown."""

    model_config = ConfigDict(from_attributes=True)

    available_balance: float
    configured_capital: float
    used_margin: float
    available_margin: float
    segment_breakdown: Dict[str, float]


# --------------------------------------------------------------------------
# Helper functions
# --------------------------------------------------------------------------


def _get_current_ist_time() -> datetime:
    """Get current time in IST (UTC+5:30).

    Returns:
        datetime in IST timezone.
    """
    utc_now = datetime.now(timezone.utc)
    ist_now = utc_now + IST_OFFSET
    return ist_now


def _compute_market_status_and_countdown(ist_now: datetime) -> tuple:
    """Compute market status and countdown seconds based on current IST time.

    Args:
        ist_now: Current datetime in IST.

    Returns:
        Tuple of (market_status, countdown_seconds).
    """
    current_time_minutes = ist_now.hour * 60 + ist_now.minute
    market_open_minutes = MARKET_OPEN_HOUR * 60 + MARKET_OPEN_MINUTE
    market_close_minutes = MARKET_CLOSE_HOUR * 60 + MARKET_CLOSE_MINUTE

    if current_time_minutes < market_open_minutes:
        # Pre-market: countdown to market open
        market_status = "pre_market"
        seconds_to_open = (market_open_minutes - current_time_minutes) * 60 - ist_now.second
        countdown_seconds = max(0, seconds_to_open)
    elif current_time_minutes < market_close_minutes:
        # Market open: countdown to market close
        market_status = "open"
        seconds_to_close = (market_close_minutes - current_time_minutes) * 60 - ist_now.second
        countdown_seconds = max(0, seconds_to_close)
    else:
        # Market closed: countdown to next day open (approx)
        market_status = "closed"
        # Seconds remaining in today + seconds from midnight to 9:15
        seconds_remaining_today = (24 * 60 - current_time_minutes) * 60 - ist_now.second
        seconds_to_open_next_day = market_open_minutes * 60
        countdown_seconds = max(0, seconds_remaining_today + seconds_to_open_next_day)

    return market_status, countdown_seconds


def _get_session_status(redis_client: RedisClient, user_id: int) -> str:
    """Check Zerodha session status from Redis.

    Args:
        redis_client: Redis client instance.
        user_id: Current user's ID.

    Returns:
        Session status string: "connected", "disconnected", or "expired".
    """
    session_key = f"kite:session:{user_id}"
    try:
        session_data = redis_client.get(session_key)
        if session_data is None:
            return "disconnected"

        # If session data exists, check if it's expired via TTL
        ttl = redis_client.ttl(session_key)
        if ttl == -2:
            # Key does not exist
            return "disconnected"
        elif ttl == -1:
            # Key exists with no expiry — connected
            return "connected"
        elif ttl > 0:
            # Key exists with TTL — connected (still valid)
            return "connected"
        else:
            return "expired"
    except Exception as e:
        logger.warning(f"Error checking session status: {e}")
        return "disconnected"


def _get_worker_statuses(redis_client: RedisClient) -> List[WorkerStatus]:
    """Check worker heartbeat status from Redis.

    A worker is considered "running" if its heartbeat key was updated
    within the last 60 seconds.

    Args:
        redis_client: Redis client instance.

    Returns:
        List of WorkerStatus with each worker's name and status.
    """
    workers = []
    now = time.time()

    for worker_name in KNOWN_WORKERS:
        heartbeat_key = f"worker:{worker_name}:heartbeat"
        try:
            heartbeat_value = redis_client.get(heartbeat_key)
            if heartbeat_value is not None:
                last_heartbeat = float(heartbeat_value)
                if (now - last_heartbeat) <= WORKER_HEARTBEAT_MAX_AGE:
                    workers.append(WorkerStatus(name=worker_name, status="running"))
                else:
                    workers.append(WorkerStatus(name=worker_name, status="stopped"))
            else:
                workers.append(WorkerStatus(name=worker_name, status="stopped"))
        except (ValueError, TypeError) as e:
            logger.warning(f"Error reading heartbeat for {worker_name}: {e}")
            workers.append(WorkerStatus(name=worker_name, status="stopped"))

    return workers


def _get_capital_data(redis_client: RedisClient, user_id: int) -> CapitalResponse:
    """Get capital and margin data from Redis cache.

    The margin data is populated by the existing market data worker
    from the Zerodha API. Key: kite:margins:{user_id}

    Args:
        redis_client: Redis client instance.
        user_id: Current user's ID.

    Returns:
        CapitalResponse with balance, capital, margin, and segment breakdown.
    """
    margins_key = f"kite:margins:{user_id}"
    try:
        margins_data = redis_client.get(margins_key)
        if margins_data is not None:
            data = json.loads(margins_data)
            return CapitalResponse(
                available_balance=float(data.get("available_balance", 0.0)),
                configured_capital=float(data.get("configured_capital", 0.0)),
                used_margin=float(data.get("used_margin", 0.0)),
                available_margin=float(data.get("available_margin", 0.0)),
                segment_breakdown=data.get("segment_breakdown", {
                    "equity": 0.0,
                    "commodity": 0.0,
                    "fno": 0.0,
                }),
            )
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.warning(f"Error parsing margin data for user {user_id}: {e}")

    # Return default/empty values if no data in Redis
    return CapitalResponse(
        available_balance=0.0,
        configured_capital=0.0,
        used_margin=0.0,
        available_margin=0.0,
        segment_breakdown={
            "equity": 0.0,
            "commodity": 0.0,
            "fno": 0.0,
        },
    )


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------


@router.get("/status/system", response_model=SystemStatusResponse)
async def get_system_status(
    user_id: int = Depends(get_current_user),
    redis_client: RedisClient = Depends(get_redis),
) -> SystemStatusResponse:
    """Get system status including market hours countdown, session, and workers.

    Returns market status (pre_market/open/closed), countdown in seconds,
    Zerodha session connectivity status, and background worker statuses.

    Requirements: 16.1-16.5
    """
    ist_now = _get_current_ist_time()
    market_status, countdown_seconds = _compute_market_status_and_countdown(ist_now)
    session_status = _get_session_status(redis_client, user_id)
    workers = _get_worker_statuses(redis_client)

    return SystemStatusResponse(
        market_status=market_status,
        countdown_seconds=countdown_seconds,
        session_status=session_status,
        workers=workers,
    )


@router.get("/status/capital", response_model=CapitalResponse)
async def get_capital_status(
    user_id: int = Depends(get_current_user),
    redis_client: RedisClient = Depends(get_redis),
) -> CapitalResponse:
    """Get capital and margin breakdown.

    Returns available balance, configured capital, used/available margin,
    and segment breakdown (equity, commodity, F&O) from Redis cache.
    Data is populated by the existing market data worker from Zerodha API.

    Requirements: 13.1-13.4
    """
    return _get_capital_data(redis_client, user_id)
