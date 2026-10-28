from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from ..deps import DB, ApprovedHub, CurrentUser
from ..models import Charger, ConnectorType, Review, User, VerificationStatus
from ..schemas import ChargerCreate, ChargerOut, ChargerUpdate, _check_window
from ..services.geo import bounding_box, haversine_km

router = APIRouter(prefix="/chargers", tags=["chargers"])


def _get_or_404(db, charger_id: int) -> Charger:
    charger = db.get(Charger, charger_id)
    if not charger:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Charger not found")
    return charger


def to_out(db, chargers: list[Charger], distances: dict[int, float] | None = None) -> list[ChargerOut]:
    """Serialise chargers with rating aggregates (one grouped query for the whole list)."""
    ids = [c.id for c in chargers]
    ratings = {}
    if ids:
        rows = db.execute(
            select(Review.charger_id, func.avg(Review.rating), func.count(Review.id))
            .where(Review.charger_id.in_(ids)).group_by(Review.charger_id)
        ).all()
        ratings = {cid: (round(float(avg), 2), n) for cid, avg, n in rows}
    out = []
    for c in chargers:
        o = ChargerOut.model_validate(c)
        o.distance_km = (distances or {}).get(c.id)
        o.avg_rating, o.review_count = ratings.get(c.id, (None, 0))
        out.append(o)
    return out


@router.post("", response_model=ChargerOut, status_code=status.HTTP_201_CREATED)
def create_charger(body: ChargerCreate, db: DB, user: ApprovedHub):
    charger = Charger(owner_id=user.id, **body.model_dump())
    db.add(charger)
    db.commit()
    return to_out(db, [charger])[0]


@router.get("", response_model=list[ChargerOut])
def search_chargers(
    db: DB,
    lat: float | None = Query(None, ge=-90, le=90),
    lon: float | None = Query(None, ge=-180, le=180),
    radius_km: float = Query(10, gt=0, le=200),
    connector_type: ConnectorType | None = None,
    min_power_kw: float | None = Query(None, gt=0),
    max_price_per_kwh: float | None = Query(None, ge=0),
    min_rating: float | None = Query(None, ge=1, le=5),
    limit: int = Query(50, ge=1, le=200),
):
    """List active chargers. With `lat` and `lon`, results are filtered by radius and sorted nearest-first."""
    if (lat is None) != (lon is None):
        raise HTTPException(422, "Provide both lat and lon, or neither")

    stmt = select(Charger).where(Charger.is_active.is_(True),
                                 Charger.owner.has((User.verification_status == VerificationStatus.APPROVED) & User.is_active.is_(True)))
    if connector_type:
        stmt = stmt.where(Charger.connector_type == connector_type)
    if min_power_kw is not None:
        stmt = stmt.where(Charger.power_kw >= min_power_kw)
    if max_price_per_kwh is not None:
        stmt = stmt.where(Charger.price_per_kwh <= max_price_per_kwh)

    distances: dict[int, float] = {}
    if lat is None:
        chargers = list(db.scalars(stmt.order_by(Charger.id.desc())))
    else:
        min_lat, max_lat, min_lon, max_lon = bounding_box(lat, lon, radius_km)
        stmt = stmt.where(Charger.latitude.between(min_lat, max_lat), Charger.longitude.between(min_lon, max_lon))
        chargers = []
        for c in db.scalars(stmt):
            d = haversine_km(lat, lon, c.latitude, c.longitude)
            if d <= radius_km:
                distances[c.id] = round(d, 2)
                chargers.append(c)
        chargers.sort(key=lambda c: distances[c.id])

    out = to_out(db, chargers, distances)
    if min_rating is not None:
        out = [c for c in out if c.avg_rating is not None and c.avg_rating >= min_rating]
    return out[:limit]


@router.get("/mine", response_model=list[ChargerOut])
def my_chargers(db: DB, user: CurrentUser):
    rows = db.scalars(select(Charger).where(Charger.owner_id == user.id).order_by(Charger.id)).all()
    return to_out(db, list(rows))


@router.get("/{charger_id}", response_model=ChargerOut)
def get_charger(charger_id: int, db: DB):
    return to_out(db, [_get_or_404(db, charger_id)])[0]


@router.patch("/{charger_id}", response_model=ChargerOut)
def update_charger(charger_id: int, body: ChargerUpdate, db: DB, user: CurrentUser):
    charger = _get_or_404(db, charger_id)
    if charger.owner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can edit this charger")
    changes = body.model_dump(exclude_unset=True)
    new_from = changes.get("available_from", charger.available_from)
    new_to = changes.get("available_to", charger.available_to)
    try:
        _check_window(new_from, new_to)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    for field, value in changes.items():
        setattr(charger, field, value)
    db.commit()
    return to_out(db, [charger])[0]
