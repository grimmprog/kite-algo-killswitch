"""Add broker_connections and market_data_source_configs tables

Revision ID: a008
Revises: a007
Create Date: 2024-01-08 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a008"
down_revision = "a007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- broker_connections table ---
    op.create_table(
        "broker_connections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("broker_type", sa.String(50), nullable=False),
        sa.Column("access_token_encrypted", sa.String(1000), nullable=True),
        sa.Column("client_id_encrypted", sa.String(500), nullable=True),
        sa.Column("token_expiry", sa.DateTime(), nullable=True),
        sa.Column("totp_key_encrypted", sa.String(500), nullable=True),
        sa.Column(
            "auto_login_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column("last_auto_login_at", sa.DateTime(), nullable=True),
        sa.Column("last_auto_login_success", sa.Boolean(), nullable=True),
        sa.Column("account_name", sa.String(255), nullable=True),
        sa.Column(
            "status",
            sa.String(50),
            nullable=False,
            server_default="disconnected",
        ),
        sa.Column("error_message", sa.String(500), nullable=True),
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
            name="fk_broker_connections_user_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("user_id", "broker_type", name="uq_user_broker"),
    )

    # Indexes for broker_connections
    op.create_index(
        "idx_broker_connections_user_id",
        "broker_connections",
        ["user_id"],
    )

    # Auto-update trigger for broker_connections.updated_at
    op.execute("""
        CREATE OR REPLACE FUNCTION update_broker_connections_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_broker_connections_updated_at
            BEFORE UPDATE ON broker_connections
            FOR EACH ROW
            EXECUTE FUNCTION update_broker_connections_updated_at();
    """)

    # --- market_data_source_configs table ---
    op.create_table(
        "market_data_source_configs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.String(50), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_market_data_source_configs_user_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("user_id", "source_id", name="uq_user_source"),
    )

    # Indexes for market_data_source_configs
    op.create_index(
        "idx_market_data_source_configs_user_id",
        "market_data_source_configs",
        ["user_id"],
    )


def downgrade() -> None:
    # Drop market_data_source_configs
    op.drop_table("market_data_source_configs")

    # Drop broker_connections trigger and function
    op.execute(
        "DROP TRIGGER IF EXISTS trg_broker_connections_updated_at ON broker_connections"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS update_broker_connections_updated_at()"
    )

    # Drop broker_connections
    op.drop_table("broker_connections")
