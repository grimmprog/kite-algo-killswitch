"""Seed Test Data API for the Admin Testing UI.

Provides POST /admin/api/seed to populate Redis with realistic mock data
so the dashboard can be tested without running Celery workers or having
a live broker connection.
"""

import json
import logging
import random
from datetime import datetime

from fastapi import APIRouter, Depends

from src.admin.dependencies import get_redis
from src.cache.redis_client import RedisClient
from src.cache.redis_keys import RedisKeys, TTL

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/seed")
async def seed_test_data(
    redis: RedisClient = Depends(get_redis),
):
    """Seed Redis with realistic mock market data and risk metrics.

    Populates:
    - Market data for NIFTY and BANKNIFTY (spot, VWAP, option chain, timestamp)
    - Risk metrics for users 1-3 (pnl, greeks, margin)
    - Market ticks for VWAP calculation
    - Does NOT set kill switch flags (test those manually)

    Returns summary of what was seeded.
    """
    seeded = {}

    # --- Market Data ---
    nifty_spot = round(random.uniform(22000, 23000), 2)
    nifty_vwap = round(nifty_spot + random.uniform(-50, 50), 2)
    banknifty_spot = round(random.uniform(46000, 48000), 2)
    banknifty_vwap = round(banknifty_spot + random.uniform(-100, 100), 2)

    nifty_chain = []
    base_strike = int(nifty_spot / 50) * 50
    for i in range(-5, 6):
        strike = base_strike + i * 50
        nifty_chain.append({
            "strike": float(strike),
            "option_type": "CE",
            "tradingsymbol": f"NIFTY{strike}CE",
            "ltp": round(max(0, nifty_spot - strike + random.uniform(10, 100)), 2),
            "expiry": "2025-01-30",
        })
        nifty_chain.append({
            "strike": float(strike),
            "option_type": "PE",
            "tradingsymbol": f"NIFTY{strike}PE",
            "ltp": round(max(0, strike - nifty_spot + random.uniform(10, 100)), 2),
            "expiry": "2025-01-30",
        })

    nifty_data = {
        "spot": nifty_spot,
        "vwap": nifty_vwap,
        "option_chain": nifty_chain,
        "timestamp": datetime.now().isoformat(),
    }
    banknifty_data = {
        "spot": banknifty_spot,
        "vwap": banknifty_vwap,
        "option_chain": [],
        "timestamp": datetime.now().isoformat(),
    }

    redis.setex(RedisKeys.market_data("NIFTY"), 300, json.dumps(nifty_data))
    redis.setex(RedisKeys.market_data("BANKNIFTY"), 300, json.dumps(banknifty_data))
    seeded["market_data"] = {"NIFTY": nifty_spot, "BANKNIFTY": banknifty_spot}

    # --- Market Ticks (for VWAP) ---
    for symbol, spot in [("NIFTY", nifty_spot), ("BANKNIFTY", banknifty_spot)]:
        ticks_key = RedisKeys.market_ticks(symbol)
        # Clear existing ticks
        redis.delete(ticks_key)
        # Add 20 ticks
        import time
        for i in range(20):
            tick = json.dumps({
                "price": round(spot + random.uniform(-20, 20), 2),
                "volume": random.randint(5000, 50000),
                "timestamp": time.time() - i * 4,
            })
            redis.lpush(ticks_key, tick)
        redis.expire(ticks_key, TTL.MARKET_TICKS)

    seeded["market_ticks"] = {"NIFTY": 20, "BANKNIFTY": 20}

    # --- Risk Metrics for test users ---
    test_users = [
        {"user_id": 1, "capital": 100000},
        {"user_id": 2, "capital": 200000},
        {"user_id": 3, "capital": 50000},
    ]

    for user_info in test_users:
        uid = user_info["user_id"]
        capital = user_info["capital"]
        pnl = round(random.uniform(-capital * 0.03, capital * 0.02), 2)
        margin = round(random.uniform(capital * 0.2, capital * 0.7), 2)

        risk_key = RedisKeys.user_risk(uid)
        redis.hset(risk_key, mapping={
            "pnl": str(pnl),
            "net_delta": str(round(random.uniform(-5, 5), 4)),
            "net_gamma": str(round(random.uniform(-0.5, 0.5), 4)),
            "net_vega": str(round(random.uniform(-100, 100), 2)),
            "margin_used": str(margin),
            "updated_at": datetime.now().isoformat(),
        })

    seeded["risk_metrics"] = [u["user_id"] for u in test_users]

    # --- Recent orders for user 1 (for duplicate detection testing) ---
    orders_key = RedisKeys.user_recent_orders(1)
    redis.delete(orders_key)
    redis.lpush(orders_key, "NIFTY:BUY:50")
    redis.lpush(orders_key, "BANKNIFTY:SELL:25")
    redis.expire(orders_key, TTL.RECENT_ORDERS)
    seeded["recent_orders_user_1"] = ["NIFTY:BUY:50", "BANKNIFTY:SELL:25"]

    logger.info("Test data seeded into Redis: %s", seeded)

    return {
        "status": "success",
        "message": "Test data seeded into Redis",
        "seeded": seeded,
    }


@router.post("/api/seed/clear")
async def clear_test_data(
    redis: RedisClient = Depends(get_redis),
):
    """Clear all seeded test data from Redis."""
    cleared = []

    for symbol in ["NIFTY", "BANKNIFTY"]:
        redis.delete(RedisKeys.market_data(symbol))
        redis.delete(RedisKeys.market_ticks(symbol))
        cleared.append(f"market:{symbol}:data")
        cleared.append(f"market:{symbol}:ticks")

    for uid in range(1, 4):
        redis.delete(RedisKeys.user_risk(uid))
        redis.delete(RedisKeys.user_killswitch(uid))
        redis.delete(RedisKeys.user_recent_orders(uid))
        cleared.append(f"user:{uid}:risk")
        cleared.append(f"user:{uid}:killswitch")
        cleared.append(f"user:{uid}:recent_orders")

    return {"status": "success", "cleared": cleared}
