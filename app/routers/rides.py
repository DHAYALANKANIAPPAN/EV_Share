from datetime import timedelta

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from ..config import settings
from ..deps import DB, ApprovedDriver, ApprovedHub, CurrentUser
from ..models import Booking, BookingEvent, BookingStatus, Charger, utcnow
from ..schemas import DurationIn, DurationQuoteOut, LocationIn, RideCreate, RideDetailOut, RideOut
from ..services.availability import fits_window, window_label
from ..services.events import log
from ..services.expiry import expire_unpaid
from ..services.geo import haversine_km
from ..services.live import charger_is_live
from ..services.money import split
from ..services.notify import notify

router = APIRouter(prefix="/rides", tags=["rides"])


def _metres(lat1, lon1, lat2, lon2) -> float:
    return haversine_km(lat1, lon1, lat2, lon2) * 1000


def _own_ride(db, ride_id: int, user) -> Booking:
    booking = db.get(Booking, ride_id)
    if not booking or booking.kind != "ride":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ride not found")
    if booking.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the driver of this ride can do that")
    return booking


@router.post("", response_model=RideOut, status_code=status.HTTP_201_CREATED)
def request_ride(body: RideCreate, db: DB, user: ApprovedDriver):
    """Ask a live hub to take you now. The host has 2 minutes to accept. The charging time is chosen later, after arrival."""
    expire_unpaid(db)
    charger = db.get(Charger, body.charger_id)
    if not charger or not charger.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Charger not found or not available")
    if charger.owner_id == user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot book your own charger")
    if not charger_is_live(charger):
        raise HTTPException(status.HTTP_409_CONFLICT, "This hub is offline right now. Try again when it's live.")
    if body.range_km is not None and _metres(body.latitude, body.longitude, charger.latitude, charger.longitude) > body.range_km * 1000:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "This hub is outside your car's range.")
    now = utcnow()
    end = now + timedelta(minutes=settings.ride_slot_minutes)
    if settings.max_active_bookings > 0:
        active = db.scalar(select(func.count(Booking.id)).where(
            Booking.user_id == user.id, Booking.status.in_([BookingStatus.REQUESTED, BookingStatus.CONFIRMED]), Booking.end_time > now))
        if active >= settings.max_active_bookings:
            raise HTTPException(status.HTTP_409_CONFLICT, "You already have an active booking. Finish or cancel it before booking another.")
    if not fits_window(charger, now, end):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Charger is only available {window_label(charger)}")
    clash = db.scalar(select(Booking.id).where(
        Booking.charger_id == charger.id, Booking.status.in_([BookingStatus.REQUESTED, BookingStatus.CONFIRMED]),
        Booking.start_time < end, Booking.end_time > now).limit(1))
    if clash:
        raise HTTPException(status.HTTP_409_CONFLICT, "This hub is busy right now. Try another hub.")

    fee, hub = split(settings.ride_price_rs)
    booking = Booking(charger_id=charger.id, user_id=user.id, kind="ride", status=BookingStatus.REQUESTED,
                      start_time=now, end_time=end, estimated_cost=settings.ride_price_rs,
                      platform_fee=fee, hub_amount=hub,
                      response_deadline=now + timedelta(minutes=settings.ride_response_minutes),
                      driver_lat=body.latitude, driver_lon=body.longitude, driver_location_at=now)
    db.add(booking)
    db.flush()
    log(db, booking, f"Ride requested. The host has {settings.ride_response_minutes} minutes to accept.")
    db.commit()
    notify(charger.owner.email, "New ride request on EV Share",
           f"{user.name} wants your charger '{charger.title}' now. Accept within {settings.ride_response_minutes} minutes in EV Share > Orders.")
    return booking


