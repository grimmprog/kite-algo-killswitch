"""KillSwitchLog model for the Multi-User Web Trading Platform.

Implements Requirements: 2.4, 6.7
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, validates, relationship

from src.database.base import Base


class KillSwitchLog(Base):
    """Logs of kill switch activations for audit and history.

    Records each kill switch trigger event including the reason,
    loss metrics, and number of positions closed.
    """

    __tablename__ = "killswitch_logs"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # User reference
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )

    # Trigger details
    trigger_reason: Mapped[str] = mapped_column(String(500), nullable=False)
    loss_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    capital_at_trigger: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    positions_closed_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    # Timestamp
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now
    )

    # Relationships
    user: Mapped["User"] = relationship(  # noqa: F821
        "User", back_populates="killswitch_logs"
    )

    # --- Validators ---

    @validates("trigger_reason")
    def validate_trigger_reason(self, key: str, value: str) -> str:
        """Validate that trigger_reason is not empty."""
        if not value or not value.strip():
            raise ValueError("Trigger reason cannot be empty")
        return value

    @validates("positions_closed_count")
    def validate_positions_closed_count(self, key: str, value: int) -> int:
        """Validate that positions_closed_count is non-negative."""
        if value is not None and value < 0:
            raise ValueError("Positions closed count must be non-negative")
        return value

    def __repr__(self) -> str:
        return (
            f"<KillSwitchLog(id={self.id}, user_id={self.user_id}, "
            f"trigger_reason='{self.trigger_reason}', "
            f"positions_closed_count={self.positions_closed_count}, "
            f"timestamp={self.timestamp})>"
        )
