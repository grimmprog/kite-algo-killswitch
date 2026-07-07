"""Tests for KillSwitchLog model validation.

Tests Requirements: 3.5
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import datetime
from src.database.models.killswitch_log import KillSwitchLog
from src.database.base import Base


class TestKillSwitchLogModelDefinition:
    """Test KillSwitchLog model table definition."""

    def test_tablename(self):
        assert KillSwitchLog.__tablename__ == "killswitch_logs"

    def test_columns_exist(self):
        column_names = [c.name for c in KillSwitchLog.__table__.columns]
        expected = [
            "id",
            "user_id",
            "trigger_reason",
            "loss_percent",
            "capital_at_trigger",
            "positions_closed_count",
            "timestamp",
        ]
        for col in expected:
            assert col in column_names, f"Missing column: {col}"

    def test_inherits_from_base(self):
        assert issubclass(KillSwitchLog, Base)

    def test_id_is_primary_key(self):
        id_col = KillSwitchLog.__table__.c.id
        assert id_col.primary_key is True

    def test_user_id_not_nullable(self):
        user_id_col = KillSwitchLog.__table__.c.user_id
        assert user_id_col.nullable is False

    def test_trigger_reason_not_nullable(self):
        trigger_col = KillSwitchLog.__table__.c.trigger_reason
        assert trigger_col.nullable is False

    def test_positions_closed_count_not_nullable(self):
        pcc_col = KillSwitchLog.__table__.c.positions_closed_count
        assert pcc_col.nullable is False

    def test_loss_percent_nullable(self):
        lp_col = KillSwitchLog.__table__.c.loss_percent
        assert lp_col.nullable is True

    def test_capital_at_trigger_nullable(self):
        cat_col = KillSwitchLog.__table__.c.capital_at_trigger
        assert cat_col.nullable is True

    def test_timestamp_not_nullable(self):
        ts_col = KillSwitchLog.__table__.c.timestamp
        assert ts_col.nullable is False


class TestKillSwitchLogDefaults:
    """Test KillSwitchLog model default values."""

    def test_positions_closed_count_default(self):
        pcc_col = KillSwitchLog.__table__.c.positions_closed_count
        assert pcc_col.default.arg == 0

    def test_timestamp_has_default(self):
        ts_col = KillSwitchLog.__table__.c.timestamp
        assert ts_col.default is not None


class TestKillSwitchLogTriggerReasonValidation:
    """Test trigger_reason validation."""

    def test_valid_trigger_reason(self):
        result = KillSwitchLog.validate_trigger_reason(
            None, "trigger_reason", "Daily loss limit exceeded"
        )
        assert result == "Daily loss limit exceeded"

    def test_valid_trigger_reason_with_details(self):
        result = KillSwitchLog.validate_trigger_reason(
            None, "trigger_reason", "Loss exceeded 5% threshold"
        )
        assert result == "Loss exceeded 5% threshold"

    def test_empty_trigger_reason_rejected(self):
        with pytest.raises(ValueError, match="Trigger reason cannot be empty"):
            KillSwitchLog.validate_trigger_reason(None, "trigger_reason", "")

    def test_whitespace_only_trigger_reason_rejected(self):
        with pytest.raises(ValueError, match="Trigger reason cannot be empty"):
            KillSwitchLog.validate_trigger_reason(None, "trigger_reason", "   ")

    def test_none_trigger_reason_rejected(self):
        with pytest.raises(ValueError, match="Trigger reason cannot be empty"):
            KillSwitchLog.validate_trigger_reason(None, "trigger_reason", None)


class TestKillSwitchLogPositionsClosedCountValidation:
    """Test positions_closed_count validation."""

    def test_valid_zero(self):
        result = KillSwitchLog.validate_positions_closed_count(
            None, "positions_closed_count", 0
        )
        assert result == 0

    def test_valid_positive(self):
        result = KillSwitchLog.validate_positions_closed_count(
            None, "positions_closed_count", 5
        )
        assert result == 5

    def test_valid_large_count(self):
        result = KillSwitchLog.validate_positions_closed_count(
            None, "positions_closed_count", 100
        )
        assert result == 100

    def test_negative_count_rejected(self):
        with pytest.raises(
            ValueError, match="Positions closed count must be non-negative"
        ):
            KillSwitchLog.validate_positions_closed_count(
                None, "positions_closed_count", -1
            )

    def test_large_negative_rejected(self):
        with pytest.raises(
            ValueError, match="Positions closed count must be non-negative"
        ):
            KillSwitchLog.validate_positions_closed_count(
                None, "positions_closed_count", -100
            )


class TestKillSwitchLogRepr:
    """Test KillSwitchLog __repr__ method."""

    def test_repr_format(self):
        class FakeLog:
            id = 1
            user_id = 42
            trigger_reason = "Loss limit exceeded"
            positions_closed_count = 3
            timestamp = datetime(2024, 1, 15, 10, 30, 0)

        result = KillSwitchLog.__repr__(FakeLog())
        assert "KillSwitchLog" in result
        assert "1" in result
        assert "42" in result
        assert "Loss limit exceeded" in result
        assert "3" in result
