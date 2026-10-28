from ..config import settings
from ..models import Charger, User, utcnow
from .geo import haversine_km


def hub_is_live(user: User, now=None) -> bool:
    return user.live_until is not None and user.live_lat is not None and user.live_until > (now or utcnow())


def distance_m(user: User, charger: Charger) -> float:
    return haversine_km(user.live_lat, user.live_lon, charger.latitude, charger.longitude) * 1000


def charger_is_live(charger: Charger, now=None) -> bool:
    """Live = charger listed, its hub active and live, and the hub's last ping was within the allowed distance."""
    owner = charger.owner
    return bool(charger.is_active and owner.is_active and hub_is_live(owner, now) and distance_m(owner, charger) <= settings.live_radius_m)
