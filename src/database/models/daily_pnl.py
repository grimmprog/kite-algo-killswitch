"""Daily P&L Snapshot model — stores end-of-day trading performance.

Used for:
- Historical P&L tracking per day
- AI analysis of trading patterns over time
- Capital growth/drawdown visualization
"""

from datetime import date, datetime

from sqlalchemy import Column, Date, DateTime, Float, Integer, String, Text
from sqlalchemy.sql import func

from src.database.base import Base


class DailyPnLSnapshot(Base):
    """Stores daily profit/loss and capital snapshots for each user.

    One row per user per trading day. Captures everything needed
    for AI analysis: P&L, capital, trade count, win rate, charges.
    """

    __tablename__ = "daily_pnl_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    trade_date = Column(Date, nullable=False, index=True)

    # P&L
    gross_pnl = Column(Float, nullable=False, default=0.0)
    total_charges = Column(Float, nullable=False, default=0.0)
    net_pnl = Column(Float, nullable=False, default=0.0)

    # Capital
    opening_capital = Column(Float, nullable=False, default=0.0)
    closing_capital = Column(Float, nullable=False, default=0.0)

    # Trade stats
    total_trades = Column(Integer, nullable=False, default=0)
    winning_trades = Column(Integer, nullable=False, default=0)
    losing_trades = Column(Integer, nullable=False, default=0)
    max_profit_trade = Column(Float, default=0.0)
    max_loss_trade = Column(Float, default=0.0)

    # Breakdown
    brokerage = Column(Float, default=0.0)
    stt = Column(Float, default=0.0)
    exchange_charges = Column(Float, default=0.0)
    gst = Column(Float, default=0.0)

    # Metadata for AI analysis
    instruments_traded = Column(Text, nullable=True)  # JSON list of symbols
    notes = Column(Text, nullable=True)  # AI-generated daily summary
    ai_grade = Column(String(10), nullable=True)  # AI performance grade (A-F)

    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<DailyPnL user={self.user_id} date={self.trade_date} net={self.net_pnl}>"
