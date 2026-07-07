"""Pydantic request and response models for the API.

Defines validation schemas for all API endpoints. FastAPI uses these models
to automatically validate request bodies and return 422 errors (via the
validation_exception_handler in error_handlers.py) when data is invalid.

Requirements covered:
- 4.2.1: Validate all incoming request data
- 4.2.3: Return appropriate error responses for invalid input
"""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# --------------------------------------------------------------------------
# Auth schemas
# --------------------------------------------------------------------------


class LoginRequest(BaseModel):
    """Login request with email and password validation."""

    email: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)


class TokenResponse(BaseModel):
    """JWT token pair returned after successful authentication."""

    model_config = ConfigDict(from_attributes=True)

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: int


class RefreshRequest(BaseModel):
    """Request to refresh an expired access token."""

    refresh_token: str


# --------------------------------------------------------------------------
# Trade schemas
# --------------------------------------------------------------------------


class TradeRequest(BaseModel):
    """Trade execution request with full validation.

    - symbol: Trading instrument symbol (e.g., 'RELIANCE', 'NIFTY24JUNFUT')
    - exchange: Must be one of NSE, NFO, BSE, BFO
    - quantity: Must be positive integer
    - side: Must be BUY or SELL
    - order_type: MARKET or LIMIT (defaults to MARKET)
    - price: Required for LIMIT orders, must be positive
    - risk_snapshot: Optional risk metrics at time of trade
    """

    symbol: str = Field(..., min_length=1, max_length=50)
    exchange: str = Field(..., pattern=r"^(NSE|NFO|BSE|BFO)$")
    quantity: int = Field(..., gt=0)
    side: str = Field(..., pattern=r"^(BUY|SELL)$")
    order_type: str = Field(default="MARKET", pattern=r"^(MARKET|LIMIT)$")
    price: Optional[float] = Field(default=None, gt=0)
    risk_snapshot: Optional[Dict] = None


class TradeResponse(BaseModel):
    """Response after a trade is queued for execution."""

    task_id: str
    message: str


# --------------------------------------------------------------------------
# Dashboard schemas
# --------------------------------------------------------------------------


class RiskMetricsResponse(BaseModel):
    """Current risk metrics for a user's portfolio."""

    model_config = ConfigDict(from_attributes=True)

    daily_loss_pct: float
    capital_used_pct: float
    margin_used_pct: float
    killswitch_active: bool
    net_delta: float
    net_gamma: float
    net_vega: float
    unrealized_pnl: float


class PositionResponse(BaseModel):
    """A single open position."""

    model_config = ConfigDict(from_attributes=True)

    symbol: str
    quantity: int
    entry_price: float
    current_price: Optional[float] = None
    pnl: float
    margin_used: float


# --------------------------------------------------------------------------
# Kill switch schemas
# --------------------------------------------------------------------------


class KillSwitchStatusResponse(BaseModel):
    """Kill switch status for a user."""

    model_config = ConfigDict(from_attributes=True)

    active: bool
    user_id: int

# --------------------------------------------------------------------------
# Trade history schemas
# --------------------------------------------------------------------------


class TradeHistoryResponse(BaseModel):
    """A single trade record from the database.

    Maps directly from the Trade SQLAlchemy model.
    Nullable fields (exit_price, exit_timestamp) handle open trades.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    exchange: str
    qty: int
    side: str
    entry_price: float
    exit_price: Optional[float] = None
    pnl: float
    margin_used: Optional[float] = None
    status: str
    timestamp: datetime
    exit_timestamp: Optional[datetime] = None


# --------------------------------------------------------------------------
# Order history schemas
# --------------------------------------------------------------------------


class OrderHistoryResponse(BaseModel):
    """A single order record from the database.

    Maps directly from the Order SQLAlchemy model.
    Nullable fields (broker_order_id, price, error_message) handle
    pending or failed orders.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    broker_order_id: Optional[str] = None
    symbol: str
    qty: int
    price: Optional[float] = None
    status: str
    retries: int
    error_message: Optional[str] = None
    timestamp: datetime


# --------------------------------------------------------------------------
# Dashboard schemas (composite)
# --------------------------------------------------------------------------


class DashboardResponse(BaseModel):
    """Composite dashboard response combining risk metrics and positions.

    Used by the GET /api/v1/dashboard endpoint to return all
    dashboard data in a single response.
    """

    risk_metrics: RiskMetricsResponse
    positions: List[PositionResponse]
    killswitch_active: bool
