"""password reset codes: one-time codes now carry a purpose

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-30
"""
import sqlalchemy as sa
from alembic import op

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # existing codes were all email-verification codes, so they get the 'verify' purpose
    with op.batch_alter_table('otp_codes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('purpose', sa.String(length=20), nullable=False, server_default='verify'))


def downgrade() -> None:
    with op.batch_alter_table('otp_codes', schema=None) as batch_op:
        batch_op.drop_column('purpose')
