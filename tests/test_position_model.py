"""Tests for Position model validation.

Tests Requirements: 3.3
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.database.models.position import Position
from src.database.base import Base


class TestPositionModelDefinition:
    """Test Position model table definition."""

    def test_tablename(self):
        assert Position.__tablename__ == "positions"

    def test_columns_exist(self):
        column_names = [c.name for c in Position.__table__.columns]
        expected = [
            "id",
            "user_id",
            "net_delta",
            "net_gamma",
            "net_vega",
            "margin_used",
            "unrealized_pnl",
            "updated_at",
        ]
        for col in expected:
            assert col in column_names, f"Missing column: {col}"

    def test_user_id_unique_constraint(self):
        user_id_col = Position.__table__.c.user_id
        assert user_id_col.unique is True

    def test_user_id_not_nullable(self):
        user_id_col = Position.__table__.c.user_id
        assert user_id_col.nullable is False

    def test_net_delta_default(self):
        col = Position.__table__.c.net_delta
        assert col.default.arg == 0.0

    def test_net_gamma_default(self):
        col = Position.__table__.c.net_gamma
        assert col.default.arg == 0.0

    def test_net_vega_default(self):
        col = Position.__table__.c.net_vega
        assert col.default.arg == 0.0

    def test_margin_used_default(self):
        col = Position.__table__.c.margin_used
        assert col.default.arg == 0.0

    def test_unrealized_pnl_default(self):
        col = Position.__table__.c.unrealized_pnl
        assert col.default.arg == 0.0

    def test_inherits_from_base(self):
        assert issubclass(Position, Base)


class TestPositionMarginUsedValidation:
    """Test margin_used validation (non-negative)."""

    def test_valid_margin_zero(self):
        result = Position.validate_margin_used(None, "margin_used", 0.0)
        assert result == 0.0

    def test_valid_margin_positive(self):
        result = Position.validate_margin_used(None, "margin_used", 5000.0)
        assert result == 5000.0

    def test_valid_margin_small_positive(self):
        result = Position.validate_margin_used(None, "margin_used", 0.01)
        assert result == 0.01

    def test_negative_margin_rejected(self):
        with pytest.raises(ValueError, match="margin_used must be >= 0"):
            Position.validate_margin_used(None, "margin_used", -1.0)

    def test_large_negative_margin_rejected(self):
        with pytest.raises(ValueError, match="margin_used must be >= 0"):
            Position.validate_margin_used(None, "margin_used", -10000.0)

    def test_none_margin_accepted(self):
        result = Position.validate_margin_used(None, "margin_used", None)
        assert result is None


class TestPositionRepr:
    """Test Position __repr__ method."""

    def test_repr_format(self):
        class FakePosition:
            id = 1
            user_id = 42
            net_delta = 0.5
            margin_used = 1000.0
            unrealized_pnl = -200.0

        result = Position.__repr__(FakePosition())
        assert "Position" in result
        assert "1" in result
        assert "42" in result
        assert "0.5" in result
        assert "1000.0" in result
        assert "-200.0" in result
