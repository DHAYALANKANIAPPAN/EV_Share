from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Booking, BookingStatus, Payment, PaymentStatus, utcnow


def expire_unpaid(db: Session) -> int:
    """Cancel confirmed bookings that were never paid within the hold window, freeing their slot.

    Free slots (cost 0) and paid bookings are never expired. Called lazily before reads/writes
    that depend on slot availability, so no background worker is needed.
    """
    if settings.unpaid_hold_minutes <= 0:
        return 0
    cutoff = utcnow() - timedelta(minutes=settings.unpaid_hold_minutes)
    stale = db.scalars(
        select(Booking).outerjoin(Payment, Payment.booking_id == Booking.id).where(
            Booking.status == BookingStatus.CONFIRMED,
            Booking.created_at < cutoff,
            Booking.estimated_cost > 0,
            or_(Payment.id.is_(None), Payment.status == PaymentStatus.PENDING),
        )
    ).all()
    for b in stale:
        b.status = BookingStatus.CANCELLED
    if stale:
        db.commit()
    return len(stale)
