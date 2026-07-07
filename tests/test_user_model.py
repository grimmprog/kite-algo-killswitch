"""Tests for User model validation.

Tests Requirements: 1.1.1, 1.1.3, 1.1.6, 1.1.7, 1.1.8, 1.1.9, 3.1
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.database.models.user import User
from src.database.base import Base


class TestUserModelDefinition:
    """Test User model table definition."""

    def test_tablename(self):
        assert User.__tablename__ == "users"

    def test_columns_exist(self):
        column_names = [c.name for c in User.__table__.columns]
        expected = [
            "id",
            "email",
            "password_hash",
            "capital",
            "risk_profile",
            "daily_loss_limit_percent",
            "max_trade_risk_percent",
            "killswitch_state",
            "broker_access_token",
            "broker_refresh_token",
            "broker_token_expiry",
            "created_at",
            "last_login",
            "is_active",
        ]
        for col in expected:
            assert col in column_names, f"Missing column: {col}"

    def test_email_unique_constraint(self):
        email_col = User.__table__.c.email
        assert email_col.unique is True

    def test_email_not_nullable(self):
        email_col = User.__table__.c.email
        assert email_col.nullable is False

    def test_capital_default(self):
        capital_col = User.__table__.c.capital
        assert capital_col.default.arg == 100000.0

    def test_risk_profile_default(self):
        risk_col = User.__table__.c.risk_profile
        assert risk_col.default.arg == "moderate"

    def test_killswitch_default(self):
        ks_col = User.__table__.c.killswitch_state
        assert ks_col.default.arg is False

    def test_is_active_default(self):
        active_col = User.__table__.c.is_active
        assert active_col.default.arg is True

    def test_inherits_from_base(self):
        assert issubclass(User, Base)


class TestUserEmailValidation:
    """Test email validation."""

    def test_valid_email(self):
        result = User.validate_email(None, "email", "user@example.com")
        assert result == "user@example.com"

    def test_valid_email_with_dots(self):
        result = User.validate_email(None, "email", "first.last@domain.co.uk")
        assert result == "first.last@domain.co.uk"

    def test_invalid_email_no_at(self):
        with pytest.raises(ValueError, match="Invalid email format"):
            User.validate_email(None, "email", "invalid-email")

    def test_invalid_email_no_domain(self):
        with pytest.raises(ValueError, match="Invalid email format"):
            User.validate_email(None, "email", "user@")

    def test_empty_email(self):
        with pytest.raises(ValueError, match="Email cannot be empty"):
            User.validate_email(None, "email", "")

    def test_invalid_email_spaces(self):
        with pytest.raises(ValueError, match="Invalid email format"):
            User.validate_email(None, "email", "user @example.com")


class TestUserCapitalValidation:
    """Test capital validation."""

    def test_valid_capital(self):
        result = User.validate_capital(None, "capital", 50000.0)
        assert result == 50000.0

    def test_valid_capital_small(self):
        result = User.validate_capital(None, "capital", 0.01)
        assert result == 0.01

    def test_zero_capital_rejected(self):
        with pytest.raises(ValueError, match="Capital must be positive"):
            User.validate_capital(None, "capital", 0)

    def test_negative_capital_rejected(self):
        with pytest.raises(ValueError, match="Capital must be positive"):
            User.validate_capital(None, "capital", -1000)

    def test_none_capital_rejected(self):
        with pytest.raises(ValueError, match="Capital must be positive"):
            User.validate_capital(None, "capital", None)


class TestUserRiskProfileValidation:
    """Test risk profile validation."""

    def test_conservative(self):
        result = User.validate_risk_profile(None, "risk_profile", "conservative")
        assert result == "conservative"

    def test_moderate(self):
        result = User.validate_risk_profile(None, "risk_profile", "moderate")
        assert result == "moderate"

    def test_aggressive(self):
        result = User.validate_risk_profile(None, "risk_profile", "aggressive")
        assert result == "aggressive"

    def test_invalid_profile(self):
        with pytest.raises(ValueError, match="Risk profile must be one of"):
            User.validate_risk_profile(None, "risk_profile", "risky")

    def test_empty_profile(self):
        with pytest.raises(ValueError, match="Risk profile must be one of"):
            User.validate_risk_profile(None, "risk_profile", "")


class TestUserDailyLossLimitValidation:
    """Test daily loss limit percent validation."""

    def test_valid_lower_bound(self):
        result = User.validate_daily_loss_limit_percent(
            None, "daily_loss_limit_percent", 0.5
        )
        assert result == 0.5

    def test_valid_upper_bound(self):
        result = User.validate_daily_loss_limit_percent(
            None, "daily_loss_limit_percent", 10.0
        )
        assert result == 10.0

    def test_valid_middle_value(self):
        result = User.validate_daily_loss_limit_percent(
            None, "daily_loss_limit_percent", 5.0
        )
        assert result == 5.0

    def test_below_lower_bound(self):
        with pytest.raises(
            ValueError, match="Daily loss limit percent must be between 0.5 and 10.0"
        ):
            User.validate_daily_loss_limit_percent(
                None, "daily_loss_limit_percent", 0.4
            )

    def test_above_upper_bound(self):
        with pytest.raises(
            ValueError, match="Daily loss limit percent must be between 0.5 and 10.0"
        ):
            User.validate_daily_loss_limit_percent(
                None, "daily_loss_limit_percent", 10.1
            )

    def test_none_value(self):
        with pytest.raises(
            ValueError, match="Daily loss limit percent must be between 0.5 and 10.0"
        ):
            User.validate_daily_loss_limit_percent(
                None, "daily_loss_limit_percent", None
            )


class TestUserMaxTradeRiskValidation:
    """Test max trade risk percent validation."""

    def test_valid_lower_bound(self):
        result = User.validate_max_trade_risk_percent(
            None, "max_trade_risk_percent", 0.1
        )
        assert result == 0.1

    def test_valid_upper_bound(self):
        result = User.validate_max_trade_risk_percent(
            None, "max_trade_risk_percent", 5.0
        )
        assert result == 5.0

    def test_valid_middle_value(self):
        result = User.validate_max_trade_risk_percent(
            None, "max_trade_risk_percent", 2.5
        )
        assert result == 2.5

    def test_below_lower_bound(self):
        with pytest.raises(
            ValueError, match="Max trade risk percent must be between 0.1 and 5.0"
        ):
            User.validate_max_trade_risk_percent(
                None, "max_trade_risk_percent", 0.05
            )

    def test_above_upper_bound(self):
        with pytest.raises(
            ValueError, match="Max trade risk percent must be between 0.1 and 5.0"
        ):
            User.validate_max_trade_risk_percent(
                None, "max_trade_risk_percent", 5.1
            )

    def test_none_value(self):
        with pytest.raises(
            ValueError, match="Max trade risk percent must be between 0.1 and 5.0"
        ):
            User.validate_max_trade_risk_percent(
                None, "max_trade_risk_percent", None
            )


class TestUserPasswordHashValidation:
    """Test password hash validation."""

    def test_valid_hash(self):
        result = User.validate_password_hash(
            None, "password_hash", "$2b$12$somehashvalue"
        )
        assert result == "$2b$12$somehashvalue"

    def test_empty_hash_rejected(self):
        with pytest.raises(ValueError, match="Password hash cannot be empty"):
            User.validate_password_hash(None, "password_hash", "")

    def test_none_hash_rejected(self):
        with pytest.raises(ValueError, match="Password hash cannot be empty"):
            User.validate_password_hash(None, "password_hash", None)


class TestUserRepr:
    """Test User __repr__ method."""

    def test_repr_format(self):
        # Call __repr__ directly with a mock-like object to test formatting
        # We can't instantiate fully without related models being registered
        class FakeUser:
            id = 1
            email = "test@example.com"
            risk_profile = "moderate"
            capital = 100000.0
            is_active = True

        result = User.__repr__(FakeUser())
        assert "User" in result
        assert "test@example.com" in result
        assert "moderate" in result
        assert "100000.0" in result
        assert "True" in result
