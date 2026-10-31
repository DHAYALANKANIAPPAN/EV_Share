import io
import os
from datetime import timedelta
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from app.config import settings
from app.models import Document, User, VerificationStatus, utcnow
from app.services import storage as storage_mod
from app.services.retention import purge_expired_documents

from .conftest import register_and_login
from .test_verification import PDF, make_admin, up

os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")


@pytest.fixture()
def s3(monkeypatch):
    with mock_aws():
        boto3.client("s3", region_name="ap-south-1").create_bucket(Bucket="docs", CreateBucketConfiguration={"LocationConstraint": "ap-south-1"})
        for k, v in dict(storage_backend="s3", s3_bucket="docs", s3_prefix="documents/", s3_region="ap-south-1", s3_endpoint_url="").items():
            monkeypatch.setattr(settings, k, v)
        storage_mod._build.cache_clear()
        yield boto3.client("s3", region_name="ap-south-1")
        storage_mod._build.cache_clear()


def test_local_storage_round_trip(tmp_path):
    st = storage_mod.LocalStorage(str(tmp_path / "x"))
    st.put("a", b"cipher")
    assert st.get("a") == b"cipher"
    st.delete("a"); st.delete("a")  # deleting twice is fine
    with pytest.raises(FileNotFoundError):
        st.get("a")


def test_documents_are_stored_encrypted_in_s3_and_readable_by_reviewers(client, s3):
    h = register_and_login(client, "b@example.com", "Bala", approved=False)
    assert up(client, h, "AADHAAR").status_code == 201
    keys = [o["Key"] for o in s3.list_objects_v2(Bucket="docs").get("Contents", [])]
    assert len(keys) == 1 and keys[0].startswith("documents/")
    assert b"SECRET-AADHAAR-MARKER" not in s3.get_object(Bucket="docs", Key=keys[0])["Body"].read()  # only ciphertext leaves the app

    up(client, h, "AADHAAR", PDF + b"v2")  # replacing deletes the old object
    assert len(s3.list_objects_v2(Bucket="docs")["Contents"]) == 1

    admin = make_admin(client)
    with client.session_factory() as db:
        u = db.query(User).filter_by(email="b@example.com").one()
        u.verification_status = VerificationStatus.PENDING
        doc_id = u.documents[0].id
        db.commit()
    f = client.get(f"/admin/documents/{doc_id}/file", headers=admin)
    assert f.status_code == 200 and f.content == PDF + b"v2"


def set_user(client, email, **fields):
    with client.session_factory() as db:
        u = db.query(User).filter_by(email=email).one()
        for k, v in fields.items():
            setattr(u, k, v)
        db.commit()


def doc_count(client):
    with client.session_factory() as db:
        return db.query(Document).count()


def test_retention_deletes_only_what_is_no_longer_needed(client):
    old, recent = utcnow() - timedelta(days=60), utcnow() - timedelta(days=5)
    cases = {  # email -> fields; whether its documents should be purged
        "approved-old@example.com": (dict(verification_status=VerificationStatus.APPROVED, reviewed_at=old), True),
        "approved-recent@example.com": (dict(verification_status=VerificationStatus.APPROVED, reviewed_at=recent), False),
        "pending@example.com": (dict(verification_status=VerificationStatus.PENDING, reviewed_at=None, submitted_at=old), False),
        "rejected-60d@example.com": (dict(verification_status=VerificationStatus.REJECTED, reviewed_at=old), False),   # 90-day rule
        "rejected-100d@example.com": (dict(verification_status=VerificationStatus.REJECTED, reviewed_at=utcnow() - timedelta(days=100)), True),
        "removed-old@example.com": (dict(is_active=False, removed_at=old), True),
    }
    for email, (fields, _) in cases.items():
        h = register_and_login(client, email, email.split("@")[0], approved=False)
        up(client, h, "AADHAAR")
        set_user(client, email, **fields)
    h = register_and_login(client, "abandoned@example.com", "Abandoned", approved=False)  # uploaded, never submitted
    up(client, h, "AADHAAR")
    with client.session_factory() as db:
        for d in db.query(Document).join(User).filter(User.email == "abandoned@example.com"):
            d.created_at = old
        db.commit()
    files_before = len(list(Path(settings.upload_dir).glob("*")))
    total = doc_count(client)

    with client.session_factory() as db:
        dry = purge_expired_documents(db, dry_run=True)
    assert dry["documents"] == 4 and doc_count(client) == total  # approved-old, rejected-100d, removed-old, abandoned

    with client.session_factory() as db:
        done = purge_expired_documents(db)
    assert done["documents"] == 4 and done["users"] == 4 and doc_count(client) == total - 4
    assert len(list(Path(settings.upload_dir).glob("*"))) == files_before - 4  # the files really are gone
    with client.session_factory() as db:
        kept = {u.email for u in db.query(User).join(Document).all()}
        assert "pending@example.com" in kept and "approved-recent@example.com" in kept and "approved-old@example.com" not in kept
        assert db.query(User).filter_by(email="approved-old@example.com").one().verification_status == VerificationStatus.APPROVED  # the account itself is untouched
        assert purge_expired_documents(db)["documents"] == 0  # running again does nothing
