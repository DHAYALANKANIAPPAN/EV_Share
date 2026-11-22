from datetime import timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Booking, BookingStatus, Payment, PaymentStatus, utcnow


def expire_unpaid(db: Session) -> int:
    """Release bookings nobody is acting on. Checked lazily before reads and writes (no background worker needed):
    - requests the host did not answer in time (2 minutes for rides, the host window for slots);
    - accepted slot bookings the driver did not pay for in time;
    - rides the driver never reached in time, and rides whose arrival was confirmed but not paid in time.
    Paid bookings are never expired."""
    now, changed = utcnow(), 0
    for b in db.scalars(select(Booking).where(Booking.status == BookingStatus.REQUESTED)):
        deadline = b.response_deadline
        if deadline is None and settings.hub_response_minutes > 0:
            deadline = b.created_at + timedelta(minutes=settings.hub_response_minutes)
        if deadline is not None and deadline < now:
            b.status, b.decline_reason = BookingStatus.CANCELLED, "The host didn't respond in time."
            changed += 1
    unpaid = or_(Payment.id.is_(None), Payment.status == PaymentStatus.PENDING)
    if settings.unpaid_hold_minutes > 0:
        stale = db.scalars(select(Booking).outerjoin(Payment, Payment.booking_id == Booking.id).where(
            Booking.kind == "slot", Booking.status == BookingStatus.CONFIRMED,
            func.coalesce(Booking.accepted_at, Booking.created_at) < now - timedelta(minutes=settings.unpaid_hold_minutes),
            Booking.estimated_cost > 0, unpaid))
        for b in stale:
            b.status, b.decline_reason = BookingStatus.CANCELLED, "Payment wasn't completed in time."
            changed += 1
        stale_rides = db.scalars(select(Booking).outerjoin(Payment, Payment.booking_id == Booking.id).where(
            Booking.kind == "ride", Booking.status == BookingStatus.CONFIRMED, Booking.ride_stage == "ARRIVAL_CONFIRMED",
            Booking.arrival_confirmed_at < now - timedelta(minutes=settings.unpaid_hold_minutes), unpaid))
        for b in stale_rides:
            b.status, b.decline_reason = BookingStatus.CANCELLED, "Payment wasn't completed in time."
            changed += 1
    for b in db.scalars(select(Booking).where(
            Booking.kind == "ride", Booking.status == BookingStatus.CONFIRMED, Booking.ride_stage == "EN_ROUTE",
            Booking.accepted_at < now - timedelta(minutes=settings.ride_en_route_max_minutes))):
        b.status, b.decline_reason = BookingStatus.CANCELLED, "The driver didn't reach the hub in time."
        changed += 1
    if changed:
        db.commit()
    return changed
