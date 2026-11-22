from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Payout


def payout_total(db: Session, hub_user_id: int, status: str) -> float:
    total = db.scalar(select(func.coalesce(func.sum(Payout.amount), 0.0)).where(
        Payout.hub_user_id == hub_user_id, Payout.status == status))
    return round(float(total or 0.0), 2)
