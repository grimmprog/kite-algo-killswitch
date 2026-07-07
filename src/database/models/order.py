"""Order model for the Multi-User Web Trading Platform.

Implements Requirements: 1.1, 7.1, 7.4
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Float, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, validates, relationship

from src.database.base import Base

# Valid order statuses
VALID_ORDER_STATUSES = ("PENDING", "COMPLETE", "REJECTED", "CANCELLED")


class Order(Base):
    """Order records for trade execution tracking.

    Each order belongs to a user and tracks broker order placement,
    status updates, retries, and error messages.
    """

    __tablename__ = "orders"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # User reference
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Order details
    broker_order_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    symbol: Mapped[str] = mapped_column(String(50), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Status tracking
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING"
    )
    retries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )

    # Metadata
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="orders")  # noqa: F821

    # --- Validators ---

    @validates("symbol")
    def validate_symbol(self, key: str, value: str) -> str:
        """Validate that symbol is non-empty."""
        if not value or not value.strip():
            raise ValueError("Symbol cannot be empty")
        return value

    @validates("qty")
    def validate_qty(self, key: str, value: int) -> int:
        """Validate that quantity is positive."""
        if value is None or value <= 0:
            raise ValueError("Quantity must be positive")
        return value

    @validates("status")
    def validate_status(self, key: str, value: str) -> str:
        """Validate that status is one of the allowed values."""
        if value not in VALID_ORDER_STATUSES:
            raise ValueError(
                f"Status must be one of: {', '.join(VALID_ORDER_STATUSES)}. "
                f"Got: {value}"
            )
        return value

    @validates("retries")
    def validate_retries(self, key: str, value: int) -> int:
        """Validate that retries is non-negative."""
        if value is None or value < 0:
            raise ValueError("Retries must be non-negative")
        return value

    def __repr__(self) -> str:
        return (
            f"<Order(id={self.id}, user_id={self.user_id}, "
            f"symbol='{self.symbol}', qty={self.qty}, "
            f"status='{self.status}')>"
        )
