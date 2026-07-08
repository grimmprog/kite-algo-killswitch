"""Scanner API endpoints for trend-pullback, breakout, and consolidation scanning.

Requirements covered:
- 1.1: Trigger backend trend-pullback scan for all symbols in watchlist
- 2.1: Display active consolidation patterns on monitored option symbols
- Breakout: Multi-touch breakout/breakdown detection with ATR trailing stop

Endpoints:
- POST /api/v1/scanner/trend-pullback — Trigger trend pullback scan for user's watchlist
- POST /api/v1/scanner/breakout       — Trigger price-action breakout scan
- GET  /api/v1/scanner/consolidation  — Get active consolidation patterns
- GET  /api/v1/scanner/signals        — Get scan results/signal history
"""

import json
import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.dependencies import get_db, get_redis, get_current_user
from src.cache.redis_client import RedisClient
from src.database.models.scan_signal import ScanSignal as ScanSignalModel
from src.database.models.user_settings import UserSettings
from src.services.scanner_service import (
    ConsolidationPattern,
    ScannerService,
    ScanSignal,
)
from src.services.price_action_engine import (
    EngineConfig,
    detect_signals,
    get_active_signals,
    prepare_dataframe,
    TradeStateManager,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["scanner"])

# --- Response schemas ---


class TrendPullbackRequest(BaseModel):
    """Optional request body for trend pullback scan.

    If watchlist is not provided, the user's configured watchlist is used.
    """

    watchlist: Optional[List[str]] = Field(
        default=None,
        description="Optional override watchlist. If not provided, uses user's configured watchlist.",
    )


class ScanSignalResponse(BaseModel):
    """Response model for a single scan signal."""

    symbol: str
    scan_type: str
    confidence_score: float
    entry_price: float
    stop_loss: float
    target_price: float
    max_potential_loss: float
    timestamp: str
    metadata: Dict = Field(default_factory=dict)


class TrendPullbackResponse(BaseModel):
    """Response model for trend pullback scan results."""

    signals: List[ScanSignalResponse]
    scan_status: str
    symbols_scanned: int
    message: str


class BreakoutRequest(BaseModel):
    """Request body for price-action breakout scan.

    If watchlist is not provided, the user's configured watchlist is used.
    """

    watchlist: Optional[List[str]] = Field(
        default=None,
        description="Optional override watchlist. Uses user's configured watchlist if omitted.",
    )
    lookback: int = Field(default=20, ge=5, le=100, description="Rolling window for resistance/support detection")
    tolerance: float = Field(default=0.001, gt=0, le=0.05, description="Tolerance for level touches (0.001 = 0.1%)")
    vol_multiplier: float = Field(default=1.5, ge=1.0, le=5.0, description="Volume exhaustion multiplier")
    atr_period: int = Field(default=14, ge=5, le=50, description="ATR lookback period")
    atr_multiplier: float = Field(default=2.5, ge=1.0, le=10.0, description="ATR trailing stop multiplier")
    min_touches: int = Field(default=3, ge=2, le=10, description="Minimum touches before breakout is valid")


class BreakoutSignalResponse(BaseModel):
    """Response model for a single breakout signal."""

    symbol: str
    direction: int  # 1 = bullish (Buy Call), -1 = bearish (Buy Put)
    direction_label: str  # "BUY_CALL" or "BUY_PUT"
    level_value: float
    touch_count: int
    breakout_price: float
    volume_confirmed: bool
    atr_value: float
    initial_stop_loss: float
    trailing_stop_loss: Optional[float] = None
    confidence_score: float
    timestamp: str = ""


class BreakoutResponse(BaseModel):
    """Response model for breakout scan results."""

    signals: List[BreakoutSignalResponse]
    scan_status: str
    symbols_scanned: int
    config_used: Dict
    message: str


class ConsolidationPatternResponse(BaseModel):
    """Response model for a consolidation pattern."""

    symbol: str
    range_high: float
    range_low: float
    avg_price: float
    candle_count: int
    duration_minutes: int
    is_breakout: bool
    breakout_price: Optional[float] = None


