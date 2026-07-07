"""Worker Status API endpoints for the Admin Testing UI.

Provides GET /admin/api/workers to query Celery inspect API
for worker state and task schedule information.

Requirements covered:
- 7.1: Display market data task status
- 7.2: Display risk engine task status
- 7.3: Display registered Celery workers
- 9.9: GET /admin/api/workers endpoint
"""

import logging
from typing import Any, Dict, List

from fastapi import APIRouter

from src.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/workers")
async def get_workers() -> Dict[str, Any]:
    """Query Celery for active workers and beat schedule info.

    Returns worker online/offline state and registered beat tasks
    with their intervals. Handles Celery broker unavailability gracefully.

    Returns:
        JSON with workers list and tasks list.
    """
    workers: List[Dict[str, str]] = []
    tasks: List[Dict[str, Any]] = []

    # Query active workers
    try:
        inspect = celery_app.control.inspect(timeout=2.0)
        ping_response = inspect.ping() or {}

        for worker_name, response in ping_response.items():
            workers.append({
                "name": worker_name,
                "status": "online" if response else "offline",
            })
    except Exception as e:
        logger.error("Failed to query Celery workers: %s", e)
        # Return empty workers list on broker unavailability

    # Beat schedule info (read from config, always available)
    try:
        beat_schedule = celery_app.conf.beat_schedule or {}
        for task_name, config in beat_schedule.items():
            schedule_value = config.get("schedule")
            # Handle both numeric and timedelta schedules
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
        logger.error("Failed to read beat schedule: %s", e)

    return {"workers": workers, "tasks": tasks}
