"""AI Trading Assistant API endpoints.

Requirements covered:
- 17.1-17.5: AI Trading Assistant API Integration
- 18.1-18.6: AI Signal Quality Analysis
- 19.1-19.6: AI Entry Point Suggestions
- 20.1-20.5: AI Consolidation Breakout Analysis
- 21.1-21.6: AI Exit Recommendations
- 22.1-22.5: AI Market Context Narrative
- 23.1-23.5: AI Trade Review and Learning
- 24.1-24.6: AI Risk Warnings

Endpoints:
- POST /api/v1/ai/analyze-signal        — Request AI signal analysis
- POST /api/v1/ai/entry-suggestion      — Request AI entry suggestion
- POST /api/v1/ai/consolidation-analysis — Request AI consolidation analysis
- GET  /api/v1/ai/exit-recommendation/{position_id} — Get AI exit recommendation
- GET  /api/v1/ai/market-narrative      — Get current market narrative
- POST /api/v1/ai/review-trade          — Request AI trade review
- GET  /api/v1/ai/risk-warnings         — Get active AI risk warnings
- GET  /api/v1/ai/risk-score            — Get daily risk assessment score
"""

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.dependencies import get_db, get_redis, get_current_user
from src.cache.redis_client import RedisClient
from src.database.models.user_settings import UserSettings
from src.services.ai_trading_service import (
    AIProvider,
    AITradingService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["ai"])


# ---------------------------------------------------------------------------
# Request/Response schemas
# ---------------------------------------------------------------------------


class AnalyzeSignalRequest(BaseModel):
    """Request body for AI signal analysis."""

    signal_context: Dict[str, Any] = Field(
        ...,
        description="Signal data: symbol, timeframe, indicators, price_action_pattern, volume_profile, recent_candles",
    )


class EntrySuggestionRequest(BaseModel):
    """Request body for AI entry suggestion."""

    signal_context: Dict[str, Any] = Field(
        ...,
        description="Signal data: symbol, entry_price, stop_loss, target_price, confidence_score",
    )
    market_data: Dict[str, Any] = Field(
        ...,
        description="Market data: bid, ask, vwap, recent_velocity, support_levels, resistance_levels",
    )


class ConsolidationAnalysisRequest(BaseModel):
    """Request body for AI consolidation analysis."""

    pattern: Dict[str, Any] = Field(
        ...,
        description="Consolidation pattern: range_high, range_low, avg_price, candle_count, duration_minutes",
    )
    market_context: Dict[str, Any] = Field(
        ...,
        description="Market context: trend_direction, volume_profile, time_of_day, key_levels, vwap",
    )


class ReviewTradeRequest(BaseModel):
    """Request body for AI trade review."""

    trade: Dict[str, Any] = Field(
        ...,
        description="Completed trade data: symbol, entry_price, exit_price, pnl, quantity, entry_time, exit_time",
    )
    market_history: Dict[str, Any] = Field(
        ...,
        description="Historical market data during the trade period",
    )


class AIAnalysisResponse(BaseModel):
    """Generic AI analysis response."""

    success: bool
    data: Dict[str, Any] = Field(default_factory=dict)
    message: str = ""


class AIRiskScoreResponse(BaseModel):
    """Response for the daily risk score endpoint."""

    success: bool
    risk_score: float = 0.0
    risk_level: str = "low"  # low, medium, high, critical
    factors: List[str] = Field(default_factory=list)
    message: str = ""


# ---------------------------------------------------------------------------
# Helper: get AI service for user
# ---------------------------------------------------------------------------