class ConsolidationResponse(BaseModel):
    """Response for consolidation patterns endpoint."""

    patterns: List[ConsolidationPatternResponse]
    count: int


class SignalHistoryResponse(BaseModel):
    """Response model for a historical signal record."""

    id: int
    symbol: str
    signal_type: str
    confidence_score: float
    entry_price: float
    stop_loss: float
    target_price: float
    max_potential_loss: float
    status: str
    ai_quality_rating: Optional[str] = None
    created_at: str


# --------------------------------------------------------------------------
# POST /api/v1/scanner/trend-pullback
# --------------------------------------------------------------------------


@router.post("/scanner/trend-pullback", response_model=TrendPullbackResponse)
async def trigger_trend_pullback_scan(
    request: Optional[TrendPullbackRequest] = None,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """Trigger a trend-pullback scan for the authenticated user's watchlist.

    If the request body provides a watchlist, that is used. Otherwise, the
    user's configured watchlist from settings is used.

    The scan fetches candle data from Redis cache (populated by the market data
    worker) and runs the trend-pullback analysis on each symbol.

    Requirements:
    - 1.1: Trigger backend trend-pullback scan for all symbols in configured watchlist
    """
    # Determine watchlist
    watchlist = None
    if request and request.watchlist:
        watchlist = request.watchlist
    else:
        # Get user's configured watchlist from settings
        settings = (
            db.query(UserSettings)
            .filter(UserSettings.user_id == user_id)
            .first()
        )
        if settings and settings.watchlist:
            watchlist = settings.watchlist

    if not watchlist:
        return TrendPullbackResponse(
            signals=[],
            scan_status="completed",
            symbols_scanned=0,
            message="No symbols in watchlist. Configure watchlist in Settings.",
        )

    # Fetch candle data from Redis for each symbol
    candle_data_by_symbol: Dict[str, List[Dict]] = {}
    for symbol in watchlist:
        candle_key = f"market:{symbol}:candles"
        candle_json = redis.get(candle_key)
        if candle_json:
            try:
                candles = json.loads(candle_json)
                candle_data_by_symbol[symbol] = candles
            except (json.JSONDecodeError, TypeError):
                logger.warning("Failed to parse candle data for %s", symbol)

    # Run the scan
    scanner_service = ScannerService()
    try:
        signals = scanner_service.run_trend_pullback_scan(
            watchlist=watchlist,
            candle_data_by_symbol=candle_data_by_symbol,
        )
    except Exception as e:
        logger.error("Trend pullback scan failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Scan failed: {str(e)}",
        )

    # Convert to response models
    signal_responses = [
        ScanSignalResponse(
            symbol=s.symbol,
            scan_type=s.scan_type.value,
            confidence_score=s.confidence_score,
            entry_price=s.entry_price,
            stop_loss=s.stop_loss,
            target_price=s.target_price,
            max_potential_loss=s.max_potential_loss,
            timestamp=s.timestamp,
            metadata=s.metadata,
        )
        for s in signals
    ]

    # Persist signals to the database for history
    for s in signals:
        db_signal = ScanSignalModel(
            user_id=user_id,
            signal_type=s.scan_type.value,
            symbol=s.symbol,
            confidence_score=s.confidence_score,
            entry_price=s.entry_price,
            stop_loss=s.stop_loss,
            target_price=s.target_price,
            max_potential_loss=s.max_potential_loss,
            status="pending",
            metadata_json=s.metadata,
        )
        db.add(db_signal)

    if signals:
        db.commit()

    message = (
        f"Found {len(signals)} signal(s) from {len(watchlist)} symbols."
        if signals
        else f"No setups found across {len(watchlist)} symbols."
    )

    return TrendPullbackResponse(
        signals=signal_responses,
        scan_status="completed",
        symbols_scanned=len(watchlist),
        message=message,
    )


# --------------------------------------------------------------------------
# POST /api/v1/scanner/breakout
# --------------------------------------------------------------------------


@router.post("/scanner/breakout", response_model=BreakoutResponse)
async def trigger_breakout_scan(
    request: Optional[BreakoutRequest] = None,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """Trigger a multi-touch breakout/breakdown scan using the Price Action Engine.

    Analyzes symbols in the user's watchlist for:
    - Rolling resistance/support zone detection with adaptive tolerance
    - Multi-touch accumulation (3+ touches at a level before breakout)
    - High-volume confirmation (exhaustion volume filter)
    - Compression rules (ascending lows for bullish, descending highs for bearish)

    Each detected signal includes a dynamic ATR-based trailing stop-loss
    that ratchets (can only tighten, never widen).

    Returns signals with confidence scoring, entry prices, and initial
    stop-loss levels ready for execution.
    """
    # Parse config from request or use defaults
    if request:
        engine_config = EngineConfig(
            lookback=request.lookback,
            tolerance=request.tolerance,
            vol_multiplier=request.vol_multiplier,
            atr_period=request.atr_period,
            atr_multiplier=request.atr_multiplier,
            min_touches=request.min_touches,
        )
        watchlist = request.watchlist
    else:
        engine_config = EngineConfig()
        watchlist = None

    # Determine watchlist if not provided
    if not watchlist:
        settings = (
            db.query(UserSettings)
            .filter(UserSettings.user_id == user_id)
            .first()
        )
        if settings and settings.watchlist:
            watchlist = settings.watchlist

    if not watchlist:
        return BreakoutResponse(
            signals=[],
            scan_status="completed",
            symbols_scanned=0,
            config_used=engine_config.model_dump(),
            message="No symbols in watchlist. Configure watchlist in Settings.",
        )

    # Fetch candle data from Redis for each symbol and run analysis
    all_signals: List[BreakoutSignalResponse] = []
    symbols_processed = 0

    for symbol in watchlist:
        candle_key = f"market:{symbol}:candles"
        candle_json = redis.get(candle_key)
        if not candle_json:
            continue

        try:
            candles = json.loads(candle_json)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Failed to parse candle data for %s", symbol)
            continue

        if len(candles) < 10:
            continue

        try:
            # Prepare DataFrame for the engine
            df = prepare_dataframe(candles)

            # Run the detection engine
            df = detect_signals(df, config=engine_config)

            # Extract detected signals
            detected = get_active_signals(df)
            symbols_processed += 1

            for sig in detected:
                # Get the trailing SL for the most recent signal if still active
                trailing_sl = None
                if sig.index < len(df):
                    sl_val = df.iloc[sig.index].get("Dynamic_Trailing_SL")
                    if sl_val is not None and not (isinstance(sl_val, float) and sl_val != sl_val):
                        trailing_sl = round(float(sl_val), 2)

                all_signals.append(BreakoutSignalResponse(
                    symbol=symbol,
                    direction=sig.direction,
                    direction_label="BUY_CALL" if sig.direction == 1 else "BUY_PUT",
                    level_value=sig.level_value,
                    touch_count=sig.touch_count,
                    breakout_price=sig.breakout_price,
                    volume_confirmed=sig.volume_confirmed,
                    atr_value=sig.atr_value,
                    initial_stop_loss=sig.initial_stop_loss,
                    trailing_stop_loss=trailing_sl,
                    confidence_score=sig.confidence_score,
                    timestamp=sig.timestamp,
                ))

        except (ValueError, KeyError) as e:
            logger.warning("Breakout scan failed for %s: %s", symbol, str(e))
            continue

    # Persist high-confidence signals to database
    for sig in all_signals:
        if sig.confidence_score >= 65:
            db_signal = ScanSignalModel(
                user_id=user_id,
                signal_type="multi_touch_breakout",
                symbol=sig.symbol,
                confidence_score=sig.confidence_score,
                entry_price=sig.breakout_price,
                stop_loss=sig.initial_stop_loss,
                target_price=sig.breakout_price + (sig.breakout_price - sig.initial_stop_loss) * 2,  # 2:1 R:R
                max_potential_loss=abs(sig.breakout_price - sig.initial_stop_loss),
                status="pending",
                metadata_json={
                    "direction": sig.direction_label,
                    "touch_count": sig.touch_count,
                    "level_value": sig.level_value,
                    "volume_confirmed": sig.volume_confirmed,
                    "atr_value": sig.atr_value,
                    "trailing_stop": sig.trailing_stop_loss,
                },
            )
            db.add(db_signal)

    if all_signals:
        db.commit()

    # Sort by confidence descending
    all_signals.sort(key=lambda s: s.confidence_score, reverse=True)

    message = (
        f"Found {len(all_signals)} breakout signal(s) from {symbols_processed} symbols."
        if all_signals
        else f"No breakout setups found across {symbols_processed} symbols."
    )

    return BreakoutResponse(
        signals=all_signals,
        scan_status="completed",
        symbols_scanned=symbols_processed,
        config_used=engine_config.model_dump(),
        message=message,
    )


# --------------------------------------------------------------------------
# GET /api/v1/scanner/consolidation
# --------------------------------------------------------------------------


@router.get("/scanner/consolidation", response_model=ConsolidationResponse)
async def get_consolidation_patterns(
    user_id: int = Depends(get_current_user),
    redis: RedisClient = Depends(get_redis),
    db: Session = Depends(get_db),
):
    """Get active consolidation patterns detected on monitored option symbols.

    Reads the latest consolidation data from Redis (populated by the
    consolidation scanner worker). Returns all active patterns for symbols
    in the user's watchlist.

    Requirements:
    - 2.1: Display active consolidation patterns detected on monitored option symbols
    """
    # Get user's watchlist
    settings = (
        db.query(UserSettings)
        .filter(UserSettings.user_id == user_id)
        .first()
    )
    watchlist = settings.watchlist if settings and settings.watchlist else []

    patterns: List[ConsolidationPatternResponse] = []
    scanner_service = ScannerService()

    for symbol in watchlist:
        # Check Redis for cached consolidation patterns
        consolidation_key = f"market:{symbol}:consolidation"
        consolidation_json = redis.get(consolidation_key)

        if consolidation_json:
            try:
                pattern_data = json.loads(consolidation_json)
                patterns.append(
                    ConsolidationPatternResponse(
                        symbol=pattern_data.get("symbol", symbol),
                        range_high=pattern_data["range_high"],
                        range_low=pattern_data["range_low"],
                        avg_price=pattern_data["avg_price"],
                        candle_count=pattern_data["candle_count"],
                        duration_minutes=pattern_data["duration_minutes"],
                        is_breakout=pattern_data.get("is_breakout", False),
                        breakout_price=pattern_data.get("breakout_price"),
                    )
                )
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.warning(
                    "Failed to parse consolidation data for %s: %s", symbol, e
                )

    return ConsolidationResponse(patterns=patterns, count=len(patterns))


# --------------------------------------------------------------------------
# GET /api/v1/scanner/signals
# --------------------------------------------------------------------------


@router.get("/scanner/signals", response_model=List[SignalHistoryResponse])
async def get_scan_signals(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    signal_type: Optional[str] = Query(None, description="Filter by signal type"),
    status_filter: Optional[str] = Query(
        None, alias="status", description="Filter by status"
    ),
):
    """Get scan results and signal history for the authenticated user.

    Returns paginated signal history with optional filtering by type and status.

    Requirements:
    - 1.1: Scan results accessible via API
    """
    offset = (page - 1) * page_size

    query = db.query(ScanSignalModel).filter(ScanSignalModel.user_id == user_id)

    if signal_type:
        query = query.filter(ScanSignalModel.signal_type == signal_type)
    if status_filter:
        query = query.filter(ScanSignalModel.status == status_filter)

    signals = (
        query.order_by(ScanSignalModel.created_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )

    return [
        SignalHistoryResponse(
            id=s.id,
            symbol=s.symbol,
            signal_type=s.signal_type,
            confidence_score=s.confidence_score,
            entry_price=s.entry_price,
            stop_loss=s.stop_loss,
            target_price=s.target_price,
            max_potential_loss=s.max_potential_loss,
            status=s.status,
            ai_quality_rating=s.ai_quality_rating,
            created_at=s.created_at.isoformat() if s.created_at else "",
        )
        for s in signals
    ]
