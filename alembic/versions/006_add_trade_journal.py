"""Add trade_journal table

Revision ID: a006
Revises: a005
Create Date: 2024-01-06 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a006"
down_revision = "a005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trade_journal",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("trade_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(50), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=False),
        sa.Column("exit_price", sa.Float(), nullable=True),
        sa.Column("pnl", sa.Float(), nullable=True),
        sa.Column("setup_type", sa.String(100), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("trend_direction", sa.String(20), nullable=True),
        sa.Column("exit_reason", sa.String(255), nullable=True),
        sa.Column("ai_grade", sa.String(2), nullable=True),
        sa.Column("ai_entry_feedback", sa.Text(), nullable=True),
        sa.Column("ai_exit_feedback", sa.Text(), nullable=True),
        sa.Column("ai_sizing_feedback", sa.Text(), nullable=True),
        sa.Column("ai_risk_feedback", sa.Text(), nullable=True),
        sa.Column("ai_patterns", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_trade_journal_user_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["trade_id"],
            ["trades.id"],
            name="fk_trade_journal_trade_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "trend_direction IN ('bullish', 'bearish', 'neutral')",
            name="chk_trade_journal_trend_direction",
        ),
        sa.CheckConstraint(
            "ai_grade IN ('A', 'B', 'C', 'D', 'F')",
            name="chk_trade_journal_ai_grade",
        ),
        sa.CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 100",
            name="chk_trade_journal_confidence_score",
        ),
    )
    op.create_index("idx_trade_journal_user_id", "trade_journal", ["user_id"])
    op.create_index("idx_trade_journal_trade_id", "trade_journal", ["trade_id"])
    op.create_index("idx_trade_journal_trade_date", "trade_journal", ["trade_date"])
    op.create_index(
        "idx_trade_journal_user_trade_date",
        "trade_journal",
        ["user_id", "trade_date"],
    )


def downgrade() -> None:
    op.drop_table("trade_journal")
