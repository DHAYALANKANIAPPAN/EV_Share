from datetime import timedelta

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from ..config import settings
from ..deps import DB, ApprovedHub
from ..models import Charger, utcnow
from ..schemas import LiveIn, LiveOut
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
