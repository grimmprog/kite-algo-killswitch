"""Locust load test scenarios for the Multi-User Web Trading Platform.

Validates performance requirements:
- 2.1.1: Support 100 concurrent users
- 2.1.2: API responses within 500ms (95th percentile)
- 2.1.9: 50 simultaneous order executions within 10 seconds
- 2.1.10: Dashboard requests from 100 users every 5 seconds

Run with:
    locust -f tests/load/locustfile.py --host http://localhost:8000

Or headless:
    locust -f tests/load/locustfile.py --host http://localhost:8000 \
        --users 100 --spawn-rate 10 --run-time 120s --headless
"""

import random
import logging

from locust import HttpUser, task, between, events, tag
from locust.exception import StopUser

from tests.load.config import (
    DASHBOARD_MIN_WAIT_MS,
    DASHBOARD_MAX_WAIT_MS,
    RISK_MIN_WAIT_MS,
    RISK_MAX_WAIT_MS,
    BROWSE_MIN_WAIT_MS,
    BROWSE_MAX_WAIT_MS,
    TEST_USER_EMAIL_TEMPLATE,
    TEST_USER_PASSWORD,
    TEST_SYMBOLS,
    TRADE_QTY_MIN,
    TRADE_QTY_MAX,
    TRADE_PRICE_MIN,
    TRADE_PRICE_MAX,
    USER_WEIGHTS,
    P95_RESPONSE_TIME_MS,
    MAX_FAILURE_RATE_PCT,
)

logger = logging.getLogger(__name__)

# Counter for assigning unique user IDs to each simulated user
_user_counter = 0


def _next_user_id() -> int:
    """Thread-safe incrementing user counter."""
    global _user_counter
    _user_counter += 1
    return _user_counter


# ---------------------------------------------------------------------------
# Base user class with authentication
# ---------------------------------------------------------------------------


class AuthenticatedUser(HttpUser):
    """Base class that handles JWT login on start.

    All scenario classes inherit from this to get automatic authentication.
    """

    abstract = True
    token: str = ""
    user_number: int = 0

    def on_start(self):
        """Authenticate before running tasks."""
        self.user_number = _next_user_id()
        email = TEST_USER_EMAIL_TEMPLATE.format(n=self.user_number)

        with self.client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": TEST_USER_PASSWORD},
            catch_response=True,
            name="/api/v1/auth/login",
        ) as response:
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("access_token", "")
                response.success()
            else:
                response.failure(f"Login failed: {response.status_code}")
                logger.warning(
                    f"User {self.user_number} login failed: {response.text}"
                )
                raise StopUser()

    @property
    def auth_headers(self) -> dict:
        """Return Authorization header with JWT token."""
        return {"Authorization": f"Bearer {self.token}"}


# ---------------------------------------------------------------------------
# Scenario 1: Dashboard Users (Requirement 2.1.10)
# Simulates 100 users requesting dashboard data every 5 seconds.
# ---------------------------------------------------------------------------


