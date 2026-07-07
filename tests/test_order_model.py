"""Tests for Order model validation.

Tests Requirements: 3.4
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.database.models.order import Order, VALID_ORDER_STATUSES
from src.database.base import Base


class TestOrderModelDefinition:
    """Test Order model table definition."""

    def test_tablename(self):
        assert Order.__tablename__ == "orders"

    def test_columns_exist(self):
        column_names = [c.name for c in Order.__table__.columns]
        expected = [
            "id",
            "user_id",
            "broker_order_id",
            "symbol",
            "qty",
            "price",
            "status",
            "retries",
            "error_message",
            "timestamp",
        ]
        for col in expected:
            assert col in column_names, f"Missing column: {col}"

    def test_inherits_from_base(self):
        assert issubclass(Order, Base)

    def test_user_id_not_nullable(self):
        user_id_col = Order.__table__.c.user_id
        assert user_id_col.nullable is False

    def test_symbol_not_nullable(self):
        symbol_col = Order.__table__.c.symbol
        assert symbol_col.nullable is False

    def test_qty_not_nullable(self):
        qty_col = Order.__table__.c.qty
        assert qty_col.nullable is False

    def test_status_not_nullable(self):
        status_col = Order.__table__.c.status
        assert status_col.nullable is False

    def test_retries_not_nullable(self):
        retries_col = Order.__table__.c.retries
        assert retries_col.nullable is False

    def test_timestamp_not_nullable(self):
        timestamp_col = Order.__table__.c.timestamp
        assert timestamp_col.nullable is False

    def test_broker_order_id_nullable(self):
        col = Order.__table__.c.broker_order_id
        assert col.nullable is True

    def test_price_nullable(self):
        col = Order.__table__.c.price
        assert col.nullable is True

    def test_error_message_nullable(self):
        col = Order.__table__.c.error_message
        assert col.nullable is True

    def test_status_default(self):
        status_col = Order.__table__.c.status
        assert status_col.default.arg == "PENDING"

    def test_retries_default(self):
        retries_col = Order.__table__.c.retries
        assert retries_col.default.arg == 0


class TestOrderSymbolValidation:
    """Test symbol validation."""

    def test_valid_symbol(self):
        result = Order.validate_symbol(None, "symbol", "RELIANCE")
        assert result == "RELIANCE"

    def test_valid_symbol_with_suffix(self):
        result = Order.validate_symbol(None, "symbol", "NIFTY50-FUT")
        assert result == "NIFTY50-FUT"

    def test_empty_symbol_rejected(self):
        with pytest.raises(ValueError, match="Symbol cannot be empty"):
            Order.validate_symbol(None, "symbol", "")

    def test_whitespace_only_symbol_rejected(self):
        with pytest.raises(ValueError, match="Symbol cannot be empty"):
            Order.validate_symbol(None, "symbol", "   ")

    def test_none_symbol_rejected(self):
        with pytest.raises(ValueError, match="Symbol cannot be empty"):
            Order.validate_symbol(None, "symbol", None)


class TestOrderQtyValidation:
    """Test quantity validation."""

    def test_valid_qty(self):
        result = Order.validate_qty(None, "qty", 10)
        assert result == 10

    def test_valid_qty_one(self):
        result = Order.validate_qty(None, "qty", 1)
        assert result == 1

    def test_zero_qty_rejected(self):
        with pytest.raises(ValueError, match="Quantity must be positive"):
            Order.validate_qty(None, "qty", 0)

    def test_negative_qty_rejected(self):
        with pytest.raises(ValueError, match="Quantity must be positive"):
            Order.validate_qty(None, "qty", -5)

    def test_none_qty_rejected(self):
        with pytest.raises(ValueError, match="Quantity must be positive"):
            Order.validate_qty(None, "qty", None)


class TestOrderStatusValidation:
    """Test status validation."""

    def test_pending_status(self):
        result = Order.validate_status(None, "status", "PENDING")
        assert result == "PENDING"

    def test_complete_status(self):
        result = Order.validate_status(None, "status", "COMPLETE")
        assert result == "COMPLETE"

    def test_rejected_status(self):
        result = Order.validate_status(None, "status", "REJECTED")
        assert result == "REJECTED"

    def test_cancelled_status(self):
        result = Order.validate_status(None, "status", "CANCELLED")
        assert result == "CANCELLED"

    def test_invalid_status(self):
        with pytest.raises(ValueError, match="Status must be one of"):
            Order.validate_status(None, "status", "UNKNOWN")

    def test_lowercase_status_rejected(self):
        with pytest.raises(ValueError, match="Status must be one of"):
            Order.validate_status(None, "status", "pending")

    def test_empty_status_rejected(self):
        with pytest.raises(ValueError, match="Status must be one of"):
            Order.validate_status(None, "status", "")


class TestOrderRetriesValidation:
    """Test retries validation."""

    def test_valid_retries_zero(self):
        result = Order.validate_retries(None, "retries", 0)
        assert result == 0

    def test_valid_retries_positive(self):
        result = Order.validate_retries(None, "retries", 3)
        assert result == 3

    def test_negative_retries_rejected(self):
        with pytest.raises(ValueError, match="Retries must be non-negative"):
            Order.validate_retries(None, "retries", -1)

    def test_none_retries_rejected(self):
        with pytest.raises(ValueError, match="Retries must be non-negative"):
            Order.validate_retries(None, "retries", None)


class TestOrderRepr:
    """Test Order __repr__ method."""

    def test_repr_format(self):
        class FakeOrder:
            id = 42
            user_id = 7
            symbol = "INFY"
            qty = 100
            status = "PENDING"

        result = Order.__repr__(FakeOrder())
        assert "Order" in result
        assert "42" in result
        assert "7" in result
        assert "INFY" in result
        assert "100" in result
        assert "PENDING" in result
