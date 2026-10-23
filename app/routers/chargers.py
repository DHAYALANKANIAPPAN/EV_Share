from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from ..deps import DB, CurrentUser
from ..models import Charger, ConnectorType
from ..schemas import ChargerCreate, ChargerOut, ChargerUpdate
from ..services.geo import bounding_box, haversine_km

router = APIRouter(prefix="/chargers", tags=["chargers"])


def _get_or_404(db, charger_id: int) -> Charger:
    charger = db.get(Charger, charger_id)
    if not charger:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Charger not found")
    return charger


@router.post("", response_model=ChargerOut, status_code=status.HTTP_201_CREATED)
def create_charger(body: ChargerCreate, db: DB, user: CurrentUser):
    charger = Charger(owner_id=user.id, **body.model_dump())
    db.add(charger)
    db.commit()
    return charger


@router.get("", response_model=list[ChargerOut])
def search_chargers(
    db: DB,
    lat: float | None = Query(None, ge=-90, le=90),
    lon: float | None = Query(None, ge=-180, le=180),
    radius_km: float = Query(10, gt=0, le=200),
    connector_type: ConnectorType | None = None,
    min_power_kw: float | None = Query(None, gt=0),
    max_price_per_kwh: float | None = Query(None, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """List active chargers. With `lat` and `lon`, results are filtered by radius and sorted nearest-first."""
    if (lat is None) != (lon is None):
        raise HTTPException(422, "Provide both lat and lon, or neither")

    stmt = select(Charger).where(Charger.is_active.is_(True))
    if connector_type:
        stmt = stmt.where(Charger.connector_type == connector_type)
    if min_power_kw is not None:
        stmt = stmt.where(Charger.power_kw >= min_power_kw)
    if max_price_per_kwh is not None:
        stmt = stmt.where(Charger.price_per_kwh <= max_price_per_kwh)

    if lat is None:
        return db.scalars(stmt.order_by(Charger.id.desc()).limit(limit)).all()

    min_lat, max_lat, min_lon, max_lon = bounding_box(lat, lon, radius_km)
    stmt = stmt.where(Charger.latitude.between(min_lat, max_lat), Charger.longitude.between(min_lon, max_lon))
    results = []
    for c in db.scalars(stmt):
        d = haversine_km(lat, lon, c.latitude, c.longitude)
        if d <= radius_km:
            out = ChargerOut.model_validate(c)
            out.distance_km = round(d, 2)
            results.append(out)
    results.sort(key=lambda c: c.distance_km)
    return results[:limit]


@router.get("/mine", response_model=list[ChargerOut])
def my_chargers(db: DB, user: CurrentUser):
    return db.scalars(select(Charger).where(Charger.owner_id == user.id).order_by(Charger.id)).all()


@router.get("/{charger_id}", response_model=ChargerOut)
def get_charger(charger_id: int, db: DB):
    return _get_or_404(db, charger_id)


@router.patch("/{charger_id}", response_model=ChargerOut)
def update_charger(charger_id: int, body: ChargerUpdate, db: DB, user: CurrentUser):
    charger = _get_or_404(db, charger_id)
    if charger.owner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can edit this charger")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(charger, field, value)
    db.commit()
    return charger
