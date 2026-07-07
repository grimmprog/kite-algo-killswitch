"""Seed Redis with index market data for testing."""
import redis
import json

r = redis.Redis()

data = {
    "NIFTY 50": {
        "spot": 24370.45,
        "change_1h_pct": -0.15,
        "change_daily_pct": -0.22,
        "momentum_score": 45,
        "volume_score": 60,
        "trend_direction": "bearish",
    },
    "SENSEX": {
        "spot": 78212.80,
        "change_1h_pct": -0.05,
        "change_daily_pct": -0.09,
        "momentum_score": 48,
        "volume_score": 55,
        "trend_direction": "neutral",
    },
    "BANK NIFTY": {
        "spot": 58154.15,
        "change_1h_pct": -0.12,
        "change_daily_pct": -0.19,
        "momentum_score": 42,
        "volume_score": 50,
        "trend_direction": "bearish",
    },
}

for symbol, d in data.items():
    key = f"market:{symbol}:data"
    r.set(key, json.dumps(d))
    print(f"Set {key}")

print("Done - Redis seeded")
