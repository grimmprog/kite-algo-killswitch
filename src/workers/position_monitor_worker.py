"""Celery task for per-user position monitoring with SL/Target/Trailing/Exit evaluation.

Schedules position monitoring to run for EACH active user every 2 seconds.
A beat-scheduled task (schedule_position_monitoring) dispatches individual
monitor_positions tasks per user, enabling parallel monitoring.

For each user with open positions:
- Fetches live prices from the Kite API
- Evaluates SL/Target/Trailing Stop conditions
- Evaluates exit conditions (EMA cross, VWAP touch, consecutive green, time-based)
- Triggers auto-exit orders when conditions are met
- Publishes position_monitor_update events via Redis PubSub (every 2s)
- Publishes exit_condition_update events when status changes
- Publishes auto_exit_triggered events on auto-exit

Requirements covered:
- 7.2: Push price updates to Position_Monitor_UI at max interval of 2 seconds
- 7.3: Display "SL Hit" status and trigger auto-exit flow when price hits SL
- 7.4: Display "Target Hit" status and trigger auto-exit flow when price hits target
- 7.5: Display trailing stop level, update as price moves favorably
- 7.6: Trigger auto-exit flow when price retraces to trailing stop level
- 8.1: Show all active exit conditions with evaluation status
- 8.2: EMA cross, VWAP touch, consecutive green candles, time-based exit conditions
- 8.3: Visually highlight triggered exit conditions
- 8.4: Indicate exit pending/triggered when any exit condition is met
- 8.5: Push exit condition evaluations in real time via WebSocket
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.cache.redis_client import RedisClient, get_redis_client
from src.cache.redis_keys import RedisKeys
from src.services.position_monitor_service import (
    ExitCondition,
    MarketData,
    MonitoredPosition,
    PositionMonitorService,
)
from src.services.trade_journal_service import TradeJournalService
from src.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Database URL from environment
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/trading_platform",
)

# Redis PubSub channel prefixes (matches websocket_relay.py convention)
CHANNEL_POSITION_MONITOR = "position:monitor"
CHANNEL_EXIT_CONDITION = "position:exit_condition"
CHANNEL_AUTO_EXIT = "position:auto_exit"

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


def get_users_with_open_positions(db_session: Session) -> List[int]:
    """Query database for user IDs that have active monitored positions.

    Args:
        db_session: SQLAlchemy session for database queries.

    Returns:
        List of user IDs with at least one active position being monitored.
    """
    from src.database.models.position_monitor import PositionMonitorState

    try:
        user_ids = (
            db_session.query(PositionMonitorState.user_id)
            .filter(PositionMonitorState.status == "active")
            .distinct()
            .all()
        )
        return [uid[0] for uid in user_ids]
    except Exception as e:
        logger.error(
            "Failed to query users with open positions: %s: %s",
            type(e).__name__,
            str(e),
        )
        return []


def get_user_kite_client(user_id: int, db_session: Session):
    """Get a configured KiteConnect client for a specific user.

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


def fetch_live_prices(kite_client, symbols: List[str]) -> Dict[str, float]:
    """Fetch live prices for a list of symbols from the Kite API.

    Uses the LTP (Last Traded Price) API for efficient price fetching.

    Args:
        kite_client: A configured KiteConnect instance.
        symbols: List of trading symbols to fetch prices for.

    Returns:
        Dictionary mapping symbol → current price.
        Missing symbols are omitted from the result.
    """
    if not symbols:
        return {}

    try:
        # Build instrument list for LTP call (NSE format for equity, NFO for options)
        instruments = []
        for symbol in symbols:
            # Try NFO first (options), fallback handled by Kite API
            instruments.append(f"NFO:{symbol}")

        ltp_data = kite_client.ltp(instruments)

        prices = {}
        for instrument_key, data in ltp_data.items():
            # Extract symbol from instrument key like "NFO:NIFTY23DECFUT"
            symbol = instrument_key.split(":")[-1] if ":" in instrument_key else instrument_key
            if "last_price" in data:
                prices[symbol] = data["last_price"]

        return prices

    except Exception as e:
        logger.error(
            "Error fetching live prices: %s: %s",
            type(e).__name__,
            str(e),
        )
        return {}


