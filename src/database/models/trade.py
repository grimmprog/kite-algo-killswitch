"""Trade model for the Multi-User Web Trading Platform.

Implements Requirements: 1.1, 2.1, 2.2, 2.3
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Float, Integer, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, validates, relationship

from src.database.base import Base


class Trade(Base):
    """Trade records for the multi-user web trading platform.

    Each trade belongs to a user and tracks entry/exit prices,
    P&L, margin usage, and risk snapshots.
    """

    __tablename__ = "trades"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key to users
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Trade details
    symbol: Mapped[str] = mapped_column(String(50), nullable=False)
    exchange: Mapped[str] = mapped_column(String(10), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False)

    # Pricing
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    exit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Risk tracking
    margin_used: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    risk_snapshot_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Status
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")

    # Timestamps
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, index=True
    )
    exit_timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )

    # Relationships
    user = relationship("User", back_populates="trades")

    # --- Validators ---

    @validates("symbol")
    def validate_symbol(self, key: str, value: str) -> str:
        """Validate that symbol is non-empty."""
        if not value or not value.strip():
            raise ValueError("Symbol cannot be empty")
        return value

    @validates("exchange")
    def validate_exchange(self, key: str, value: str) -> str:
        """Validate that exchange is one of the allowed values."""
        allowed = ("NSE", "NFO", "BSE", "BFO")
        if value not in allowed:
            raise ValueError(
                f"Exchange must be one of: {', '.join(allowed)}. Got: {value}"
            )
        return value

    @validates("qty")
    def validate_qty(self, key: str, value: int) -> int:
        """Validate that quantity is non-zero."""
        if value == 0:
            raise ValueError("Quantity cannot be zero")
        return value

    @validates("entry_price")
    def validate_entry_price(self, key: str, value: float) -> float:
        """Validate that entry price is positive."""
        if value is None or value <= 0:
            raise ValueError("Entry price must be positive")
        return value

    @validates("side")
    def validate_side(self, key: str, value: str) -> str:
        """Validate that side is BUY or SELL."""
        allowed = ("BUY", "SELL")
        if value not in allowed:
            raise ValueError(
                f"Side must be one of: {', '.join(allowed)}. Got: {value}"
            )
        return value

    @validates("status")
    def validate_status(self, key: str, value: str) -> str:
        """Validate that status is OPEN or CLOSED."""
        allowed = ("OPEN", "CLOSED")
        if value not in allowed:
            raise ValueError(
                f"Status must be one of: {', '.join(allowed)}. Got: {value}"
            )
        return value

    def __repr__(self) -> str:
        return (
            f"<Trade(id={self.id}, user_id={self.user_id}, "
            f"symbol='{self.symbol}', side='{self.side}', "
            f"qty={self.qty}, entry_price={self.entry_price}, "
            f"status='{self.status}')>"
        )
