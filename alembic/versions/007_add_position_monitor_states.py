"""Add position_monitor_states table

Revision ID: a007
Revises: a006
Create Date: 2024-01-07 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a007"
down_revision = "a006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "position_monitor_states",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("trade_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(50), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=False),
        sa.Column("current_price", sa.Float(), nullable=True),
        sa.Column("stop_loss", sa.Float(), nullable=False),
        sa.Column("target", sa.Float(), nullable=False),
        sa.Column(
            "trailing_stop_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column("trailing_stop_level", sa.Float(), nullable=True),
        sa.Column("trailing_stop_distance", sa.Float(), nullable=True),
        sa.Column(
            "unrealized_pnl", sa.Float(), nullable=False, server_default="0"
        ),
        sa.Column("distance_to_sl_pct", sa.Float(), nullable=True),
        sa.Column("distance_to_target_pct", sa.Float(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
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
            name="fk_position_monitor_states_user_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["trade_id"],
            ["trades.id"],
            name="fk_position_monitor_states_trade_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'sl_hit', 'target_hit', 'trailing_stop_hit', 'closed')",
            name="chk_position_monitor_states_status",
        ),
        sa.CheckConstraint(
            "entry_price > 0",
            name="chk_position_monitor_states_entry_price_positive",
        ),
        sa.CheckConstraint(
            "stop_loss > 0",
            name="chk_position_monitor_states_stop_loss_positive",
        ),
        sa.CheckConstraint(
            "target > 0",
            name="chk_position_monitor_states_target_positive",
        ),
    )

    # Indexes
    op.create_index(
        "idx_position_monitor_states_user_id",
        "position_monitor_states",
        ["user_id"],
    )
    op.create_index(
        "idx_position_monitor_states_trade_id",
        "position_monitor_states",
        ["trade_id"],
    )
    op.create_index(
        "idx_position_monitor_states_status",
        "position_monitor_states",
        ["status"],
    )
    op.create_index(
        "idx_position_monitor_states_user_status",
        "position_monitor_states",
        ["user_id", "status"],
    )

    # Auto-update trigger for updated_at
    op.execute("""
        CREATE OR REPLACE FUNCTION update_position_monitor_states_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_position_monitor_states_updated_at
            BEFORE UPDATE ON position_monitor_states
            FOR EACH ROW
            EXECUTE FUNCTION update_position_monitor_states_updated_at();
    """)


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_position_monitor_states_updated_at ON position_monitor_states"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS update_position_monitor_states_updated_at()"
    )
    op.drop_table("position_monitor_states")
