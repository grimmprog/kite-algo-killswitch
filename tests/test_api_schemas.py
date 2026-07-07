"""Tests for src/api/schemas.py

Validates that Pydantic models enforce field constraints correctly.
When these models are used in FastAPI route handlers, invalid data
triggers a 422 response via the validation_exception_handler.

Tests cover:
- LoginRequest: email/password length constraints
- TradeRequest: symbol, exchange, quantity, side, order_type, price validation
- Valid data is accepted without errors
- Response models can serialize from ORM objects (from_attributes=True)
- Null/optional fields are handled correctly
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

from src.api.schemas import (
    LoginRequest,
    RefreshRequest,
    TokenResponse,
    TradeRequest,
    TradeResponse,
    RiskMetricsResponse,
    PositionResponse,
    KillSwitchStatusResponse,
    TradeHistoryResponse,
    OrderHistoryResponse,
    DashboardResponse,
)


# --------------------------------------------------------------------------
# 8.3.1 / 8.3.2 / 8.3.3: Pydantic model validation
# --------------------------------------------------------------------------


class TestLoginRequest:
    """Tests for LoginRequest validation."""

    def test_valid_login(self):
        """Valid email and password should pass validation."""
        req = LoginRequest(email="user@example.com", password="securepass123")
        assert req.email == "user@example.com"
        assert req.password == "securepass123"

    def test_empty_email_rejected(self):
        """Empty email should fail min_length=1 constraint."""
        with pytest.raises(ValidationError) as exc_info:
            LoginRequest(email="", password="securepass123")
        errors = exc_info.value.errors()
        assert any("email" in str(e["loc"]) for e in errors)

    def test_password_too_short(self):
        """Password shorter than 8 characters should fail."""
        with pytest.raises(ValidationError) as exc_info:
            LoginRequest(email="user@example.com", password="short")
        errors = exc_info.value.errors()
        assert any("password" in str(e["loc"]) for e in errors)

    def test_password_too_long(self):
        """Password longer than 128 characters should fail."""
        with pytest.raises(ValidationError) as exc_info:
            LoginRequest(email="user@example.com", password="x" * 129)
        errors = exc_info.value.errors()
        assert any("password" in str(e["loc"]) for e in errors)

    def test_missing_email_rejected(self):
        """Missing email field should fail."""
        with pytest.raises(ValidationError):
            LoginRequest(password="securepass123")

    def test_missing_password_rejected(self):
        """Missing password field should fail."""
        with pytest.raises(ValidationError):
            LoginRequest(email="user@example.com")


class TestTradeRequest:
    """Tests for TradeRequest validation."""

    def test_valid_trade(self):
        """Valid trade request should pass validation."""
        req = TradeRequest(
            symbol="RELIANCE",
            exchange="NSE",
            quantity=10,
            side="BUY",
        )
        assert req.symbol == "RELIANCE"
        assert req.exchange == "NSE"
        assert req.quantity == 10
        assert req.side == "BUY"
        assert req.order_type == "MARKET"
        assert req.price is None

    def test_valid_limit_order(self):
        """Limit order with price should pass."""
        req = TradeRequest(
            symbol="INFY",
            exchange="BSE",
            quantity=5,
            side="SELL",
            order_type="LIMIT",
            price=1500.50,
        )
        assert req.order_type == "LIMIT"
        assert req.price == 1500.50

    def test_invalid_exchange_rejected(self):
        """Exchange not in NSE/NFO/BSE/BFO should fail."""
        with pytest.raises(ValidationError) as exc_info:
            TradeRequest(
                symbol="RELIANCE",
                exchange="NASDAQ",
                quantity=10,
                side="BUY",
            )
        errors = exc_info.value.errors()
        assert any("exchange" in str(e["loc"]) for e in errors)

    def test_invalid_side_rejected(self):
        """Side not BUY or SELL should fail."""
        with pytest.raises(ValidationError) as exc_info:
            TradeRequest(
                symbol="RELIANCE",
                exchange="NSE",
                quantity=10,
                side="HOLD",
            )
        errors = exc_info.value.errors()
        assert any("side" in str(e["loc"]) for e in errors)

    def test_zero_quantity_rejected(self):
        """Quantity must be > 0."""
        with pytest.raises(ValidationError) as exc_info:
            TradeRequest(
                symbol="RELIANCE",
                exchange="NSE",
                quantity=0,
                side="BUY",
            )
        errors = exc_info.value.errors()
        assert any("quantity" in str(e["loc"]) for e in errors)

    def test_negative_quantity_rejected(self):
        """Negative quantity should fail."""
        with pytest.raises(ValidationError) as exc_info:
            TradeRequest(
                symbol="RELIANCE",
                exchange="NSE",
                quantity=-5,
                side="BUY",
            )
        errors = exc_info.value.errors()
        assert any("quantity" in str(e["loc"]) for e in errors)

    def test_empty_symbol_rejected(self):
        """Empty symbol should fail min_length=1 constraint."""
        with pytest.raises(ValidationError) as exc_info:
            TradeRequest(
                symbol="",
                exchange="NSE",
                quantity=10,
                side="BUY",
            )
        errors = exc_info.value.errors()
        assert any("symbol" in str(e["loc"]) for e in errors)

    def test_negative_price_rejected(self):
        """Negative price should fail gt=0 constraint."""
        with pytest.raises(ValidationError) as exc_info:
            TradeRequest(
                symbol="RELIANCE",
                exchange="NSE",
                quantity=10,
                side="BUY",
                price=-100.0,
            )
        errors = exc_info.value.errors()
        assert any("price" in str(e["loc"]) for e in errors)

    def test_invalid_order_type_rejected(self):
        """Order type not MARKET or LIMIT should fail."""
        with pytest.raises(ValidationError) as exc_info:
            TradeRequest(
                symbol="RELIANCE",
                exchange="NSE",
                quantity=10,
                side="BUY",
                order_type="STOP_LOSS",
            )
        errors = exc_info.value.errors()
        assert any("order_type" in str(e["loc"]) for e in errors)

    def test_risk_snapshot_optional(self):
        """risk_snapshot can be omitted or provided as a dict."""
        req = TradeRequest(
            symbol="NIFTY24JUNFUT",
            exchange="NFO",
            quantity=1,
            side="SELL",
            risk_snapshot={"daily_loss_pct": 1.5},
        )
        assert req.risk_snapshot == {"daily_loss_pct": 1.5}


class TestResponseModels:
    """Tests for response model construction."""

    def test_token_response(self):
        """TokenResponse should hold token data."""
        resp = TokenResponse(
            access_token="abc",
            refresh_token="def",
            user_id=42,
        )
        assert resp.token_type == "bearer"
        assert resp.user_id == 42

    def test_trade_response(self):
        """TradeResponse should hold task_id and message."""
        resp = TradeResponse(task_id="task-123", message="Order queued")
        assert resp.task_id == "task-123"

    def test_risk_metrics_response(self):
        """RiskMetricsResponse with all fields."""
        resp = RiskMetricsResponse(
            daily_loss_pct=2.5,
            capital_used_pct=45.0,
            margin_used_pct=60.0,
            killswitch_active=False,
            net_delta=0.5,
            net_gamma=0.01,
            net_vega=100.0,
            unrealized_pnl=-5000.0,
        )
        assert resp.killswitch_active is False

    def test_position_response(self):
        """PositionResponse with optional current_price."""
        resp = PositionResponse(
            symbol="RELIANCE",
            quantity=10,
            entry_price=2500.0,
            current_price=None,
            pnl=-200.0,
            margin_used=25000.0,
        )
        assert resp.current_price is None

    def test_killswitch_status_response(self):
        """KillSwitchStatusResponse should hold active status."""
        resp = KillSwitchStatusResponse(active=True, user_id=1)
        assert resp.active is True


# --------------------------------------------------------------------------
# 8.4.1 / 8.4.2 / 8.4.3: Response models, ORM serialization, null handling
# --------------------------------------------------------------------------


class TestTradeHistoryResponse:
    """Tests for TradeHistoryResponse schema."""

    def test_valid_open_trade(self):
        """Open trade with null exit_price and exit_timestamp."""
        resp = TradeHistoryResponse(
            id=1,
            symbol="RELIANCE",
            exchange="NSE",
            qty=10,
            side="BUY",
            entry_price=2500.0,
            exit_price=None,
            pnl=0.0,
            margin_used=25000.0,
            status="OPEN",
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
            exit_timestamp=None,
        )
        assert resp.exit_price is None
        assert resp.exit_timestamp is None
        assert resp.status == "OPEN"

    def test_valid_closed_trade(self):
        """Closed trade with exit_price and exit_timestamp populated."""
        resp = TradeHistoryResponse(
            id=2,
            symbol="INFY",
            exchange="NSE",
            qty=-5,
            side="SELL",
            entry_price=1500.0,
            exit_price=1480.0,
            pnl=100.0,
            margin_used=7500.0,
            status="CLOSED",
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
            exit_timestamp=datetime(2024, 1, 15, 14, 30, 0),
        )
        assert resp.exit_price == 1480.0
        assert resp.exit_timestamp is not None
        assert resp.pnl == 100.0

    def test_from_attributes_enabled(self):
        """TradeHistoryResponse should support from_attributes for ORM objects."""
        assert TradeHistoryResponse.model_config.get("from_attributes") is True

    def test_null_margin_used(self):
        """margin_used can be null for trades without margin tracking."""
        resp = TradeHistoryResponse(
            id=3,
            symbol="NIFTY24JUNFUT",
            exchange="NFO",
            qty=1,
            side="BUY",
            entry_price=22000.0,
            pnl=-500.0,
            margin_used=None,
            status="OPEN",
            timestamp=datetime(2024, 1, 15, 10, 0, 0),
        )
        assert resp.margin_used is None


class TestOrderHistoryResponse:
    """Tests for OrderHistoryResponse schema."""

    def test_valid_complete_order(self):
        """Completed order with all fields."""
        resp = OrderHistoryResponse(
            id=1,
            broker_order_id="ORD-12345",
            symbol="RELIANCE",
            qty=10,
            price=2500.0,
            status="COMPLETE",
            retries=0,
            error_message=None,
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
        )
        assert resp.broker_order_id == "ORD-12345"
        assert resp.error_message is None

    def test_pending_order_null_fields(self):
        """Pending order with null broker_order_id and price."""
        resp = OrderHistoryResponse(
            id=2,
            broker_order_id=None,
            symbol="INFY",
            qty=5,
            price=None,
            status="PENDING",
            retries=0,
            error_message=None,
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
        )
        assert resp.broker_order_id is None
        assert resp.price is None

    def test_rejected_order_with_error(self):
        """Rejected order with error_message and retries."""
        resp = OrderHistoryResponse(
            id=3,
            broker_order_id="ORD-99999",
            symbol="BANKNIFTY24JUNFUT",
            qty=1,
            price=48000.0,
            status="REJECTED",
            retries=3,
            error_message="Insufficient margin",
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
        )
        assert resp.retries == 3
        assert resp.error_message == "Insufficient margin"

    def test_from_attributes_enabled(self):
        """OrderHistoryResponse should support from_attributes for ORM objects."""
        assert OrderHistoryResponse.model_config.get("from_attributes") is True


class TestDashboardResponse:
    """Tests for DashboardResponse schema."""

    def test_valid_dashboard(self):
        """Dashboard response with risk metrics and positions."""
        resp = DashboardResponse(
            risk_metrics=RiskMetricsResponse(
                daily_loss_pct=1.5,
                capital_used_pct=30.0,
                margin_used_pct=45.0,
                killswitch_active=False,
                net_delta=0.3,
                net_gamma=0.01,
                net_vega=50.0,
                unrealized_pnl=-2000.0,
            ),
            positions=[
                PositionResponse(
                    symbol="RELIANCE",
                    quantity=10,
                    entry_price=2500.0,
                    current_price=2520.0,
                    pnl=200.0,
                    margin_used=25000.0,
                ),
            ],
            killswitch_active=False,
        )
        assert len(resp.positions) == 1
        assert resp.killswitch_active is False

    def test_empty_positions(self):
        """Dashboard with no open positions."""
        resp = DashboardResponse(
            risk_metrics=RiskMetricsResponse(
                daily_loss_pct=0.0,
                capital_used_pct=0.0,
                margin_used_pct=0.0,
                killswitch_active=False,
                net_delta=0.0,
                net_gamma=0.0,
                net_vega=0.0,
                unrealized_pnl=0.0,
            ),
            positions=[],
            killswitch_active=False,
        )
        assert resp.positions == []


class TestOrmSerialization:
    """Tests that response models can be constructed from ORM-like objects."""

    def test_position_response_from_orm_object(self):
        """PositionResponse can be constructed from an object with attributes."""

        class FakePosition:
            symbol = "RELIANCE"
            quantity = 10
            entry_price = 2500.0
            current_price = 2520.0
            pnl = 200.0
            margin_used = 25000.0

        resp = PositionResponse.model_validate(FakePosition())
        assert resp.symbol == "RELIANCE"
        assert resp.current_price == 2520.0

    def test_position_response_from_orm_null_current_price(self):
        """PositionResponse handles null current_price from ORM objects."""

        class FakePosition:
            symbol = "INFY"
            quantity = 5
            entry_price = 1500.0
            current_price = None
            pnl = 0.0
            margin_used = 7500.0

        resp = PositionResponse.model_validate(FakePosition())
        assert resp.current_price is None

    def test_trade_history_from_orm_object(self):
        """TradeHistoryResponse can be constructed from an ORM-like object."""

        class FakeTrade:
            id = 1
            symbol = "RELIANCE"
            exchange = "NSE"
            qty = 10
            side = "BUY"
            entry_price = 2500.0
            exit_price = None
            pnl = 0.0
            margin_used = 25000.0
            status = "OPEN"
            timestamp = datetime(2024, 1, 15, 10, 30, 0)
            exit_timestamp = None

        resp = TradeHistoryResponse.model_validate(FakeTrade())
        assert resp.id == 1
        assert resp.exit_price is None
        assert resp.exit_timestamp is None

    def test_order_history_from_orm_object(self):
        """OrderHistoryResponse can be constructed from an ORM-like object."""

        class FakeOrder:
            id = 1
            broker_order_id = "ORD-123"
            symbol = "RELIANCE"
            qty = 10
            price = 2500.0
            status = "COMPLETE"
            retries = 0
            error_message = None
            timestamp = datetime(2024, 1, 15, 10, 30, 0)

        resp = OrderHistoryResponse.model_validate(FakeOrder())
        assert resp.broker_order_id == "ORD-123"
        assert resp.error_message is None

    def test_risk_metrics_from_attributes(self):
        """RiskMetricsResponse should support from_attributes."""
        assert RiskMetricsResponse.model_config.get("from_attributes") is True

    def test_killswitch_status_from_attributes(self):
        """KillSwitchStatusResponse should support from_attributes."""
        assert KillSwitchStatusResponse.model_config.get("from_attributes") is True
