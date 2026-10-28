"""user removal

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-28 03:20:46.290528
"""
from alembic import op
import sqlalchemy as sa


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column('removed_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('removal_reason', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('removed_by_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_users_removed_by', 'users', ['removed_by_id'], ['id'])



def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint('fk_users_removed_by', type_='foreignkey')
        batch_op.drop_column('removed_by_id')
        batch_op.drop_column('removal_reason')
        batch_op.drop_column('removed_at')
        batch_op.drop_column('is_active')

