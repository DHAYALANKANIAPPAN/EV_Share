import base64
import hashlib
import uuid
from pathlib import Path

from cryptography.fernet import Fernet
from fastapi import HTTPException, UploadFile

from ..config import settings
from ..models import Document, DocType, User

_MAGIC = {b"%PDF-": "application/pdf", b"\xff\xd8\xff": "image/jpeg", b"\x89PNG\r\n\x1a\n": "image/png"}


def _fernet() -> Fernet:
    key = settings.docs_encryption_key.encode() if settings.docs_encryption_key else \
        base64.urlsafe_b64encode(hashlib.sha256(settings.secret_key.encode()).digest())  # dev only
    return Fernet(key)


def _dir() -> Path:
    p = Path(settings.upload_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _sniff(data: bytes) -> str | None:
    return next((ct for magic, ct in _MAGIC.items() if data.startswith(magic)), None)


def save_document(db, user: User, doc_type: DocType, upload: UploadFile) -> Document:
    limit = settings.docs_max_mb * 1024 * 1024
    data = upload.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"File is too large. The limit is {settings.docs_max_mb} MB.")
    content_type = _sniff(data)
    if content_type is None:  # judge by content, never by the file name or the browser's claim
        raise HTTPException(400, "Upload a PDF, JPG or PNG file.")
    stored = uuid.uuid4().hex
    (_dir() / stored).write_bytes(_fernet().encrypt(data))
    doc = next((d for d in user.documents if d.doc_type == doc_type), None)
    if doc:
        (_dir() / doc.stored_name).unlink(missing_ok=True)
        doc.stored_name, doc.content_type, doc.size = stored, content_type, len(data)
        doc.original_name = (upload.filename or "document")[:255]
    else:
        doc = Document(user_id=user.id, doc_type=doc_type, stored_name=stored, content_type=content_type,
                       size=len(data), original_name=(upload.filename or "document")[:255])
        db.add(doc)
    db.commit()
    return doc


def read_document(doc: Document) -> bytes:
    return _fernet().decrypt((_dir() / doc.stored_name).read_bytes())
