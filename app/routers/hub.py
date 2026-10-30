from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import or_, select

from ..config import settings
from ..deps import DB, ApprovedHub
from ..models import Booking, BookingStatus, Charger, utcnow
from ..schemas import DeclineIn, HubOrderOut, LiveIn, LiveOut
from ..services.expiry import expire_unpaid
from ..services.notify import notify
from ..services.live import charger_is_live, distance_m, hub_is_live

router = APIRouter(prefix="/hub", tags=["hub"])


def _my_chargers(db, user) -> list[Charger]:
    return list(db.scalars(select(Charger).where(Charger.owner_id == user.id, Charger.is_active.is_(True))))


def _out(db, user) -> LiveOut:
    chargers = _my_chargers(db, user)
    live = hub_is_live(user)
    return LiveOut(is_live=live, live_until=user.live_until if live else None, chargers_total=len(chargers),
                   chargers_live=sum(charger_is_live(c) for c in chargers) if live else 0,
                   radius_m=settings.live_radius_m, ttl_minutes=settings.live_ttl_minutes)


@router.get("/live", response_model=LiveOut)
def live_status(db: DB, user: ApprovedHub):
    return _out(db, user)


@router.post("/live", response_model=LiveOut)
def go_live(body: LiveIn, db: DB, user: ApprovedHub):
    """Go live (or send a heartbeat). The hub must be physically near at least one of its chargers right now."""
    chargers = _my_chargers(db, user)
    if not chargers:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "List a charger first, then you can go live.")
    user.live_lat, user.live_lon = body.latitude, body.longitude
    if not any(distance_m(user, c) <= settings.live_radius_m for c in chargers):
        user.live_until = user.live_lat = user.live_lon = None  # moved away from every charger: stop taking orders now
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"You don't seem to be at your charger. Move within {settings.live_radius_m} m of it and try again.")
    user.live_until = utcnow() + timedelta(minutes=settings.live_ttl_minutes)
    db.commit()
    return _out(db, user)


@router.post("/offline", response_model=LiveOut)
def go_offline(db: DB, user: ApprovedHub):
    user.live_until = None
    db.commit()
    return _out(db, user)


@router.get("/orders", response_model=list[HubOrderOut])
def orders(db: DB, user: ApprovedHub, scope: Literal["pending", "upcoming", "past"] = "pending"):
    """Bookings on this hub's chargers: new requests, accepted upcoming ones, or history."""
    expire_unpaid(db)
    now = utcnow()
    stmt = select(Booking).join(Charger, Charger.id == Booking.charger_id).where(Charger.owner_id == user.id)
    if scope == "pending":
        stmt = stmt.where(Booking.status == BookingStatus.REQUESTED, Booking.end_time > now).order_by(Booking.created_at)
    elif scope == "upcoming":
        stmt = stmt.where(Booking.status == BookingStatus.CONFIRMED, Booking.end_time > now).order_by(Booking.start_time)
    else:
        stmt = stmt.where(or_(Booking.end_time <= now, Booking.status.in_([BookingStatus.DECLINED, BookingStatus.CANCELLED, BookingStatus.COMPLETED]))).order_by(Booking.start_time.desc()).limit(50)
    return db.scalars(stmt).all()


def _own_order(db, booking_id: int, user) -> Booking:
    booking = db.get(Booking, booking_id)
    if not booking or booking.charger.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    return booking


def _answerable(booking: Booking) -> None:
    if booking.status != BookingStatus.REQUESTED:
        raise HTTPException(status.HTTP_409_CONFLICT, "This request was already answered or has expired.")
    if booking.end_time <= utcnow():
        raise HTTPException(status.HTTP_409_CONFLICT, "That time slot has already passed.")


@router.post("/orders/{booking_id}/accept", response_model=HubOrderOut)
def accept_order(booking_id: int, db: DB, user: ApprovedHub):
    expire_unpaid(db)
    booking = _own_order(db, booking_id, user)
    _answerable(booking)
    booking.status, booking.accepted_at = BookingStatus.CONFIRMED, utcnow()
    db.commit()
    pay = " Open EV Share > My bookings to pay and get directions." if booking.estimated_cost > 0 else " Open EV Share > My bookings for directions."
    notify(booking.driver.email, "Your charging request was accepted",
           f"'{booking.charger.title}' accepted your request.{pay}" + (f" Please pay within {settings.unpaid_hold_minutes} minutes." if booking.estimated_cost > 0 and settings.unpaid_hold_minutes > 0 else ""))
    return booking


@router.post("/orders/{booking_id}/decline", response_model=HubOrderOut)
def decline_order(booking_id: int, body: DeclineIn, db: DB, user: ApprovedHub):
    expire_unpaid(db)
    booking = _own_order(db, booking_id, user)
    _answerable(booking)
    booking.status, booking.decline_reason = BookingStatus.DECLINED, (body.reason or "").strip() or None
    db.commit()
    notify(booking.driver.email, "Your charging request was declined",
           f"'{booking.charger.title}' couldn't take your request." + (f" Reason: {booking.decline_reason}" if booking.decline_reason else "") + " You haven't been charged. You can try another charger.")
    return booking
