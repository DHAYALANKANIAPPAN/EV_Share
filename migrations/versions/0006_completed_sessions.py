"""completed sessions

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-29
"""
from alembic import op

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite stores the status as text; Postgres keeps it in a native enum, and new values cannot be added inside a transaction.
    if op.get_bind().dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE bookingstatus ADD VALUE IF NOT EXISTS 'COMPLETED'")


def downgrade() -> None:
    op.execute("UPDATE bookings SET status = 'CONFIRMED' WHERE status = 'COMPLETED'")  # (the enum value stays on Postgres; it is harmless)
