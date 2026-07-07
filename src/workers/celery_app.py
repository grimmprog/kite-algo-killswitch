"""Celery application configuration for the Multi-User Web Trading Platform.

Creates and configures the Celery app instance used by all workers
(market data, risk engine, execution).

Requirements covered:
- 1.6.1: Fetch spot prices for configured instruments every 3-5 seconds
"""

import os

from celery import Celery
from celery.schedules import crontab

# Redis URL for broker (message queue) and backend (result storage)
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "trading_platform",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

# Celery configuration
celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # Timezone
    timezone="Asia/Kolkata",
    enable_utc=True,
    # Task behavior
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Result expiry (1 hour)
    result_expires=3600,
)

# Beat schedule: periodic tasks
celery_app.conf.beat_schedule = {
    "update-market-data-every-4s": {
        "task": "src.workers.market_data_task.update_market_data",
        "schedule": 4.0,  # Every 4 seconds (midpoint of 3-5s range)
    },
    "schedule-risk-monitoring-every-3s": {
        "task": "src.workers.risk_engine_task.schedule_risk_monitoring",
        "schedule": 3.0,  # Every 3 seconds (Requirement 1.4.1)
    },
    "check-signal-expiry-every-5s": {
        "task": "src.workers.signal_expiry_worker.check_signal_expiry",
        "schedule": 5.0,  # Every 5 seconds (Requirements 4.5, 4.6)
    },
    "schedule-pnl-monitoring-every-5s": {
        "task": "src.workers.auto_monitor_task.schedule_pnl_monitoring",
        "schedule": 5.0,  # Every 5 seconds (Requirements 10.2-10.5)
    },
    "evaluate-exit-recommendations-every-30s": {
        "task": "src.workers.ai_worker.schedule_exit_evaluations",
        "schedule": 30.0,  # Every 30 seconds (Requirement 21.1)
    },
    "schedule-position-monitoring-every-2s": {
        "task": "src.workers.position_monitor_worker.schedule_position_monitoring",
        "schedule": 2.0,  # Every 2 seconds (Requirements 7.2, 7.3, 7.4, 7.5, 7.6, 8.1-8.5)
    },
    "auto-login-daily-8-45-am": {
        "task": "src.workers.auto_login_worker.schedule_auto_logins",
        "schedule": crontab(hour=3, minute=15),  # 8:45 AM IST = 3:15 UTC
    },
    "save-daily-pnl-3-35-pm": {
        "task": "src.workers.daily_pnl_worker.save_all_daily_pnl",
        "schedule": crontab(hour=10, minute=5),  # 3:35 PM IST = 10:05 UTC
    },
}

# Auto-discover tasks from workers package
celery_app.autodiscover_tasks(["src.workers"])
