"""Server-Sent Events (SSE) streaming for the Admin Testing UI.

Provides an async generator that reads data from Redis at configured
intervals and yields typed SSE events for real-time dashboard updates.

Requirements covered:
- 8.1: SSE connection on page load
- 8.4: Typed events (market_data, risk_metrics, killswitch_status, worker_status)
- 8.5: Push only changed values
- 9.10: GET /admin/sse endpoint
"""

import asyncio
import json
import logging
from typing import AsyncGenerator, Any, Dict, List, Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from src.cache.redis_client import get_redis_client
from src.cache.redis_keys import RedisKeys, RiskMetrics

logger = logging.getLogger(__name__)

router = APIRouter()

INSTRUMENTS = ["NIFTY", "BANKNIFTY"]


def _get_market_data() -> Dict[str, Optional[Dict[str, Any]]]:
    """Fetch market data for all instruments from Redis."""
    redis = get_redis_client()
    result: Dict[str, Optional[Dict[str, Any]]] = {}
    for symbol in INSTRUMENTS:
        try:
            key = RedisKeys.market_data(symbol)
            raw = redis.get(key)
            if raw:
                result[symbol] = json.loads(raw)
            else:
                result[symbol] = None
        except Exception as e:
            logger.error("SSE: Failed to read market data for %s: %s", symbol, e)
            result[symbol] = None
    return result


def _get_all_risk_metrics() -> Dict[str, Optional[Dict[str, Any]]]:
    """Fetch risk metrics for all users that have risk data in Redis.

    Scans user:{id}:risk keys for IDs 1-100 (reasonable range for dev tool).
    """
    redis = get_redis_client()
    result: Dict[str, Optional[Dict[str, Any]]] = {}
    for user_id in range(1, 101):
        try:
            key = RedisKeys.user_risk(user_id)
            raw = redis.hgetall(key)
            if raw:
                metrics = RiskMetrics.from_redis_hash(raw)
                result[str(user_id)] = {
                    "pnl": metrics.pnl,
                    "net_delta": metrics.net_delta,
                    "net_gamma": metrics.net_gamma,
                    "net_vega": metrics.net_vega,
                    "margin_used": metrics.margin_used,
                    "updated_at": metrics.updated_at,
                }
        except Exception as e:
            logger.error("SSE: Failed to read risk for user %d: %s", user_id, e)
    return result


def _get_all_killswitch_status() -> Dict[str, Dict[str, bool]]:
    """Fetch kill switch status for all users (IDs 1-100)."""
    redis = get_redis_client()
    result: Dict[str, Dict[str, bool]] = {}
    for user_id in range(1, 101):
        try:
            key = RedisKeys.user_killswitch(user_id)
            value = redis.get(key)
            if value is not None:
                result[str(user_id)] = {"active": value == "true"}
            else:
                # Only include users that have some killswitch data set
                # For SSE, we include all known users with inactive status
                # to allow the UI to show status for all users
                pass
        except Exception as e:
            logger.error("SSE: Failed to read killswitch for user %d: %s", user_id, e)
    return result


def _get_worker_status() -> Dict[str, Any]:
    """Fetch Celery worker status and beat schedule."""
    try:
        from src.workers.celery_app import celery_app

        workers: List[Dict[str, str]] = []
        tasks: List[Dict[str, Any]] = []

        try:
            inspect = celery_app.control.inspect(timeout=2.0)
            ping_response = inspect.ping() or {}
            for worker_name, response in ping_response.items():
                workers.append({
                    "name": worker_name,
                    "status": "online" if response else "offline",
                })
        except Exception as e:
            logger.error("SSE: Failed to query Celery workers: %s", e)

        try:
            beat_schedule = celery_app.conf.beat_schedule or {}
            for task_name, config in beat_schedule.items():
                schedule_value = config.get("schedule")
                if hasattr(schedule_value, "total_seconds"):
                    schedule_seconds = schedule_value.total_seconds()
                else:
                    schedule_seconds = float(schedule_value) if schedule_value else None
                tasks.append({
                    "name": task_name,
                    "task": config.get("task", ""),
                    "schedule_seconds": schedule_seconds,
                })
        except Exception as e:
            logger.error("SSE: Failed to read beat schedule: %s", e)

        return {"workers": workers, "tasks": tasks}
    except Exception as e:
        logger.error("SSE: Failed to get worker status: %s", e)
        return {"workers": [], "tasks": []}


async def sse_event_generator() -> AsyncGenerator[str, None]:
    """Generate SSE events with typed data from Redis.

    Intervals:
    - market_data: every 4 seconds
    - risk_metrics: every 3 seconds
    - killswitch_status: every 3 seconds
    - worker_status: every 5 seconds

    Only pushes changed data by comparing with previous state.
    Skips failed Redis reads gracefully (continues streaming).
    """
    previous_state: Dict[str, Any] = {}
    tick = 0

    while True:
        tick += 1

        # Market data every 4 seconds
        if tick % 4 == 0:
            try:
                data = _get_market_data()
                if data != previous_state.get("market_data"):
                    previous_state["market_data"] = data
                    yield f"event: market_data\ndata: {json.dumps(data)}\n\n"
            except Exception as e:
                logger.error("SSE: Error generating market_data event: %s", e)

        # Risk metrics every 3 seconds
        if tick % 3 == 0:
            try:
                risk = _get_all_risk_metrics()
                if risk != previous_state.get("risk_metrics"):
                    previous_state["risk_metrics"] = risk
                    yield f"event: risk_metrics\ndata: {json.dumps(risk)}\n\n"
            except Exception as e:
                logger.error("SSE: Error generating risk_metrics event: %s", e)

            try:
                ks = _get_all_killswitch_status()
                if ks != previous_state.get("killswitch_status"):
                    previous_state["killswitch_status"] = ks
                    yield f"event: killswitch_status\ndata: {json.dumps(ks)}\n\n"
            except Exception as e:
                logger.error("SSE: Error generating killswitch_status event: %s", e)

        # Worker status every 5 seconds
        if tick % 5 == 0:
            try:
                workers = _get_worker_status()
                if workers != previous_state.get("worker_status"):
                    previous_state["worker_status"] = workers
                    yield f"event: worker_status\ndata: {json.dumps(workers)}\n\n"
            except Exception as e:
                logger.error("SSE: Error generating worker_status event: %s", e)

        await asyncio.sleep(1)


@router.get("/sse")
async def sse_stream():
    """SSE streaming endpoint.

    Returns a StreamingResponse that pushes typed events
    (market_data, risk_metrics, killswitch_status, worker_status)
    at configured intervals.
    """
    return StreamingResponse(
        sse_event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
