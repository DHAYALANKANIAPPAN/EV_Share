from ..models import BookingEvent


def log(db, booking, message: str) -> None:
    """Add a short message to a booking's timeline. Shown to the driver and the host, e.g. 'Driver reached the hub'."""
    db.add(BookingEvent(booking_id=booking.id, message=message[:300]))
