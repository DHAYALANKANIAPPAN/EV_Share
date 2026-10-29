import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import func, select

from ..deps import DB, AdminUser
from ..models import Booking, BookingStatus, Charger, Document, Role, User, VerificationStatus, utcnow
from ..schemas import AdminUserOut, AdminVerificationOut, DecisionIn, RemoveIn, RemoveOut, UserListOut
from ..services.bookings import cancel_with_refund
from ..services.documents import read_document
from ..services.mailer import MailError, send_mail

router = APIRouter(prefix="/admin", tags=["admin"])
log = logging.getLogger("evshare.admin")


@router.get("/verifications", response_model=list[AdminVerificationOut])
def list_verifications(db: DB, admin: AdminUser, status_filter: VerificationStatus = VerificationStatus.PENDING):
    users = db.scalars(select(User).where(User.verification_status == status_filter).order_by(User.submitted_at)).all()
    return [AdminVerificationOut(user_id=u.id, name=u.name, email=u.email, role=u.role, hub_type=u.hub_type,
                                 vehicle_number=u.vehicle_number, status=u.verification_status,
                                 submitted_at=u.submitted_at, documents=u.documents) for u in users]


@router.get("/documents/{doc_id}/file")
def download_document(doc_id: int, db: DB, admin: AdminUser):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return Response(read_document(doc), media_type=doc.content_type,
                    headers={"Cache-Control": "no-store", "Content-Disposition": f'inline; filename="{doc.doc_type.value.lower()}"'})


@router.post("/verifications/{user_id}/decision", response_model=AdminVerificationOut)
def decide(user_id: int, body: DecisionIn, db: DB, admin: AdminUser):
    user = db.get(User, user_id)
    if not user or user.verification_status != VerificationStatus.PENDING:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No pending application for this user.")
    if user.id == admin.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can't review your own application.")
    if not body.approve and not (body.reason and len(body.reason.strip()) >= 5):
        raise HTTPException(422, "Give the applicant a short reason so they can fix and resubmit.")
    user.verification_status = VerificationStatus.APPROVED if body.approve else VerificationStatus.REJECTED
    user.rejection_reason = None if body.approve else body.reason.strip()
    user.reviewed_at, user.reviewed_by_id = utcnow(), admin.id
    db.commit()
    return AdminVerificationOut(user_id=user.id, name=user.name, email=user.email, role=user.role, hub_type=user.hub_type,
                                vehicle_number=user.vehicle_number, status=user.verification_status,
                                submitted_at=user.submitted_at, documents=user.documents)


@router.get("/users", response_model=UserListOut)
def list_users(db: DB, admin: AdminUser, role: Role | None = None, state: Literal["all", "active", "removed"] = "all",
               q: str | None = Query(None, max_length=100), limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    """Drivers and hubs (reviewers are never listed), newest first."""
    stmt = select(User).where(User.is_admin.is_(False))
    if role:
        stmt = stmt.where(User.role == role)
    if state != "all":
        stmt = stmt.where(User.is_active.is_(state == "active"))
    if q and q.strip():
        needle = q.strip().lower()
        stmt = stmt.where(func.lower(User.email).contains(needle, autoescape=True) | func.lower(User.name).contains(needle, autoescape=True))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    return UserListOut(items=db.scalars(stmt.order_by(User.id.desc()).limit(limit).offset(offset)).all(), total=total)


def _target(db, user_id: int, admin) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if user.is_admin or user.id == admin.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Reviewer accounts can't be changed here.")
    return user


@router.post("/users/{user_id}/remove", response_model=RemoveOut)
def remove_user(user_id: int, body: RemoveIn, db: DB, admin: AdminUser):
    """Disable an account: login stops working, upcoming bookings are cancelled (and refunded), the user is emailed the reason.
    The email address stays reserved, so they must register again with a different one."""
    user = _target(db, user_id, admin)
    if not user.is_active:
        raise HTTPException(status.HTTP_409_CONFLICT, "This account is already removed.")
    upcoming = db.scalars(select(Booking).where(Booking.status.in_([BookingStatus.REQUESTED, BookingStatus.CONFIRMED]), Booking.end_time > utcnow(),
                                                (Booking.user_id == user.id) | Booking.charger.has(Charger.owner_id == user.id))).all()
    for booking in upcoming:  # one at a time: if the payment gateway fails, a retry carries on where this stopped
        cancel_with_refund(booking)
        db.commit()
    user.is_active, user.removed_at, user.removal_reason, user.removed_by_id = False, utcnow(), body.reason.strip(), admin.id
    db.commit()
    sent = True
    try:
        send_mail(user.email, "Your EV Share account has been removed",
                  f"Hello {user.name},\n\nA reviewer has removed your EV Share account.\n\nReason: {user.removal_reason}\n\n"
                  "You can no longer sign in with this account, and any upcoming bookings were cancelled (paid bookings are refunded).\n"
                  "To keep using EV Share, register a new account with a different email address and complete verification again.\n"
                  "If you think this was a mistake, contact EV Share support.\n")
    except MailError:
        sent = False
        log.exception("could not email removal notice to user %s", user.id)
    return RemoveOut(user=user, cancelled_bookings=len(upcoming), email_sent=sent)


@router.post("/users/{user_id}/restore", response_model=AdminUserOut)
def restore_user(user_id: int, db: DB, admin: AdminUser):
    user = _target(db, user_id, admin)
    if user.is_active:
        raise HTTPException(status.HTTP_409_CONFLICT, "This account is not removed.")
    user.is_active, user.removed_at, user.removal_reason, user.removed_by_id = True, None, None, None
    db.commit()
    try:
        send_mail(user.email, "Your EV Share account has been restored", f"Hello {user.name},\n\nYour EV Share account is active again. You can sign in as before.\n")
    except MailError:
        log.exception("could not email restore notice to user %s", user.id)
    return user
