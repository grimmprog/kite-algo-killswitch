"""Technical Charts API endpoints.

Requirements covered:
- 15.1: Display candlestick chart with EMA(20), VWAP, and MACD overlays
- 15.2: Display most recent 50 candles at 5-minute intervals by default
- 15.3: Allow switching between 3-min, 5-min, and 15-min candle intervals
- 15.4: Mark signal entry point and stop-loss on chart when viewing a signal
- 15.5: Display data unavailability message when historical data is missing

Endpoints:
- GET /api/v1/charts/{symbol}                — Get candlestick + indicator data
- GET /api/v1/charts/{symbol}/signal/{signal_id} — Get chart with signal entry/SL overlay
"""

import json
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from src.api.dependencies import get_db, get_redis, get_current_user
from src.cache.redis_client import RedisClient
from src.database.models.scan_signal import ScanSignal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["charts"])


# --------------------------------------------------------------------------
# Response schemas
# --------------------------------------------------------------------------


class CandleData(BaseModel):
    """A single candlestick data point."""

    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class IndicatorData(BaseModel):
    """Technical indicator values for the chart."""

    ema20: List[Optional[float]]
    vwap: List[Optional[float]]
    macd_line: List[Optional[float]]
    macd_signal: List[Optional[float]]
    macd_histogram: List[Optional[float]]


class SignalOverlay(BaseModel):
    """Signal entry/SL markers for chart overlay."""

    signal_id: int
    entry_price: float
    stop_loss: float
    target_price: Optional[float] = None
    symbol: str


class ChartResponse(BaseModel):
    """Complete chart data response with candles and indicators."""

    symbol: str
    interval: str
    candle_count: int
    candles: List[CandleData]
    indicators: IndicatorData
    signal_overlay: Optional[SignalOverlay] = None


# --------------------------------------------------------------------------
# Indicator calculation helpers
# --------------------------------------------------------------------------


def _compute_ema(closes: List[float], period: int = 20) -> List[Optional[float]]:
    """Compute Exponential Moving Average.

    Returns a list of EMA values. Values before the period are None.

    Args:
        closes: List of closing prices.
        period: EMA period (default 20).

    Returns:
        List of EMA values with None for insufficient data points.
    """
    if len(closes) < period:
        return [None] * len(closes)

    ema_values: List[Optional[float]] = [None] * (period - 1)
    # SMA for first EMA value
    sma = sum(closes[:period]) / period
    ema_values.append(round(sma, 2))

    multiplier = 2 / (period + 1)
    for i in range(period, len(closes)):
        ema_val = (closes[i] - ema_values[-1]) * multiplier + ema_values[-1]
        ema_values.append(round(ema_val, 2))

    return ema_values


def _compute_vwap(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    volumes: List[int],
) -> List[Optional[float]]:
    """Compute Volume Weighted Average Price (cumulative intraday).

    Args:
        highs: List of high prices.
        lows: List of low prices.
        closes: List of closing prices.
        volumes: List of volumes.

    Returns:
        List of cumulative VWAP values.
    """
    vwap_values: List[Optional[float]] = []
    cumulative_tp_vol = 0.0
    cumulative_vol = 0

    for i in range(len(closes)):
        typical_price = (highs[i] + lows[i] + closes[i]) / 3
        cumulative_tp_vol += typical_price * volumes[i]
        cumulative_vol += volumes[i]

        if cumulative_vol > 0:
            vwap_values.append(round(cumulative_tp_vol / cumulative_vol, 2))
        else:
            vwap_values.append(None)

    return vwap_values


