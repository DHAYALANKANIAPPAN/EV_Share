from datetime import timedelta

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from ..config import settings
from ..deps import DB, ApprovedDriver, CurrentUser
from ..models import Booking, BookingStatus, Charger, utcnow
from ..schemas import BookingCreate, BookingOut
from ..services.availability import fits_window, window_label
from ..services.expiry import expire_unpaid
from ..services.bookings import cancel_with_refund
from ..services.live import charger_is_live
from ..services.notify import notify

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
    if settings.max_active_bookings > 0:
        active = db.scalar(select(func.count(Booking.id)).where(
            Booking.user_id == user.id, Booking.status.in_([BookingStatus.REQUESTED, BookingStatus.CONFIRMED]), Booking.end_time > utcnow()))
        if active >= settings.max_active_bookings:
            raise HTTPException(status.HTTP_409_CONFLICT, "You already have an active booking. Finish or cancel it before booking another.")
    if not charger_is_live(charger):
        raise HTTPException(status.HTTP_409_CONFLICT, "This hub is offline right now and can't take new bookings. Try again when it's live.")
    if not fits_window(charger, body.start_time, body.end_time):
        raise HTTPException(422, f"Charger is only available {window_label(charger)}")

    clash = db.scalar(
        select(Booking.id).where(
            Booking.charger_id == charger.id,
            Booking.status.in_([BookingStatus.REQUESTED, BookingStatus.CONFIRMED]),
            Booking.start_time < body.end_time,
            Booking.end_time > body.start_time,
        ).limit(1)
    )
    if clash:
        raise HTTPException(status.HTTP_409_CONFLICT, "That time slot is already booked")

    hours = duration.total_seconds() / 3600
    # Slot price: charger running at full power for the whole slot (no metering yet).
    cost = round(charger.power_kw * hours * charger.price_per_kwh, 2)
    booking = Booking(charger_id=charger.id, user_id=user.id, start_time=body.start_time, end_time=body.end_time,
                      estimated_cost=cost, status=BookingStatus.REQUESTED)
    db.add(booking)
    db.commit()
    notify(charger.owner.email, "New charging request on EV Share",
           f"{user.name} asked to use '{charger.title}'. Open EV Share > Orders to accept or decline within {settings.hub_response_minutes} minutes.")
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
    if booking.status not in (BookingStatus.REQUESTED, BookingStatus.CONFIRMED):
        raise HTTPException(status.HTTP_409_CONFLICT, "This booking is already closed.")

    cancel_with_refund(booking)
    db.commit()
    return booking


@router.post("/{booking_id}/finish", response_model=BookingOut)
def finish_session(booking_id: int, db: DB, user: CurrentUser):
    """Mark a running session as done (by the driver or the hub). The charger becomes free for other drivers straight away."""
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")
    if user.id not in (booking.user_id, booking.charger.owner_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed to finish this session")
    if booking.status != BookingStatus.CONFIRMED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only an accepted booking can be marked as done.")
    now = utcnow()
    if booking.start_time > now:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This session hasn't started yet. Cancel it instead if you no longer need it.")
    if booking.estimated_cost > 0 and booking.payment_status != "PAID":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This booking hasn't been paid yet.")
    booking.status = BookingStatus.COMPLETED
    booking.end_time = min(booking.end_time, now)  # frees whatever was left of the slot
    db.commit()
    return booking