def fetch_market_data_for_position(
    kite_client, symbol: str, redis_client: RedisClient
) -> Optional[MarketData]:
    """Fetch market data (price, EMA, VWAP, candles) for exit condition evaluation.

    Attempts to read cached market data from Redis first. Falls back to
    computing from available data if cache is stale.

    Args:
        kite_client: A configured KiteConnect instance.
        symbol: The trading symbol.
        redis_client: Redis client for cached market data.

    Returns:
        MarketData object with current indicators, or None if unavailable.
    """
    try:
        # Try to get cached market data from Redis
        market_key = RedisKeys.market_data(symbol)
        cached_data = redis_client.get(market_key)

        current_price = 0.0
        ema20 = 0.0
        vwap = 0.0
        candles: List[Dict[str, float]] = []

        if cached_data:
            data = json.loads(cached_data)
            current_price = float(data.get("spot", 0.0))
            vwap = float(data.get("vwap", 0.0))
            ema20 = float(data.get("ema20", current_price))
            candles = data.get("candles", [])
        else:
            # Fetch LTP as minimum data
            try:
                ltp = kite_client.ltp([f"NFO:{symbol}"])
                key = f"NFO:{symbol}"
                if key in ltp:
                    current_price = ltp[key].get("last_price", 0.0)
            except Exception:
                pass

        if current_price <= 0:
            return None

        # Use current_price for ema20/vwap if not available from cache
        if ema20 <= 0:
            ema20 = current_price
        if vwap <= 0:
            vwap = current_price

        return MarketData(
            current_price=current_price,
            ema20=ema20,
            vwap=vwap,
            candles=candles,
            current_time=datetime.now(timezone.utc),
        )

    except Exception as e:
        logger.error(
            "Error fetching market data for %s: %s: %s",
            symbol,
            type(e).__name__,
            str(e),
        )
        return None