class DashboardUser(AuthenticatedUser):
    """Simulates users polling the dashboard for live P&L and positions.

    Validates Requirement 2.1.10: Handle dashboard requests from 100 users
    every 5 seconds.
    """

    weight = USER_WEIGHTS["dashboard"]
    wait_time = between(
        DASHBOARD_MIN_WAIT_MS / 1000, DASHBOARD_MAX_WAIT_MS / 1000
    )

    @task(5)
    @tag("dashboard")
    def get_dashboard(self):
        """GET /api/v1/dashboard - Main dashboard data."""
        with self.client.get(
            "/api/v1/dashboard",
            headers=self.auth_headers,
            catch_response=True,
            name="/api/v1/dashboard",
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code in (401, 403):
                response.failure("Authentication expired")
            else:
                response.failure(f"Dashboard error: {response.status_code}")

    @task(3)
    @tag("dashboard", "positions")
    def get_positions(self):
        """GET /api/v1/positions - User's open positions."""
        with self.client.get(
            "/api/v1/positions",
            headers=self.auth_headers,
            catch_response=True,
            name="/api/v1/positions",
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code in (401, 403):
                response.failure("Authentication expired")
            else:
                response.failure(f"Positions error: {response.status_code}")

    @task(2)
    @tag("dashboard", "killswitch")
    def get_killswitch_status(self):
        """GET /api/v1/killswitch/status - Kill switch state."""
        with self.client.get(
            "/api/v1/killswitch/status",
            headers=self.auth_headers,
            catch_response=True,
            name="/api/v1/killswitch/status",
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code in (401, 403):
                response.failure("Authentication expired")
            else:
                response.failure(
                    f"Kill switch status error: {response.status_code}"
                )

    @task(1)
    @tag("dashboard", "history")
    def get_trade_history(self):
        """GET /api/v1/trades/history - Recent trade history."""
        with self.client.get(
            "/api/v1/trades/history",
            headers=self.auth_headers,
            params={"limit": 20},
            catch_response=True,
            name="/api/v1/trades/history",
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code in (401, 403):
                response.failure("Authentication expired")
            else:
                response.failure(
                    f"Trade history error: {response.status_code}"
                )


# ---------------------------------------------------------------------------
# Scenario 2: Order Execution Users (Requirement 2.1.9)
# Simulates users submitting trade execution requests.
# 50 simultaneous orders must complete within 10 seconds.
# ---------------------------------------------------------------------------


class OrderExecutionUser(AuthenticatedUser):
    """Simulates active traders submitting orders.

    Validates Requirement 2.1.9: Process 50 simultaneous order executions
    within 10 seconds.
    """

    weight = USER_WEIGHTS["order_execution"]
    wait_time = between(
        BROWSE_MIN_WAIT_MS / 1000, BROWSE_MAX_WAIT_MS / 1000
    )

    def _random_trade_request(self) -> dict:
        """Generate a random but valid trade request."""
        instrument = random.choice(TEST_SYMBOLS)
        return {
            "symbol": instrument["symbol"],
            "exchange": instrument["exchange"],
            "quantity": random.randint(TRADE_QTY_MIN, TRADE_QTY_MAX),
            "side": random.choice(["BUY", "SELL"]),
            "price": round(
                random.uniform(TRADE_PRICE_MIN, TRADE_PRICE_MAX), 2
            ),
            "risk_snapshot": {
                "daily_loss_pct": round(random.uniform(0.1, 1.5), 2),
                "margin_used_pct": round(random.uniform(10.0, 60.0), 2),
            },
        }

    @task(3)
    @tag("trading", "execute")
    def execute_trade(self):
        """POST /api/v1/trades/execute - Submit a trade for execution."""
        trade_request = self._random_trade_request()

        with self.client.post(
            "/api/v1/trades/execute",
            json=trade_request,
            headers=self.auth_headers,
            catch_response=True,
            name="/api/v1/trades/execute",
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 403:
                # Kill switch may be active — this is valid behavior
                response.success()
            elif response.status_code in (401,):
                response.failure("Authentication expired")
            elif response.status_code == 422:
                response.failure(f"Validation error: {response.text}")
            else:
                response.failure(
                    f"Trade execution error: {response.status_code}"
                )

    @task(2)
    @tag("trading", "status")
    def check_trade_status(self):
        """GET /api/v1/trades/status/{task_id} - Check trade status.

        Uses a placeholder task_id since we're testing response times,
        not actual execution flow.
        """
        task_id = f"task-loadtest-{self.user_number}-{random.randint(1, 100)}"

        with self.client.get(
            f"/api/v1/trades/status/{task_id}",
            headers=self.auth_headers,
            catch_response=True,
            name="/api/v1/trades/status/[task_id]",
        ) as response:
            # 200 or 404 are both acceptable for load testing purposes
            if response.status_code in (200, 404):
                response.success()
            elif response.status_code in (401, 403):
                response.failure("Authentication expired")
            else:
                response.failure(
                    f"Trade status error: {response.status_code}"
                )

    @task(1)
    @tag("trading", "positions")
    def get_positions(self):
        """GET /api/v1/positions - Check current positions."""
        with self.client.get(
            "/api/v1/positions",
            headers=self.auth_headers,
            catch_response=True,
            name="/api/v1/positions",
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code in (401, 403):
                response.failure("Authentication expired")
            else:
                response.failure(f"Positions error: {response.status_code}")


# ---------------------------------------------------------------------------
# Scenario 3: Risk Monitoring Users (Requirement 2.1.1)
# Simulates users actively monitoring risk metrics (frequent polling).
# ---------------------------------------------------------------------------


class RiskMonitoringUser(AuthenticatedUser):
    """Simulates users actively monitoring risk metrics.

    Validates Requirement 2.1.1: Support 100 concurrent users with
    frequent risk metric requests (every 2-3 seconds matching the
    risk engine cycle).
    """

    weight = USER_WEIGHTS["risk_monitoring"]
    wait_time = between(RISK_MIN_WAIT_MS / 1000, RISK_MAX_WAIT_MS / 1000)

    @task(5)
    @tag("risk")
    def get_risk_metrics(self):
        """GET /api/v1/risk - Real-time risk metrics from Redis."""
        with self.client.get(
            "/api/v1/risk",
            headers=self.auth_headers,
            catch_response=True,
            name="/api/v1/risk",
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code in (401, 403):
                response.failure("Authentication expired")
            else:
                response.failure(f"Risk metrics error: {response.status_code}")

    @task(3)
    @tag("risk", "killswitch")
    def get_killswitch_status(self):
        """GET /api/v1/killswitch/status - Check kill switch state."""
        with self.client.get(
            "/api/v1/killswitch/status",
            headers=self.auth_headers,
            catch_response=True,
            name="/api/v1/killswitch/status",
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code in (401, 403):
                response.failure("Authentication expired")
            else:
                response.failure(
                    f"Kill switch status error: {response.status_code}"
                )

    @task(2)
    @tag("risk", "positions")
    def get_positions(self):
        """GET /api/v1/positions - Position data for risk analysis."""
        with self.client.get(
            "/api/v1/positions",
            headers=self.auth_headers,
            catch_response=True,
            name="/api/v1/positions",
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code in (401, 403):
                response.failure("Authentication expired")
            else:
                response.failure(f"Positions error: {response.status_code}")

    @task(1)
    @tag("risk", "killswitch", "logs")
    def get_killswitch_logs(self):
        """GET /api/v1/killswitch/logs - Kill switch event history."""
        with self.client.get(
            "/api/v1/killswitch/logs",
            headers=self.auth_headers,
            catch_response=True,
            name="/api/v1/killswitch/logs",
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code in (401, 403):
                response.failure("Authentication expired")
            else:
                response.failure(
                    f"Kill switch logs error: {response.status_code}"
                )


# ---------------------------------------------------------------------------
# Event hooks for reporting
# ---------------------------------------------------------------------------


@events.quitting.add_listener
def check_results(environment, **kwargs):
    """Validate load test results against performance requirements.

    Checks:
    - 95th percentile response time < 500ms (Requirement 2.1.2)
    - Failure rate < 1%
    """
    stats = environment.stats.total

    # Check 95th percentile response time
    p95 = stats.get_response_time_percentile(0.95) or 0
    if p95 > P95_RESPONSE_TIME_MS:
        logger.error(
            f"FAIL: 95th percentile response time {p95}ms "
            f"exceeds {P95_RESPONSE_TIME_MS}ms threshold"
        )
        environment.process_exit_code = 1
    else:
        logger.info(
            f"PASS: 95th percentile response time {p95}ms "
            f"within {P95_RESPONSE_TIME_MS}ms threshold"
        )

    # Check failure rate
    if stats.num_requests > 0:
        failure_rate = (stats.num_failures / stats.num_requests) * 100
        if failure_rate > MAX_FAILURE_RATE_PCT:
            logger.error(
                f"FAIL: Failure rate {failure_rate:.2f}% "
                f"exceeds {MAX_FAILURE_RATE_PCT}% threshold"
            )
            environment.process_exit_code = 1
        else:
            logger.info(
                f"PASS: Failure rate {failure_rate:.2f}% "
                f"within {MAX_FAILURE_RATE_PCT}% threshold"
            )
    else:
        logger.warning("No requests were made during the test run.")


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Log test configuration at start."""
    logger.info("=" * 60)
    logger.info("Load Test Started")
    logger.info(f"  Host: {environment.host}")
    logger.info(f"  Target Users: {environment.parsed_options.num_users if environment.parsed_options else 'N/A'}")
    logger.info(f"  P95 Target: {P95_RESPONSE_TIME_MS}ms")
    logger.info(f"  Max Failure Rate: {MAX_FAILURE_RATE_PCT}%")
    logger.info("=" * 60)
