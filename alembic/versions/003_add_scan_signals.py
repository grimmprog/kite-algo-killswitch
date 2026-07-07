"""Add scan_signals table

Revision ID: a003
Revises: a002
Create Date: 2024-01-03 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a003"
down_revision = "a002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scan_signals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "signal_type",
            sa.String(50),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(50), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=False),
        sa.Column("stop_loss", sa.Float(), nullable=False),
        sa.Column("target_price", sa.Float(), nullable=False),
        sa.Column("max_potential_loss", sa.Float(), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "countdown_seconds",
            sa.Integer(),
            nullable=False,
            server_default="60",
        ),
        sa.Column("expires_at", sa.TIMESTAMP(), nullable=True),
        # AI fields
        sa.Column("ai_quality_rating", sa.String(50), nullable=True),
        sa.Column("ai_warnings", sa.JSON(), nullable=True),
        sa.Column("ai_explanation", sa.Text(), nullable=True),
        # Additional metadata
        sa.Column("metadata", sa.JSON(), nullable=True),
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
            name="fk_scan_signals_user_id",
            ondelete="CASCADE",
        ),
        # Constraints
        sa.CheckConstraint(
            "signal_type IN ('trend_pullback', 'consolidation_breakout')",
            name="chk_scan_signals_signal_type",
        ),
        sa.CheckConstraint(
            "confidence_score >= 50 AND confidence_score <= 100",
            name="chk_scan_signals_confidence_score",
        ),
        sa.CheckConstraint(
            "entry_price > 0",
            name="chk_scan_signals_entry_price_positive",
        ),
        sa.CheckConstraint(
            "stop_loss > 0",
            name="chk_scan_signals_stop_loss_positive",
        ),
        sa.CheckConstraint(
            "target_price > 0",
            name="chk_scan_signals_target_price_positive",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'expired')",
            name="chk_scan_signals_status",
        ),
        sa.CheckConstraint(
            "countdown_seconds >= 0",
            name="chk_scan_signals_countdown_non_negative",
        ),
    )
    # Indexes
    op.create_index("idx_scan_signals_user_id", "scan_signals", ["user_id"])
    op.create_index("idx_scan_signals_status", "scan_signals", ["status"])
    op.create_index("idx_scan_signals_symbol", "scan_signals", ["symbol"])

    # Auto-update updated_at on row modification
    op.execute("""
        CREATE OR REPLACE FUNCTION update_scan_signals_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_scan_signals_updated_at
            BEFORE UPDATE ON scan_signals
            FOR EACH ROW
            EXECUTE FUNCTION update_scan_signals_updated_at();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_scan_signals_updated_at ON scan_signals")
    op.execute("DROP FUNCTION IF EXISTS update_scan_signals_updated_at()")
    op.drop_table("scan_signals")
