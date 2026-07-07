"""Paper trading models for simulated trading accounts and trades.

Implements Requirements: 11.1
"""

from datetime import datetime
from typing import Optional, List

from sqlalchemy import String, Float, Integer, TIMESTAMP, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, validates, relationship

from src.database.base import Base


class PaperAccount(Base):
    """Paper trading account for simulated trading.

    Each user has one paper account with a virtual balance
    and aggregate trade statistics.
    """

    __tablename__ = "paper_accounts"

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

    # Account balance and capital
    balance: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="40000.0"
    )
    starting_capital: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="40000.0"
    )

    # Aggregate stats
    total_pnl: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="0.0"
    )
    total_trades: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    winning_trades: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    losing_trades: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default="NOW()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default="NOW()"
    )

    # Relationships
    user = relationship("User", back_populates="paper_account")
    paper_trades: Mapped[List["PaperTrade"]] = relationship(
        "PaperTrade", back_populates="account", lazy="dynamic"
    )

    def __repr__(self) -> str:
        return (
            f"<PaperAccount(id={self.id}, user_id={self.user_id}, "
            f"balance={self.balance}, total_trades={self.total_trades})>"
        )


class PaperTrade(Base):
    """Individual paper trade within a paper trading account.

    Tracks simulated option trades with entry/exit prices,
    stop loss, target, and P&L.
    """

    __tablename__ = "paper_trades"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign keys
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("paper_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Trade details
    symbol: Mapped[str] = mapped_column(String(100), nullable=False)
    strike: Mapped[float] = mapped_column(Float, nullable=False)
    option_type: Mapped[str] = mapped_column(String(2), nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    exit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=False)
    target: Mapped[float] = mapped_column(Float, nullable=False)

    # Status and results
    status: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="open", index=True
    )
    pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    exit_reason: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    setup_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default="NOW()"
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)

    # Relationships
    user = relationship("User")
    account = relationship("PaperAccount", back_populates="paper_trades")

    # --- Validators ---

    @validates("option_type")
    def validate_option_type(self, key: str, value: str) -> str:
        """Validate option type is CE or PE."""
        allowed = ("CE", "PE")
        if value not in allowed:
            raise ValueError(
                f"Option type must be one of: {', '.join(allowed)}. Got: {value}"
            )
        return value

    @validates("status")
    def validate_status(self, key: str, value: str) -> str:
        """Validate status is open or closed."""
        allowed = ("open", "closed")
        if value not in allowed:
            raise ValueError(
                f"Status must be one of: {', '.join(allowed)}. Got: {value}"
            )
        return value

    def __repr__(self) -> str:
        return (
            f"<PaperTrade(id={self.id}, user_id={self.user_id}, "
            f"symbol='{self.symbol}', option_type='{self.option_type}', "
            f"status='{self.status}', pnl={self.pnl})>"
        )
