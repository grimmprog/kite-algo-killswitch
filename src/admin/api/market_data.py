"""Market Data API endpoints for the Admin Testing UI.

Provides GET /admin/api/market-data to read cached market data
from Redis for all configured instruments.

Requirements covered:
- 2.1: Fetch spot prices for NIFTY, BANKNIFTY
- 2.2: Fetch VWAP values
- 2.3: Fetch option chain data
- 2.5: Show "No data available" when unavailable
- 2.6: Display last cache update timestamp
- 9.3: GET /admin/api/market-data endpoint
"""

import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends

from src.admin.dependencies import get_redis
from src.cache.redis_client import RedisClient
from src.cache.redis_keys import RedisKeys

logger = logging.getLogger(__name__)

router = APIRouter()

INSTRUMENTS = ["NIFTY", "BANKNIFTY"]


@router.get("/api/market-data")
async def get_market_data(
    redis: RedisClient = Depends(get_redis),
) -> Dict[str, Optional[Dict[str, Any]]]:
    """Fetch cached market data for all configured instruments.

    Reads market data from Redis using RedisKeys.market_data(symbol).
    Returns null for instruments where data is unavailable.

    Returns:
        JSON object mapping each symbol to its market data or null.
    """
    result: Dict[str, Optional[Dict[str, Any]]] = {}

    for symbol in INSTRUMENTS:
        try:
            key = RedisKeys.market_data(symbol)
            raw = redis.get(key)
            if raw:
                result[symbol] = json.loads(raw)
            else:
                result[symbol] = None
        except Exception as e:
            logger.error("Failed to read market data for %s: %s", symbol, e)
            result[symbol] = None

    return result
