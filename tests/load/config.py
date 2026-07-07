"""Load test configuration for the Multi-User Web Trading Platform.

Defines test parameters based on performance requirements:
- 2.1.1: Support 100 concurrent users
- 2.1.2: API responses within 500ms (95th percentile)
- 2.1.9: 50 simultaneous order executions within 10 seconds
- 2.1.10: Dashboard requests from 100 users every 5 seconds
"""

import os

# ---------------------------------------------------------------------------
# Host configuration
# ---------------------------------------------------------------------------

# Base URL of the platform API server
HOST = os.environ.get("LOAD_TEST_HOST", "http://localhost:8000")

# ---------------------------------------------------------------------------
# User simulation parameters
# ---------------------------------------------------------------------------

# Total concurrent users to simulate (Requirement 2.1.1)
CONCURRENT_USERS = int(os.environ.get("LOAD_TEST_USERS", "100"))

# Rate at which new users are spawned (users per second)
SPAWN_RATE = int(os.environ.get("LOAD_TEST_SPAWN_RATE", "10"))

# Total run time for the load test (seconds)
RUN_TIME = os.environ.get("LOAD_TEST_RUN_TIME", "120s")

# ---------------------------------------------------------------------------
# Scenario-specific parameters
# ---------------------------------------------------------------------------

# Dashboard scenario: users poll dashboard every 5 seconds (Requirement 2.1.10)
DASHBOARD_MIN_WAIT_MS = 4000  # 4 seconds minimum between requests
DASHBOARD_MAX_WAIT_MS = 6000  # 6 seconds maximum between requests

# Order execution scenario: burst of 50 simultaneous orders (Requirement 2.1.9)
ORDER_BURST_SIZE = 50
ORDER_EXECUTION_TIMEOUT_S = 10  # Must complete within 10 seconds

# Risk monitoring scenario: 100 users checking risk metrics
RISK_MIN_WAIT_MS = 2000  # Check risk every 2-3 seconds (matches risk engine cycle)
RISK_MAX_WAIT_MS = 3000

# General API browsing (positions, trade history)
BROWSE_MIN_WAIT_MS = 3000
BROWSE_MAX_WAIT_MS = 8000

# ---------------------------------------------------------------------------
# Performance thresholds (Requirement 2.1.2)
# ---------------------------------------------------------------------------

# 95th percentile response time target in milliseconds
P95_RESPONSE_TIME_MS = 500

# Maximum acceptable failure rate (percentage)
MAX_FAILURE_RATE_PCT = 1.0

# ---------------------------------------------------------------------------
# Authentication credentials for load test users
# ---------------------------------------------------------------------------

# Test user template: load test creates users test_user_0..test_user_N
TEST_USER_EMAIL_TEMPLATE = os.environ.get(
    "LOAD_TEST_USER_EMAIL", "loadtest_user_{n}@test.com"
)
TEST_USER_PASSWORD = os.environ.get("LOAD_TEST_USER_PASSWORD", "LoadTest123!")

# ---------------------------------------------------------------------------
# Trade execution parameters
# ---------------------------------------------------------------------------

# Symbols used in load test trade requests
TEST_SYMBOLS = [
    {"symbol": "NIFTY23DEC21000CE", "exchange": "NFO"},
    {"symbol": "NIFTY23DEC21000PE", "exchange": "NFO"},
    {"symbol": "BANKNIFTY23DEC45000CE", "exchange": "NFO"},
    {"symbol": "BANKNIFTY23DEC45000PE", "exchange": "NFO"},
    {"symbol": "RELIANCE", "exchange": "NSE"},
    {"symbol": "INFY", "exchange": "NSE"},
    {"symbol": "TCS", "exchange": "NSE"},
    {"symbol": "HDFCBANK", "exchange": "NSE"},
]

# Default trade quantity range for random order generation
TRADE_QTY_MIN = 1
TRADE_QTY_MAX = 50

# Price range (used for limit orders in load testing)
TRADE_PRICE_MIN = 50.0
TRADE_PRICE_MAX = 500.0

# ---------------------------------------------------------------------------
# User weight distribution (controls scenario mix)
# ---------------------------------------------------------------------------

# Weights determine how many users are assigned to each scenario.
# Higher weight = more users running that scenario.
USER_WEIGHTS = {
    "dashboard": 5,      # Most users just watch the dashboard
    "order_execution": 2,  # Some users actively trade
    "risk_monitoring": 3,  # Users checking risk metrics frequently
}
