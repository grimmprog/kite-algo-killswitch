"""UserSettings model for per-user trading configuration.

Implements Requirements: 5.1
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Float, Boolean, Integer, JSON, TIMESTAMP, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, validates, relationship

from src.database.base import Base


class UserSettings(Base):
    """Per-user trading configuration and AI preferences.

    Each user has exactly one settings row (one-to-one).
    Stores watchlist, trading times, confidence thresholds,
    capital, kill switch thresholds, and AI toggles.
    """

    __tablename__ = "user_settings"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key to users (one-to-one)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Strategy settings - watchlist
    watchlist: Mapped[list] = mapped_column(JSON, nullable=False, server_default="[]")

    # Trading times
    trading_start_time: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="09:15"
    )
    trading_end_time: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="15:30"
    )

    # Confidence and trade limits
    confidence_threshold: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="70"
    )
    max_trades_per_day: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="5"
    )
    max_active_trades: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="3"
    )

    # Capital
    capital: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="100000.0"
    )

    # Lot sizes (JSON dict: symbol -> lot size)
    lot_sizes: Mapped[dict] = mapped_column(JSON, nullable=False, server_default="{}")

    # Kill switch thresholds - daily loss
    daily_loss_type: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="percentage"
    )
    daily_loss_value: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="2.0"
    )

    # Kill switch thresholds - profit target
    profit_target_type: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="percentage"
    )
    profit_target_value: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="5.0"
    )

    # Kill switch thresholds - drawdown
    drawdown_type: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="percentage"
    )
    drawdown_value: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="3.0"
    )

    # Profit warning percentage
    profit_warning_pct: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="80.0"
    )

    # Signal countdown
    signal_countdown_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="60"
    )

    # AI configuration
    ai_provider: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="'openai'"
    )
    ai_signal_analysis_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    ai_entry_suggestions_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    ai_exit_recommendations_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    ai_market_narrative_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    ai_trade_review_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    ai_risk_warnings_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default="NOW()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default="NOW()"
    )

    # Relationships
    user = relationship("User", back_populates="settings")

    # --- Validators ---

    @validates("confidence_threshold")
    def validate_confidence_threshold(self, key: str, value: int) -> int:
        """Validate confidence threshold is between 50 and 100."""
        if value is None or value < 50 or value > 100:
            raise ValueError("Confidence threshold must be between 50 and 100")
        return value

    @validates("max_trades_per_day")
    def validate_max_trades_per_day(self, key: str, value: int) -> int:
        """Validate max trades per day is between 1 and 10."""
        if value is None or value < 1 or value > 10:
            raise ValueError("Max trades per day must be between 1 and 10")
        return value

    @validates("capital")
    def validate_capital(self, key: str, value: float) -> float:
        """Validate that capital is positive."""
        if value is None or value <= 0:
            raise ValueError("Capital must be positive")
        return value

    @validates("daily_loss_type")
    def validate_daily_loss_type(self, key: str, value: str) -> str:
        """Validate daily loss type."""
        allowed = ("percentage", "absolute")
        if value not in allowed:
            raise ValueError(
                f"Daily loss type must be one of: {', '.join(allowed)}. Got: {value}"
            )
        return value

    @validates("profit_target_type")
    def validate_profit_target_type(self, key: str, value: str) -> str:
        """Validate profit target type."""
        allowed = ("percentage", "absolute")
        if value not in allowed:
            raise ValueError(
                f"Profit target type must be one of: {', '.join(allowed)}. Got: {value}"
            )
        return value

    @validates("drawdown_type")
    def validate_drawdown_type(self, key: str, value: str) -> str:
        """Validate drawdown type."""
        allowed = ("percentage", "absolute")
        if value not in allowed:
            raise ValueError(
                f"Drawdown type must be one of: {', '.join(allowed)}. Got: {value}"
            )
        return value

    def __repr__(self) -> str:
        return (
            f"<UserSettings(id={self.id}, user_id={self.user_id}, "
            f"capital={self.capital}, confidence_threshold={self.confidence_threshold})>"
        )