def _get_ai_service(
    user_id: int, db: Session
) -> Optional[AITradingService]:
    """Build an AITradingService from user's AI settings.

    Returns None if AI is not configured (no provider or key).
    """
    settings = (
        db.query(UserSettings)
        .filter(UserSettings.user_id == user_id)
        .first()
    )

    if not settings:
        return None

    provider_str = settings.ai_provider or "gemini"
    try:
        provider = AIProvider(provider_str)
    except ValueError:
        provider = AIProvider.GEMINI

    # API key comes from environment (keyed by provider)
    import os

    api_key = os.environ.get(f"AI_{provider_str.upper()}_API_KEY", "")
    if not api_key:
        # Fallback to generic key
        api_key = os.environ.get("AI_API_KEY", "")

    if not api_key:
        return None

    return AITradingService(provider=provider, api_key=api_key)


def _ai_unavailable_response(message: str = "AI analysis unavailable") -> AIAnalysisResponse:
    """Return a graceful degradation response (200, not 500)."""
    return AIAnalysisResponse(
        success=False,
        data={},
        message=message,
    )


# ---------------------------------------------------------------------------
# POST /api/v1/ai/analyze-signal
# ---------------------------------------------------------------------------


@router.post("/ai/analyze-signal", response_model=AIAnalysisResponse)
async def analyze_signal(
    request: AnalyzeSignalRequest,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Request AI signal quality analysis.

    Sends signal context to AI for quality evaluation. Returns quality rating,
    warnings, and explanation. Gracefully degrades if AI is unavailable.

    Requirements: 18.1-18.6
    """
    ai_service = _get_ai_service(user_id, db)
    if not ai_service:
        return _ai_unavailable_response(
            "AI not configured. Set AI provider and API key in Settings."
        )

    try:
        result = ai_service.analyze_signal(request.signal_context)
    except Exception as e:
        logger.error("AI analyze_signal error for user %d: %s", user_id, str(e))
        return _ai_unavailable_response()

    # Check for graceful degradation from the service itself
    if isinstance(result, dict) and result.get("error"):
        return AIAnalysisResponse(
            success=False,
            data=result,
            message=result.get("message", "AI analysis unavailable"),
        )

    return AIAnalysisResponse(
        success=True,
        data=result,
        message="Signal analysis complete",
    )


# ---------------------------------------------------------------------------
# POST /api/v1/ai/entry-suggestion
# ---------------------------------------------------------------------------


@router.post("/ai/entry-suggestion", response_model=AIAnalysisResponse)
async def entry_suggestion(
    request: EntrySuggestionRequest,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Request AI optimal entry point suggestion.

    Analyzes bid/ask spread, price velocity, support/resistance proximity,
    and VWAP distance to suggest entry timing, SL placement, and R:R.

    Requirements: 19.1-19.6
    """
    ai_service = _get_ai_service(user_id, db)
    if not ai_service:
        return _ai_unavailable_response(
            "AI not configured. Set AI provider and API key in Settings."
        )

    try:
        result = ai_service.suggest_entry(
            request.signal_context, request.market_data
        )
    except Exception as e:
        logger.error("AI suggest_entry error for user %d: %s", user_id, str(e))
        return _ai_unavailable_response()

    if isinstance(result, dict) and result.get("error"):
        return AIAnalysisResponse(
            success=False,
            data=result,
            message=result.get("message", "AI analysis unavailable"),
        )

    return AIAnalysisResponse(
        success=True,
        data=result,
        message="Entry suggestion complete",
    )


# ---------------------------------------------------------------------------
# POST /api/v1/ai/consolidation-analysis
# ---------------------------------------------------------------------------


@router.post("/ai/consolidation-analysis", response_model=AIAnalysisResponse)
async def consolidation_analysis(
    request: ConsolidationAnalysisRequest,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Request AI consolidation breakout analysis.

    Analyzes consolidation pattern for breakout probability, direction,
    expected move magnitude, and false breakout warnings.

    Requirements: 20.1-20.5
    """
    ai_service = _get_ai_service(user_id, db)
    if not ai_service:
        return _ai_unavailable_response(
            "AI not configured. Set AI provider and API key in Settings."
        )

    try:
        result = ai_service.analyze_consolidation(
            request.pattern, request.market_context
        )
    except Exception as e:
        logger.error(
            "AI analyze_consolidation error for user %d: %s", user_id, str(e)
        )
        return _ai_unavailable_response()

    if isinstance(result, dict) and result.get("error"):
        return AIAnalysisResponse(
            success=False,
            data=result,
            message=result.get("message", "AI analysis unavailable"),
        )

    return AIAnalysisResponse(
        success=True,
        data=result,
        message="Consolidation analysis complete",
    )


# ---------------------------------------------------------------------------
# GET /api/v1/ai/exit-recommendation/{position_id}
# ---------------------------------------------------------------------------


@router.get(
    "/ai/exit-recommendation/{position_id}", response_model=AIAnalysisResponse
)
async def get_exit_recommendation(
    position_id: int,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """Get AI exit recommendation for an open position.

    Evaluates current market conditions and position state to recommend
    hold, tighten stop, book partial, or exit now.

    Requirements: 21.1-21.6
    """
    ai_service = _get_ai_service(user_id, db)
    if not ai_service:
        return _ai_unavailable_response(
            "AI not configured. Set AI provider and API key in Settings."
        )

    # Fetch position data from Redis cache
    position_key = f"position_monitor:{user_id}:{position_id}"
    position_json = redis.get(position_key)

    if not position_json:
        return AIAnalysisResponse(
            success=False,
            data={},
            message=f"Position {position_id} not found or not being monitored",
        )

    try:
        position_data = json.loads(position_json)
    except (json.JSONDecodeError, TypeError):
        return AIAnalysisResponse(
            success=False,
            data={},
            message="Failed to parse position data",
        )

    # Fetch market data from Redis
    symbol = position_data.get("symbol", "")
    market_key = f"market:{symbol}:data"
    market_json = redis.get(market_key)
    market_data: Dict[str, Any] = {}
    if market_json:
        try:
            market_data = json.loads(market_json)
        except (json.JSONDecodeError, TypeError):
            pass

    try:
        result = ai_service.evaluate_exit(position_data, market_data)
    except Exception as e:
        logger.error(
            "AI evaluate_exit error for user %d, position %d: %s",
            user_id,
            position_id,
            str(e),
        )
        return _ai_unavailable_response()

    if isinstance(result, dict) and result.get("error"):
        return AIAnalysisResponse(
            success=False,
            data=result,
            message=result.get("message", "AI analysis unavailable"),
        )

    return AIAnalysisResponse(
        success=True,
        data=result,
        message="Exit recommendation ready",
    )


# ---------------------------------------------------------------------------
# GET /api/v1/ai/market-narrative
# ---------------------------------------------------------------------------


@router.get("/ai/market-narrative", response_model=AIAnalysisResponse)
async def get_market_narrative(
    session_type: Optional[str] = Query(
        default=None,
        description="Session type: morning_brief, mid_morning, lunch, afternoon",
    ),
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """Get AI-generated market narrative for the current session.

    Generates plain-English market commentary including key points, bias,
    expected range, and key support/resistance levels.

    Requirements: 22.1-22.5
    """
    ai_service = _get_ai_service(user_id, db)
    if not ai_service:
        return _ai_unavailable_response(
            "AI not configured. Set AI provider and API key in Settings."
        )

    # Determine session type from time if not provided
    if not session_type:
        from datetime import datetime
        import pytz

        ist = pytz.timezone("Asia/Kolkata")
        now = datetime.now(ist)
        hour = now.hour
        minute = now.minute
        current_time_min = hour * 60 + minute

        if current_time_min < 10 * 60 + 30:
            session_type = "morning_brief"
        elif current_time_min < 12 * 60 + 30:
            session_type = "mid_morning"
        elif current_time_min < 14 * 60:
            session_type = "lunch"
        else:
            session_type = "afternoon"

    # Fetch market data from Redis for context
    market_data: Dict[str, Any] = {}
    narrative_cache_key = f"ai:narrative:{session_type}"
    cached = redis.get(narrative_cache_key)
    if cached:
        try:
            cached_data = json.loads(cached)
            return AIAnalysisResponse(
                success=True,
                data=cached_data,
                message=f"Market narrative ({session_type})",
            )
        except (json.JSONDecodeError, TypeError):
            pass

    # Gather market data from Redis
    for symbol in ["NIFTY 50", "BANK NIFTY", "SENSEX"]:
        key = f"market:{symbol}:data"
        data_json = redis.get(key)
        if data_json:
            try:
                market_data[symbol] = json.loads(data_json)
            except (json.JSONDecodeError, TypeError):
                pass

    try:
        result = ai_service.generate_narrative(session_type, market_data)
    except Exception as e:
        logger.error(
            "AI generate_narrative error for user %d: %s", user_id, str(e)
        )
        return _ai_unavailable_response()

    if isinstance(result, dict) and result.get("error"):
        return AIAnalysisResponse(
            success=False,
            data=result,
            message=result.get("message", "AI analysis unavailable"),
        )

    # Cache narrative for 15 minutes
    try:
        redis.setex(narrative_cache_key, 900, json.dumps(result))
    except Exception:
        pass  # Non-critical caching failure

    return AIAnalysisResponse(
        success=True,
        data=result,
        message=f"Market narrative ({session_type})",
    )


# ---------------------------------------------------------------------------
# POST /api/v1/ai/review-trade
# ---------------------------------------------------------------------------


@router.post("/ai/review-trade", response_model=AIAnalysisResponse)
async def review_trade(
    request: ReviewTradeRequest,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Request AI review of a completed trade.

    Provides grade (A-F), feedback on entry/exit/sizing/risk, optimal
    comparison, and identified patterns for improvement.

    Requirements: 23.1-23.5
    """
    ai_service = _get_ai_service(user_id, db)
    if not ai_service:
        return _ai_unavailable_response(
            "AI not configured. Set AI provider and API key in Settings."
        )

    try:
        result = ai_service.review_trade(request.trade, request.market_history)
    except Exception as e:
        logger.error("AI review_trade error for user %d: %s", user_id, str(e))
        return _ai_unavailable_response()

    if isinstance(result, dict) and result.get("error"):
        return AIAnalysisResponse(
            success=False,
            data=result,
            message=result.get("message", "AI analysis unavailable"),
        )

    return AIAnalysisResponse(
        success=True,
        data=result,
        message="Trade review complete",
    )


# ---------------------------------------------------------------------------
# GET /api/v1/ai/risk-warnings
# ---------------------------------------------------------------------------


@router.get("/ai/risk-warnings", response_model=AIAnalysisResponse)
async def get_risk_warnings(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """Get active AI risk warnings for the authenticated user.

    Detects behavioral anomalies (revenge trading, consecutive losses)
    and market condition risks. Returns active warnings with severity.

    Requirements: 24.1-24.6
    """
    ai_service = _get_ai_service(user_id, db)
    if not ai_service:
        return _ai_unavailable_response(
            "AI not configured. Set AI provider and API key in Settings."
        )

    # Build user state from Redis (recent trades, current positions)
    user_state: Dict[str, Any] = {}
    user_state_key = f"user:{user_id}:trading_state"
    state_json = redis.get(user_state_key)
    if state_json:
        try:
            user_state = json.loads(state_json)
        except (json.JSONDecodeError, TypeError):
            pass

    # Fetch market data
    market_data: Dict[str, Any] = {}
    market_key = f"market:overview"
    market_json = redis.get(market_key)
    if market_json:
        try:
            market_data = json.loads(market_json)
        except (json.JSONDecodeError, TypeError):
            pass

    try:
        result = ai_service.detect_risk_anomalies(user_state, market_data)
    except Exception as e:
        logger.error(
            "AI detect_risk_anomalies error for user %d: %s", user_id, str(e)
        )
        return _ai_unavailable_response()

    if isinstance(result, dict) and result.get("error"):
        return AIAnalysisResponse(
            success=False,
            data=result,
            message=result.get("message", "AI analysis unavailable"),
        )

    return AIAnalysisResponse(
        success=True,
        data=result,
        message="Risk warnings retrieved",
    )


# ---------------------------------------------------------------------------
# GET /api/v1/ai/risk-score
# ---------------------------------------------------------------------------


@router.get("/ai/risk-score", response_model=AIRiskScoreResponse)
async def get_risk_score(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """Get daily risk assessment score for the authenticated user.

    Computes a composite risk score (0-100) based on:
    - Number of trades today
    - Current P&L vs thresholds
    - Market volatility (VIX)
    - Behavioral patterns (consecutive losses, trade frequency)

    Returns a score, risk level, and contributing factors.

    Requirements: 24.1-24.6
    """
    # Try cached risk score first
    risk_score_key = f"ai:risk_score:{user_id}"
    cached = redis.get(risk_score_key)
    if cached:
        try:
            cached_data = json.loads(cached)
            return AIRiskScoreResponse(**cached_data)
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    # Gather data for risk score computation
    user_state: Dict[str, Any] = {}
    user_state_key = f"user:{user_id}:trading_state"
    state_json = redis.get(user_state_key)
    if state_json:
        try:
            user_state = json.loads(state_json)
        except (json.JSONDecodeError, TypeError):
            pass

    # Compute risk score from available data
    risk_score = 0.0
    factors: List[str] = []

    # Factor 1: Trades today
    trades_today = user_state.get("trades_today", 0)
    if trades_today >= 8:
        risk_score += 25.0
        factors.append("High trade count today")
    elif trades_today >= 5:
        risk_score += 15.0
        factors.append("Elevated trade count")

    # Factor 2: Consecutive losses
    consecutive_losses = user_state.get("consecutive_losses", 0)
    if consecutive_losses >= 3:
        risk_score += 30.0
        factors.append(f"{consecutive_losses} consecutive losses — consider a break")
    elif consecutive_losses >= 2:
        risk_score += 15.0
        factors.append("Multiple consecutive losses")

    # Factor 3: P&L proximity to thresholds
    pnl_pct_of_threshold = user_state.get("pnl_pct_of_threshold", 0)
    if pnl_pct_of_threshold >= 80:
        risk_score += 25.0
        factors.append("P&L approaching kill switch threshold")
    elif pnl_pct_of_threshold >= 60:
        risk_score += 10.0
        factors.append("P&L moving toward threshold")

    # Factor 4: Market volatility
    vix_key = "market:VIX"
    vix_json = redis.get(vix_key)
    if vix_json:
        try:
            vix_data = json.loads(vix_json)
            vix_value = vix_data.get("value", 15)
            if vix_value > 25:
                risk_score += 20.0
                factors.append("High market volatility (VIX elevated)")
            elif vix_value > 20:
                risk_score += 10.0
                factors.append("Elevated market volatility")
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    # Clamp score to 0-100
    risk_score = max(0.0, min(100.0, risk_score))

    # Determine risk level
    if risk_score >= 75:
        risk_level = "critical"
    elif risk_score >= 50:
        risk_level = "high"
    elif risk_score >= 25:
        risk_level = "medium"
    else:
        risk_level = "low"

    if not factors:
        factors.append("No elevated risk factors detected")

    response = AIRiskScoreResponse(
        success=True,
        risk_score=round(risk_score, 1),
        risk_level=risk_level,
        factors=factors,
        message=f"Daily risk level: {risk_level}",
    )

    # Cache for 60 seconds
    try:
        redis.setex(
            risk_score_key,
            60,
            json.dumps(response.model_dump()),
        )
    except Exception:
        pass

    return response
