"""Add notifications table

Revision ID: a005
Revises: a004
Create Date: 2024-01-05 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a005"
down_revision = "a004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column(
            "is_read", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_notifications_user_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "severity IN ('info', 'warning', 'critical')",
            name="chk_notifications_severity",
        ),
        sa.CheckConstraint(
            "category IN ('signal', 'trade', 'killswitch', 'threshold', 'ai', 'system')",
            name="chk_notifications_category",
        ),
    )

    # Indexes
    op.create_index("idx_notifications_user_id", "notifications", ["user_id"])
    op.create_index(
        "idx_notifications_user_is_read",
        "notifications",
        ["user_id", "is_read"],
    )
    op.create_index(
        "idx_notifications_created_at", "notifications", ["created_at"]
    )


def downgrade() -> None:
    op.drop_table("notifications")
