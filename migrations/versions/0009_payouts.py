"""host payouts: one record per finished paid session, marked paid by an admin

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-20
"""
import sqlalchemy as sa
from alembic import op

revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'payouts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('hub_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('booking_id', sa.Integer(), sa.ForeignKey('bookings.id'), nullable=False, unique=True),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('status', sa.String(length=10), nullable=False),
        sa.Column('reference', sa.String(length=120), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('paid_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_payouts_hub_user_id', 'payouts', ['hub_user_id'])


def downgrade() -> None:
    op.drop_index('ix_payouts_hub_user_id', table_name='payouts')
    op.drop_table('payouts')
