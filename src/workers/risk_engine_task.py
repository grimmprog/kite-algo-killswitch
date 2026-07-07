"""Celery task for per-user risk monitoring.

Schedules the RiskEngineWorker to run for EACH active user every 3 seconds.
A beat-scheduled task (schedule_risk_monitoring) dispatches individual
run_risk_engine tasks per user, enabling parallel risk checks.

Requirements covered:
- 1.4.1: Monitor each user's P&L every 2-3 seconds
- 1.8.5: Maintain separate execution queue for each user
- 2.3.8: Continue processing other users when one user's operation fails
"""

import logging
import os
from typing import Dict, List

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.cache.redis_client import get_redis_client
from src.cache.redis_keys import RedisKeys
from src.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Database URL from environment
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/trading_platform",
)

# Module-level engine/session factory (lazy init)
_engine = None
_SessionFactory = None


def _get_session_factory():
    """Get or create the SQLAlchemy session factory (lazy singleton).

    Returns:
        A sessionmaker bound to the database engine.
    """
    global _engine, _SessionFactory
    if _SessionFactory is None:
        _engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        _SessionFactory = sessionmaker(bind=_engine)
    return _SessionFactory


def get_db_session() -> Session:
    """Create a new database session.

    Returns:
        A new SQLAlchemy Session instance.
    """
    factory = _get_session_factory()
    return factory()


def get_active_users(db_session: Session) -> List[Dict]:
    """Query database for all active users with valid broker tokens.

    An active user is one where:
    - is_active is True
    - broker_access_token is not None (has a valid broker connection)

    Args:
        db_session: SQLAlchemy session for database queries.

    Returns:
        List of dicts with user_id, capital, daily_loss_limit_percent
        for each active user.
    """
    from src.database.models.user import User

    try:
        users = (
            db_session.query(User)
            .filter(
                User.is_active == True,  # noqa: E712
                User.broker_access_token.isnot(None),
            )
            .all()
        )

        return [
            {
                "user_id": user.id,
                "capital": user.capital,
                "daily_loss_limit_percent": user.daily_loss_limit_percent,
            }
            for user in users
        ]
    except Exception as e:
        logger.error("Failed to query active users: %s: %s", type(e).__name__, str(e))
        return []


def get_user_kite_client(user_id: int, db_session: Session):
    """Get a configured KiteConnect client for a specific user.

    Reads the user's broker_access_token from the database and creates
    a KiteConnect instance configured for that user.

    Args:
        user_id: The user's database ID.
        db_session: SQLAlchemy session for database queries.

    Returns:
        A configured KiteConnect instance for the user.

    Raises:
        RuntimeError: If the user has no valid broker token or KITE_API_KEY is missing.
    """
    from kiteconnect import KiteConnect

    from src.database.models.user import User

    api_key = os.environ.get("KITE_API_KEY")
    if not api_key:
        raise RuntimeError("KITE_API_KEY environment variable is required")

    user = db_session.query(User).filter(User.id == user_id).first()
    if not user or not user.broker_access_token:
        raise RuntimeError(f"User {user_id} has no valid broker access token")

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(user.broker_access_token)
    return kite


@celery_app.task(name="src.workers.risk_engine_task.run_risk_engine")
def run_risk_engine(user_id: int) -> Dict:
    """Celery task: Run risk engine for a specific user.

    Performs a full risk monitoring cycle for one user:
    1. Check if killswitch is already active (skip if so)
    2. Get user's Kite client from broker integration
    3. Create RiskEngineWorker and run the full cycle
    4. Handle errors per user without affecting other users

    Requirements covered:
    - 1.4.1: Monitor each user's P&L every 2-3 seconds
    - 1.5.2: Block all new trades immediately when kill switch activates
    - 2.3.8: Continue processing other users when one user's operation fails

    Args:
        user_id: The user's database ID.

    Returns:
        A dict summarizing the run:
            - "status" (str): "success", "skipped", or "error"
            - "user_id" (int): The user's ID
            - "reason" (str): Description of the outcome
    """
    try:
        return _execute_risk_engine(user_id)
    except Exception as e:
        logger.error(
            "Unexpected top-level error in run_risk_engine for user %d: %s: %s",
            user_id,
            type(e).__name__,
            str(e),
        )
        return {
            "status": "error",
            "user_id": user_id,
            "reason": f"Unexpected error: {type(e).__name__}: {str(e)}",
        }


