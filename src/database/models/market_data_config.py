"""MarketDataSourceConfig model for per-user data source preferences.

Implements Requirements: 6.6, 8.7
"""

from sqlalchemy import String, Boolean, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class MarketDataSourceConfig(Base):
    """User's market data source configuration.

    Stores which data sources are enabled and their priority order
    for each user. Lower priority value means higher precedence.
    """

    __tablename__ = "market_data_source_configs"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key to users
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Data source identifier: "nsepy" | "yfinance" | "kite_historical" | "dhan_market"
    source_id: Mapped[str] = mapped_column(String(50), nullable=False)

    # Human-readable display name for the source
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Whether this data source is active for the user
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Priority order (lower value = higher priority)
    priority: Mapped[int] = mapped_column(Integer, default=0)

    # Unique constraint: one config per source per user
    __table_args__ = (
        UniqueConstraint("user_id", "source_id", name="uq_user_source"),
    )

    def __repr__(self) -> str:
        return (
            f"<MarketDataSourceConfig(id={self.id}, user_id={self.user_id}, "
            f"source_id='{self.source_id}', enabled={self.enabled}, priority={self.priority})>"
        )
