from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from ..deps import DB, CurrentUser
from ..models import DocType, Role, VerificationStatus, utcnow
from ..schemas import DocumentOut, OtpConfirm, RequiredDoc, SubmitIn, VehicleIn, VerificationOut
from ..services import otp
from ..services.documents import save_document
from ..services.verification import LABELS, required_docs

router = APIRouter(prefix="/verification", tags=["verification"])


def _out(user) -> VerificationOut:
    have = {d.doc_type: d for d in user.documents}
    req = [RequiredDoc(doc_type=t, label=LABELS[t], uploaded=t in have, original_name=have[t].original_name if t in have else None)
           for t in required_docs(user)]
    ready = user.email_verified and all(r.uploaded for r in req) and (user.role != Role.DRIVER or bool(user.vehicle_number))
    return VerificationOut(role=user.role, hub_type=user.hub_type, status=user.verification_status,
                           rejection_reason=user.rejection_reason, email_verified=user.email_verified,
                           vehicle_number=user.vehicle_number, required=req,
                           can_submit=ready and user.verification_status in (VerificationStatus.NOT_SUBMITTED, VerificationStatus.REJECTED))


def _editable(user):
    if user.verification_status in (VerificationStatus.PENDING, VerificationStatus.APPROVED):
        raise HTTPException(status.HTTP_409_CONFLICT, "Your documents are under review or already approved and can't be changed now.")


@router.get("/status", response_model=VerificationOut)
def my_status(user: CurrentUser):
    return _out(user)


@router.post("/otp/send", status_code=status.HTTP_204_NO_CONTENT)
def send_code(db: DB, user: CurrentUser):
    if user.email_verified:
        raise HTTPException(status.HTTP_409_CONFLICT, "Your email is already verified.")
    otp.send_otp(db, user)


@router.post("/otp/confirm", response_model=VerificationOut)
def confirm_code(body: OtpConfirm, db: DB, user: CurrentUser):
    otp.confirm_otp(db, user, body.code)
    return _out(user)


@router.put("/vehicle", response_model=VerificationOut)
def set_vehicle(body: VehicleIn, db: DB, user: CurrentUser):
    if user.role != Role.DRIVER:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only driver accounts have a vehicle.")
    _editable(user)
    user.vehicle_number = body.vehicle_number
    db.commit()
    return _out(user)


@router.post("/documents", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def upload_document(db: DB, user: CurrentUser, doc_type: Annotated[DocType, Form()], file: Annotated[UploadFile, File()]):
    _editable(user)
    if doc_type not in required_docs(user):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That document isn't needed for your account type.")
    return save_document(db, user, doc_type, file)


@router.post("/submit", response_model=VerificationOut)
def submit(body: SubmitIn, db: DB, user: CurrentUser):
    _editable(user)
    if not body.consent:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Please agree to let EV Share review your documents.")
    if not user.email_verified:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Verify your email with the code first.")
    if user.role == Role.DRIVER and not user.vehicle_number:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Add your vehicle registration number first.")
    have = {d.doc_type for d in user.documents}
    missing = [LABELS[t] for t in required_docs(user) if t not in have]
    if missing:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Still needed: " + "; ".join(missing))
    user.verification_status, user.rejection_reason = VerificationStatus.PENDING, None
    user.consented_at = user.submitted_at = utcnow()
    db.commit()
    return _out(user)
