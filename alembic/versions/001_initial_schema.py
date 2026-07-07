"""Initial schema - create all tables

Revision ID: a001
Revises: None
Create Date: 2024-01-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Users table ---
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("capital", sa.Float(), nullable=False, server_default="100000.0"),
        sa.Column(
            "risk_profile",
            sa.String(50),
            nullable=False,
            server_default="moderate",
        ),
        sa.Column(
            "daily_loss_limit_percent",
            sa.Float(),
            nullable=False,
            server_default="2.0",
        ),
        sa.Column(
            "max_trade_risk_percent",
            sa.Float(),
            nullable=False,
            server_default="1.0",
        ),
        sa.Column(
            "killswitch_state",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column("broker_access_token", sa.String(500), nullable=True),
        sa.Column("broker_refresh_token", sa.String(500), nullable=True),
        sa.Column("broker_token_expiry", sa.TIMESTAMP(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("last_login", sa.TIMESTAMP(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.CheckConstraint("capital > 0", name="chk_users_capital_positive"),
        sa.CheckConstraint(
            "risk_profile IN ('conservative', 'moderate', 'aggressive')",
            name="chk_users_risk_profile",
        ),
        sa.CheckConstraint(
            "daily_loss_limit_percent >= 0.5 AND daily_loss_limit_percent <= 10.0",
            name="chk_users_daily_loss_limit",
        ),
        sa.CheckConstraint(
            "max_trade_risk_percent >= 0.1 AND max_trade_risk_percent <= 5.0",
            name="chk_users_max_trade_risk",
        ),
    )
    op.create_index("idx_users_email", "users", ["email"])

    # --- Trades table ---
    op.create_table(
        "trades",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(50), nullable=False),
        sa.Column("exchange", sa.String(10), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.Column("side", sa.String(10), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=False),
        sa.Column("exit_price", sa.Float(), nullable=True),
        sa.Column("pnl", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("margin_used", sa.Float(), nullable=True),
        sa.Column("risk_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"),
        sa.Column(
            "timestamp",
            sa.TIMESTAMP(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("exit_timestamp", sa.TIMESTAMP(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_trades_user_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "LENGTH(TRIM(symbol)) > 0", name="chk_trades_symbol_non_empty"
        ),
        sa.CheckConstraint(
            "exchange IN ('NSE', 'NFO', 'BSE', 'BFO')", name="chk_trades_exchange"
        ),
        sa.CheckConstraint("qty != 0", name="chk_trades_qty_non_zero"),
        sa.CheckConstraint("entry_price > 0", name="chk_trades_entry_price_positive"),
        sa.CheckConstraint("side IN ('BUY', 'SELL')", name="chk_trades_side"),
        sa.CheckConstraint(
            "status IN ('OPEN', 'CLOSED')", name="chk_trades_status"
        ),
    )
    op.create_index("idx_trades_user_id", "trades", ["user_id"])
    op.create_index("idx_trades_timestamp", "trades", ["timestamp"])
    op.create_index("idx_trades_user_status", "trades", ["user_id", "status"])

    # --- Positions table ---
    op.create_table(
        "positions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("net_delta", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("net_gamma", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("net_vega", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("margin_used", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("unrealized_pnl", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_positions_user",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("user_id", name="uq_positions_user_id"),
        sa.CheckConstraint(
            "margin_used >= 0", name="chk_positions_margin_non_negative"
        ),
    )
    op.create_index("idx_positions_user_id", "positions", ["user_id"])

    # Create the trigger function and trigger for positions.updated_at
    op.execute("""
        CREATE OR REPLACE FUNCTION update_positions_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_positions_updated_at
            BEFORE UPDATE ON positions
            FOR EACH ROW
            EXECUTE FUNCTION update_positions_updated_at();
    """)

    # --- Orders table ---
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("broker_order_id", sa.String(100), nullable=True),
        sa.Column("symbol", sa.String(50), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="PENDING"
        ),
        sa.Column("retries", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.String(500), nullable=True),
        sa.Column(
            "timestamp",
            sa.TIMESTAMP(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_orders_user",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "LENGTH(TRIM(symbol)) > 0", name="chk_orders_symbol_non_empty"
        ),
        sa.CheckConstraint("qty > 0", name="chk_orders_qty_positive"),
        sa.CheckConstraint(
            "status IN ('PENDING', 'COMPLETE', 'REJECTED', 'CANCELLED')",
            name="chk_orders_status",
        ),
        sa.CheckConstraint("retries >= 0", name="chk_orders_retries_non_negative"),
    )
    op.create_index("idx_orders_user_id", "orders", ["user_id"])

    # --- KillSwitch Logs table ---
    op.create_table(
        "killswitch_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("trigger_reason", sa.String(500), nullable=False),
        sa.Column("loss_percent", sa.Float(), nullable=True),
        sa.Column("capital_at_trigger", sa.Float(), nullable=True),
        sa.Column(
            "positions_closed_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "timestamp",
            sa.TIMESTAMP(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_killswitch_logs_user",
        ),
        sa.CheckConstraint(
            "LENGTH(TRIM(trigger_reason)) > 0",
            name="chk_killswitch_logs_trigger_reason_nonempty",
        ),
        sa.CheckConstraint(
            "positions_closed_count >= 0",
            name="chk_killswitch_logs_positions_closed_nonneg",
        ),
    )
    op.create_index("idx_killswitch_logs_user_id", "killswitch_logs", ["user_id"])


def downgrade() -> None:
    # Drop tables in reverse order to respect foreign key dependencies
    op.drop_table("killswitch_logs")
    op.drop_table("orders")

    # Drop trigger and function before dropping positions table
    op.execute("DROP TRIGGER IF EXISTS trg_positions_updated_at ON positions")
    op.execute("DROP FUNCTION IF EXISTS update_positions_updated_at()")
    op.drop_table("positions")

    op.drop_table("trades")
    op.drop_table("users")
