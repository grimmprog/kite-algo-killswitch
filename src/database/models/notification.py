"""Notification model for user alerts and system messages.

Implements Requirements: 14.1
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Boolean, Text, Integer, JSON, TIMESTAMP, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, validates, relationship

from src.database.base import Base


class Notification(Base):
    """User notifications for signals, trades, kill switch events, and AI insights.

    Notifications have severity levels and categories to support
    filtering and prioritized display.
    """

    __tablename__ = "notifications"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key to users
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Notification content
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)

    # Read state
    is_read: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )

    # Additional metadata
    metadata_json: Mapped[Optional[dict]] = mapped_column(
        "metadata", JSON, nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default="NOW()"
    )

    # Relationships
    user = relationship("User", back_populates="notifications")

    # --- Validators ---

    @validates("severity")
    def validate_severity(self, key: str, value: str) -> str:
        """Validate severity is one of allowed values."""
        allowed = ("info", "warning", "critical")
        if value not in allowed:
            raise ValueError(
                f"Severity must be one of: {', '.join(allowed)}. Got: {value}"
            )
        return value

    @validates("category")
    def validate_category(self, key: str, value: str) -> str:
        """Validate category is one of allowed values."""
        allowed = ("signal", "trade", "killswitch", "threshold", "ai", "system")
        if value not in allowed:
            raise ValueError(
                f"Category must be one of: {', '.join(allowed)}. Got: {value}"
            )
        return value

    def __repr__(self) -> str:
        return (
            f"<Notification(id={self.id}, user_id={self.user_id}, "
            f"severity='{self.severity}', category='{self.category}', "
            f"title='{self.title}', is_read={self.is_read})>"
        )
