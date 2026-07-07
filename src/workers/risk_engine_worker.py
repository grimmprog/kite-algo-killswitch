"""Risk Engine Worker for the Multi-User Web Trading Platform.

Per-user risk engine that monitors positions, computes risk metrics,
and triggers kill switch when thresholds are breached. Runs every
2-3 seconds per active user.

Requirements covered:
- 1.2.7: Fetch user positions from broker every 2-3 seconds
- 1.4.1: Monitor each user's P&L every 2-3 seconds
- 1.4.2: Compute live P&L from broker positions
- 1.4.5: Cache risk metrics in Redis with timestamp
- 1.5.1: Set kill switch flag in Redis atomically
- 1.5.2: Block all new trades immediately when kill switch activates
- 1.5.4: Close all open positions via market orders
- 1.5.5: Log kill switch activation to database
- 1.5.6: Notify user via all channels
- 1.5.8: Prevent kill switch from triggering multiple times for same event
- 2.1.3: Complete risk engine cycle within 2 seconds per user
- 2.3.6: Handle broker API failures with retries
- 2.3.7: Log all errors with full context
- 2.3.8: Continue processing other users when one user's operation fails
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Tuple

import redis
from kiteconnect import exceptions as kite_exceptions

from src.cache.redis_keys import RedisKeys
from src.database.models.killswitch_log import KillSwitchLog

logger = logging.getLogger(__name__)


class RiskEngineWorker:
    """Per-user risk engine - runs every 2-3 seconds per active user.

    Fetches the user's current positions from the broker, computes
    risk metrics (P&L, Greeks, margin), caches them in Redis, and
    triggers the kill switch if thresholds are breached.

    Args:
        user_id: The user's database ID.
        kite_client: A configured KiteConnect instance for the user.
        redis_client: RedisClient instance for caching risk metrics.
        db_session: SQLAlchemy session for database operations.
    """

    def __init__(self, user_id: int, kite_client, redis_client, db_session) -> None:
        """Initialize RiskEngineWorker.

        Args:
            user_id: The user's database ID.
            kite_client: A configured KiteConnect instance for the user.
            redis_client: RedisClient instance for caching.
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

    def fetch_positions(self) -> List[Dict]:
        """Fetch user's net positions from broker, filtering out closed positions.

        Calls the Kite Connect positions() API which returns a dict
        with 'net' and 'day' keys. We extract the 'net' positions list
        which contains the consolidated view of all positions, then
        filter out zero-quantity positions (already closed).

        Each position dict from Kite contains fields like:
            - tradingsymbol (str): Trading symbol
            - exchange (str): Exchange (NSE, NFO, etc.)
            - product (str): Product type (MIS, NRML, CNC)
            - quantity (int): Net quantity (positive=long, negative=short)
            - average_price (float): Average entry price
            - last_price (float): Current market price
            - pnl (float): Realized + unrealized P&L
            - unrealised (float): Unrealized P&L
            - realised (float): Realized P&L
            - buy_quantity (int): Total buy quantity
            - sell_quantity (int): Total sell quantity

        Requirements covered:
        - 1.2.7: Fetch user positions from broker every 2-3 seconds
        - 1.4.2: Compute live P&L from broker positions

        Returns:
            List of position dicts with non-zero quantity from the broker's
            net positions. Zero-quantity (closed) positions are filtered out.
            Returns an empty list if no positions exist or if the
            API returns an empty/malformed response.

        Raises:
            Exception: Re-raises broker API exceptions (handled by caller).
        """
        logger.debug("Fetching positions for user %d", self.user_id)

        response = self.kite.positions()

        # The Kite positions() API returns:
        # {"net": [...], "day": [...]}
        # We want the 'net' positions which show the consolidated view
        if not response:
            logger.warning(
                "Empty response from positions API for user %d", self.user_id
            )
            return []

        net_positions = response.get("net", [])

        if net_positions is None:
            logger.warning(
                "Null 'net' positions in response for user %d", self.user_id
            )
            return []

        # Filter out zero-quantity positions (already closed)
        open_positions = [
            pos for pos in net_positions if pos.get("quantity", 0) != 0
        ]

        logger.debug(
            "Fetched %d net positions for user %d (%d open, %d closed filtered out)",
            len(net_positions),
            self.user_id,
            len(open_positions),
            len(net_positions) - len(open_positions),
        )

        return open_positions

    def fetch_positions_safe(self) -> List[Dict]:
        """Fetch user's net positions with error handling for broker API failures.

        Wraps fetch_positions() with comprehensive error handling so the risk
        engine does NOT crash when the broker API fails. Logs errors with full
        context (user_id, error type) and returns an empty list on failure.

        Error handling strategy:
        - TokenException: Token expired/invalid, log error, return empty.
          Caller should trigger re-authentication flow.
        - NetworkException: Connectivity issue, log warning, return empty.
          Transient error - next cycle will retry automatically.
        - DataException: Malformed response from exchange/API, log error, return empty.
        - InputException: Invalid parameters sent to API, log error, return empty.
        - GeneralException: Other Kite API errors, log error, return empty.
        - Unexpected exceptions: Catch-all safety net, log error, return empty.

        Requirements covered:
        - 2.3.6: Handle broker API failures with retries
        - 2.3.7: Log all errors with full context
        - 2.3.8: Continue processing other users when one user's operation fails

        Returns:
            List of position dicts from the broker's net positions.
            Returns an empty list if any error occurs during fetching.
        """
        try:
            return self.fetch_positions()

        except kite_exceptions.TokenException as e:
            logger.error(
                "Token expired/invalid for user %d: %s. Re-authentication required.",
                self.user_id,
                str(e),
                extra={"user_id": self.user_id, "error_type": "TokenException"},
            )
            return []

        except kite_exceptions.NetworkException as e:
            logger.warning(
                "Network error fetching positions for user %d: %s. "
                "Will retry next cycle.",
                self.user_id,
                str(e),
                extra={"user_id": self.user_id, "error_type": "NetworkException"},
            )
            return []

        except kite_exceptions.DataException as e:
            logger.error(
                "Data/exchange error fetching positions for user %d: %s.",
                self.user_id,
                str(e),
                extra={"user_id": self.user_id, "error_type": "DataException"},
            )
            return []

        except kite_exceptions.InputException as e:
            logger.error(
                "Invalid input error fetching positions for user %d: %s.",
                self.user_id,
                str(e),
                extra={"user_id": self.user_id, "error_type": "InputException"},
            )
            return []

        except kite_exceptions.GeneralException as e:
            logger.error(
                "General Kite API error fetching positions for user %d: %s.",
                self.user_id,
                str(e),
                extra={"user_id": self.user_id, "error_type": "GeneralException"},
            )
            return []

        except Exception as e:
            logger.error(
                "Unexpected error fetching positions for user %d: %s: %s",
                self.user_id,
                type(e).__name__,
                str(e),
                extra={"user_id": self.user_id, "error_type": type(e).__name__},
                exc_info=True,
            )
            return []

    def compute_live_pnl(self, positions: List[Dict]) -> float:
        """Compute live P&L by summing the 'pnl' field from all positions.

        Takes a list of position dicts (from fetch_positions() or
        filter_user_positions()) and sums the 'pnl' field from each.
        Handles edge cases gracefully:
        - Returns 0.0 for empty or None positions list
        - Defaults to 0 for positions missing the 'pnl' field
        - Defaults to 0 for positions with non-numeric 'pnl' values

        Requirements covered:
        - 1.4.1: Monitor each user's P&L every 2-3 seconds
        - 1.4.2: Compute live P&L from broker positions

        Args:
            positions: List of position dicts, each expected to contain
                       a 'pnl' field with a numeric value.

        Returns:
            Total P&L as a float. Returns 0.0 if positions is empty or None.
        """
        if not positions:
            return 0.0

        total_pnl = 0.0
        for pos in positions:
            pnl_value = pos.get("pnl", 0)
            try:
                total_pnl += float(pnl_value)
            except (TypeError, ValueError):
                logger.warning(
                    "Non-numeric pnl value '%s' in position for user %d, defaulting to 0",
                    pnl_value,
                    self.user_id,
                )
                continue

        return total_pnl

    def compute_greeks(self, positions: List[Dict]) -> Dict[str, float]:
        """Compute net delta, gamma, vega across all positions.

        Sums each Greek value multiplied by the position's quantity. Options
        positions typically provide delta, gamma, and vega fields. Equity
        positions or positions missing Greek fields default to 0.

        Requirements covered:
        - 1.4.3: Compute Greeks exposure (delta, gamma, vega) for options positions

        Args:
            positions: List of position dicts. Each position may contain:
                - 'delta' (float): Option delta per unit
                - 'gamma' (float): Option gamma per unit
                - 'vega' (float): Option vega per unit
                - 'quantity' (int): Net quantity (positive=long, negative=short)
                Fields default to 0 if missing or non-numeric.

        Returns:
            Dict with 'net_delta', 'net_gamma', 'net_vega' as floats.
            Returns all zeros if positions is empty or None.
        """
        if not positions:
            return {"net_delta": 0.0, "net_gamma": 0.0, "net_vega": 0.0}

        net_delta = 0.0
        net_gamma = 0.0
        net_vega = 0.0

        for pos in positions:
            # Extract quantity, default to 0 if missing or non-numeric
            try:
                quantity = float(pos.get("quantity", 0))
            except (TypeError, ValueError):
                logger.warning(
                    "Non-numeric quantity in position for user %d, defaulting to 0",
                    self.user_id,
                )
                quantity = 0.0

            # Extract delta, default to 0 if missing or non-numeric
            try:
                delta = float(pos.get("delta", 0))
            except (TypeError, ValueError):
                logger.warning(
                    "Non-numeric delta value '%s' in position for user %d, defaulting to 0",
                    pos.get("delta"),
                    self.user_id,
                )
                delta = 0.0

            # Extract gamma, default to 0 if missing or non-numeric
            try:
                gamma = float(pos.get("gamma", 0))
            except (TypeError, ValueError):
                logger.warning(
                    "Non-numeric gamma value '%s' in position for user %d, defaulting to 0",
                    pos.get("gamma"),
                    self.user_id,
                )
                gamma = 0.0

            # Extract vega, default to 0 if missing or non-numeric
            try:
                vega = float(pos.get("vega", 0))
            except (TypeError, ValueError):
                logger.warning(
                    "Non-numeric vega value '%s' in position for user %d, defaulting to 0",
                    pos.get("vega"),
                    self.user_id,
                )
                vega = 0.0

            net_delta += delta * quantity
            net_gamma += gamma * quantity
            net_vega += vega * quantity

        return {
            "net_delta": net_delta,
            "net_gamma": net_gamma,
            "net_vega": net_vega,
        }

    def compute_margin_used(self, positions: List[Dict]) -> float:
        """Compute total margin used by summing 'margin' field from all positions.

        Takes a list of position dicts and sums the 'margin' field from each.
        Handles edge cases gracefully:
        - Returns 0.0 for empty or None positions list
        - Defaults to 0 for positions missing the 'margin' field
        - Defaults to 0 for positions with non-numeric 'margin' values

        Requirements covered:
        - 1.4.4: Compute margin usage for each user

        Args:
            positions: List of position dicts, each may contain a 'margin'
                       field with a numeric value.

        Returns:
            Total margin used as a float. Returns 0.0 if positions is empty or None.
        """
        if not positions:
            return 0.0

        total_margin = 0.0
        for pos in positions:
            margin_value = pos.get("margin", 0)
            try:
                total_margin += float(margin_value)
            except (TypeError, ValueError):
                logger.warning(
                    "Non-numeric margin value '%s' in position for user %d, defaulting to 0",
                    margin_value,
                    self.user_id,
                )
                continue

        return total_margin

    def compute_margin_percentage(self, margin_used: float, capital: float) -> float:
        """Compute margin usage as a percentage of capital.

        Calculates (margin_used / capital) * 100. Handles edge cases:
        - Returns 0.0 if capital is zero (prevent division by zero)
        - Returns 0.0 if capital is negative (invalid capital)

        Requirements covered:
        - 1.4.4: Compute margin usage for each user
        - 1.4.8: Trigger kill switch when margin usage exceeds 90% of capital

        Args:
            margin_used: Total margin used across all positions.
            capital: User's total available capital.

        Returns:
            Margin usage percentage as a float. Returns 0.0 for invalid capital.
        """
        if capital <= 0:
            return 0.0

        return (margin_used / capital) * 100

    def filter_user_positions(self, positions: List[Dict]) -> List[Dict]:
        """Filter positions to only include open (non-zero quantity) positions for this user.

        Takes the raw positions list from the broker and:
        1. Removes closed positions (quantity == 0) since they represent no active risk
        2. Tags each position with the user_id for downstream processing and isolation

        This ensures that only positions with actual exposure are processed by the
        risk engine, and that position data is always associated with the correct user.

        Requirements covered:
        - 1.8.2: Maintain separate positions for each user
        - 1.8.6: Prevent cross-user data access
        - 1.8.8: Prefix all Redis keys with user_id

        Args:
            positions: List of position dicts from fetch_positions(). Each dict
                       should contain at minimum a 'quantity' field (int).

        Returns:
            List of position dicts with non-zero quantity, each tagged with 'user_id'.
            Returns an empty list if positions is None or empty.
        """
        if not positions:
            return []

        filtered = []
        for position in positions:
            quantity = position.get("quantity", 0)
            if quantity != 0:
                # Tag with user_id for downstream processing and isolation
                tagged_position = {**position, "user_id": self.user_id}
                filtered.append(tagged_position)

        logger.debug(
            "Filtered positions for user %d: %d open out of %d total",
            self.user_id,
            len(filtered),
            len(positions),
        )

        return filtered

    def update_redis_cache(self, pnl: float, greeks: Dict[str, float], margin_used: float) -> bool:
        """Update Redis with latest risk metrics for this user.

        Stores all computed risk metrics in a Redis hash under the key
        `user:{user_id}:risk`. Includes a timestamp for cache freshness tracking.

        The method handles Redis connection errors gracefully — it logs the error
        and returns False so the risk engine cycle can continue without crashing.

        Requirements covered:
        - 1.4.5: Cache risk metrics in Redis with timestamp
        - 3.6.1: Cache user risk metrics with key user:{user_id}:risk
        - 3.6.9: Include timestamp in all cached data

        Args:
            pnl: Computed P&L value for the user.
            greeks: Dict with 'net_delta', 'net_gamma', 'net_vega' values.
            margin_used: Total margin used across all positions.

        Returns:
            True if the cache was updated successfully, False if a Redis
            error occurred.
        """
        try:
            key = RedisKeys.user_risk(self.user_id)
            mapping = {
                "pnl": str(pnl),
                "net_delta": str(greeks.get("net_delta", 0.0)),
                "net_gamma": str(greeks.get("net_gamma", 0.0)),
                "net_vega": str(greeks.get("net_vega", 0.0)),
                "margin_used": str(margin_used),
                "updated_at": datetime.now().isoformat(),
            }
            self.redis.hset(key, mapping=mapping)
            logger.debug(
                "Updated Redis risk cache for user %d: pnl=%.2f, margin=%.2f",
                self.user_id,
                pnl,
                margin_used,
            )
            return True

        except redis.RedisError as e:
            logger.error(
                "Redis error updating risk cache for user %d: %s",
                self.user_id,
                str(e),
                extra={"user_id": self.user_id, "error_type": "RedisError"},
            )
            return False

        except Exception as e:
            logger.error(
                "Unexpected error updating risk cache for user %d: %s: %s",
                self.user_id,
                type(e).__name__,
                str(e),
                extra={"user_id": self.user_id, "error_type": type(e).__name__},
            )
            return False

    def check_thresholds(
        self,
        pnl: float,
        capital: float,
        daily_loss_limit_pct: float,
        margin_used: float,
    ) -> Tuple[bool, str]:
        """Check if risk thresholds are breached.

        Evaluates daily loss and margin usage against configured limits.
        Returns immediately on the first breach detected (daily loss checked
        first, then margin).

        Requirements covered:
        - 1.4.6: Check risk thresholds on every monitoring cycle
        - 1.4.7: Trigger kill switch when daily loss exceeds configured percentage
        - 1.4.8: Trigger kill switch when margin usage exceeds 90% of capital

        Args:
            pnl: Current P&L for the user (negative = loss).
            capital: User's total available capital.
            daily_loss_limit_pct: Maximum allowed daily loss as a percentage
                                  (e.g., 2.0 means 2%).
            margin_used: Total margin currently used across all positions.

        Returns:
            Tuple of (breached: bool, reason: str).
            - breached is True if ANY threshold is breached, False otherwise.
            - reason describes which threshold was breached, or "Within limits".
        """
        # Edge case: zero or negative capital means we can't compute percentages
        if capital <= 0:
            return False, "Within limits"

        # 6.6.1: Check daily loss limit
        loss_pct = (pnl / capital) * 100
        if loss_pct <= -daily_loss_limit_pct:
            return True, f"Daily loss limit breached: {loss_pct:.2f}%"

        # 6.6.2: Check margin limit (90% of capital)
        margin_pct = (margin_used / capital) * 100
        if margin_pct >= 90.0:
            return True, f"Margin limit breached: {margin_pct:.2f}% of capital"

        # 6.6.3: No threshold breached
        return False, "Within limits"

    def trigger_killswitch(self, reason: str, capital: float = 0.0) -> bool:
        """Activate the kill switch for this user.

        Performs the following steps in order:
        1. Set kill switch flag in Redis atomically (NX to prevent duplicates)
        2. Queue exit orders for all open positions
        3. Log the kill switch event to database
        4. Send notifications via Redis pub/sub

        Each step is independent — if one fails, the others still execute.
        This ensures maximum safety: even if Redis is down, we still try
        to close positions and log the event.

        Requirements covered:
        - 1.5.1: Set kill switch flag in Redis atomically
        - 1.5.2: Block all new trades immediately when kill switch activates
        - 1.5.4: Close all open positions via market orders
        - 1.5.5: Log kill switch activation to database
        - 1.5.6: Notify user via all channels
        - 1.5.8: Prevent kill switch from triggering multiple times for same event

        Args:
            reason: Human-readable reason for kill switch activation.
            capital: User's capital at time of trigger (for logging).

        Returns:
            True if the kill switch was newly activated (first trigger).
            False if it was already active (duplicate trigger per req 1.5.8).
        """
        logger.warning(
            "Kill switch triggered for user %d: %s",
            self.user_id,
            reason,
        )

        # 6.7.1: Set Redis flag atomically with NX (set-if-not-exists)
        was_set = self._set_killswitch_flag()
        if not was_set:
            logger.info(
                "Kill switch already active for user %d, skipping duplicate trigger",
                self.user_id,
            )
            return False

        # 6.7.2: Queue exit orders for all open positions
        positions_closed = self._queue_exit_orders()

        # 6.7.3: Log to database
        self._log_killswitch_event(reason, positions_closed, capital)

        # 6.7.4: Send notifications
        self._send_killswitch_notification(reason, positions_closed)

        logger.warning(
            "Kill switch activation complete for user %d: %d positions queued for exit",
            self.user_id,
            positions_closed,
        )

        return True

    def _set_killswitch_flag(self) -> bool:
        """Set the kill switch flag in Redis atomically.

        Uses SET with NX (set-if-not-exists) to ensure only one trigger
        succeeds even if multiple threshold breaches are detected
        simultaneously.

        Requirements covered:
        - 1.5.1: Set kill switch flag in Redis atomically
        - 1.5.8: Prevent kill switch from triggering multiple times for same event

        Returns:
            True if the flag was set (first trigger).
            False if the flag already existed (duplicate trigger).
        """
        try:
            key = RedisKeys.user_killswitch(self.user_id)
            # NX = set only if not exists; returns True if set, None/False if exists
            result = self.redis.set(key, "true", nx=True)
            if result:
                logger.info(
                    "Kill switch flag set in Redis for user %d", self.user_id
                )
                return True
            else:
                return False

        except redis.RedisError as e:
            logger.error(
                "Redis error setting kill switch flag for user %d: %s. "
                "Proceeding with kill switch activation anyway.",
                self.user_id,
                str(e),
                extra={"user_id": self.user_id, "error_type": "RedisError"},
            )
            # If Redis fails, we still want to proceed with closing positions
            # and logging. Return True to continue the kill switch flow.
            return True

        except Exception as e:
            logger.error(
                "Unexpected error setting kill switch flag for user %d: %s: %s",
                self.user_id,
                type(e).__name__,
                str(e),
                extra={"user_id": self.user_id, "error_type": type(e).__name__},
            )
            return True

    def _queue_exit_orders(self) -> int:
        """Queue exit orders for all open positions.

        Fetches current positions and queues a market exit order for each
        position with non-zero quantity. Uses Celery to send execution tasks.

        Requirements covered:
        - 1.5.4: Close all open positions via market orders

        Returns:
            Number of exit orders queued.
        """
        try:
            positions = self.fetch_positions_safe()
            queued_count = 0

            for pos in positions:
                quantity = pos.get("quantity", 0)
                if quantity != 0:
                    self._queue_single_exit_order(pos)
                    queued_count += 1

            logger.info(
                "Queued %d exit orders for user %d",
                queued_count,
                self.user_id,
            )
            return queued_count

        except Exception as e:
            logger.error(
                "Error queuing exit orders for user %d: %s: %s",
                self.user_id,
                type(e).__name__,
                str(e),
                extra={"user_id": self.user_id, "error_type": type(e).__name__},
            )
            return 0

    def _queue_single_exit_order(self, position: Dict) -> None:
        """Queue a single market exit order for a position.

        Creates a MARKET order on the opposite side to close the position.
        Long positions (qty > 0) get a SELL order.
        Short positions (qty < 0) get a BUY order.

        Args:
            position: Position dict with tradingsymbol, exchange, product, quantity.
        """
        from src.workers.celery_app import celery_app

        quantity = position.get("quantity", 0)
        if quantity == 0:
            return

        # Determine exit side: opposite of current position direction
        transaction_type = "SELL" if quantity > 0 else "BUY"
        exit_quantity = abs(quantity)

        order_params = {
            "user_id": self.user_id,
            "tradingsymbol": position.get("tradingsymbol", ""),
            "exchange": position.get("exchange", "NSE"),
            "transaction_type": transaction_type,
            "quantity": exit_quantity,
            "product": position.get("product", "MIS"),
            "order_type": "MARKET",
            "trigger_reason": "kill_switch",
        }

        try:
            celery_app.send_task(
                "src.workers.execution_task.execute_order",
                kwargs=order_params,
            )
            logger.debug(
                "Queued exit order for user %d: %s %s %d %s",
                self.user_id,
                transaction_type,
                position.get("tradingsymbol", ""),
                exit_quantity,
                position.get("exchange", ""),
            )
        except Exception as e:
            logger.error(
                "Failed to queue exit order for user %d, position %s: %s: %s",
                self.user_id,
                position.get("tradingsymbol", "unknown"),
                type(e).__name__,
                str(e),
            )

    def _log_killswitch_event(
        self, reason: str, positions_closed: int, capital: float = 0.0
    ) -> None:
        """Log the kill switch activation event to the database.

        Creates a KillSwitchLog record with full context about the trigger.

        Requirements covered:
        - 1.5.5: Log kill switch activation to database

        Args:
            reason: The reason the kill switch was triggered.
            positions_closed: Number of positions queued for exit.
            capital: User's capital at time of trigger.
        """
        try:
            # Compute loss_percent if capital is available
            loss_percent = None
            if capital > 0:
                try:
                    positions = self.fetch_positions_safe()
                    pnl = self.compute_live_pnl(positions)
                    loss_percent = (pnl / capital) * 100
                except Exception:  # nosec B110
                    pass  # best-effort pnl calculation for logging

            log_entry = KillSwitchLog(
                user_id=self.user_id,
                trigger_reason=reason,
                loss_percent=loss_percent,
                capital_at_trigger=capital if capital > 0 else None,
                positions_closed_count=positions_closed,
                timestamp=datetime.now(),
            )

            self.db.add(log_entry)
            self.db.commit()

            logger.info(
                "Kill switch event logged to database for user %d: %s",
                self.user_id,
                reason,
            )

        except Exception as e:
            logger.error(
                "Failed to log kill switch event to database for user %d: %s: %s",
                self.user_id,
                type(e).__name__,
                str(e),
                extra={"user_id": self.user_id, "error_type": type(e).__name__},
            )
            # Attempt rollback to keep session usable
            try:
                self.db.rollback()
            except Exception:  # nosec B110
                pass  # best-effort rollback after db error

    def _send_killswitch_notification(self, reason: str, positions_closed: int) -> None:
        """Send kill switch activation notification via Redis pub/sub and NotificationService.

        Performs two notification actions:
        1. Publishes a JSON message to the user's legacy notification channel
           (picked up by WebSocket server for real-time delivery).
        2. Calls the killswitch integration module to:
           - Push a critical notification via NotificationService (persisted + WebSocket)
           - Mark segments as deactivated by kill switch in Redis

        Requirements covered:
        - 1.5.6: Notify user via all channels
        - 11.4: Push critical notification on kill switch activation
        - 12.4: Indicate which segments were deactivated by kill switch

        Args:
            reason: The reason the kill switch was triggered.
            positions_closed: Number of positions queued for exit.
        """
        # Legacy Redis pub/sub notification (for backward compatibility)
        try:
            channel = f"user:{self.user_id}:notifications"
            message = json.dumps({
                "type": "killswitch_activated",
                "user_id": self.user_id,
                "reason": reason,
                "positions_closed": positions_closed,
                "timestamp": datetime.now().isoformat(),
            })

            self.redis.publish(channel, message)

            logger.info(
                "Kill switch notification sent for user %d on channel %s",
                self.user_id,
                channel,
            )

        except redis.RedisError as e:
            logger.error(
                "Redis error sending kill switch notification for user %d: %s",
                self.user_id,
                str(e),
                extra={"user_id": self.user_id, "error_type": "RedisError"},
            )

        except Exception as e:
            logger.error(
                "Unexpected error sending kill switch notification for user %d: %s: %s",
                self.user_id,
                type(e).__name__,
                str(e),
                extra={"user_id": self.user_id, "error_type": type(e).__name__},
            )

        # Integration: push critical notification + mark segments deactivated
        try:
            from src.services.killswitch_integration import handle_killswitch_activation

            handle_killswitch_activation(
                user_id=self.user_id,
                reason=reason,
                positions_closed=positions_closed,
                redis_client=self.redis,
                db_session=self.db,
            )

        except Exception as e:
            logger.error(
                "Kill switch integration error for user %d: %s: %s",
                self.user_id,
                type(e).__name__,
                str(e),
                extra={"user_id": self.user_id, "error_type": type(e).__name__},
            )