def _execute_risk_engine(user_id: int) -> Dict:
    """Internal implementation of the risk engine run for one user.

    Separated from the task function to allow the task's top-level
    try/except to catch any unexpected errors without nesting.
    """
    from src.workers.risk_engine_worker import RiskEngineWorker

    # Step 1: Check if killswitch is already active
    redis_client = get_redis_client()
    killswitch_key = RedisKeys.user_killswitch(user_id)
    killswitch_value = redis_client.get(killswitch_key)

    if killswitch_value == "true":
        logger.debug("Kill switch active for user %d, skipping risk engine", user_id)
        return {
            "status": "skipped",
            "user_id": user_id,
            "reason": "Kill switch already active",
        }

    # Step 2: Get database session and user's Kite client
    db_session = get_db_session()
    try:
        kite_client = get_user_kite_client(user_id, db_session)
    except RuntimeError as e:
        logger.warning(
            "Cannot get Kite client for user %d: %s", user_id, str(e)
        )
        db_session.close()
        return {
            "status": "error",
            "user_id": user_id,
            "reason": f"Kite client error: {str(e)}",
        }

    # Step 3: Create worker and run full risk monitoring cycle
    try:
        worker = RiskEngineWorker(
            user_id=user_id,
            kite_client=kite_client,
            redis_client=redis_client,
            db_session=db_session,
        )

        # Fetch positions safely (handles broker API errors)
        positions = worker.fetch_positions_safe()

        # Compute risk metrics
        pnl = worker.compute_live_pnl(positions)
        greeks = worker.compute_greeks(positions)
        margin_used = worker.compute_margin_used(positions)

        # Cache risk metrics in Redis
        worker.update_redis_cache(pnl, greeks, margin_used)

        # Get user config for threshold checking
        from src.database.models.user import User

        user = db_session.query(User).filter(User.id == user_id).first()
        if user:
            capital = user.capital
            daily_loss_limit_pct = user.daily_loss_limit_percent

            # Check thresholds
            breached, reason = worker.check_thresholds(
                pnl=pnl,
                capital=capital,
                daily_loss_limit_pct=daily_loss_limit_pct,
                margin_used=margin_used,
            )

            if breached:
                worker.trigger_killswitch(reason, capital)
                return {
                    "status": "success",
                    "user_id": user_id,
                    "reason": f"Kill switch triggered: {reason}",
                }

        return {
            "status": "success",
            "user_id": user_id,
            "reason": "Risk check completed",
        }

    except Exception as e:
        logger.error(
            "Error running risk engine for user %d: %s: %s",
            user_id,
            type(e).__name__,
            str(e),
            exc_info=True,
        )
        return {
            "status": "error",
            "user_id": user_id,
            "reason": f"{type(e).__name__}: {str(e)}",
        }
    finally:
        db_session.close()


@celery_app.task(name="src.workers.risk_engine_task.schedule_risk_monitoring")
def schedule_risk_monitoring() -> Dict:
    """Celery beat task: Dispatch risk engine for each active user.

    Queries the database for all active users with valid broker tokens
    and dispatches a run_risk_engine task for each one via Celery.
    This enables per-user parallelism.

    Requirements covered:
    - 1.4.1: Monitor each user's P&L every 2-3 seconds
    - 1.8.5: Maintain separate execution queue for each user

    Returns:
        A dict summarizing the dispatch:
            - "status" (str): "success" or "error"
            - "users_dispatched" (int): Number of tasks sent
            - "reason" (str): Description of the outcome
    """
    try:
        return _execute_schedule_risk_monitoring()
    except Exception as e:
        logger.error(
            "Unexpected top-level error in schedule_risk_monitoring: %s: %s",
            type(e).__name__,
            str(e),
        )
        return {
            "status": "error",
            "users_dispatched": 0,
            "reason": f"Unexpected error: {type(e).__name__}: {str(e)}",
        }


def _execute_schedule_risk_monitoring() -> Dict:
    """Internal implementation of the risk monitoring scheduler.

    Queries active users and dispatches individual risk engine tasks.
    """
    db_session = get_db_session()
    try:
        active_users = get_active_users(db_session)

        if not active_users:
            logger.debug("No active users found for risk monitoring")
            return {
                "status": "success",
                "users_dispatched": 0,
                "reason": "No active users with valid broker tokens",
            }

        # Dispatch a run_risk_engine task for each active user
        dispatched_count = 0
        for user_info in active_users:
            user_id = user_info["user_id"]
            try:
                run_risk_engine.delay(user_id)
                dispatched_count += 1
            except Exception as e:
                logger.error(
                    "Failed to dispatch risk engine for user %d: %s: %s",
                    user_id,
                    type(e).__name__,
                    str(e),
                )

        logger.info(
            "Risk monitoring scheduled: dispatched %d/%d user tasks",
            dispatched_count,
            len(active_users),
        )

        return {
            "status": "success",
            "users_dispatched": dispatched_count,
            "reason": f"Dispatched {dispatched_count} user risk engine tasks",
        }
    finally:
        db_session.close()
