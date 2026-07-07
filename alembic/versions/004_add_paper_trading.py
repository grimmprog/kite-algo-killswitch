"""Add paper trading tables

Revision ID: a004
Revises: a003
Create Date: 2024-01-04 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a004"
down_revision = "a003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Paper Accounts table ---
    op.create_table(
        "paper_accounts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("balance", sa.Float(), nullable=False, server_default="40000.0"),
        sa.Column(
            "starting_capital", sa.Float(), nullable=False, server_default="40000.0"
        ),
        sa.Column("total_pnl", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("total_trades", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("winning_trades", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("losing_trades", sa.Integer(), nullable=False, server_default="0"),
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
            name="fk_paper_accounts_user_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("user_id", name="uq_paper_accounts_user_id"),
    )
    op.create_index("idx_paper_accounts_user_id", "paper_accounts", ["user_id"])

    # --- Paper Trades table ---
    op.create_table(
        "paper_trades",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(100), nullable=False),
        sa.Column("strike", sa.Float(), nullable=False),
        sa.Column("option_type", sa.String(2), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=False),
        sa.Column("exit_price", sa.Float(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("stop_loss", sa.Float(), nullable=False),
        sa.Column("target", sa.Float(), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="open"),
        sa.Column("pnl", sa.Float(), nullable=True),
        sa.Column("exit_reason", sa.String(100), nullable=True),
        sa.Column("setup_type", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("closed_at", sa.TIMESTAMP(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_paper_trades_user_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["paper_accounts.id"],
            name="fk_paper_trades_account_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "option_type IN ('CE', 'PE')", name="chk_paper_trades_option_type"
        ),
        sa.CheckConstraint(
            "status IN ('open', 'closed')", name="chk_paper_trades_status"
        ),
    )
    op.create_index("idx_paper_trades_user_id", "paper_trades", ["user_id"])
    op.create_index("idx_paper_trades_status", "paper_trades", ["status"])


def downgrade() -> None:
    # Drop tables in reverse order to respect foreign key dependencies
    op.drop_table("paper_trades")
    op.drop_table("paper_accounts")
