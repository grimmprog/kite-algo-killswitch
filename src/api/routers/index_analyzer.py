"""Index Analyzer API endpoints for index comparison and trade recommendations.

Requirements covered:
- 3.1: Fetch and display comparison data for SENSEX, NIFTY 50, and BANK NIFTY
- 3.3: Recommend the best index to trade based on highest composite score

Endpoints:
- GET /api/v1/analysis/indices        — Get index comparison data with scoring
- GET /api/v1/analysis/recommendation — Get trade recommendation (best index, CE/PE, strike)
"""

import json
import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.dependencies import get_db, get_redis, get_current_user
from src.cache.redis_client import RedisClient
from src.services.index_analyzer_service import (
    IndexAnalyzerService,
    IndexMetrics,
    IndexRecommendation,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["analysis"])

# Indices we analyze
TRACKED_INDICES = ["SENSEX", "NIFTY 50", "BANK NIFTY"]


# --- Response schemas ---


class IndexMetricsResponse(BaseModel):
    """Response model for a single index's metrics."""

    symbol: str
    current_price: float
    change_1h_pct: float
    change_daily_pct: float
    momentum_score: float
    volume_score: float
    trend_direction: str
    composite_score: float
    data_available: bool


class IndicesResponse(BaseModel):
    """Response for the index comparison endpoint."""

    indices: List[IndexMetricsResponse]
    count: int


class RecommendationResponse(BaseModel):
    """Response model for the trade recommendation endpoint."""

    best_index: str
    option_type: str
    recommended_strike: float
    strike_step: int
    reasoning: str


# --------------------------------------------------------------------------
# Helper functions
# --------------------------------------------------------------------------


def _fetch_index_market_data(
    redis: RedisClient,
) -> Dict[str, dict]:
    """Fetch raw market data for all tracked indices from Redis.

    Args:
        redis: The Redis client instance.

    Returns:
        Dict mapping index symbol to raw market data dict.
    """
    market_data: Dict[str, dict] = {}

    for symbol in TRACKED_INDICES:
        redis_key = f"market:{symbol}:data"
        raw_data = redis.get(redis_key)

        if raw_data:
            try:
                data = json.loads(raw_data)
                market_data[symbol] = {
                    "current_price": data.get("spot", 0.0),
                    "change_1h_pct": data.get("change_1h_pct", 0.0),
                    "change_daily_pct": data.get("change_daily_pct", 0.0),
                    "momentum_score": data.get("momentum_score", 0.0),
                    "volume_score": data.get("volume_score", 0.0),
                    "trend_direction": data.get("trend_direction", "neutral"),
                    "data_available": True,
                }
            except (json.JSONDecodeError, TypeError):
                logger.warning("Failed to parse market data for %s", symbol)
                market_data[symbol] = {"data_available": False}
        else:
            # No data available for this index
            market_data[symbol] = {"data_available": False}

    return market_data


# --------------------------------------------------------------------------
# GET /api/v1/analysis/indices
# --------------------------------------------------------------------------


@router.get("/analysis/indices", response_model=IndicesResponse)
async def get_index_analysis(
    user_id: int = Depends(get_current_user),
    redis: RedisClient = Depends(get_redis),
):
    """Get index comparison data for SENSEX, NIFTY 50, and BANK NIFTY.

    Fetches market data from Redis, computes momentum/volume/trend scores
    and composite scoring for each index.

    Requirements:
    - 3.1: Fetch and display comparison data for SENSEX, NIFTY 50, and BANK NIFTY
    - 3.2: Display per index: current price, 1h/daily change, momentum/volume/trend
            scores, composite score
    """
    market_data = _fetch_index_market_data(redis)

    analyzer = IndexAnalyzerService()
    metrics_list = analyzer.analyze_indices(market_data)

    responses = [
        IndexMetricsResponse(
            symbol=m.symbol,
            current_price=m.current_price,
            change_1h_pct=m.change_1h_pct,
            change_daily_pct=m.change_daily_pct,
            momentum_score=m.momentum_score,
            volume_score=m.volume_score,
            trend_direction=m.trend_direction,
            composite_score=m.composite_score,
            data_available=m.data_available,
        )
        for m in metrics_list
    ]

    return IndicesResponse(indices=responses, count=len(responses))


# --------------------------------------------------------------------------
# GET /api/v1/analysis/recommendation
# --------------------------------------------------------------------------


@router.get("/analysis/recommendation", response_model=Optional[RecommendationResponse])
async def get_trade_recommendation(
    user_id: int = Depends(get_current_user),
    redis: RedisClient = Depends(get_redis),
):
    """Get trade recommendation based on index analysis.

    Selects the best index to trade based on composite scores, suggests
    CE/PE based on trend direction, and calculates nearest ATM strike.

    Requirements:
    - 3.3: Recommend best index to trade based on highest composite score
    - 3.4: Suggest CE or PE based on trend direction
    - 3.5: Recommend nearest ATM strike price
    - 3.6: Handle data unavailability (rank only available indices)
    """
    market_data = _fetch_index_market_data(redis)

    analyzer = IndexAnalyzerService()
    metrics_list = analyzer.analyze_indices(market_data)
    recommendation = analyzer.recommend_trade(metrics_list)

    if recommendation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No index data available to generate a recommendation. Market data may be unavailable.",
        )

    return RecommendationResponse(
        best_index=recommendation.best_index,
        option_type=recommendation.option_type,
        recommended_strike=recommendation.recommended_strike,
        strike_step=recommendation.strike_step,
        reasoning=recommendation.reasoning,
    )
