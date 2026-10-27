from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from ..deps import DB, AdminUser
from ..models import Document, User, VerificationStatus, utcnow
from ..schemas import AdminVerificationOut, DecisionIn
from ..services.documents import read_document

router = APIRouter(prefix="/admin", tags=["admin"])


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
