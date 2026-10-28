from datetime import timedelta

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from ..config import settings
from ..deps import DB, ApprovedDriver, CurrentUser
from ..models import Booking, BookingStatus, Charger, utcnow
from ..schemas import BookingCreate, BookingOut
from ..services.availability import fits_window, window_label
from ..services.expiry import expire_unpaid
from ..services.bookings import cancel_with_refund
from ..services.live import charger_is_live

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.post("", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
def create_booking(body: BookingCreate, db: DB, user: ApprovedDriver):
    if body.end_time <= body.start_time:
        raise HTTPException(422, "end_time must be after start_time")
    if body.start_time < utcnow():
        raise HTTPException(422, "start_time must be in the future")
    duration = body.end_time - body.start_time
    if duration > timedelta(hours=settings.max_booking_hours):
        raise HTTPException(422, f"A booking can be at most {settings.max_booking_hours} hours")

    expire_unpaid(db)
    charger = db.get(Charger, body.charger_id)
    if not charger or not charger.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Charger not found or not available")
    if charger.owner_id == user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot book your own charger")
    if not charger_is_live(charger):
        raise HTTPException(status.HTTP_409_CONFLICT, "This hub is offline right now and can't take new bookings. Try again when it's live.")
    if not fits_window(charger, body.start_time, body.end_time):
        raise HTTPException(422, f"Charger is only available {window_label(charger)}")

    clash = db.scalar(
        select(Booking.id).where(
            Booking.charger_id == charger.id,
            Booking.status == BookingStatus.CONFIRMED,
            Booking.start_time < body.end_time,
            Booking.end_time > body.start_time,
        ).limit(1)
    )
    if clash:
        raise HTTPException(status.HTTP_409_CONFLICT, "That time slot is already booked")

    hours = duration.total_seconds() / 3600
    # Slot price: charger running at full power for the whole slot (no metering yet).
    cost = round(charger.power_kw * hours * charger.price_per_kwh, 2)
    booking = Booking(charger_id=charger.id, user_id=user.id, start_time=body.start_time,
                      end_time=body.end_time, estimated_cost=cost)
    db.add(booking)
    db.commit()
    return booking


@router.get("/mine", response_model=list[BookingOut])
def my_bookings(db: DB, user: CurrentUser):
    expire_unpaid(db)
    return db.scalars(select(Booking).where(Booking.user_id == user.id).order_by(Booking.start_time.desc())).all()


@router.get("/charger/{charger_id}", response_model=list[BookingOut])
def charger_bookings(charger_id: int, db: DB, user: CurrentUser):
    """Bookings on a charger. Only visible to its owner."""
    expire_unpaid(db)
    charger = db.get(Charger, charger_id)
    if not charger:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Charger not found")
    if charger.owner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can view these bookings")
    return db.scalars(select(Booking).where(Booking.charger_id == charger_id).order_by(Booking.start_time)).all()


@router.post("/{booking_id}/cancel", response_model=BookingOut)
def cancel_booking(booking_id: int, db: DB, user: CurrentUser):
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")
    if user.id not in (booking.user_id, booking.charger.owner_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed to cancel this booking")
    if booking.status == BookingStatus.CANCELLED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Booking already cancelled")

    cancel_with_refund(booking)
    db.commit()
    return booking
