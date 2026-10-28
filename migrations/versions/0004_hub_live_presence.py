"""hub live presence

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-28 03:23:47.949343
"""
from alembic import op
import sqlalchemy as sa


revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('live_until', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('live_lat', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('live_lon', sa.Float(), nullable=True))



def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('live_lon')
        batch_op.drop_column('live_lat')
        batch_op.drop_column('live_until')