def publish_position_update(
    redis_client: RedisClient, user_id: int, position: MonitoredPosition
) -> bool:
    """Publish position monitor update via Redis PubSub.

    Publishes to channel: position:monitor:{user_id}
    Relayed by websocket_relay → position_monitor_update Socket.IO event.

    Args:
        redis_client: Redis client for PubSub publishing.
        user_id: The user's ID for channel routing.
        position: The monitored position with computed metrics.

    Returns:
        True if published successfully, False otherwise.
    """
    channel = f"{CHANNEL_POSITION_MONITOR}:{user_id}"
    payload = {
        "position_id": position.position_id,
        "symbol": position.symbol,
        "entry_price": position.entry_price,
        "current_price": position.current_price,
        "quantity": position.quantity,
        "stop_loss": position.stop_loss,
        "target": position.target,
        "trailing_stop_enabled": position.trailing_stop_enabled,
        "trailing_stop_level": position.trailing_stop_level,
        "unrealized_pnl": position.unrealized_pnl,
        "distance_to_sl_pct": round(position.distance_to_sl_pct, 2),
        "distance_to_target_pct": round(position.distance_to_target_pct, 2),
        "status": position.status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        redis_client.client.publish(channel, json.dumps(payload))
        logger.debug(
            "Published position_monitor_update for user %d, position %d",
            user_id,
            position.position_id,
        )
        return True
    except Exception as e:
        logger.error(
            "Failed to publish position update for user %d: %s: %s",
            user_id,
            type(e).__name__,
            str(e),
        )
        return False


def publish_exit_condition_update(
    redis_client: RedisClient,
    user_id: int,
    position_id: int,
    conditions: List[ExitCondition],
) -> bool:
    """Publish exit condition evaluation update via Redis PubSub.

    Publishes to channel: position:exit_condition:{user_id}
    Relayed by websocket_relay → exit_condition_update Socket.IO event.

    Args:
        redis_client: Redis client for PubSub publishing.
        user_id: The user's ID for channel routing.
        position_id: The ID of the position being evaluated.
        conditions: List of evaluated exit conditions.

    Returns:
        True if published successfully, False otherwise.
    """
    channel = f"{CHANNEL_EXIT_CONDITION}:{user_id}"
    payload = {
        "position_id": position_id,
        "conditions": [
            {
                "name": cond.name,
                "description": cond.description,
                "is_met": cond.is_met,
                "details": cond.details,
            }
            for cond in conditions
        ],
        "any_met": any(c.is_met for c in conditions),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        redis_client.client.publish(channel, json.dumps(payload))
        logger.debug(
            "Published exit_condition_update for user %d, position %d",
            user_id,
            position_id,
        )
        return True
    except Exception as e:
        logger.error(
            "Failed to publish exit condition update for user %d: %s: %s",
            user_id,
            type(e).__name__,
            str(e),
        )
        return False


def publish_auto_exit_triggered(
    redis_client: RedisClient,
    user_id: int,
    exit_data: Dict[str, Any],
) -> bool:
    """Publish auto-exit triggered event via Redis PubSub.

    Publishes to channel: position:auto_exit:{user_id}
    Relayed by websocket_relay → auto_exit_triggered Socket.IO event.

    Args:
        redis_client: Redis client for PubSub publishing.
        user_id: The user's ID for channel routing.
        exit_data: Dictionary with exit details from trigger_auto_exit().

    Returns:
        True if published successfully, False otherwise.
    """
    channel = f"{CHANNEL_AUTO_EXIT}:{user_id}"
    payload = {
        **exit_data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        redis_client.client.publish(channel, json.dumps(payload))
        logger.info(
            "Published auto_exit_triggered for user %d, position %d, reason: %s",
            user_id,
            exit_data.get("position_id"),
            exit_data.get("exit_reason"),
        )
        return True
    except Exception as e:
        logger.error(
            "Failed to publish auto-exit event for user %d: %s: %s",
            user_id,
            type(e).__name__,
            str(e),
        )
        return False


def cache_position_state(
    redis_client: RedisClient, user_id: int, position: MonitoredPosition
) -> None:
    """Cache current position state in Redis for other services (e.g., AI exit advisor).

    Key format: position_monitor:{user_id}:{position_id}

    Args:
        redis_client: Redis client for caching.
        user_id: The user's ID.
        position: The monitored position with current metrics.
    """
    key = f"position_monitor:{user_id}:{position.position_id}"
    data = {
        "position_id": position.position_id,
        "symbol": position.symbol,
        "entry_price": position.entry_price,
        "current_price": position.current_price,
        "quantity": position.quantity,
        "stop_loss": position.stop_loss,
        "target": position.target,
        "trailing_stop_enabled": position.trailing_stop_enabled,
        "trailing_stop_level": position.trailing_stop_level,
        "unrealized_pnl": position.unrealized_pnl,
        "distance_to_sl_pct": position.distance_to_sl_pct,
        "distance_to_target_pct": position.distance_to_target_pct,
        "status": position.status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        redis_client.set(key, json.dumps(data), ttl=10)
    except Exception as e:
        logger.warning(
            "Failed to cache position state for user %d, position %d: %s",
            user_id,
            position.position_id,
            str(e),
        )


def _create_journal_entry_on_exit(
    db_session: Optional[Session],
    user_id: int,
    trade_id: Optional[int],
    exit_reason: str,
    exit_price: float,
    redis_client: Optional[RedisClient] = None,
) -> None:
    """Create a TradeJournalEntry after a successful auto-exit.

    Gathers AI grade from Redis cache if available, then delegates to
    TradeJournalService for entry creation.

    This function is fire-and-forget — failures are logged but do not
    block the monitoring cycle.

    Args:
        db_session: SQLAlchemy session for database operations.
        user_id: The user who owns the trade.
        trade_id: The ID of the exited trade.
        exit_reason: The exit reason (sl_hit, target_hit, etc.).
        exit_price: The price at which the trade was exited.
        redis_client: Optional Redis client for fetching AI data.
    """
    if db_session is None or trade_id is None:
        logger.debug(
            "Skipping journal entry creation: db_session=%s, trade_id=%s",
            "None" if db_session is None else "ok",
            trade_id,
        )
        return

    try:
        # Try to fetch cached AI grade from Redis (from AI exit advisor)
        ai_grade = None
        if redis_client:
            try:
                ai_cache_key = f"ai:trade_review:{user_id}:{trade_id}"
                ai_data_json = redis_client.get(ai_cache_key)
                if ai_data_json:
                    ai_data = json.loads(ai_data_json)
                    ai_grade = ai_data.get("grade")
            except Exception:
                pass  # AI data is optional

        journal_service = TradeJournalService(db=db_session)
        journal_service.create_journal_entry_on_exit(
            trade_id=trade_id,
            user_id=user_id,
            exit_reason=exit_reason,
            exit_price=exit_price,
            ai_grade=ai_grade,
        )
    except Exception as e:
        logger.error(
            "Failed to create journal entry for trade %d (user %d): %s: %s",
            trade_id,
            user_id,
            type(e).__name__,
            str(e),
        )


@celery_app.task(name="src.workers.position_monitor_worker.monitor_positions")
def monitor_positions(user_id: int) -> Dict:
    """Celery task: Run position monitoring cycle for a specific user.

    Performs a full position monitoring cycle:
    1. Fetch all active monitored positions for the user
    2. Fetch live prices from Kite API
    3. Evaluate SL/Target/Trailing Stop conditions
    4. Evaluate exit conditions (EMA cross, VWAP touch, green candles, time-based)
    5. Trigger auto-exit when conditions are met
    6. Publish updates via Redis PubSub for WebSocket relay

    Requirements covered:
    - 7.2: Push price updates at max interval of 2 seconds
    - 7.3: Trigger auto-exit when SL hit
    - 7.4: Trigger auto-exit when target hit
    - 7.5: Update trailing stop as price moves favorably
    - 7.6: Trigger auto-exit when trailing stop hit
    - 8.1-8.5: Evaluate and publish exit conditions in real time

    Args:
        user_id: The user's database ID.

    Returns:
        Dict summarizing the run:
            - "status": "success", "skipped", or "error"
            - "user_id": The user's ID
            - "positions_monitored": Number of positions processed
            - "auto_exits_triggered": Number of auto-exits triggered
            - "reason": Description of the outcome
    """
    try:
        return _execute_monitor_positions(user_id)
    except Exception as e:
        logger.error(
            "Unexpected top-level error in monitor_positions for user %d: %s: %s",
            user_id,
            type(e).__name__,
            str(e),
        )
        return {
            "status": "error",
            "user_id": user_id,
            "positions_monitored": 0,
            "auto_exits_triggered": 0,
            "reason": f"Unexpected error: {type(e).__name__}: {str(e)}",
        }


def _execute_monitor_positions(user_id: int) -> Dict:
    """Internal implementation of position monitoring for one user.

    Orchestrates the full monitoring cycle: fetch positions, fetch prices,
    evaluate conditions, trigger exits, publish updates.
    """
    redis_client = get_redis_client()

    # Check if kill switch is active — skip monitoring if so
    killswitch_key = RedisKeys.user_killswitch(user_id)
    killswitch_value = redis_client.get(killswitch_key)
    if killswitch_value == "true":
        logger.debug("Kill switch active for user %d, skipping position monitor", user_id)
        return {
            "status": "skipped",
            "user_id": user_id,
            "positions_monitored": 0,
            "auto_exits_triggered": 0,
            "reason": "Kill switch active",
        }

    db_session = get_db_session()
    try:
        # Initialize service
        service = PositionMonitorService(db=db_session)

        # Step 1: Get all active monitored positions
        positions = service.get_monitored_positions(user_id)
        if not positions:
            return {
                "status": "success",
                "user_id": user_id,
                "positions_monitored": 0,
                "auto_exits_triggered": 0,
                "reason": "No active positions to monitor",
            }

        # Step 2: Get Kite client for live prices
        try:
            kite_client = get_user_kite_client(user_id, db_session)
        except RuntimeError as e:
            logger.warning(
                "Cannot get Kite client for user %d: %s", user_id, str(e)
            )
            return {
                "status": "error",
                "user_id": user_id,
                "positions_monitored": 0,
                "auto_exits_triggered": 0,
                "reason": f"Kite client error: {str(e)}",
            }

        # Step 3: Fetch live prices for all position symbols
        symbols = list({pos.symbol for pos in positions})
        live_prices = fetch_live_prices(kite_client, symbols)

        # Step 4: Process each position
        auto_exits_triggered = 0
        positions_monitored = 0

        for position in positions:
            try:
                result = _process_single_position(
                    service=service,
                    kite_client=kite_client,
                    redis_client=redis_client,
                    user_id=user_id,
                    position=position,
                    live_prices=live_prices,
                    db_session=db_session,
                )
                positions_monitored += 1
                if result.get("auto_exit_triggered"):
                    auto_exits_triggered += 1
            except Exception as e:
                logger.error(
                    "Error processing position %d for user %d: %s: %s",
                    position.position_id,
                    user_id,
                    type(e).__name__,
                    str(e),
                )
                # Continue processing other positions
                continue

        return {
            "status": "success",
            "user_id": user_id,
            "positions_monitored": positions_monitored,
            "auto_exits_triggered": auto_exits_triggered,
            "reason": (
                f"Monitored {positions_monitored} positions, "
                f"{auto_exits_triggered} auto-exit(s) triggered"
            ),
        }

    except Exception as e:
        logger.error(
            "Error running position monitor for user %d: %s: %s",
            user_id,
            type(e).__name__,
            str(e),
            exc_info=True,
        )
        return {
            "status": "error",
            "user_id": user_id,
            "positions_monitored": 0,
            "auto_exits_triggered": 0,
            "reason": f"{type(e).__name__}: {str(e)}",
        }
    finally:
        db_session.close()


def _process_single_position(
    service: PositionMonitorService,
    kite_client,
    redis_client: RedisClient,
    user_id: int,
    position: MonitoredPosition,
    live_prices: Dict[str, float],
    db_session: Optional[Session] = None,
) -> Dict[str, Any]:
    """Process a single position: update price, check conditions, trigger exits.

    Args:
        service: PositionMonitorService instance.
        kite_client: Configured KiteConnect instance.
        redis_client: Redis client for PubSub and caching.
        user_id: The user's ID.
        position: The monitored position to process.
        live_prices: Dict of symbol → current live price.
        db_session: Optional SQLAlchemy session for journal entry creation.

    Returns:
        Dict with:
            - "auto_exit_triggered" (bool): Whether an auto-exit was triggered.
            - "exit_reason" (str or None): The reason if auto-exit was triggered.
    """
    # Get current price from live prices or use cached price
    current_price = live_prices.get(position.symbol, position.current_price)

    # Update position's current_price in the model for evaluation
    position = MonitoredPosition(
        position_id=position.position_id,
        symbol=position.symbol,
        entry_price=position.entry_price,
        current_price=current_price,
        quantity=position.quantity,
        stop_loss=position.stop_loss,
        target=position.target,
        trailing_stop_enabled=position.trailing_stop_enabled,
        trailing_stop_level=position.trailing_stop_level,
        trailing_stop_distance=position.trailing_stop_distance,
        unrealized_pnl=(current_price - position.entry_price) * position.quantity,
        distance_to_sl_pct=(
            (current_price - position.stop_loss) / current_price * 100
            if current_price > 0
            else 0.0
        ),
        distance_to_target_pct=(
            (position.target - current_price) / current_price * 100
            if current_price > 0
            else 0.0
        ),
        status=position.status,
    )

    # Step A: Update trailing stop if enabled
    if position.trailing_stop_enabled:
        new_trailing_level = service.update_trailing_stop(position, current_price)
        if new_trailing_level is not None:
            position = position.model_copy(
                update={"trailing_stop_level": new_trailing_level}
            )

    # Step B: Check SL/Target/Trailing Stop conditions
    exit_reason = service.check_sl_target(position, current_price)
    auto_exit_triggered = False

    if exit_reason:
        # Trigger auto-exit
        try:
            exit_data = service.trigger_auto_exit(position.position_id, exit_reason)
            auto_exit_triggered = True

            # Publish auto_exit_triggered event
            publish_auto_exit_triggered(redis_client, user_id, exit_data)

            # Create TradeJournalEntry for this exit (Requirement 14.5)
            _create_journal_entry_on_exit(
                db_session=db_session,
                user_id=user_id,
                trade_id=exit_data.get("trade_id"),
                exit_reason=exit_reason,
                exit_price=current_price,
                redis_client=redis_client,
            )

            # Update position status for the publish below
            position = position.model_copy(update={"status": exit_reason})

            logger.info(
                "Auto-exit triggered for user %d, position %d: %s",
                user_id,
                position.position_id,
                exit_reason,
            )
        except (ValueError, Exception) as e:
            logger.error(
                "Failed to trigger auto-exit for position %d: %s: %s",
                position.position_id,
                type(e).__name__,
                str(e),
            )

    # Step C: Evaluate exit conditions (only if still active)
    if not auto_exit_triggered:
        market_data = fetch_market_data_for_position(
            kite_client, position.symbol, redis_client
        )
        if market_data:
            # Update market_data with the live price
            market_data = MarketData(
                current_price=current_price,
                ema20=market_data.ema20,
                vwap=market_data.vwap,
                candles=market_data.candles,
                current_time=market_data.current_time,
            )

            conditions = service.evaluate_exit_conditions(position, market_data)

            # Publish exit condition update
            publish_exit_condition_update(
                redis_client, user_id, position.position_id, conditions
            )

            # If any exit condition is met, trigger auto-exit
            if any(c.is_met for c in conditions):
                met_conditions = [c for c in conditions if c.is_met]
                reason_detail = ", ".join(c.name for c in met_conditions)

                try:
                    exit_data = service.trigger_auto_exit(
                        position.position_id, "closed"
                    )
                    exit_data["exit_conditions_met"] = reason_detail
                    auto_exit_triggered = True

                    publish_auto_exit_triggered(redis_client, user_id, exit_data)

                    # Create TradeJournalEntry for this exit (Requirement 14.5)
                    _create_journal_entry_on_exit(
                        db_session=db_session,
                        user_id=user_id,
                        trade_id=exit_data.get("trade_id"),
                        exit_reason=f"exit_condition:{reason_detail}",
                        exit_price=current_price,
                        redis_client=redis_client,
                    )

                    position = position.model_copy(update={"status": "closed"})

                    logger.info(
                        "Exit condition auto-exit for user %d, position %d: %s",
                        user_id,
                        position.position_id,
                        reason_detail,
                    )
                except (ValueError, Exception) as e:
                    logger.error(
                        "Failed to trigger exit condition auto-exit for position %d: %s: %s",
                        position.position_id,
                        type(e).__name__,
                        str(e),
                    )

    # Step D: Publish position monitor update (always, for every cycle)
    publish_position_update(redis_client, user_id, position)

    # Step E: Cache position state for other services
    cache_position_state(redis_client, user_id, position)

    return {
        "auto_exit_triggered": auto_exit_triggered,
        "exit_reason": exit_reason if auto_exit_triggered else None,
    }


@celery_app.task(name="src.workers.position_monitor_worker.schedule_position_monitoring")
def schedule_position_monitoring() -> Dict:
    """Celery beat task: Dispatch position monitoring for each user with open positions.

    Queries the database for users with active monitored positions and
    dispatches individual monitor_positions tasks per user via Celery.

    Requirements covered:
    - 7.2: Position monitoring runs every 2 seconds per user

    Returns:
        Dict summarizing the dispatch:
            - "status": "success" or "error"
            - "users_dispatched": Number of tasks sent
            - "reason": Description of the outcome
    """
    try:
        return _execute_schedule_position_monitoring()
    except Exception as e:
        logger.error(
            "Unexpected top-level error in schedule_position_monitoring: %s: %s",
            type(e).__name__,
            str(e),
        )
        return {
            "status": "error",
            "users_dispatched": 0,
            "reason": f"Unexpected error: {type(e).__name__}: {str(e)}",
        }


def _execute_schedule_position_monitoring() -> Dict:
    """Internal implementation of the position monitoring scheduler.

    Queries for users with active positions and dispatches monitor tasks.
    """
    db_session = get_db_session()
    try:
        user_ids = get_users_with_open_positions(db_session)

        if not user_ids:
            logger.debug("No users with active monitored positions")
            return {
                "status": "success",
                "users_dispatched": 0,
                "reason": "No users with active monitored positions",
            }

        # Dispatch a monitor_positions task for each user
        dispatched_count = 0
        for user_id in user_ids:
            try:
                monitor_positions.delay(user_id)
                dispatched_count += 1
            except Exception as e:
                logger.error(
                    "Failed to dispatch position monitor for user %d: %s: %s",
                    user_id,
                    type(e).__name__,
                    str(e),
                )

        logger.info(
            "Position monitoring scheduled: dispatched %d/%d user tasks",
            dispatched_count,
            len(user_ids),
        )

        return {
            "status": "success",
            "users_dispatched": dispatched_count,
            "reason": f"Dispatched {dispatched_count} user position monitor tasks",
        }
    finally:
        db_session.close()
