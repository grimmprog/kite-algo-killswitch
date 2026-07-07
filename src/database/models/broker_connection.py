"""BrokerConnection model for multi-broker credential storage.

Implements Requirements: 2.1, 3.3, 4.2, 5.2, 8.1
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Boolean, DateTime, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.base import Base


class BrokerConnection(Base):
    """Broker connection credentials and configuration per user.

    Stores encrypted credentials, connection status, and auto-login
    configuration for each broker type (kite, dhan) per user.
    """

    __tablename__ = "broker_connections"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key to users
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Broker type: "kite" | "dhan"
    broker_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Encrypted credentials
    access_token_encrypted: Mapped[Optional[str]] = mapped_column(
        String(1000), nullable=True
    )
    client_id_encrypted: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )

    # Kite-specific fields
    token_expiry: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    totp_key_encrypted: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    auto_login_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    last_auto_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    last_auto_login_success: Mapped[Optional[bool]] = mapped_column(
        Boolean, nullable=True
    )

    # Dhan-specific fields
    account_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Common status fields
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="disconnected"
    )
    error_message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )

    # Unique constraint: one connection per broker type per user
    __table_args__ = (
        UniqueConstraint("user_id", "broker_type", name="uq_user_broker"),
    )

    # Relationships
    user = relationship("User", back_populates="broker_connections")

    def __repr__(self) -> str:
        return (
            f"<BrokerConnection(id={self.id}, user_id={self.user_id}, "
            f"broker_type='{self.broker_type}', status='{self.status}')>"
        )
