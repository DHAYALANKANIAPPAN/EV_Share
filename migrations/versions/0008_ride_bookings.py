"""on-demand rides: driver picks a hub, host accepts in 2 minutes, arrival, charging time, payment and commission

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-19
"""
import sqlalchemy as sa
from alembic import op

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('bookings', schema=None) as b:
        b.add_column(sa.Column('kind', sa.String(length=10), nullable=False, server_default='slot'))
        b.add_column(sa.Column('ride_stage', sa.String(length=20), nullable=True))
        b.add_column(sa.Column('response_deadline', sa.DateTime(), nullable=True))
        b.add_column(sa.Column('driver_lat', sa.Float(), nullable=True))
        b.add_column(sa.Column('driver_lon', sa.Float(), nullable=True))
        b.add_column(sa.Column('driver_location_at', sa.DateTime(), nullable=True))
        b.add_column(sa.Column('arrived_at', sa.DateTime(), nullable=True))
        b.add_column(sa.Column('arrival_confirmed_at', sa.DateTime(), nullable=True))
        b.add_column(sa.Column('duration_minutes', sa.Integer(), nullable=True))
        b.add_column(sa.Column('platform_fee', sa.Float(), nullable=True))
        b.add_column(sa.Column('hub_amount', sa.Float(), nullable=True))
    # existing bookings: the 20% commission applies to them too
    # CAST to NUMERIC makes ROUND work on Postgres as well as SQLite
    op.execute("UPDATE bookings SET "
               "platform_fee = CAST(ROUND(CAST(estimated_cost * 0.2 AS NUMERIC), 2) AS DOUBLE PRECISION), "
               "hub_amount = estimated_cost - CAST(ROUND(CAST(estimated_cost * 0.2 AS NUMERIC), 2) AS DOUBLE PRECISION) "
               "WHERE hub_amount IS NULL")
    op.create_table(
        'booking_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('booking_id', sa.Integer(), sa.ForeignKey('bookings.id'), nullable=False),
        sa.Column('message', sa.String(length=300), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_booking_events_booking_id', 'booking_events', ['booking_id'])


def downgrade() -> None:
    op.drop_index('ix_booking_events_booking_id', table_name='booking_events')
    op.drop_table('booking_events')
    with op.batch_alter_table('bookings', schema=None) as b:
        for col in ['hub_amount', 'platform_fee', 'duration_minutes', 'arrival_confirmed_at', 'arrived_at',
                    'driver_location_at', 'driver_lon', 'driver_lat', 'response_deadline', 'ride_stage', 'kind']:
            b.drop_column(col)
