"""Position model for the Multi-User Web Trading Platform.

Implements Requirements: 2.1, 2.2, 2.3
"""

from datetime import datetime

from sqlalchemy import Integer, Float, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, validates, relationship

from src.database.base import Base


class Position(Base):
    """Live snapshot of per-user position metrics and Greeks exposure.

    Each user has exactly one position record that aggregates
    net delta, gamma, vega, margin usage, and unrealized PnL.
    """

    __tablename__ = "positions"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # User reference (one position record per user)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    # Greeks exposure
    net_delta: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    net_gamma: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    net_vega: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Risk metrics
    margin_used: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    unrealized_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Metadata
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )

    # Relationships
    user = relationship("User", back_populates="positions")

    # --- Validators ---

    @validates("margin_used")
    def validate_margin_used(self, key: str, value: float) -> float:
        """Validate that margin_used is non-negative."""
        if value is not None and value < 0:
            raise ValueError("margin_used must be >= 0")
        return value

    def __repr__(self) -> str:
        return (
            f"<Position(id={self.id}, user_id={self.user_id}, "
            f"net_delta={self.net_delta}, margin_used={self.margin_used}, "
            f"unrealized_pnl={self.unrealized_pnl})>"
        )
