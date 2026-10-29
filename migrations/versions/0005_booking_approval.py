"""booking approval

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-28 08:58:22.962616
"""
from alembic import op
import sqlalchemy as sa


revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Postgres keeps booking statuses in a native enum type; new values can't be added inside a transaction.
    if op.get_bind().dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE bookingstatus ADD VALUE IF NOT EXISTS 'REQUESTED'")
            op.execute("ALTER TYPE bookingstatus ADD VALUE IF NOT EXISTS 'DECLINED'")
    # Existing CONFIRMED bookings stay confirmed (they count as already accepted by the hub).
    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('accepted_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('decline_reason', sa.Text(), nullable=True))



def downgrade() -> None:
    # (the extra enum values on Postgres are harmless and are left in place)
    op.execute("UPDATE bookings SET status = 'CANCELLED' WHERE status IN ('REQUESTED', 'DECLINED')")
    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.drop_column('decline_reason')
        batch_op.drop_column('accepted_at')