def _compute_macd(
    closes: List[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    """Compute MACD line, signal line, and histogram.

    Args:
        closes: List of closing prices.
        fast_period: Fast EMA period (default 12).
        slow_period: Slow EMA period (default 26).
        signal_period: Signal EMA period (default 9).

    Returns:
        Tuple of (macd_line, signal_line, histogram) lists.
    """
    if len(closes) < slow_period:
        n = len(closes)
        return [None] * n, [None] * n, [None] * n

    # Compute fast and slow EMAs
    fast_ema = _compute_ema(closes, fast_period)
    slow_ema = _compute_ema(closes, slow_period)

    # MACD line = fast EMA - slow EMA
    macd_line: List[Optional[float]] = []
    for i in range(len(closes)):
        if fast_ema[i] is not None and slow_ema[i] is not None:
            macd_line.append(round(fast_ema[i] - slow_ema[i], 4))
        else:
            macd_line.append(None)

    # Signal line = EMA of MACD line
    macd_valid = [v for v in macd_line if v is not None]
    if len(macd_valid) < signal_period:
        signal_line = [None] * len(closes)
        histogram = [None] * len(closes)
        return macd_line, signal_line, histogram

    signal_ema = _compute_ema(macd_valid, signal_period)

    # Map signal EMA back to full list
    signal_line: List[Optional[float]] = [None] * (len(closes) - len(macd_valid))
    for i, val in enumerate(signal_ema):
        signal_line.append(round(val, 4) if val is not None else None)

    # Histogram = MACD - Signal
    histogram: List[Optional[float]] = []
    for i in range(len(closes)):
        if macd_line[i] is not None and signal_line[i] is not None:
            histogram.append(round(macd_line[i] - signal_line[i], 4))
        else:
            histogram.append(None)

    return macd_line, signal_line, histogram


def _compute_indicators(candles: List[CandleData]) -> IndicatorData:
    """Compute all technical indicators from candle data.

    Args:
        candles: List of CandleData objects.

    Returns:
        IndicatorData with EMA20, VWAP, and MACD values.
    """
    closes = [c.close for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    volumes = [c.volume for c in candles]

    ema20 = _compute_ema(closes, 20)
    vwap = _compute_vwap(highs, lows, closes, volumes)
    macd_line, macd_signal, macd_histogram = _compute_macd(closes)

    return IndicatorData(
        ema20=ema20,
        vwap=vwap,
        macd_line=macd_line,
        macd_signal=macd_signal,
        macd_histogram=macd_histogram,
    )


# --------------------------------------------------------------------------
# Data fetching helpers
# --------------------------------------------------------------------------

VALID_INTERVALS = ("3min", "5min", "15min")


def _get_candles_from_redis(
    redis_client: RedisClient, symbol: str, interval: str, count: int
) -> Optional[List[CandleData]]:
    """Attempt to fetch candle data from Redis cache.

    Key pattern: market:{symbol}:candles:{interval}

    Args:
        redis_client: Redis client instance.
        symbol: Trading symbol.
        interval: Candle interval (3min, 5min, 15min).
        count: Number of candles to return.

    Returns:
        List of CandleData if cached, None otherwise.
    """
    cache_key = f"market:{symbol}:candles:{interval}"
    cached_data = redis_client.get(cache_key)

    if not cached_data:
        return None

    try:
        candles_raw = json.loads(cached_data)
        if not isinstance(candles_raw, list):
            return None

        # Take the most recent `count` candles
        recent_candles = candles_raw[-count:] if len(candles_raw) > count else candles_raw

        candles = []
        for c in recent_candles:
            candles.append(
                CandleData(
                    timestamp=c.get("timestamp", ""),
                    open=float(c.get("open", 0)),
                    high=float(c.get("high", 0)),
                    low=float(c.get("low", 0)),
                    close=float(c.get("close", 0)),
                    volume=int(c.get("volume", 0)),
                )
            )
        return candles if candles else None
    except (json.JSONDecodeError, TypeError, KeyError, ValueError):
        logger.warning("Failed to parse cached candle data for %s", symbol)
        return None


def _get_candles_from_market_data(
    redis_client: RedisClient, symbol: str
) -> Optional[List[CandleData]]:
    """Fallback: try to build candle data from market:{symbol}:data.

    This is a simplified fallback using market data if candles cache
    is not populated.

    Args:
        redis_client: Redis client instance.
        symbol: Trading symbol.

    Returns:
        List with single candle from market data, or None.
    """
    market_key = f"market:{symbol}:data"
    market_data_str = redis_client.get(market_key)

    if not market_data_str:
        return None

    try:
        market_data = json.loads(market_data_str)
        spot = market_data.get("spot")
        if spot is None:
            return None

        # Return a minimal response indicating live data available
        # but no historical candles
        return None
    except (json.JSONDecodeError, TypeError):
        return None


# --------------------------------------------------------------------------
# GET /api/v1/charts/{symbol}
# --------------------------------------------------------------------------


@router.get("/charts/{symbol}", response_model=ChartResponse)
async def get_chart_data(
    symbol: str,
    user_id: int = Depends(get_current_user),
    redis: RedisClient = Depends(get_redis),
    interval: str = Query(
        "5min",
        description="Candle interval: 3min, 5min, or 15min",
    ),
    count: int = Query(
        50,
        ge=10,
        le=200,
        description="Number of candles to return (default 50)",
    ),
):
    """Get candlestick chart data with EMA(20), VWAP, and MACD indicators.

    15.1: Returns candles with EMA(20), VWAP, and MACD overlays.
    15.2: Default 50 candles at 5-minute interval.
    15.3: Supports 3-min, 5-min, and 15-min intervals.
    15.5: Returns 404 if historical data is unavailable.
    """
    # Validate interval
    if interval not in VALID_INTERVALS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid interval '{interval}'. Must be one of: {', '.join(VALID_INTERVALS)}",
        )

    # Try Redis cache first
    candles = _get_candles_from_redis(redis, symbol, interval, count)

    # Fallback to market data key
    if candles is None:
        candles = _get_candles_from_market_data(redis, symbol)

    # If no data available, return 404
    if candles is None or len(candles) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Historical data unavailable for symbol '{symbol}' at interval '{interval}'",
        )

    # Compute indicators
    indicators = _compute_indicators(candles)

    return ChartResponse(
        symbol=symbol,
        interval=interval,
        candle_count=len(candles),
        candles=candles,
        indicators=indicators,
        signal_overlay=None,
    )


# --------------------------------------------------------------------------
# GET /api/v1/charts/{symbol}/signal/{signal_id}
# --------------------------------------------------------------------------


@router.get("/charts/{symbol}/signal/{signal_id}", response_model=ChartResponse)
async def get_chart_with_signal(
    symbol: str,
    signal_id: int,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    interval: str = Query(
        "5min",
        description="Candle interval: 3min, 5min, or 15min",
    ),
    count: int = Query(
        50,
        ge=10,
        le=200,
        description="Number of candles to return (default 50)",
    ),
):
    """Get chart data with signal entry/SL overlay markers.

    15.4: Marks signal entry point and stop-loss level on the chart.
    15.5: Returns 404 if historical data is unavailable.

    Fetches the signal from the database, validates it belongs to
    the user and matches the requested symbol, then overlays
    entry/SL/target markers on the chart.
    """
    # Validate interval
    if interval not in VALID_INTERVALS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid interval '{interval}'. Must be one of: {', '.join(VALID_INTERVALS)}",
        )

    # Fetch signal from database
    signal = (
        db.query(ScanSignal)
        .filter(
            ScanSignal.id == signal_id,
            ScanSignal.user_id == user_id,
        )
        .first()
    )

    if signal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Signal {signal_id} not found",
        )

    # Validate symbol matches signal
    if signal.symbol.upper() != symbol.upper():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Signal {signal_id} is for symbol '{signal.symbol}', not '{symbol}'",
        )

    # Try Redis cache first
    candles = _get_candles_from_redis(redis, symbol, interval, count)

    # Fallback to market data key
    if candles is None:
        candles = _get_candles_from_market_data(redis, symbol)

    # If no data available, return 404
    if candles is None or len(candles) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Historical data unavailable for symbol '{symbol}' at interval '{interval}'",
        )

    # Compute indicators
    indicators = _compute_indicators(candles)

    # Build signal overlay
    overlay = SignalOverlay(
        signal_id=signal.id,
        entry_price=signal.entry_price,
        stop_loss=signal.stop_loss,
        target_price=signal.target_price,
        symbol=signal.symbol,
    )

    return ChartResponse(
        symbol=symbol,
        interval=interval,
        candle_count=len(candles),
        candles=candles,
        indicators=indicators,
        signal_overlay=overlay,
    )
