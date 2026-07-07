"""Live Market Data API endpoint.

Requirements covered:
- 8.9: Authentication required on all endpoints
- 8.10: Live market data accessible via REST

Endpoints:
- GET /api/v1/market-data/live — Get live market index data
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_user, get_db, get_redis
from src.cache.redis_client import RedisClient
from src.services.market_data_service import (
    DataUnavailableError,
    LiveMarketResponse,
    MarketDataService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/market-data", tags=["live-market"])


# ---------------------------------------------------------------------------
# GET /api/v1/market-data/live
# ---------------------------------------------------------------------------


@router.get("/live", response_model=LiveMarketResponse)
async def get_live_market_data(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """Get live market index data (NIFTY 50, SENSEX, BANK NIFTY, NIFTY IT).

    Fetches data from the user's configured data sources in priority order
    with Redis caching (30s TTL). Returns 503 if all sources fail.

    Requires authentication via Bearer token.

    Returns:
        LiveMarketResponse with indices, market_open flag, data_source, and
        last_successful_fetch timestamp.

    Raises:
        HTTPException 503: If all configured data sources are unavailable.
    """
    service = MarketDataService(db=db, redis_client=redis)

    try:
        return service.fetch_live_indices(user_id)
    except DataUnavailableError as e:
        logger.warning("Live market data unavailable for user %d: %s", user_id, e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "detail": "Data unavailable",
                "last_fetch": getattr(e, "last_fetch", None),
            },
        )
