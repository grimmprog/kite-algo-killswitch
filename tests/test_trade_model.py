"""Tests for Trade model validation.

Tests Requirements: 3.2
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.database.models.trade import Trade
from src.database.base import Base


class TestTradeModelDefinition:
    """Test Trade model table definition."""

    def test_tablename(self):
        assert Trade.__tablename__ == "trades"

    def test_columns_exist(self):
        column_names = [c.name for c in Trade.__table__.columns]
        expected = [
            "id",
            "user_id",
            "symbol",
            "exchange",
            "qty",
            "side",
            "entry_price",
            "exit_price",
            "pnl",
            "margin_used",
            "risk_snapshot_json",
            "status",
            "timestamp",
            "exit_timestamp",
        ]
        for col in expected:
            assert col in column_names, f"Missing column: {col}"

    def test_inherits_from_base(self):
        assert issubclass(Trade, Base)

    def test_user_id_not_nullable(self):
        user_id_col = Trade.__table__.c.user_id
        assert user_id_col.nullable is False

    def test_symbol_not_nullable(self):
        symbol_col = Trade.__table__.c.symbol
        assert symbol_col.nullable is False

    def test_status_default(self):
        status_col = Trade.__table__.c.status
        assert status_col.default.arg == "OPEN"

    def test_pnl_default(self):
        pnl_col = Trade.__table__.c.pnl
        assert pnl_col.default.arg == 0.0


class TestTradeSymbolValidation:
    """Test symbol validation - must be non-empty."""

    def test_valid_symbol(self):
        result = Trade.validate_symbol(None, "symbol", "RELIANCE")
        assert result == "RELIANCE"

    def test_valid_symbol_with_numbers(self):
        result = Trade.validate_symbol(None, "symbol", "NIFTY23NOV18000CE")
        assert result == "NIFTY23NOV18000CE"

    def test_empty_string_rejected(self):
        with pytest.raises(ValueError, match="Symbol cannot be empty"):
            Trade.validate_symbol(None, "symbol", "")

    def test_whitespace_only_rejected(self):
        with pytest.raises(ValueError, match="Symbol cannot be empty"):
            Trade.validate_symbol(None, "symbol", "   ")

    def test_none_rejected(self):
        with pytest.raises(ValueError, match="Symbol cannot be empty"):
            Trade.validate_symbol(None, "symbol", None)


class TestTradeExchangeValidation:
    """Test exchange validation - must be NSE, NFO, BSE, or BFO."""

    def test_valid_nse(self):
        result = Trade.validate_exchange(None, "exchange", "NSE")
        assert result == "NSE"

    def test_valid_nfo(self):
        result = Trade.validate_exchange(None, "exchange", "NFO")
        assert result == "NFO"

    def test_valid_bse(self):
        result = Trade.validate_exchange(None, "exchange", "BSE")
        assert result == "BSE"

    def test_valid_bfo(self):
        result = Trade.validate_exchange(None, "exchange", "BFO")
        assert result == "BFO"

    def test_invalid_exchange(self):
        with pytest.raises(ValueError, match="Exchange must be one of"):
            Trade.validate_exchange(None, "exchange", "MCX")

    def test_lowercase_rejected(self):
        with pytest.raises(ValueError, match="Exchange must be one of"):
            Trade.validate_exchange(None, "exchange", "nse")

    def test_empty_string_rejected(self):
        with pytest.raises(ValueError, match="Exchange must be one of"):
            Trade.validate_exchange(None, "exchange", "")


class TestTradeQtyValidation:
    """Test quantity validation - must be non-zero."""

    def test_valid_positive_qty(self):
        result = Trade.validate_qty(None, "qty", 10)
        assert result == 10

    def test_valid_negative_qty(self):
        result = Trade.validate_qty(None, "qty", -5)
        assert result == -5

    def test_zero_rejected(self):
        with pytest.raises(ValueError, match="Quantity cannot be zero"):
            Trade.validate_qty(None, "qty", 0)

    def test_large_qty_valid(self):
        result = Trade.validate_qty(None, "qty", 100000)
        assert result == 100000


class TestTradeEntryPriceValidation:
    """Test entry price validation - must be positive."""

    def test_valid_price(self):
        result = Trade.validate_entry_price(None, "entry_price", 150.50)
        assert result == 150.50

    def test_valid_small_price(self):
        result = Trade.validate_entry_price(None, "entry_price", 0.01)
        assert result == 0.01

    def test_zero_rejected(self):
        with pytest.raises(ValueError, match="Entry price must be positive"):
            Trade.validate_entry_price(None, "entry_price", 0)

    def test_negative_rejected(self):
        with pytest.raises(ValueError, match="Entry price must be positive"):
            Trade.validate_entry_price(None, "entry_price", -100.0)

    def test_none_rejected(self):
        with pytest.raises(ValueError, match="Entry price must be positive"):
            Trade.validate_entry_price(None, "entry_price", None)


class TestTradeSideValidation:
    """Test side validation - must be BUY or SELL."""

    def test_valid_buy(self):
        result = Trade.validate_side(None, "side", "BUY")
        assert result == "BUY"

    def test_valid_sell(self):
        result = Trade.validate_side(None, "side", "SELL")
        assert result == "SELL"

    def test_invalid_side(self):
        with pytest.raises(ValueError, match="Side must be one of"):
            Trade.validate_side(None, "side", "HOLD")

    def test_lowercase_rejected(self):
        with pytest.raises(ValueError, match="Side must be one of"):
            Trade.validate_side(None, "side", "buy")

    def test_empty_string_rejected(self):
        with pytest.raises(ValueError, match="Side must be one of"):
            Trade.validate_side(None, "side", "")


class TestTradeStatusValidation:
    """Test status validation - must be OPEN or CLOSED."""

    def test_valid_open(self):
        result = Trade.validate_status(None, "status", "OPEN")
        assert result == "OPEN"

    def test_valid_closed(self):
        result = Trade.validate_status(None, "status", "CLOSED")
        assert result == "CLOSED"

    def test_invalid_status(self):
        with pytest.raises(ValueError, match="Status must be one of"):
            Trade.validate_status(None, "status", "PENDING")

    def test_lowercase_rejected(self):
        with pytest.raises(ValueError, match="Status must be one of"):
            Trade.validate_status(None, "status", "open")

    def test_empty_string_rejected(self):
        with pytest.raises(ValueError, match="Status must be one of"):
            Trade.validate_status(None, "status", "")


class TestTradeRepr:
    """Test Trade __repr__ method."""

    def test_repr_format(self):
        class FakeTrade:
            id = 1
            user_id = 42
            symbol = "RELIANCE"
            side = "BUY"
            qty = 10
            entry_price = 2500.0
            status = "OPEN"

        result = Trade.__repr__(FakeTrade())
        assert "Trade" in result
        assert "RELIANCE" in result
        assert "BUY" in result
        assert "OPEN" in result
