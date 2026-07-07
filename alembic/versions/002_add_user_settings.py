"""Add user_settings table

Revision ID: a002
Revises: a001
Create Date: 2024-01-02 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a002"
down_revision = "a001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        # Strategy settings - watchlist
        sa.Column("watchlist", sa.JSON(), nullable=False, server_default="[]"),
        # Trading times
        sa.Column(
            "trading_start_time",
            sa.String(10),
            nullable=False,
            server_default="09:15",
        ),
        sa.Column(
            "trading_end_time",
            sa.String(10),
            nullable=False,
            server_default="15:30",
        ),
        # Confidence and trade limits
        sa.Column(
            "confidence_threshold",
            sa.Integer(),
            nullable=False,
            server_default="70",
        ),
        sa.Column(
            "max_trades_per_day",
            sa.Integer(),
            nullable=False,
            server_default="5",
        ),
        sa.Column(
            "max_active_trades",
            sa.Integer(),
            nullable=False,
            server_default="3",
        ),
        # Capital
        sa.Column("capital", sa.Float(), nullable=False, server_default="100000.0"),
        # Lot sizes (JSON dict: symbol -> lot size)
        sa.Column("lot_sizes", sa.JSON(), nullable=False, server_default="{}"),
        # Kill switch thresholds - daily loss
        sa.Column(
            "daily_loss_type",
            sa.String(20),
            nullable=False,
            server_default="percentage",
        ),
        sa.Column(
            "daily_loss_value", sa.Float(), nullable=False, server_default="2.0"
        ),
        # Kill switch thresholds - profit target
        sa.Column(
            "profit_target_type",
            sa.String(20),
            nullable=False,
            server_default="percentage",
        ),
        sa.Column(
            "profit_target_value", sa.Float(), nullable=False, server_default="5.0"
        ),
        # Kill switch thresholds - drawdown
        sa.Column(
            "drawdown_type",
            sa.String(20),
            nullable=False,
            server_default="percentage",
        ),
        sa.Column(
            "drawdown_value", sa.Float(), nullable=False, server_default="3.0"
        ),
        # Profit warning percentage
        sa.Column(
            "profit_warning_pct", sa.Float(), nullable=False, server_default="80.0"
        ),
        # Signal countdown
        sa.Column(
            "signal_countdown_seconds",
            sa.Integer(),
            nullable=False,
            server_default="60",
        ),
        # AI configuration
        sa.Column(
            "ai_provider",
            sa.String(50),
            nullable=False,
            server_default="'openai'",
        ),
        sa.Column(
            "ai_signal_analysis_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column(
            "ai_entry_suggestions_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column(
            "ai_exit_recommendations_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column(
            "ai_market_narrative_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column(
            "ai_trade_review_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column(
            "ai_risk_warnings_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        # Timestamps
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
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
            name="fk_user_settings_user_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("user_id", name="uq_user_settings_user_id"),
        # Constraints
        sa.CheckConstraint(
            "confidence_threshold >= 50 AND confidence_threshold <= 100",
            name="chk_user_settings_confidence_threshold",
        ),
        sa.CheckConstraint(
            "max_trades_per_day >= 1 AND max_trades_per_day <= 10",
            name="chk_user_settings_max_trades_per_day",
        ),
        sa.CheckConstraint(
            "max_active_trades >= 1",
            name="chk_user_settings_max_active_trades",
        ),
        sa.CheckConstraint(
            "capital > 0",
            name="chk_user_settings_capital_positive",
        ),
        sa.CheckConstraint(
            "daily_loss_type IN ('percentage', 'absolute')",
            name="chk_user_settings_daily_loss_type",
        ),
        sa.CheckConstraint(
            "daily_loss_value > 0",
            name="chk_user_settings_daily_loss_value_positive",
        ),
        sa.CheckConstraint(
            "profit_target_type IN ('percentage', 'absolute')",
            name="chk_user_settings_profit_target_type",
        ),
        sa.CheckConstraint(
            "profit_target_value > 0",
            name="chk_user_settings_profit_target_value_positive",
        ),
        sa.CheckConstraint(
            "drawdown_type IN ('percentage', 'absolute')",
            name="chk_user_settings_drawdown_type",
        ),
        sa.CheckConstraint(
            "drawdown_value > 0",
            name="chk_user_settings_drawdown_value_positive",
        ),
        sa.CheckConstraint(
            "signal_countdown_seconds >= 0",
            name="chk_user_settings_signal_countdown_non_negative",
        ),
    )
    op.create_index("idx_user_settings_user_id", "user_settings", ["user_id"])

    # Auto-update updated_at on row modification
    op.execute("""
        CREATE OR REPLACE FUNCTION update_user_settings_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_user_settings_updated_at
            BEFORE UPDATE ON user_settings
            FOR EACH ROW
            EXECUTE FUNCTION update_user_settings_updated_at();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_user_settings_updated_at ON user_settings")
    op.execute("DROP FUNCTION IF EXISTS update_user_settings_updated_at()")
    op.drop_table("user_settings")
