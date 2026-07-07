"""Execution Worker for the Multi-User Web Trading Platform.

Order execution worker with retry logic that handles order placement,
validation, and confirmation. Validates trades before execution including
kill switch check, margin validation, and duplicate detection.

Requirements covered:
- 1.3.3: Validate trades before execution (kill switch, margin, duplicates)
- 1.3.5: Retry failed orders up to 3 times with exponential backoff
- 1.3.10: Block new trades when kill switch is active
- 1.4.8: Trigger kill switch when margin usage exceeds 90% of capital
- 2.3.6: Handle broker API failures with retries
"""

import logging
import time
from datetime import datetime
from typing import Dict, List, Tuple

import redis
from kiteconnect import exceptions as kite_exceptions
from sqlalchemy.exc import SQLAlchemyError

from src.cache.redis_keys import RedisKeys
from src.database.models.order import Order
from src.database.models.trade import Trade
from src.database.models.user import User
from src.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


class ExecutionWorker:
    """Order execution worker with retry logic.

    Handles order validation, placement, confirmation, and storage.
    Validates each order against the kill switch, margin limits, and
    duplicate detection before sending to the broker.

    Args:
        user_id: The user's database ID.
        kite_client: A configured KiteConnect instance for the user.
        redis_client: Redis client instance for cache reads.
        db_session: SQLAlchemy session for database operations.
    """

    def __init__(self, user_id: int, kite_client, redis_client, db_session) -> None:
        """Initialize ExecutionWorker.

        Args:
            user_id: The user's database ID.
            kite_client: A configured KiteConnect instance for the user.
            redis_client: Redis client instance for cache reads.
            db_session: SQLAlchemy session for database access.

        Raises:
            ValueError: If user_id is invalid or required dependencies are None.
        """
        if not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("user_id must be a positive integer")
        if kite_client is None:
            raise ValueError("kite_client cannot be None")
        if redis_client is None:
            raise ValueError("redis_client cannot be None")
        if db_session is None:
            raise ValueError("db_session cannot be None")

        self.user_id = user_id
        self.kite = kite_client
        self.redis = redis_client
        self.db = db_session
        self.max_retries = 3
        self.retry_backoff = 1.0  # seconds

    def check_killswitch(self) -> bool:
        """Check if user's kill switch is active.

        Reads the kill switch flag from Redis using the standard key pattern.
        Returns True if the kill switch is active (trading should be blocked),
        False if inactive or if the key doesn't exist.

        On Redis errors, returns True (block trading) as a safety measure —
        it's safer to reject a trade than to allow one when the system state
        is uncertain.

        Requirements covered:
        - 1.3.3: Validate trades before execution (kill switch check)
        - 1.3.10: Block new trades when kill switch is active

        Returns:
            True if kill switch is active or if Redis is unreachable (safe default).
            False if kill switch is inactive or key doesn't exist.
        """
        try:
            key = RedisKeys.user_killswitch(self.user_id)
            status = self.redis.get(key)

            if status is None:
                # Key doesn't exist — kill switch is not active
                return False

            # Handle both bytes and string responses from Redis
            if isinstance(status, bytes):
                return status == b"true"
            return status == "true"

        except redis.RedisError as e:
            logger.error(
                "Redis error checking kill switch for user %d: %s. "
                "Defaulting to active (blocking trades) for safety.",
                self.user_id,
                str(e),
                extra={"user_id": self.user_id, "error_type": "RedisError"},
            )
            # Safe default: block trading if we can't confirm kill switch state
            return True

        except Exception as e:
            logger.error(
                "Unexpected error checking kill switch for user %d: %s: %s. "
                "Defaulting to active (blocking trades) for safety.",
                self.user_id,
                type(e).__name__,
                str(e),
                extra={"user_id": self.user_id, "error_type": type(e).__name__},
            )
            # Safe default: block trading if we can't confirm kill switch state
            return True

    def check_margin_availability(self) -> Tuple[bool, str]:
        """Check if user has sufficient margin to place a trade.

        Reads the current margin_used from the Redis risk metrics hash and
        compares it against 90% of the user's capital from the database.
        If margin_used >= 90% of capital, the trade is rejected.

        On Redis or database errors, returns (False, "...") as a safety measure —
        it's safer to reject a trade than to allow one when the system state
        is uncertain.

        Requirements covered:
        - 1.3.3: Validate trades before execution (margin check)
        - 1.4.8: Trigger kill switch when margin usage exceeds 90% of capital

        Returns:
            Tuple of (is_valid, message):
            - (True, "Margin available") if margin_used < 90% of capital
            - (False, "Insufficient margin") if margin_used >= 90% of capital
            - (False, "Margin check failed: ...") on errors
        """
        try:
            # Read margin_used from Redis risk hash
            key = RedisKeys.user_risk(self.user_id)
            risk_data = self.redis.hgetall(key)

            if not risk_data:
                # No risk data in Redis — could be a fresh user with no positions
                margin_used = 0.0
            else:
                # Handle both bytes and string keys from Redis
                raw_margin = risk_data.get(b"margin_used") or risk_data.get("margin_used")
                margin_used = float(raw_margin) if raw_margin else 0.0

        except redis.RedisError as e:
            logger.error(
                "Redis error reading margin for user %d: %s. "
                "Blocking trade for safety.",
                self.user_id,
                str(e),
                extra={"user_id": self.user_id, "error_type": "RedisError"},
            )
            return False, "Margin check failed: Redis unavailable"

        except (ValueError, TypeError) as e:
            logger.error(
                "Error parsing margin data for user %d: %s. "
                "Blocking trade for safety.",
                self.user_id,
                str(e),
                extra={"user_id": self.user_id, "error_type": type(e).__name__},
            )
            return False, "Margin check failed: invalid margin data"

        try:
            # Get user's capital from database
            user = self.db.query(User).filter_by(id=self.user_id).first()

            if user is None:
                logger.error(
                    "User %d not found in database during margin check.",
                    self.user_id,
                    extra={"user_id": self.user_id},
                )
                return False, "Margin check failed: user not found"

            capital = user.capital

        except SQLAlchemyError as e:
            logger.error(
                "Database error reading capital for user %d: %s. "
                "Blocking trade for safety.",
                self.user_id,
                str(e),
                extra={"user_id": self.user_id, "error_type": "SQLAlchemyError"},
            )
            return False, "Margin check failed: database unavailable"

        except Exception as e:
            logger.error(
                "Unexpected error reading capital for user %d: %s: %s. "
                "Blocking trade for safety.",
                self.user_id,
                type(e).__name__,
                str(e),
                extra={"user_id": self.user_id, "error_type": type(e).__name__},
            )
            return False, "Margin check failed: unexpected error"

        # Check 90% margin limit (Requirement 1.4.8)
        margin_limit = capital * 0.9
        if margin_used >= margin_limit:
            logger.warning(
                "Margin limit exceeded for user %d: margin_used=%.2f, "
                "capital=%.2f, limit=%.2f (90%%).",
                self.user_id,
                margin_used,
                capital,
                margin_limit,
                extra={
                    "user_id": self.user_id,
                    "margin_used": margin_used,
                    "capital": capital,
                    "margin_limit": margin_limit,
                },
            )
            return False, "Insufficient margin"

        return True, "Margin available"

    def create_order_signature(self, order: Dict) -> str:
        """Create a unique signature for an order used in duplicate detection.

        Generates a string in the format `{symbol}:{side}:{quantity}` that
        uniquely identifies an order for deduplication purposes. This signature
        is used both when checking for duplicates and when marking an order
        as recently placed.

        Requirements covered:
        - 1.3.9: Prevent duplicate orders within 60 seconds

        Args:
            order: Dictionary containing at least 'symbol', 'side', and 'quantity'.

        Returns:
            A string signature in the format "SYMBOL:SIDE:QUANTITY".

        Raises:
            KeyError: If required keys ('symbol', 'side', 'quantity') are missing.
            TypeError: If order is None or not a dictionary.
        """
        if order is None:
            raise TypeError("order cannot be None")
        if not isinstance(order, dict):
            raise TypeError("order must be a dictionary")

        # Validate required keys exist
        required_keys = ("symbol", "side", "quantity")
        missing_keys = [k for k in required_keys if k not in order]
        if missing_keys:
            raise KeyError(
                f"Order is missing required keys: {', '.join(missing_keys)}"
            )

        return f"{order['symbol']}:{order['side']}:{order['quantity']}"

    def is_duplicate_order(self, order: Dict) -> bool:
        """Check if order is a duplicate within the last 60 seconds.

        Creates an order signature from the order's symbol, side, and quantity,
        then checks the user's recent orders list in Redis for a match. The
        Redis list has a 60-second TTL (set by mark_recent_order on placement).

        On Redis errors, returns False (allow the trade) — blocking a valid
        trade is worse than allowing a potential duplicate which can be
        reconciled after the fact.

        Requirements covered:
        - 1.3.3: Validate trades before execution (duplicate check)
        - 1.3.9: Prevent duplicate orders within 60 seconds

        Args:
            order: Dictionary containing at least 'symbol', 'side', and 'quantity'.

        Returns:
            True if a duplicate order signature is found in the recent orders list.
            False if no duplicate found, or if Redis is unreachable (permissive default).
        """
        try:
            order_signature = self.create_order_signature(order)

            key = RedisKeys.user_recent_orders(self.user_id)
            recent_orders = self.redis.lrange(key, 0, -1)

            for recent in recent_orders:
                # Handle both bytes and string responses from Redis
                value = recent.decode() if isinstance(recent, bytes) else recent
                if value == order_signature:
                    logger.warning(
                        "Duplicate order detected for user %d: %s",
                        self.user_id,
                        order_signature,
                        extra={
                            "user_id": self.user_id,
                            "order_signature": order_signature,
                        },
                    )
                    return True

            return False

        except redis.RedisError as e:
            logger.error(
                "Redis error checking duplicate orders for user %d: %s. "
                "Allowing trade (permissive default).",
                self.user_id,
                str(e),
                extra={"user_id": self.user_id, "error_type": "RedisError"},
            )
            # Permissive default: allow the trade if we can't check for duplicates
            return False

        except (KeyError, TypeError) as e:
            logger.error(
                "Invalid order data for duplicate check, user %d: %s: %s. "
                "Allowing trade (permissive default).",
                self.user_id,
                type(e).__name__,
                str(e),
                extra={"user_id": self.user_id, "error_type": type(e).__name__},
            )
            # Permissive default: allow the trade if order data is malformed
            return False

        except Exception as e:
            logger.error(
                "Unexpected error checking duplicate orders for user %d: %s: %s. "
                "Allowing trade (permissive default).",
                self.user_id,
                type(e).__name__,
                str(e),
                extra={"user_id": self.user_id, "error_type": type(e).__name__},
            )
            # Permissive default: allow the trade if anything unexpected happens
            return False

    def mark_recent_order(self, order: Dict) -> None:
        """Record an order in the user's recent orders list for duplicate detection.

        After a successful order placement, this method pushes the order's
        signature to the user's recent_orders Redis list. The list is trimmed
        to 10 entries and given a 60-second TTL so that duplicate detection
        only looks back over a short, bounded window.

        This method handles Redis errors gracefully — a failure to mark an
        order should never break the trade flow. The order has already been
        placed at this point, so we log the error and continue.

        Requirements covered:
        - 1.3.9: Prevent duplicate orders within 60 seconds

        Args:
            order: Dictionary containing at least 'symbol', 'side', and 'quantity'.
        """
        try:
            order_signature = self.create_order_signature(order)
            key = RedisKeys.user_recent_orders(self.user_id)

            # Push to left of list (most recent first)
            self.redis.lpush(key, order_signature)
            # Keep only the last 10 orders
            self.redis.ltrim(key, 0, 9)
            # Set 60-second TTL for the duplicate detection window
            self.redis.expire(key, 60)

        except redis.RedisError as e:
            logger.error(
                "Redis error marking recent order for user %d: %s. "
                "Order was placed but duplicate detection may miss it.",
                self.user_id,
                str(e),
                extra={"user_id": self.user_id, "error_type": "RedisError"},
            )

        except (KeyError, TypeError) as e:
            logger.error(
                "Invalid order data for marking recent order, user %d: %s: %s.",
                self.user_id,
                type(e).__name__,
                str(e),
                extra={"user_id": self.user_id, "error_type": type(e).__name__},
            )

        except Exception as e:
            logger.error(
                "Unexpected error marking recent order for user %d: %s: %s.",
                self.user_id,
                type(e).__name__,
                str(e),
                extra={"user_id": self.user_id, "error_type": type(e).__name__},
            )

    def place_order(self, order: Dict) -> Dict:
        """Place an order with the broker via the Kite Connect API.

        Calls self.kite.place_order() with the appropriate parameters mapped
        from the internal order dictionary format. Uses VARIETY_REGULAR and
        product='MIS' (intraday) for all orders.

        Handles specific Kite API exceptions with appropriate logging and
        retryability classification:
        - TokenException: ERROR level, non-retryable (auth issue)
        - NetworkException: WARNING level, retryable (transient)
        - OrderException: WARNING level, non-retryable (exchange rejection)
        - InputException: ERROR level, non-retryable (bad params)
        - General/unknown Exception: ERROR level, non-retryable

        Parameter mapping from order dict to Kite API:
        - order['exchange'] -> exchange
        - order['symbol'] -> tradingsymbol
        - order['side'] -> transaction_type
        - order['quantity'] -> quantity
        - order.get('order_type', 'MARKET') -> order_type
        - order.get('price') -> price (optional, for LIMIT orders)

        Requirements covered:
        - 1.3.4: Place orders with broker via Kite API
        - 1.3.5: Retry failed orders up to 3 times with exponential backoff
        - 2.3.6: Handle broker API failures with retries

        Args:
            order: Dictionary containing order details with keys:
                - exchange (str): Exchange segment (e.g., 'NSE', 'NFO')
                - symbol (str): Trading symbol
                - side (str): Transaction type ('BUY' or 'SELL')
                - quantity (int): Order quantity
                - order_type (str, optional): Order type, defaults to 'MARKET'
                - price (float, optional): Price for LIMIT orders

        Returns:
            Dictionary with keys:
            - success (bool): True if order placed successfully
            - order_id (str or None): Broker order ID on success, None on failure
            - message (str): Human-readable status message
            - error_type (str or None): Exception class name on failure, None on success
            - retryable (bool): Whether the caller should retry this order
        """
        try:
            order_id = self.kite.place_order(
                variety=self.kite.VARIETY_REGULAR,
                exchange=order['exchange'],
                tradingsymbol=order['symbol'],
                transaction_type=order['side'],
                quantity=order['quantity'],
                product='MIS',
                order_type=order.get('order_type', 'MARKET'),
                price=order.get('price'),
            )
            return {
                'success': True,
                'order_id': order_id,
                'message': 'Order placed successfully',
                'error_type': None,
                'retryable': False,
            }

        except kite_exceptions.TokenException as e:
            logger.error(
                "Token error placing order for user %d: %s. "
                "Authentication issue - not retryable.",
                self.user_id,
                str(e),
                extra={
                    "user_id": self.user_id,
                    "error_type": "TokenException",
                    "order_symbol": order.get("symbol"),
                },
            )
            return {
                'success': False,
                'order_id': None,
                'message': f"Token error: {e}",
                'error_type': 'TokenException',
                'retryable': False,
            }

        except kite_exceptions.NetworkException as e:
            logger.warning(
                "Network error placing order for user %d: %s. "
                "Transient issue - retryable.",
                self.user_id,
                str(e),
                extra={
                    "user_id": self.user_id,
                    "error_type": "NetworkException",
                    "order_symbol": order.get("symbol"),
                },
            )
            return {
                'success': False,
                'order_id': None,
                'message': f"Network error: {e}",
                'error_type': 'NetworkException',
                'retryable': True,
            }

        except kite_exceptions.OrderException as e:
            logger.warning(
                "Order rejected by exchange for user %d: %s. "
                "Exchange rejection - not retryable.",
                self.user_id,
                str(e),
                extra={
                    "user_id": self.user_id,
                    "error_type": "OrderException",
                    "order_symbol": order.get("symbol"),
                },
            )
            return {
                'success': False,
                'order_id': None,
                'message': f"Order rejected: {e}",
                'error_type': 'OrderException',
                'retryable': False,
            }

        except kite_exceptions.InputException as e:
            logger.error(
                "Invalid order parameters for user %d: %s. "
                "Bad input - not retryable.",
                self.user_id,
                str(e),
                extra={
                    "user_id": self.user_id,
                    "error_type": "InputException",
                    "order_symbol": order.get("symbol"),
                },
            )
            return {
                'success': False,
                'order_id': None,
                'message': f"Invalid parameters: {e}",
                'error_type': 'InputException',
                'retryable': False,
            }

        except kite_exceptions.GeneralException as e:
            logger.error(
                "General Kite API error placing order for user %d: %s. "
                "Not retryable.",
                self.user_id,
                str(e),
                extra={
                    "user_id": self.user_id,
                    "error_type": "GeneralException",
                    "order_symbol": order.get("symbol"),
                },
            )
            return {
                'success': False,
                'order_id': None,
                'message': f"API error: {e}",
                'error_type': 'GeneralException',
                'retryable': False,
            }

        except Exception as e:
            logger.error(
                "Unexpected error placing order for user %d: %s: %s. "
                "Not retryable.",
                self.user_id,
                type(e).__name__,
                str(e),
                extra={
                    "user_id": self.user_id,
                    "error_type": type(e).__name__,
                    "order_symbol": order.get("symbol"),
                },
            )
            return {
                'success': False,
                'order_id': None,
                'message': str(e),
                'error_type': type(e).__name__,
                'retryable': False,
            }

    def validate_order(self, order: Dict) -> Tuple[bool, str]:
        """Validate order before placement by running all pre-trade checks.

        Runs three validation checks in sequence, returning on the first failure:
        1. Kill switch check — blocks all orders UNLESS order has reason='killswitch_exit'
           (exit orders must bypass the kill switch so the system can close positions)
        2. Margin availability check — rejects if margin_used >= 90% of capital
        3. Duplicate order check — rejects if same symbol:side:quantity seen in last 60s

        Requirements covered:
        - 1.3.3: Validate trades before execution (kill switch, margin, duplicates)
        - 1.3.10: Block new trades when kill switch is active

        Args:
            order: Dictionary containing order details. Must include 'symbol', 'side',
                   and 'quantity'. May optionally include 'reason' for bypass logic.

        Returns:
            Tuple of (is_valid, message):
            - (True, "Valid") if all checks pass
            - (False, reason) on first failed check
        """
        # Check 1: Kill switch (bypass for killswitch_exit orders)
        if self.check_killswitch() and order.get("reason") != "killswitch_exit":
            return False, "Kill switch is active"

        # Check 2: Margin availability
        margin_ok, margin_msg = self.check_margin_availability()
        if not margin_ok:
            return False, margin_msg

        # Check 3: Duplicate order detection
        if self.is_duplicate_order(order):
            return False, "Duplicate order detected"

        return True, "Valid"

    def check_order_status(self, order_id: str) -> Dict:
        """Check the status of an order with the broker.

        Calls self.kite.order_history(order_id) to determine whether a
        previously placed order was actually filled by the broker. This is
        critical for retry safety — a network error doesn't mean the order
        wasn't placed.

        Args:
            order_id: The broker order ID to check.

        Returns:
            Dictionary with keys:
            - status (str): Order status ('COMPLETE', 'PENDING', 'REJECTED', etc.)
                            or 'UNKNOWN' if the status couldn't be determined.
            - filled (bool): True if the order status is 'COMPLETE', False otherwise.
        """
        try:
            order_history = self.kite.order_history(order_id)

            if not order_history:
                logger.warning(
                    "Empty order history for order %s, user %d. "
                    "Returning unknown status.",
                    order_id,
                    self.user_id,
                    extra={
                        "user_id": self.user_id,
                        "order_id": order_id,
                    },
                )
                return {"status": "UNKNOWN", "filled": False}

            # The last entry in order_history has the most recent status
            latest = order_history[-1]
            status = latest.get("status", "UNKNOWN")

            return {
                "status": status,
                "filled": status == "COMPLETE",
            }

        except Exception as e:
            logger.warning(
                "Error checking order status for order %s, user %d: %s: %s. "
                "Returning unknown status.",
                order_id,
                self.user_id,
                type(e).__name__,
                str(e),
                extra={
                    "user_id": self.user_id,
                    "order_id": order_id,
                    "error_type": type(e).__name__,
                },
            )
            return {"status": "UNKNOWN", "filled": False}

    def confirm_fill(self, order_id: str, timeout: int = 30) -> Dict:
        """Wait for order fill confirmation by polling order status.

        Polls self.kite.order_history(order_id) every 1 second until the order
        reaches a terminal state (COMPLETE, REJECTED, CANCELLED) or the timeout
        is exceeded. Handles exceptions during polling gracefully by logging
        and continuing to poll.

        Requirements covered:
        - 1.3.6: Wait up to 30 seconds for order fill confirmation

        Args:
            order_id: The broker order ID to monitor.
            timeout: Maximum seconds to wait for fill confirmation (default 30).

        Returns:
            Dictionary with fill result:
            - If filled: {'filled': True, 'quantity': int, 'price': float}
            - If rejected/cancelled: {'filled': False, 'reason': str}
            - If timeout: {'filled': False, 'reason': 'Timeout waiting for fill'}
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                order_history = self.kite.order_history(order_id)
                order_status = order_history[-1]
                if order_status['status'] == 'COMPLETE':
                    return {
                        'filled': True,
                        'quantity': order_status['filled_quantity'],
                        'price': order_status['average_price'],
                    }
                elif order_status['status'] in ['REJECTED', 'CANCELLED']:
                    return {
                        'filled': False,
                        'reason': order_status.get('status_message', 'Order rejected'),
                    }
            except Exception as e:
                logger.warning(
                    "Error polling order status for order %s, user %d: %s: %s. "
                    "Will continue polling.",
                    order_id,
                    self.user_id,
                    type(e).__name__,
                    str(e),
                    extra={
                        "user_id": self.user_id,
                        "order_id": order_id,
                        "error_type": type(e).__name__,
                    },
                )
            time.sleep(1)
        return {'filled': False, 'reason': 'Timeout waiting for fill'}

    def execute_with_retry(self, order: Dict) -> Dict:
        """Execute an order with retry logic for transient failures.

        Calls place_order() and retries up to self.max_retries (3) times
        if the failure is retryable (e.g., NetworkException). Uses exponential
        backoff with time.sleep(retry_backoff * attempt_number) between retries.

        Non-retryable failures are returned immediately without retry.
        After exhausting all retries, returns the last failure result with
        a message indicating max retries were reached.

        Requirements covered:
        - 1.3.5: Retry failed orders up to 3 times with exponential backoff
        - 2.3.6: Handle broker API failures with retries

        Args:
            order: Dictionary containing order details (same format as place_order).

        Returns:
            Dictionary with keys:
            - success (bool): True if order placed successfully
            - order_id (str or None): Broker order ID on success, None on failure
            - message (str): Human-readable status message
            - error_type (str or None): Exception class name on failure, None on success
            - retryable (bool): Whether the failure was retryable
            - attempts (int): Total number of attempts made (1 = no retries)
        """
        result = self.place_order(order)

        # If successful on first attempt, return immediately
        if result['success']:
            result['attempts'] = 1
            return result

        # If not retryable, return the failure immediately
        if not result.get('retryable', False):
            result['attempts'] = 1
            return result

        # Retry up to max_retries times for retryable failures
        last_result = result
        for attempt in range(1, self.max_retries + 1):
            # Before retrying, check if the previous attempt's order was actually filled
            # A network error doesn't mean the order wasn't placed — the error might
            # have occurred after the broker processed the order.
            prev_order_id = last_result.get('order_id')
            if prev_order_id:
                order_status = self.check_order_status(prev_order_id)
                if order_status['filled']:
                    logger.info(
                        "Order %s was already filled for user %d. "
                        "Skipping retry to avoid duplicate order.",
                        prev_order_id,
                        self.user_id,
                        extra={
                            "user_id": self.user_id,
                            "order_id": prev_order_id,
                            "order_symbol": order.get("symbol"),
                        },
                    )
                    return {
                        'success': True,
                        'order_id': prev_order_id,
                        'message': 'Order already filled (confirmed before retry)',
                        'error_type': None,
                        'retryable': False,
                        'attempts': attempt,
                    }

            logger.warning(
                "Retrying order for user %d, attempt %d/%d. "
                "Previous error: %s",
                self.user_id,
                attempt,
                self.max_retries,
                last_result.get('message', 'Unknown error'),
                extra={
                    "user_id": self.user_id,
                    "attempt": attempt,
                    "max_retries": self.max_retries,
                    "order_symbol": order.get("symbol"),
                },
            )

            # Exponential backoff: retry_backoff * attempt_number
            backoff_time = self.retry_backoff * attempt
            time.sleep(backoff_time)

            last_result = self.place_order(order)

            if last_result['success']:
                last_result['attempts'] = attempt + 1
                return last_result

            # If this retry returned a non-retryable error, stop retrying
            if not last_result.get('retryable', False):
                last_result['attempts'] = attempt + 1
                return last_result

        # All retries exhausted
        last_result['attempts'] = self.max_retries + 1
        last_result['message'] = (
            f"Max retries ({self.max_retries}) exhausted. "
            f"Last error: {last_result.get('error_type', 'Unknown')}"
        )
        logger.error(
            "Max retries exhausted for order for user %d. "
            "Attempts: %d. Last error: %s",
            self.user_id,
            self.max_retries + 1,
            last_result.get('error_type', 'Unknown'),
            extra={
                "user_id": self.user_id,
                "attempts": self.max_retries + 1,
                "order_symbol": order.get("symbol"),
            },
        )
        return last_result

    def store_trade(self, order: Dict, result: Dict) -> bool:
        """Store completed trade in database.

        Creates an Order record and optionally a Trade record (if the order
        was filled). Commits both in a single transaction. If any database
        error occurs, the session is rolled back and the error is logged.

        Requirements covered:
        - 1.1: Store order and trade records
        - 7.1: Order record tracking

        Args:
            order: Dictionary containing order details with keys:
                - symbol (str): Trading symbol
                - exchange (str): Exchange segment (e.g., 'NSE', 'NFO')
                - quantity (int): Order quantity
                - side (str): Transaction type ('BUY' or 'SELL')
            result: Dictionary containing execution result with keys:
                - order_id (str, optional): Broker order ID
                - price (float, optional): Execution price
                - status (str, optional): Order status, defaults to 'COMPLETE'
                - attempts (int, optional): Number of attempts made, defaults to 1
                - message (str, optional): Error message if not successful
                - success (bool): Whether the order was successful
                - filled (bool, optional): Whether the order was filled

        Returns:
            True if records were stored successfully, False on failure.
        """
        try:
            # Determine error message: only store if order was not successful
            error_message = None
            if not result.get('success', True):
                error_message = result.get('message')

            # Create Order record
            order_record = Order(
                user_id=self.user_id,
                broker_order_id=result.get('order_id'),
                symbol=order['symbol'],
                qty=order['quantity'],
                price=result.get('price'),
                status=result.get('status', 'COMPLETE'),
                retries=result.get('attempts', 1) - 1,
                error_message=error_message,
                timestamp=datetime.now(),
            )
            self.db.add(order_record)

            # Store trade record if the order was filled
            if result.get('filled'):
                qty = order['quantity'] if order['side'] == 'BUY' else -order['quantity']
                trade_record = Trade(
                    user_id=self.user_id,
                    symbol=order['symbol'],
                    exchange=order['exchange'],
                    qty=qty,
                    side=order['side'],
                    entry_price=result['price'],
                    status='OPEN',
                    timestamp=datetime.now(),
                )
                self.db.add(trade_record)

            self.db.commit()

            logger.info(
                "Stored trade records for user %d, symbol %s.",
                self.user_id,
                order['symbol'],
                extra={
                    "user_id": self.user_id,
                    "symbol": order['symbol'],
                    "filled": result.get('filled', False),
                },
            )
            return True

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(
                "Database error storing trade for user %d: %s. "
                "Session rolled back.",
                self.user_id,
                str(e),
                extra={
                    "user_id": self.user_id,
                    "error_type": "SQLAlchemyError",
                    "symbol": order.get('symbol'),
                },
            )
            return False

        except Exception as e:
            self.db.rollback()
            logger.error(
                "Unexpected error storing trade for user %d: %s: %s. "
                "Session rolled back.",
                self.user_id,
                type(e).__name__,
                str(e),
                extra={
                    "user_id": self.user_id,
                    "error_type": type(e).__name__,
                    "symbol": order.get('symbol'),
                },
            )
            return False

    def update_position_cache(self, order: Dict, result: Dict) -> None:
        """Update position snapshot in Redis after a trade is executed.

        Triggers an immediate risk engine update via Celery so the user's
        metrics reflect the new position, and invalidates the stale risk
        cache in Redis so that reads between now and when the risk engine
        runs don't serve outdated data.

        This method handles errors gracefully — a failure to update the
        cache should never break the trade flow. The order has already been
        placed and stored at this point.

        Requirements covered:
        - 1.4: Risk engine metrics update after trade execution

        Args:
            order: Dictionary containing order details (symbol, side, quantity, etc.).
            result: Dictionary containing execution result (order_id, price, etc.).
        """
        # Task 7.7.1: Trigger risk engine update
        try:
            celery_app.send_task('run_risk_engine', args=[self.user_id])
            logger.info(
                "Triggered risk engine update for user %d after trade on %s.",
                self.user_id,
                order.get('symbol', 'unknown'),
                extra={
                    "user_id": self.user_id,
                    "symbol": order.get('symbol'),
                    "order_id": result.get('order_id'),
                },
            )
        except Exception as e:
            logger.error(
                "Failed to trigger risk engine update for user %d: %s: %s. "
                "Trade was stored successfully but risk metrics may be stale.",
                self.user_id,
                type(e).__name__,
                str(e),
                extra={
                    "user_id": self.user_id,
                    "error_type": type(e).__name__,
                    "symbol": order.get('symbol'),
                },
            )

        # Task 7.7.2: Invalidate stale cache
        try:
            risk_key = RedisKeys.user_risk(self.user_id)
            self.redis.delete(risk_key)
            logger.info(
                "Invalidated stale risk cache for user %d (key: %s).",
                self.user_id,
                risk_key,
                extra={
                    "user_id": self.user_id,
                    "redis_key": risk_key,
                },
            )
        except Exception as e:
            logger.error(
                "Failed to invalidate risk cache for user %d: %s: %s. "
                "Stale data may be served until next risk engine run.",
                self.user_id,
                type(e).__name__,
                str(e),
                extra={
                    "user_id": self.user_id,
                    "error_type": type(e).__name__,
                },
            )
