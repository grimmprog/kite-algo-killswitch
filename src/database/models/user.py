"""User model for the Multi-User Web Trading Platform.

Implements Requirements: 1.1, 3.1, 2.4
"""

import re
from datetime import datetime
from typing import Optional, List

from sqlalchemy import String, Float, Boolean, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column, validates, relationship

from src.database.base import Base


class User(Base):
    """User accounts for the multi-user web trading platform.

    Each user has isolated capital, positions, risk thresholds,
    and kill switch state.
    """

    __tablename__ = "users"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Authentication
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # Trading configuration
    capital: Mapped[float] = mapped_column(Float, nullable=False, default=100000.0)
    risk_profile: Mapped[str] = mapped_column(
        String(50), nullable=False, default="moderate"
    )

    # Risk thresholds
    daily_loss_limit_percent: Mapped[float] = mapped_column(
        Float, nullable=False, default=2.0
    )
    max_trade_risk_percent: Mapped[float] = mapped_column(
        Float, nullable=False, default=1.0
    )

    # Kill switch state
    killswitch_state: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    # Broker integration (encrypted tokens)
    broker_access_token: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    broker_refresh_token: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    broker_token_expiry: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now
    )
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationships (string references to avoid circular imports)
    trades: Mapped[List["Trade"]] = relationship(  # noqa: F821
        "Trade", back_populates="user", lazy="dynamic"
    )
    positions: Mapped[Optional["Position"]] = relationship(  # noqa: F821
        "Position", back_populates="user", uselist=False
    )
    orders: Mapped[List["Order"]] = relationship(  # noqa: F821
        "Order", back_populates="user", lazy="dynamic"
    )
    killswitch_logs: Mapped[List["KillSwitchLog"]] = relationship(  # noqa: F821
        "KillSwitchLog", back_populates="user", lazy="dynamic"
    )
    settings: Mapped[Optional["UserSettings"]] = relationship(  # noqa: F821
        "UserSettings", back_populates="user", uselist=False
    )
    scan_signals: Mapped[List["ScanSignal"]] = relationship(  # noqa: F821
        "ScanSignal", back_populates="user", lazy="dynamic"
    )
    paper_account: Mapped[Optional["PaperAccount"]] = relationship(  # noqa: F821
        "PaperAccount", back_populates="user", uselist=False
    )
    notifications: Mapped[List["Notification"]] = relationship(  # noqa: F821
        "Notification", back_populates="user", lazy="dynamic"
    )
    trade_journal_entries: Mapped[List["TradeJournalEntry"]] = relationship(  # noqa: F821
        "TradeJournalEntry", back_populates="user", lazy="dynamic"
    )
    position_monitor_states: Mapped[List["PositionMonitorState"]] = relationship(  # noqa: F821
        "PositionMonitorState", back_populates="user", lazy="dynamic"
    )
    broker_connections: Mapped[List["BrokerConnection"]] = relationship(  # noqa: F821
        "BrokerConnection", back_populates="user", lazy="dynamic"
    )

    # --- Validators ---

    @validates("email")
    def validate_email(self, key: str, value: str) -> str:
        """Validate email format."""
        if not value:
            raise ValueError("Email cannot be empty")
        # Basic email regex pattern
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        if not re.match(pattern, value):
            raise ValueError(f"Invalid email format: {value}")
        return value

    @validates("capital")
    def validate_capital(self, key: str, value: float) -> float:
        """Validate that capital is positive."""
        if value is None or value <= 0:
            raise ValueError("Capital must be positive")
        return value

    @validates("risk_profile")
    def validate_risk_profile(self, key: str, value: str) -> str:
        """Validate risk profile is one of the allowed values."""
        allowed = ("conservative", "moderate", "aggressive")
        if value not in allowed:
            raise ValueError(
                f"Risk profile must be one of: {', '.join(allowed)}. Got: {value}"
            )
        return value

    @validates("daily_loss_limit_percent")
    def validate_daily_loss_limit_percent(self, key: str, value: float) -> float:
        """Validate daily loss limit percent is between 0.5 and 10.0."""
        if value is None or value < 0.5 or value > 10.0:
            raise ValueError(
                "Daily loss limit percent must be between 0.5 and 10.0"
            )
        return value

    @validates("max_trade_risk_percent")
    def validate_max_trade_risk_percent(self, key: str, value: float) -> float:
        """Validate max trade risk percent is between 0.1 and 5.0."""
        if value is None or value < 0.1 or value > 5.0:
            raise ValueError(
                "Max trade risk percent must be between 0.1 and 5.0"
            )
        return value

    @validates("password_hash")
    def validate_password_hash(self, key: str, value: str) -> str:
        """Validate password hash is not empty.

        Note: The minimum length of 8 characters is enforced on the raw password
        before hashing, at the service layer. This validator ensures the hash
        itself is not empty.
        """
        if not value:
            raise ValueError("Password hash cannot be empty")
        return value

    def __repr__(self) -> str:
        return (
            f"<User(id={self.id}, email='{self.email}', "
            f"risk_profile='{self.risk_profile}', "
            f"capital={self.capital}, is_active={self.is_active})>"
        )
