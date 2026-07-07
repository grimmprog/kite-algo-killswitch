"""TradeJournalEntry model for AI-powered trade analysis and journaling.

Implements Requirements: 7.1
"""

from datetime import datetime, date
from typing import Optional

from sqlalchemy import String, Float, Text, Integer, JSON, TIMESTAMP, Date, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, validates, relationship

from src.database.base import Base


class TradeJournalEntry(Base):
    """AI-analyzed trade journal entry.

    Each entry corresponds to a completed trade and includes
    AI-generated feedback on entry, exit, sizing, and risk management.
    """

    __tablename__ = "trade_journal"

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

    # Trade snapshot
    symbol: Mapped[str] = mapped_column(String(50), nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    exit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    setup_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    trend_direction: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    exit_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # AI analysis fields
    ai_grade: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    ai_entry_feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_exit_feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_sizing_feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_risk_feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_patterns: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default="NOW()"
    )
    trade_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Relationships
    user = relationship("User", back_populates="trade_journal_entries")
    trade = relationship("Trade")

    # --- Validators ---

    @validates("trend_direction")
    def validate_trend_direction(self, key: str, value: Optional[str]) -> Optional[str]:
        """Validate trend direction is one of allowed values."""
        if value is None:
            return value
        allowed = ("bullish", "bearish", "neutral")
        if value not in allowed:
            raise ValueError(
                f"Trend direction must be one of: {', '.join(allowed)}. Got: {value}"
            )
        return value

    @validates("ai_grade")
    def validate_ai_grade(self, key: str, value: Optional[str]) -> Optional[str]:
        """Validate AI grade is one of allowed values."""
        if value is None:
            return value
        allowed = ("A", "B", "C", "D", "F")
        if value not in allowed:
            raise ValueError(
                f"AI grade must be one of: {', '.join(allowed)}. Got: {value}"
            )
        return value

    @validates("confidence_score")
    def validate_confidence_score(self, key: str, value: Optional[float]) -> Optional[float]:
        """Validate confidence score is between 0 and 100."""
        if value is None:
            return value
        if value < 0 or value > 100:
            raise ValueError("Confidence score must be between 0 and 100")
        return value

    def __repr__(self) -> str:
        return (
            f"<TradeJournalEntry(id={self.id}, user_id={self.user_id}, "
            f"trade_id={self.trade_id}, symbol='{self.symbol}', "
            f"ai_grade='{self.ai_grade}', trade_date={self.trade_date})>"
        )
