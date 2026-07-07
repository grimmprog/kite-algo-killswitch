"""Scanner API endpoints for trend-pullback and consolidation scanning.

Requirements covered:
- 1.1: Trigger backend trend-pullback scan for all symbols in watchlist
- 2.1: Display active consolidation patterns on monitored option symbols

Endpoints:
- POST /api/v1/scanner/trend-pullback — Trigger trend pullback scan for user's watchlist
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
