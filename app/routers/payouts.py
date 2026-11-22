from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from ..deps import DB, AdminUser, ApprovedHub
from ..models import Payout, utcnow
from ..services.payouts import payout_total

router = APIRouter(prefix="/payouts", tags=["payouts"])


class PayoutOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    booking_id: int
    amount: float
    status: str
    reference: str | None
    created_at: datetime
    paid_at: datetime | None


class PayoutSummaryOut(BaseModel):
    pending: float
    paid: float
    items: list[PayoutOut]


class MarkPaidIn(BaseModel):
    reference: str = Field(min_length=3, max_length=120)  # the bank transfer reference


@router.get("/mine", response_model=PayoutSummaryOut)
def my_payouts(db: DB, user: ApprovedHub):
    """What the platform owes this host: pending and already paid."""
    rows = db.scalars(select(Payout).where(Payout.hub_user_id == user.id).order_by(Payout.id.desc())).all()
    return PayoutSummaryOut(pending=payout_total(db, user.id, "PENDING"), paid=payout_total(db, user.id, "PAID"),
                            items=[PayoutOut.model_validate(p) for p in rows])


@router.post("/{payout_id}/mark-paid", response_model=PayoutOut)
def mark_paid(payout_id: int, body: MarkPaidIn, db: DB, admin: AdminUser):
    """An admin records that the transfer to the host was made. Refuses a second payment for the same payout."""
    payout = db.get(Payout, payout_id)
    if not payout:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payout not found")
    if payout.status == "PAID":
        raise HTTPException(status.HTTP_409_CONFLICT, "This payout is already marked paid")
    payout.status, payout.reference, payout.paid_at = "PAID", body.reference.strip(), utcnow()
    db.commit()
    return payout
