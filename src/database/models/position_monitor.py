"""PositionMonitorState model for real-time position tracking.

Implements Requirements: 7.1
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Float, Boolean, Integer, TIMESTAMP, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, validates, relationship

from src.database.base import Base


class PositionMonitorState(Base):
    """Real-time position monitoring state.

    Tracks live positions with entry/current prices, stop loss,
    target, trailing stop configuration, and unrealized P&L.
    """

    __tablename__ = "position_monitor_states"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign keys
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trade_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("trades.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Position details
    symbol: Mapped[str] = mapped_column(String(50), nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    current_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=False)
    target: Mapped[float] = mapped_column(Float, nullable=False)

    # Trailing stop
    trailing_stop_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    trailing_stop_level: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    trailing_stop_distance: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )

    # P&L and distance metrics
    unrealized_pnl: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="0"
    )
    distance_to_sl_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    distance_to_target_pct: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )

    # Status
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="active", index=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default="NOW()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default="NOW()"
    )

    # Relationships
    user = relationship("User", back_populates="position_monitor_states")
    trade = relationship("Trade")

    # --- Validators ---

    @validates("status")
    def validate_status(self, key: str, value: str) -> str:
        """Validate status is one of allowed values."""
        allowed = ("active", "sl_hit", "target_hit", "trailing_stop_hit", "closed")
        if value not in allowed:
            raise ValueError(
                f"Status must be one of: {', '.join(allowed)}. Got: {value}"
            )
        return value

    @validates("entry_price")
    def validate_entry_price(self, key: str, value: float) -> float:
        """Validate entry price is positive."""
        if value is None or value <= 0:
            raise ValueError("Entry price must be positive")
        return value

    @validates("stop_loss")
    def validate_stop_loss(self, key: str, value: float) -> float:
        """Validate stop loss is positive."""
        if value is None or value <= 0:
            raise ValueError("Stop loss must be positive")
        return value

    @validates("target")
    def validate_target(self, key: str, value: float) -> float:
        """Validate target is positive."""
        if value is None or value <= 0:
            raise ValueError("Target must be positive")
        return value

    def __repr__(self) -> str:
        return (
            f"<PositionMonitorState(id={self.id}, user_id={self.user_id}, "
            f"trade_id={self.trade_id}, symbol='{self.symbol}', "
            f"status='{self.status}', unrealized_pnl={self.unrealized_pnl})>"
        )
