"""Scanner Worker — Celery tasks for trend-pullback and consolidation scans.

Fetches candle data from Kite API for symbols in the user's watchlist,
runs analysis via ScannerService, and publishes detected signals via
Redis PubSub for WebSocket relay to the frontend.

Tasks:
- run_trend_pullback_scan: On-demand or scheduled trend-pullback scan
- run_consolidation_scan: On-demand or scheduled consolidation breakout scan

Publishes:
- scanner:signal_detected:{user_id} — when trend-pullback signals are found
- scanner:consolidation_update:{user_id} — consolidation pattern updates/breakouts

Requirements covered:
- 1.1: Trigger backend trend-pullback scan for all symbols in watchlist
- 2.1: Display active consolidation patterns on monitored option symbols
- 2.4: Push real-time candle updates to Consolidation_Scanner_UI at 3-min intervals
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional

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

# Redis PubSub channel patterns
SIGNAL_DETECTED_CHANNEL = "scanner:signal_detected:{user_id}"
CONSOLIDATION_UPDATE_CHANNEL = "scanner:consolidation_update:{user_id}"

# Default candle fetch parameters
TREND_PULLBACK_INTERVAL = "5minute"
TREND_PULLBACK_LOOKBACK_DAYS = 2
CONSOLIDATION_INTERVAL = "3minute"
CONSOLIDATION_LOOKBACK_HOURS = 2


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


def _get_db_session() -> Session:
    """Create a new database session.

    Returns:
        A new SQLAlchemy Session instance.
    """
    factory = _get_session_factory()
    return factory()


def _get_kite_client(user_id: int, db_session: Session):
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


def _signal_detected_channel(user_id: int) -> str:
    """Redis PubSub channel for scanner signal detection events."""
    return f"scanner:signal_detected:{user_id}"


def _consolidation_update_channel(user_id: int) -> str:
    """Redis PubSub channel for consolidation pattern updates."""
    return f"scanner:consolidation_update:{user_id}"


def _fetch_candle_data(
    kite_client,
    symbol: str,
    interval: str,
    lookback_days: Optional[int] = None,
    lookback_hours: Optional[int] = None,
) -> List[Dict]:
    """Fetch historical candle data from Kite API for a symbol.

    Resolves the instrument token for the symbol and fetches OHLCV data
    from the Kite historical_data API.

    Args:
        kite_client: Configured KiteConnect instance.
        symbol: Trading symbol (e.g., "RELIANCE", "NIFTY24600CE").
        interval: Candle interval ("3minute", "5minute", "15minute", etc.).
        lookback_days: Number of days to look back (for trend scans).
        lookback_hours: Number of hours to look back (for consolidation scans).

    Returns:
        List of candle dicts with keys: open, high, low, close, volume.
        Returns empty list on failure.
    """
    try:
        # Resolve instrument token
        token = _resolve_instrument_token(kite_client, symbol)
        if token is None:
            logger.warning("Could not resolve instrument token for %s", symbol)
            return []

        # Calculate date range
        to_date = datetime.now()
        if lookback_days:
            from_date = to_date - timedelta(days=lookback_days)
        elif lookback_hours:
            from_date = to_date - timedelta(hours=lookback_hours)
        else:
            from_date = to_date - timedelta(days=1)

        # Fetch historical data
        records = kite_client.historical_data(
            token, from_date, to_date, interval=interval
        )

        if not records:
            return []

        # Normalize to list of dicts with standard keys
        candles = []
        for record in records:
            candle = {
                "open": float(record.get("open", 0)),
                "high": float(record.get("high", 0)),
                "low": float(record.get("low", 0)),
                "close": float(record.get("close", 0)),
                "volume": int(record.get("volume", 0)),
            }
            candles.append(candle)

        return candles

    except Exception as e:
        logger.error(
            "Error fetching candle data for %s (%s): %s: %s",
            symbol,
            interval,
            type(e).__name__,
            str(e),
        )
        return []


def _resolve_instrument_token(kite_client, symbol: str) -> Optional[int]:
    """Resolve a symbol name to its Kite instrument token.

    Checks common exchanges (NFO, NSE, BFO, BSE) to find the instrument.
    Caches resolved tokens in Redis for performance.

    Args:
        kite_client: Configured KiteConnect instance.
        symbol: Trading symbol to resolve.

    Returns:
        Instrument token as int, or None if not found.
    """
    redis_client = get_redis_client()

    # Check cache first
    cache_key = f"instrument_token:{symbol}"
    cached_token = redis_client.get(cache_key)
    if cached_token:
        try:
            return int(cached_token)
        except (TypeError, ValueError):
            pass

    try:
        # Try NFO first (options), then NSE (equities)
        for exchange in ("NFO", "NSE", "BFO", "BSE"):
            try:
                instruments = kite_client.ltp(f"{exchange}:{symbol}")
                if instruments:
                    key = f"{exchange}:{symbol}"
                    if key in instruments:
                        token = instruments[key].get("instrument_token")
                        if token:
                            # Cache for 24 hours
                            redis_client.set(cache_key, str(token), ttl=86400)
                            return token
            except Exception:
                continue

        # Fallback: search via instruments list (expensive, cached)
        instruments_cache_key = f"instruments_list:NSE"
        instruments_json = redis_client.get(instruments_cache_key)

        if not instruments_json:
            instruments = kite_client.instruments("NSE")
            for inst in instruments:
                if inst.get("tradingsymbol") == symbol:
                    token = inst.get("instrument_token")
                    redis_client.set(cache_key, str(token), ttl=86400)
                    return token

            # Also check NFO
            instruments = kite_client.instruments("NFO")
            for inst in instruments:
                if inst.get("tradingsymbol") == symbol:
                    token = inst.get("instrument_token")
                    redis_client.set(cache_key, str(token), ttl=86400)
                    return token

        return None

    except Exception as e:
        logger.error(
            "Error resolving instrument token for %s: %s: %s",
            symbol,
            type(e).__name__,
            str(e),
        )
        return None


def _publish_signals(user_id: int, signals: List[Dict]) -> bool:
    """Publish detected scan signals to Redis PubSub for WebSocket relay.

    Args:
        user_id: The user's database ID.
        signals: List of signal dicts to publish.

    Returns:
        True if published successfully, False otherwise.
    """
    if not signals:
        return True

    redis_client = get_redis_client()
    channel = _signal_detected_channel(user_id)

    payload = {
        "user_id": user_id,
        "signals": signals,
        "count": len(signals),
        "timestamp": datetime.now().isoformat(),
    }

    try:
        redis_client.client.publish(channel, json.dumps(payload, default=str))
        logger.info(
            "Published %d signal(s) to channel '%s' for user %d",
            len(signals),
            channel,
            user_id,
        )
        return True
    except Exception as e:
        logger.error(
            "Failed to publish signals for user %d: %s: %s",
            user_id,
            type(e).__name__,
            str(e),
        )
        return False


def _publish_consolidation_update(user_id: int, updates: List[Dict]) -> bool:
    """Publish consolidation pattern updates to Redis PubSub for WebSocket relay.

    Args:
        user_id: The user's database ID.
        updates: List of consolidation update dicts to publish.

    Returns:
        True if published successfully, False otherwise.
    """
    redis_client = get_redis_client()
    channel = _consolidation_update_channel(user_id)

    payload = {
        "user_id": user_id,
        "patterns": updates,
        "count": len(updates),
        "timestamp": datetime.now().isoformat(),
    }

    try:
        redis_client.client.publish(channel, json.dumps(payload, default=str))
        logger.debug(
            "Published %d consolidation update(s) to channel '%s' for user %d",
            len(updates),
            channel,
            user_id,
        )
        return True
    except Exception as e:
        logger.error(
            "Failed to publish consolidation updates for user %d: %s: %s",
            user_id,
            type(e).__name__,
            str(e),
        )
        return False


@celery_app.task(
    name="src.workers.scanner_worker.run_trend_pullback_scan",
    bind=True,
    max_retries=2,
    default_retry_delay=5,
)
def run_trend_pullback_scan(self, user_id: int) -> Dict:
    """Celery task: Run trend-pullback scan for a user's watchlist.

    Fetches 5-minute candle data from Kite API for all symbols in the user's
    configured watchlist, runs ScannerService.run_trend_pullback_scan, and
    publishes detected signals to Redis PubSub channel for WebSocket relay.

    Requirements covered:
    - 1.1: Trigger backend trend-pullback scan for all symbols in watchlist

    Args:
        user_id: The user's database ID.

    Returns:
        Dict summarizing the scan:
            - "status": "success", "no_signals", or "error"
            - "user_id": The user's ID
            - "signals_count": Number of signals detected
            - "symbols_scanned": Number of symbols processed
            - "reason": Description of the outcome
    """
    try:
        return _execute_trend_pullback_scan(user_id)
    except Exception as e:
        logger.error(
            "Unexpected error in run_trend_pullback_scan for user %d: %s: %s",
            user_id,
            type(e).__name__,
            str(e),
            exc_info=True,
        )
        # Retry on transient errors
        try:
            self.retry(exc=e)
        except self.MaxRetriesExceededError:
            pass

        return {
            "status": "error",
            "user_id": user_id,
            "signals_count": 0,
            "symbols_scanned": 0,
            "reason": f"Unexpected error: {type(e).__name__}: {str(e)}",
        }


def _execute_trend_pullback_scan(user_id: int) -> Dict:
    """Internal implementation of the trend-pullback scan.

    Steps:
    1. Load user's watchlist from Redis cache (or fallback to DB)
    2. Get Kite client for the user
    3. Fetch 5-minute candle data for each symbol
    4. Run ScannerService.run_trend_pullback_scan
    5. Publish detected signals to Redis PubSub
    6. Cache signals in Redis for API retrieval

    Args:
        user_id: The user's database ID.

    Returns:
        Dict summarizing the scan result.
    """
    from src.services.scanner_service import ScannerService
    from src.services.settings_service import SettingsService

    db_session = _get_db_session()
    try:
        # Step 1: Load user's watchlist (Redis cache first, DB fallback)
        watchlist = SettingsService.get_cached_watchlist(user_id)
        if watchlist is None:
            settings_service = SettingsService()
            strategy_settings = settings_service.get_strategy_settings(db_session, user_id)
            watchlist = strategy_settings.watchlist

        if not watchlist:
            logger.info("User %d has empty watchlist, skipping scan", user_id)
            return {
                "status": "no_signals",
                "user_id": user_id,
                "signals_count": 0,
                "symbols_scanned": 0,
                "reason": "Empty watchlist",
            }

        # Step 2: Get Kite client
        kite_client = _get_kite_client(user_id, db_session)

        # Step 3: Fetch candle data for each symbol
        candle_data_by_symbol: Dict[str, List[Dict]] = {}
        for symbol in watchlist:
            candles = _fetch_candle_data(
                kite_client,
                symbol,
                interval=TREND_PULLBACK_INTERVAL,
                lookback_days=TREND_PULLBACK_LOOKBACK_DAYS,
            )
            if candles:
                candle_data_by_symbol[symbol] = candles
            else:
                logger.debug(
                    "No candle data available for %s (user %d)", symbol, user_id
                )

        if not candle_data_by_symbol:
            logger.info(
                "No candle data fetched for any symbol in user %d's watchlist",
                user_id,
            )
            return {
                "status": "no_signals",
                "user_id": user_id,
                "signals_count": 0,
                "symbols_scanned": 0,
                "reason": "No candle data available for any symbol",
            }

        # Step 4: Run scanner analysis
        scanner = ScannerService()
        signals = scanner.run_trend_pullback_scan(watchlist, candle_data_by_symbol)

        # Step 5: Process signals through the full pipeline
        # (persist → AI analysis → WebSocket event)
        if signals:
            signal_dicts = [signal.model_dump() for signal in signals]

            # Use signal pipeline to persist, trigger AI, and broadcast
            from src.services.signal_pipeline import process_scanner_signals

            created_signals = process_scanner_signals(
                user_id=user_id,
                signals=signal_dicts,
                db=db_session,
                redis_client=get_redis_client(),
                countdown_seconds=_get_countdown_seconds(db_session, user_id),
            )

            # Also cache signals in Redis for API retrieval (backward compat)
            _cache_scan_results(user_id, signal_dicts)

        logger.info(
            "Trend pullback scan complete for user %d: %d signals from %d symbols",
            user_id,
            len(signals),
            len(candle_data_by_symbol),
        )

        status = "success" if signals else "no_signals"
        return {
            "status": status,
            "user_id": user_id,
            "signals_count": len(signals),
            "symbols_scanned": len(candle_data_by_symbol),
            "reason": (
                f"Found {len(signals)} signal(s)"
                if signals
                else "No setups found matching criteria"
            ),
        }

    except RuntimeError as e:
        # Kite client errors (no token, etc.)
        logger.warning(
            "Cannot run scan for user %d: %s", user_id, str(e)
        )
        return {
            "status": "error",
            "user_id": user_id,
            "signals_count": 0,
            "symbols_scanned": 0,
            "reason": str(e),
        }
    except Exception as e:
        logger.error(
            "Error in trend pullback scan for user %d: %s: %s",
            user_id,
            type(e).__name__,
            str(e),
            exc_info=True,
        )
        raise
    finally:
        db_session.close()


@celery_app.task(
    name="src.workers.scanner_worker.run_consolidation_scan",
    bind=True,
    max_retries=2,
    default_retry_delay=5,
)
def run_consolidation_scan(self, user_id: int) -> Dict:
    """Celery task: Run consolidation breakout scan for a user's watchlist.

    Fetches 3-minute candle data from Kite API for all symbols in the user's
    configured watchlist, runs ScannerService.detect_consolidation for each
    symbol, checks for breakouts, and publishes updates via Redis PubSub.

    Requirements covered:
    - 2.1: Display active consolidation patterns on monitored option symbols
    - 2.4: Push real-time candle updates at 3-minute intervals

    Args:
        user_id: The user's database ID.

    Returns:
        Dict summarizing the scan:
            - "status": "success", "no_patterns", or "error"
            - "user_id": The user's ID
            - "patterns_count": Number of consolidation patterns detected
            - "breakouts_count": Number of breakouts detected
            - "symbols_scanned": Number of symbols processed
            - "reason": Description of the outcome
    """
    try:
        return _execute_consolidation_scan(user_id)
    except Exception as e:
        logger.error(
            "Unexpected error in run_consolidation_scan for user %d: %s: %s",
            user_id,
            type(e).__name__,
            str(e),
            exc_info=True,
        )
        # Retry on transient errors
        try:
            self.retry(exc=e)
        except self.MaxRetriesExceededError:
            pass

        return {
            "status": "error",
            "user_id": user_id,
            "patterns_count": 0,
            "breakouts_count": 0,
            "symbols_scanned": 0,
            "reason": f"Unexpected error: {type(e).__name__}: {str(e)}",
        }


def _execute_consolidation_scan(user_id: int) -> Dict:
    """Internal implementation of the consolidation breakout scan.

    Steps:
    1. Load user's watchlist from Redis cache (or fallback to DB)
    2. Get Kite client for the user
    3. Fetch 3-minute candle data for each symbol
    4. Run ScannerService.detect_consolidation for each symbol
    5. Check for breakouts on detected patterns
    6. Publish pattern updates and breakout signals via Redis PubSub
    7. Cache patterns in Redis for API retrieval

    Args:
        user_id: The user's database ID.

    Returns:
        Dict summarizing the scan result.
    """
    from src.services.scanner_service import ScannerService
    from src.services.settings_service import SettingsService

    db_session = _get_db_session()
    try:
        # Step 1: Load user's watchlist (Redis cache first, DB fallback)
        watchlist = SettingsService.get_cached_watchlist(user_id)
        if watchlist is None:
            settings_service = SettingsService()
            strategy_settings = settings_service.get_strategy_settings(db_session, user_id)
            watchlist = strategy_settings.watchlist

        if not watchlist:
            logger.info("User %d has empty watchlist, skipping consolidation scan", user_id)
            return {
                "status": "no_patterns",
                "user_id": user_id,
                "patterns_count": 0,
                "breakouts_count": 0,
                "symbols_scanned": 0,
                "reason": "Empty watchlist",
            }

        # Step 2: Get Kite client
        kite_client = _get_kite_client(user_id, db_session)

        # Step 3: Fetch 3-minute candle data for each symbol
        scanner = ScannerService()
        patterns = []
        breakouts = []
        symbols_scanned = 0

        for symbol in watchlist:
            candles = _fetch_candle_data(
                kite_client,
                symbol,
                interval=CONSOLIDATION_INTERVAL,
                lookback_hours=CONSOLIDATION_LOOKBACK_HOURS,
            )

            if not candles:
                logger.debug(
                    "No 3-min candle data available for %s (user %d)",
                    symbol,
                    user_id,
                )
                continue

            symbols_scanned += 1

            # Step 4: Detect consolidation
            pattern = scanner.detect_consolidation(symbol, candles)
            if pattern is None:
                continue

            # Step 5: Check for breakout using latest price
            current_price = candles[-1]["close"] if candles else 0
            is_breakout = scanner.check_breakout(pattern, current_price)

            if is_breakout:
                pattern.is_breakout = True
                pattern.breakout_price = current_price
                breakouts.append(pattern)

            patterns.append(pattern)

        # Step 6: Publish updates via Redis PubSub
        if patterns:
            pattern_dicts = [p.model_dump() for p in patterns]
            _publish_consolidation_update(user_id, pattern_dicts)

            # If breakouts detected, persist via signal pipeline
            if breakouts:
                breakout_signal_dicts = [
                    {
                        "symbol": b.symbol,
                        "scan_type": "consolidation_breakout",
                        "signal_type": "consolidation_breakout",
                        "confidence_score": 75.0,  # Default confidence for breakouts
                        "entry_price": b.breakout_price or b.range_high,
                        "stop_loss": b.range_low,
                        "target_price": (b.breakout_price or b.range_high) + (b.range_high - b.range_low),
                        "max_potential_loss": ((b.breakout_price or b.range_high) - b.range_low),
                        "range_high": b.range_high,
                        "range_low": b.range_low,
                        "breakout_price": b.breakout_price,
                        "avg_price": b.avg_price,
                        "candle_count": b.candle_count,
                        "duration_minutes": b.duration_minutes,
                        "metadata": {
                            "range_high": b.range_high,
                            "range_low": b.range_low,
                            "candle_count": b.candle_count,
                            "duration_minutes": b.duration_minutes,
                        },
                    }
                    for b in breakouts
                ]

                # Process breakout signals through full pipeline
                from src.services.signal_pipeline import process_scanner_signals

                process_scanner_signals(
                    user_id=user_id,
                    signals=breakout_signal_dicts,
                    db=db_session,
                    redis_client=get_redis_client(),
                    countdown_seconds=_get_countdown_seconds(db_session, user_id),
                )

            # Step 7: Cache patterns in Redis
            _cache_consolidation_patterns(user_id, pattern_dicts)

        logger.info(
            "Consolidation scan complete for user %d: %d patterns, %d breakouts from %d symbols",
            user_id,
            len(patterns),
            len(breakouts),
            symbols_scanned,
        )

        status = "success" if patterns else "no_patterns"
        return {
            "status": status,
            "user_id": user_id,
            "patterns_count": len(patterns),
            "breakouts_count": len(breakouts),
            "symbols_scanned": symbols_scanned,
            "reason": (
                f"Found {len(patterns)} pattern(s), {len(breakouts)} breakout(s)"
                if patterns
                else "No consolidation patterns detected"
            ),
        }

    except RuntimeError as e:
        # Kite client errors (no token, etc.)
        logger.warning(
            "Cannot run consolidation scan for user %d: %s", user_id, str(e)
        )
        return {
            "status": "error",
            "user_id": user_id,
            "patterns_count": 0,
            "breakouts_count": 0,
            "symbols_scanned": 0,
            "reason": str(e),
        }
    except Exception as e:
        logger.error(
            "Error in consolidation scan for user %d: %s: %s",
            user_id,
            type(e).__name__,
            str(e),
            exc_info=True,
        )
        raise
    finally:
        db_session.close()


def _get_countdown_seconds(db_session: Session, user_id: int) -> int:
    """Get the signal countdown duration from user settings.

    Falls back to 60 seconds if settings cannot be loaded.

    Args:
        db_session: SQLAlchemy session for database queries.
        user_id: The user's database ID.

    Returns:
        Countdown duration in seconds.
    """
    try:
        from src.services.settings_service import SettingsService

        settings_service = SettingsService()
        strategy_settings = settings_service.get_strategy_settings(db_session, user_id)
        # Use signal_countdown if available, otherwise default to 60
        return getattr(strategy_settings, "signal_countdown_seconds", 60) or 60
    except Exception:
        return 60


def _cache_scan_results(user_id: int, signals: List[Dict]) -> None:
    """Cache scan results in Redis for API retrieval.

    Stores the latest scan results so the API can serve them
    without requiring a new scan each time.

    Args:
        user_id: The user's database ID.
        signals: List of signal dicts to cache.
    """
    redis_client = get_redis_client()
    cache_key = f"user:{user_id}:scanner:latest_signals"

    try:
        payload = json.dumps(signals, default=str)
        # Cache for 5 minutes (signals are time-sensitive)
        redis_client.set(cache_key, payload, ttl=300)
        logger.debug(
            "Cached %d scan signals for user %d (TTL 300s)",
            len(signals),
            user_id,
        )
    except Exception as e:
        logger.error(
            "Failed to cache scan results for user %d: %s: %s",
            user_id,
            type(e).__name__,
            str(e),
        )


def _cache_consolidation_patterns(user_id: int, patterns: List[Dict]) -> None:
    """Cache consolidation patterns in Redis for API retrieval.

    Stores the latest consolidation patterns so the API can serve them
    without requiring a new scan each time.

    Args:
        user_id: The user's database ID.
        patterns: List of pattern dicts to cache.
    """
    redis_client = get_redis_client()
    cache_key = f"user:{user_id}:scanner:consolidation_patterns"

    try:
        payload = json.dumps(patterns, default=str)
        # Cache for 3 minutes (aligned with 3-minute candle interval)
        redis_client.set(cache_key, payload, ttl=180)
        logger.debug(
            "Cached %d consolidation patterns for user %d (TTL 180s)",
            len(patterns),
            user_id,
        )
    except Exception as e:
        logger.error(
            "Failed to cache consolidation patterns for user %d: %s: %s",
            user_id,
            type(e).__name__,
            str(e),
        )
