from datetime import timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Booking, BookingStatus, Payment, PaymentStatus, utcnow


def expire_unpaid(db: Session) -> int:
    """Release slots nobody is using, called lazily before reads/writes (no background worker needed):
    - REQUESTED bookings the hub did not answer within `hub_response_minutes`;
    - CONFIRMED (accepted) bookings the driver did not pay within `unpaid_hold_minutes` of the acceptance.
    Free slots and paid bookings are never expired."""
    now, changed = utcnow(), 0
    if settings.hub_response_minutes > 0:
        for b in db.scalars(select(Booking).where(Booking.status == BookingStatus.REQUESTED,
                                                  Booking.created_at < now - timedelta(minutes=settings.hub_response_minutes))):
            b.status, b.decline_reason = BookingStatus.CANCELLED, "The hub didn't respond in time."
            changed += 1
    if settings.unpaid_hold_minutes > 0:
        stale = db.scalars(select(Booking).outerjoin(Payment, Payment.booking_id == Booking.id).where(
            Booking.status == BookingStatus.CONFIRMED,
            func.coalesce(Booking.accepted_at, Booking.created_at) < now - timedelta(minutes=settings.unpaid_hold_minutes),
            Booking.estimated_cost > 0,
            or_(Payment.id.is_(None), Payment.status == PaymentStatus.PENDING)))
        for b in stale:
            b.status, b.decline_reason = BookingStatus.CANCELLED, "Payment wasn't completed in time."
            changed += 1
    if changed:
        db.commit()
    return changed