@router.get("/{ride_id}", response_model=RideDetailOut)
def get_ride(ride_id: int, db: DB, user: CurrentUser):
    """The ride with its timeline. Visible to the driver and to the host of that charger only."""
    expire_unpaid(db)
    booking = db.get(Booking, ride_id)
    if not booking or booking.kind != "ride":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ride not found")
    if user.id not in (booking.user_id, booking.charger.owner_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your ride")
    detail = RideDetailOut.model_validate(booking)
    events = db.scalars(select(BookingEvent).where(BookingEvent.booking_id == booking.id).order_by(BookingEvent.id)).all()
    detail.events = [{"id": e.id, "message": e.message, "created_at": e.created_at} for e in events]
    return detail


@router.post("/{ride_id}/location", response_model=RideOut)
def share_location(ride_id: int, body: LocationIn, db: DB, user: ApprovedDriver):
    """The driver's live position, sent while on the way. The host sees it on the Orders page."""
    booking = _own_ride(db, ride_id, user)
    if booking.status != BookingStatus.CONFIRMED or booking.ride_stage != "EN_ROUTE":
        raise HTTPException(status.HTTP_409_CONFLICT, "Your location is shared while you are on the way to the hub.")
    booking.driver_lat, booking.driver_lon, booking.driver_location_at = body.latitude, body.longitude, utcnow()
    db.commit()
    return booking


@router.post("/{ride_id}/arrived", response_model=RideOut)
def mark_arrived(ride_id: int, db: DB, user: ApprovedDriver):
    """The driver taps 'I've reached'. Allowed only near the hub, with a recent location."""
    booking = _own_ride(db, ride_id, user)
    if booking.status != BookingStatus.CONFIRMED or booking.ride_stage != "EN_ROUTE":
        raise HTTPException(status.HTTP_409_CONFLICT, "You can mark arrival once the host has accepted and you are on the way.")
    fresh = booking.driver_location_at and booking.driver_location_at >= utcnow() - timedelta(seconds=settings.ride_location_max_age_s)
    if not fresh:
        raise HTTPException(status.HTTP_409_CONFLICT, "Turn on location sharing, then mark arrival.")
    distance = _metres(booking.driver_lat, booking.driver_lon, booking.charger.latitude, booking.charger.longitude)
    if distance > settings.ride_arrival_radius_m:
        raise HTTPException(status.HTTP_409_CONFLICT, f"You are about {round(distance)} m from the hub. Move closer to mark arrival.")
    booking.ride_stage, booking.arrived_at = "ARRIVED", utcnow()
    log(db, booking, "Driver reached the hub. Waiting for the host to confirm arrival.")
    db.commit()
    notify(booking.charger.owner.email, "Driver has arrived",
           f"Your driver has reached '{booking.charger.title}'. Confirm arrival in EV Share > Orders.")
    return booking


@router.post("/{ride_id}/confirm-arrival", response_model=RideOut)
def confirm_arrival(ride_id: int, db: DB, user: ApprovedHub):
    """The host confirms the driver is at the hub. The driver can then choose the charging time."""
    booking = db.get(Booking, ride_id)
    if not booking or booking.kind != "ride" or booking.charger.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ride not found")
    if booking.status != BookingStatus.CONFIRMED or booking.ride_stage != "ARRIVED":
        raise HTTPException(status.HTTP_409_CONFLICT, "The driver has not reached the hub yet.")
    booking.ride_stage, booking.arrival_confirmed_at = "ARRIVAL_CONFIRMED", utcnow()
    log(db, booking, "Host confirmed your arrival. Choose the charging time and pay.")
    db.commit()
    notify(booking.driver.email, "Arrival confirmed",
           "The host confirmed your arrival. Open EV Share > My bookings to choose the charging time and pay.")
    return booking


@router.post("/{ride_id}/duration", response_model=DurationQuoteOut)
def choose_duration(ride_id: int, body: DurationIn, db: DB, user: ApprovedDriver):
    """The driver chooses how long to charge. The amount is calculated from the ride price (Rs 100 per 30 minutes for now)."""
    booking = _own_ride(db, ride_id, user)
    if booking.status != BookingStatus.CONFIRMED or booking.ride_stage != "ARRIVAL_CONFIRMED":
        raise HTTPException(status.HTTP_409_CONFLICT, "Choose the charging time after the host confirms your arrival.")
    step = settings.ride_slot_minutes
    if body.minutes % step != 0 or body.minutes > 4 * step:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Choose charging in steps of {step} minutes, up to {4 * step} minutes.")
    amount = round(settings.ride_price_rs * body.minutes / step, 2)
    fee, hub = split(amount)
    booking.duration_minutes, booking.estimated_cost = body.minutes, amount
    booking.platform_fee, booking.hub_amount = fee, hub
    log(db, booking, f"Charging time chosen: {body.minutes} minutes, Rs {amount:.0f}. Pay to start charging.")
    db.commit()
    return DurationQuoteOut(minutes=body.minutes, amount=amount, platform_fee=fee, hub_amount=hub)
