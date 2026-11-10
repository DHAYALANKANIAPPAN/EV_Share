import asyncio
import json

from fastapi.responses import StreamingResponse
from sqlalchemy import func
from starlette.concurrency import run_in_threadpool

from ..database import SessionLocal
from ..models import Payment, PaymentStatus, Review
from ..schemas import ChargerStatOut, DailyOut, DashboardOut
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
    if settings.max_active_hub_bookings > 0:
        busy = db.scalar(select(func.count(Booking.id)).join(Charger, Charger.id == Booking.charger_id).where(
            Charger.owner_id == user.id, Booking.status == BookingStatus.CONFIRMED, Booking.end_time > utcnow(), Booking.id != booking.id))
        if busy >= settings.max_active_hub_bookings:
            raise HTTPException(status.HTTP_409_CONFLICT, "You already have an accepted booking in progress or coming up. Finish or cancel it before accepting another.")
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


def order_counts(db, user_id: int) -> dict:
    """How many requests, upcoming and running bookings this hub has. The stream sends these when they change."""
    now = utcnow()
    base = select(func.count(Booking.id)).join(Charger, Charger.id == Booking.charger_id).where(Charger.owner_id == user_id)
    return {
        "pending": db.scalar(base.where(Booking.status == BookingStatus.REQUESTED, Booking.end_time > now)),
        "upcoming": db.scalar(base.where(Booking.status == BookingStatus.CONFIRMED, Booking.start_time > now)),
        "running": db.scalar(base.where(Booking.status == BookingStatus.CONFIRMED, Booking.start_time <= now, Booking.end_time > now)),
    }


def sse_frame(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


@router.get("/stream")
async def order_stream(user: ApprovedHub):
    """Live updates for the Orders page (server-sent events). The browser reconnects by itself if the connection drops."""
    user_id = user.id

    def snapshot():
        with SessionLocal() as s:
            expire_unpaid(s)
            return order_counts(s, user_id)

    async def events():
        last = None
        while True:
            counts = await run_in_threadpool(snapshot)
            if counts != last:
                yield sse_frame("orders", counts)
                last = counts
            else:
                yield ": keep-alive\n\n"  # comment line: keeps proxies from closing an idle connection
            await asyncio.sleep(settings.stream_interval_seconds)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(db: DB, user: ApprovedHub):
    """Sessions and earnings for this hub. Earnings are gross estimates (no commission or payouts yet)."""
    expire_unpaid(db)
    since = utcnow() - timedelta(days=30)
    chargers = db.scalars(select(Charger).where(Charger.owner_id == user.id).order_by(Charger.id)).all()
    done = db.scalars(select(Booking).join(Charger, Charger.id == Booking.charger_id).where(
        Charger.owner_id == user.id, Booking.status == BookingStatus.COMPLETED)).all()

    def earned(b) -> float:
        return float(b.estimated_cost) if b.payment and b.payment.status == PaymentStatus.PAID else 0.0

    ratings = {cid: (round(float(avg), 2), n) for cid, avg, n in db.execute(
        select(Review.charger_id, func.avg(Review.rating), func.count(Review.id)).join(Charger, Charger.id == Review.charger_id)
        .where(Charger.owner_id == user.id).group_by(Review.charger_id)).all()}
    per = {c.id: {"sessions": 0, "earnings": 0.0} for c in chargers}
    for b in done:
        per.setdefault(b.charger_id, {"sessions": 0, "earnings": 0.0})
        per[b.charger_id]["sessions"] += 1
        per[b.charger_id]["earnings"] += earned(b)
    total_reviews = sum(n for _, n in ratings.values())
    overall = round(sum(avg * n for avg, n in ratings.values()) / total_reviews, 2) if total_reviews else None
    recent = [b for b in done if b.end_time >= since]
    today = utcnow().date()
    daily = []
    for offset in range(13, -1, -1):
        day = today - timedelta(days=offset)
        rows = [b for b in done if b.end_time.date() == day]
        daily.append(DailyOut(day=day.isoformat(), sessions=len(rows), earnings=round(sum(earned(b) for b in rows), 2)))
    return DashboardOut(
        sessions_total=len(done), sessions_30d=len(recent),
        earnings_total=round(sum(earned(b) for b in done), 2), earnings_30d=round(sum(earned(b) for b in recent), 2),
        avg_rating=overall, review_count=total_reviews, daily=daily,
        chargers=[ChargerStatOut(charger_id=c.id, title=c.title, sessions=per[c.id]["sessions"],
                                 earnings=round(per[c.id]["earnings"], 2), avg_rating=ratings.get(c.id, (None, 0))[0],
                                 review_count=ratings.get(c.id, (None, 0))[1]) for c in chargers],
    )
