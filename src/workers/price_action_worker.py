"""Price Action Engine Worker — Celery task for multi-touch breakout detection.

Runs the vectorized price action engine on intraday candle data for
configured instruments, detects breakout/breakdown signals, and feeds
them into the signal pipeline for persistence + WebSocket delivery.

Integrates with:
- price_action_engine.py (signal detection logic)
- signal_pipeline.py (persistence and WebSocket relay)
- market_data_service.py (candle data source)
- pivot_breakout_service.py (pivot level calculations)
"""

import logging
from typing import Dict, List, Optional

from src.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="src.workers.price_action_worker.run_price_action_scan",
    bind=True,
    max_retries=2,
    default_retry_delay=5,
)
def run_price_action_scan(self, user_id: int, symbols: List[str]) -> Dict:
    """Run the price action engine scan for a user's instrument list.

    Fetches intraday candles for each symbol, computes pivot levels,
    runs the vectorized multi-touch detection, and processes any
    signals through the standard signal pipeline.

    Args:
        user_id: The user requesting the scan.
        symbols: List of trading symbols to scan.

    Returns:
        Dict with scan results summary.
    """
    from src.cache.redis_client import get_redis_client
    from src.database.session import get_db_session
    from src.services.price_action_engine import (
        EngineConfig,
        detect_signals,
        get_active_signals,
        prepare_dataframe,
    )
    from src.services.pivot_breakout_service import PivotBreakoutService
    from src.services.signal_pipeline import process_scanner_signals

    redis_client = get_redis_client()
    pivot_service = PivotBreakoutService()
    config = EngineConfig()

    total_signals = 0
    scan_results = []

    for symbol in symbols:
        try:
            # Fetch intraday candle data from Redis cache
            candles = _get_candle_data(symbol, redis_client)
            if not candles or len(candles) < 20:
                logger.debug(
                    "Skipping %s: insufficient candle data (%d)",
                    symbol, len(candles) if candles else 0,
                )
                continue

            # Get previous day OHLC for pivot calculation
            prev_day = _get_previous_day_ohlc(symbol, redis_client)
            if prev_day:
                pivots = pivot_service.calculate_pivot_points(
                    prev_high=prev_day["high"],
                    prev_low=prev_day["low"],
                    prev_close=prev_day["close"],
                )
                pivot_value = pivots["pivot"]
            else:
                pivot_value = None

            # Prepare DataFrame and run engine
            df = prepare_dataframe(candles, pivot_value=pivot_value)
            df = detect_signals(df, config)

            # Extract signals
            signals = get_active_signals(df)

            if signals:
                # Convert to signal pipeline format
                pipeline_signals = []
                for sig in signals:
                    pipeline_signals.append({
                        "symbol": symbol,
                        "signal_type": (
                            "pivot_breakout" if sig.direction == 1
                            else "pivot_breakdown"
                        ),
                        "confidence_score": sig.confidence_score,
                        "entry_price": sig.breakout_price,
                        "stop_loss": sig.initial_stop_loss,
                        "target_price": _calculate_target(sig),
                        "max_potential_loss": abs(
                            sig.breakout_price - sig.initial_stop_loss
                        ),
                        "metadata": {
                            "engine": "price_action_engine",
                            "direction": sig.direction,
                            "touch_count": sig.touch_count,
                            "level_value": sig.level_value,
                            "volume_confirmed": sig.volume_confirmed,
                            "atr_value": sig.atr_value,
                        },
                    })

                # Feed into standard signal pipeline
                with get_db_session() as db:
                    created = process_scanner_signals(
                        user_id=user_id,
                        signals=pipeline_signals,
                        db=db,
                        redis_client=redis_client,
                        countdown_seconds=90,
                    )
                    total_signals += len(created)

                scan_results.append({
                    "symbol": symbol,
                    "signals_detected": len(signals),
                })

        except Exception as e:
            logger.error(
                "Price action scan failed for %s (user %d): %s: %s",
                symbol, user_id, type(e).__name__, str(e),
            )
            continue

    logger.info(
        "Price action scan complete for user %d: %d signals from %d symbols",
        user_id, total_signals, len(symbols),
    )

    return {
        "user_id": user_id,
        "symbols_scanned": len(symbols),
        "total_signals": total_signals,
        "results": scan_results,
    }


def _get_candle_data(
    symbol: str, redis_client
) -> Optional[List[Dict]]:
    """Fetch intraday candle data from Redis cache.

    Expects candles to be stored by the market_data_worker as a JSON list
    under key: candles:intraday:{symbol}

    Args:
        symbol: Trading symbol.
        redis_client: RedisClient instance.

    Returns:
        List of candle dicts or None if not available.
    """
    import json

    key = f"candles:intraday:{symbol}"
    raw = redis_client.get(key)
    if raw is None:
        return None

    try:
        candles = json.loads(raw)
        return candles if isinstance(candles, list) else None
    except (json.JSONDecodeError, TypeError):
        return None


def _get_previous_day_ohlc(
    symbol: str, redis_client
) -> Optional[Dict]:
    """Fetch previous day's OHLC from Redis cache.

    Expects data stored by market_data_worker under key:
    ohlc:prev_day:{symbol}

    Args:
        symbol: Trading symbol.
        redis_client: RedisClient instance.

    Returns:
        Dict with high, low, close keys or None.
    """
    import json

    key = f"ohlc:prev_day:{symbol}"
    raw = redis_client.get(key)
    if raw is None:
        return None

    try:
        data = json.loads(raw)
        if all(k in data for k in ("high", "low", "close")):
            return data
        return None
    except (json.JSONDecodeError, TypeError):
        return None


def _calculate_target(signal) -> float:
    """Calculate target price based on signal direction and risk.

    Uses 2:1 reward-to-risk ratio.

    Args:
        signal: BreakoutSignalResult object.

    Returns:
        Target price as float.
    """
    risk = abs(signal.breakout_price - signal.initial_stop_loss)
    if signal.direction == 1:  # Long
        return round(signal.breakout_price + (risk * 2), 2)
    else:  # Short
        return round(signal.breakout_price - (risk * 2), 2)
