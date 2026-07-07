"""Celery task for order execution.

Orchestrates the full trade execution flow by accepting order data,
validating it, executing with retries, confirming fill, storing the trade,
and updating caches.

Requirements covered:
- 1.3.3: Validate trades before execution (kill switch, margin, duplicates)
- 1.3.4: Place orders with broker via Kite API
- 1.3.5: Retry failed orders up to 3 times with exponential backoff
- 1.3.6: Wait up to 30 seconds for order fill confirmation
- 2.3.6: Handle broker API failures with retries
"""

import logging
import os
from typing import Dict

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.cache.redis_client import get_redis_client
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


@celery_app.task(name="execute_order")
def execute_order(order_data: dict) -> dict:
    """Celery task to execute a trade order.

    Orchestrates the full execution flow:
    1. Accept order data and extract user_id (Task 7.8.1)
    2. Validate the order
    3. Execute with retries (Task 7.8.2)
    4. Confirm fill
    5. Store trade
    6. Mark as recent
    7. Update position cache
    8. Return result (Task 7.8.3)

    Args:
        order_data: Dictionary containing order details with keys:
            - user_id (int): The user's database ID
            - symbol (str): Trading symbol
            - exchange (str): Exchange segment (e.g., 'NSE', 'NFO')
            - side (str): Transaction type ('BUY' or 'SELL')
            - quantity (int): Order quantity
            - order_type (str, optional): Order type, defaults to 'MARKET'
            - price (float, optional): Price for LIMIT orders

    Returns:
        Dictionary with execution result:
            - success (bool): Whether the order was executed successfully
            - order_id (str or None): Broker order ID on success
            - message (str): Human-readable status message
            - filled (bool): Whether the order was filled
            - fill_price (float or None): Fill price if filled
            - fill_quantity (int or None): Fill quantity if filled
    """
    try:
        return _execute_order_flow(order_data)
    except Exception as e:
        logger.error(
            "Unexpected top-level error in execute_order task: %s: %s",
            type(e).__name__,
            str(e),
            extra={"order_data": order_data},
        )
        return {
            "success": False,
            "order_id": None,
            "message": f"Unexpected error: {type(e).__name__}: {str(e)}",
            "filled": False,
            "fill_price": None,
            "fill_quantity": None,
        }


def _execute_order_flow(order_data: dict) -> dict:
    """Internal implementation of the order execution flow.

    Separated from the task function to allow the task's top-level
    try/except to catch any unexpected errors without nesting.
    """
    from src.workers.execution_worker import ExecutionWorker

    # --- Step 1: Accept order data (Task 7.8.1) ---
    user_id = order_data.get("user_id")
    if not user_id:
        return {
            "success": False,
            "order_id": None,
            "message": "Missing user_id in order data",
            "filled": False,
            "fill_price": None,
            "fill_quantity": None,
        }

    # Get dependencies
    redis_client = get_redis_client()
    db_session = get_db_session()

    try:
        kite_client = get_user_kite_client(user_id, db_session)
    except RuntimeError as e:
        logger.warning(
            "Cannot get Kite client for user %d: %s", user_id, str(e)
        )
        db_session.close()
        return {
            "success": False,
            "order_id": None,
            "message": f"Broker connection error: {str(e)}",
            "filled": False,
            "fill_price": None,
            "fill_quantity": None,
        }

    try:
        # Create execution worker
        worker = ExecutionWorker(
            user_id=user_id,
            kite_client=kite_client,
            redis_client=redis_client,
            db_session=db_session,
        )

        # --- Step 2: Validate the order ---
        valid, message = worker.validate_order(order_data)
        if not valid:
            return {
                "success": False,
                "order_id": None,
                "message": message,
                "filled": False,
                "fill_price": None,
                "fill_quantity": None,
            }

        # --- Step 3: Execute with retries (Task 7.8.2) ---
        result = worker.execute_with_retry(order_data)

        if not result["success"]:
            # Store failed order for record keeping
            worker.store_trade(order_data, result)
            return {
                "success": False,
                "order_id": result.get("order_id"),
                "message": result.get("message", "Order execution failed"),
                "filled": False,
                "fill_price": None,
                "fill_quantity": None,
            }

        # --- Step 4: Confirm fill ---
        order_id = result["order_id"]
        fill_result = worker.confirm_fill(order_id)

        # --- Step 5: Store trade ---
        trade_data = {
            **result,
            "filled": fill_result.get("filled", False),
            "price": fill_result.get("price"),
            "status": "COMPLETE" if fill_result.get("filled") else "PENDING",
        }
        worker.store_trade(order_data, trade_data)

        # --- Step 6: Mark as recent ---
        worker.mark_recent_order(order_data)

        # --- Step 7: Update position cache ---
        worker.update_position_cache(order_data, trade_data)

        # --- Step 8: Return result (Task 7.8.3) ---
        return {
            "success": True,
            "order_id": order_id,
            "message": "Order executed successfully",
            "filled": fill_result.get("filled", False),
            "fill_price": fill_result.get("price"),
            "fill_quantity": fill_result.get("quantity"),
        }

    except Exception as e:
        logger.error(
            "Error in order execution flow for user %d: %s: %s",
            user_id,
            type(e).__name__,
            str(e),
            exc_info=True,
        )
        return {
            "success": False,
            "order_id": None,
            "message": f"{type(e).__name__}: {str(e)}",
            "filled": False,
            "fill_price": None,
            "fill_quantity": None,
        }
    finally:
        db_session.close()
