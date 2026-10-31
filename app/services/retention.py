"""Automatic deletion of identity documents once they are no longer needed (data minimisation).

- approved accounts: documents are deleted `docs_retention_days` after approval (the account stays approved);
- removed accounts: `docs_retention_days` after removal;
- rejected applicants: `docs_rejected_retention_days` after the rejection;
- documents uploaded but never submitted: `docs_retention_days` after upload.
Applications under review are never touched."""
from datetime import timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Document, User, VerificationStatus, utcnow
from .storage import get_storage


def purge_expired_documents(db: Session, dry_run: bool = False) -> dict:
    now = utcnow()
    keep = now - timedelta(days=settings.docs_retention_days)
    keep_rejected = now - timedelta(days=settings.docs_rejected_retention_days)
    users = db.scalars(select(User).where(or_(
        and_(User.verification_status == VerificationStatus.APPROVED, User.reviewed_at < keep),
        and_(User.verification_status == VerificationStatus.REJECTED, User.reviewed_at < keep_rejected),
        and_(User.is_active.is_(False), User.removed_at < keep)))).all()
    abandoned = db.scalars(select(Document).join(User, User.id == Document.user_id).where(
        User.verification_status == VerificationStatus.NOT_SUBMITTED, Document.created_at < keep)).all()
    docs = {d.id: d for u in users for d in u.documents}
    docs.update({d.id: d for d in abandoned})
    if not dry_run:
        for d in docs.values():
            get_storage().delete(d.stored_name)
            db.delete(d)
        db.commit()
    return {"documents": len(docs), "users": len({d.user_id for d in docs.values()}), "dry_run": dry_run}
