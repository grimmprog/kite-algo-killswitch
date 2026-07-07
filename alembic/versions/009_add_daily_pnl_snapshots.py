"""Add daily_pnl_snapshots table.

Revision ID: 009
Create Date: 2026-07-07
"""

from alembic import op
import sqlalchemy as sa

revision = '009'
down_revision = '008_add_broker_connections_and_market_data'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'daily_pnl_snapshots',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), nullable=False, index=True),
        sa.Column('trade_date', sa.Date(), nullable=False, index=True),
        sa.Column('gross_pnl', sa.Float(), nullable=False, default=0.0),
        sa.Column('total_charges', sa.Float(), nullable=False, default=0.0),
        sa.Column('net_pnl', sa.Float(), nullable=False, default=0.0),
        sa.Column('opening_capital', sa.Float(), nullable=False, default=0.0),
        sa.Column('closing_capital', sa.Float(), nullable=False, default=0.0),
        sa.Column('total_trades', sa.Integer(), nullable=False, default=0),
        sa.Column('winning_trades', sa.Integer(), nullable=False, default=0),
        sa.Column('losing_trades', sa.Integer(), nullable=False, default=0),
        sa.Column('max_profit_trade', sa.Float(), default=0.0),
        sa.Column('max_loss_trade', sa.Float(), default=0.0),
        sa.Column('brokerage', sa.Float(), default=0.0),
        sa.Column('stt', sa.Float(), default=0.0),
        sa.Column('exchange_charges', sa.Float(), default=0.0),
        sa.Column('gst', sa.Float(), default=0.0),
        sa.Column('instruments_traded', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('ai_grade', sa.String(10), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    # Unique constraint: one record per user per day
    op.create_unique_constraint(
        'uq_daily_pnl_user_date',
        'daily_pnl_snapshots',
        ['user_id', 'trade_date'],
    )


def downgrade() -> None:
    op.drop_table('daily_pnl_snapshots')
