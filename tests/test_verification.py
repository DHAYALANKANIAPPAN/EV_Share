import io
from datetime import timedelta

import pytest

from app.models import Document, OtpCode, User, VerificationStatus, utcnow
from app.services import otp as otp_mod

from .conftest import CHARGER, register_and_login

PDF = b"%PDF-1.4\nSECRET-AADHAAR-MARKER\n%%EOF"
H = {"X-Requested-With": "evshare"}


@pytest.fixture()
def codes(monkeypatch):
    sent = []
    class Capture:
        def send(self, email, code): sent.append(code)
    monkeypatch.setattr(otp_mod, "get_sender", lambda: Capture())
    return sent


def up(client, h, doc_type, data=PDF, name="doc.pdf"):
    return client.post("/verification/documents", headers=h, data={"doc_type": doc_type}, files={"file": (name, io.BytesIO(data))})


def make_admin(client, email="root@example.com"):
    h = register_and_login(client, email, "Root", role="DRIVER")
    with client.session_factory() as db:
        db.query(User).filter_by(email=email).one().is_admin = True
        db.commit()
    return h


def test_registration_roles(client):
    bad = client.post("/auth/register", json={"email": "h@example.com", "name": "H", "password": "password123", "role": "HUB"})
    assert bad.status_code == 422  # hub needs a hub_type
    ok = client.post("/auth/register", json={"email": "h@example.com", "name": "H", "password": "password123", "role": "HUB", "hub_type": "SHOP"}).json()
    assert ok["role"] == "HUB" and ok["hub_type"] == "SHOP" and ok["verification_status"] == "NOT_SUBMITTED" and not ok["is_admin"]
    d = client.post("/auth/register", json={"email": "d@example.com", "name": "D", "password": "password123"}).json()
    assert d["role"] == "DRIVER"
    assert client.post("/auth/register", json={"email": "x@example.com", "name": "X", "password": "password123", "is_admin": True}).json()["is_admin"] is False


def test_unverified_accounts_cannot_book_or_list(client):
    host = register_and_login(client)
    pending_host = register_and_login(client, "h2@example.com", "H2", role="HUB", approved=False)
    pending_driver = register_and_login(client, "b@example.com", "Bala", approved=False)
    cid = client.post("/chargers", json=CHARGER, headers=host).json()["id"]
    assert client.post("/chargers", json=CHARGER, headers=pending_host).status_code == 403
    r = client.post("/bookings", json={"charger_id": cid, "start_time": "2031-01-01T10:00:00+00:00", "end_time": "2031-01-01T11:00:00+00:00"}, headers=pending_driver)
    assert r.status_code == 403 and "verified" in r.json()["detail"]
    driver = register_and_login(client, "c@example.com", "Chitra")
    assert client.post("/chargers", json=CHARGER, headers=driver).status_code == 403  # drivers cannot list


def test_unapproved_hub_chargers_are_hidden(client):
    host = register_and_login(client)
    client.post("/chargers", json=CHARGER, headers=host)
    assert len(client.get("/chargers").json()) == 1
    with client.session_factory() as db:
        db.query(User).filter_by(email="a@example.com").one().verification_status = VerificationStatus.REJECTED
        db.commit()
    assert client.get("/chargers").json() == []


def test_otp_flow_limits_and_expiry(client, codes, monkeypatch):
    h = register_and_login(client, "b@example.com", "Bala", approved=False)
    assert client.post("/verification/otp/send", headers=h).status_code == 204
    code = codes[-1]
    wrong = "000000" if code != "000000" else "111111"
    assert client.post("/verification/otp/confirm", headers=h, json={"code": wrong}).status_code == 400
    assert client.post("/verification/otp/confirm", headers=h, json={"code": "12ab56"}).status_code == 422
    ok = client.post("/verification/otp/confirm", headers=h, json={"code": code})
    assert ok.status_code == 200 and ok.json()["email_verified"] is True
    assert client.post("/verification/otp/confirm", headers=h, json={"code": code}).status_code == 400  # single use

    h2 = register_and_login(client, "c@example.com", "Chitra", approved=False)
    client.post("/verification/otp/send", headers=h2)
    good = codes[-1]; bad = "000000" if good != "000000" else "111111"
    for _ in range(5):
        assert client.post("/verification/otp/confirm", headers=h2, json={"code": bad}).status_code == 400
    assert client.post("/verification/otp/confirm", headers=h2, json={"code": good}).status_code == 429  # locked after 5 misses

    client.post("/verification/otp/send", headers=h2)
    with client.session_factory() as db:
        for o in db.query(OtpCode).filter_by(consumed=False):
            o.expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    assert client.post("/verification/otp/confirm", headers=h2, json={"code": codes[-1]}).status_code == 400  # expired


def test_otp_resend_cooldown(client, codes, monkeypatch):
    monkeypatch.setattr(otp_mod.settings, "otp_resend_seconds", 60)
    h = register_and_login(client, "b@example.com", "Bala", approved=False)
    assert client.post("/verification/otp/send", headers=h).status_code == 204
    assert client.post("/verification/otp/send", headers=h).status_code == 429


def test_document_validation_and_encryption_at_rest(client):
    h = register_and_login(client, "b@example.com", "Bala", approved=False)
    assert up(client, h, "AADHAAR", b"MZ not a document", "evil.pdf").status_code == 400  # judged by content, not name
    big = PDF + b"0" * (6 * 1024 * 1024)
    assert up(client, h, "AADHAAR", big).status_code == 413
    assert up(client, h, "HOUSE_DOCUMENT").status_code == 400  # not required for drivers
    r = up(client, h, "AADHAAR")
    assert r.status_code == 201
    with client.session_factory() as db:
        doc = db.query(Document).one()
        raw = (otp_mod.settings.upload_dir and __import__("pathlib").Path(otp_mod.settings.upload_dir) / doc.stored_name).read_bytes()
        assert b"SECRET-AADHAAR-MARKER" not in raw and doc.stored_name not in doc.original_name
    again = up(client, h, "AADHAAR", PDF + b"v2")  # re-upload replaces
    assert again.status_code == 201
    with client.session_factory() as db:
        assert db.query(Document).count() == 1


def test_full_driver_journey_with_admin_review(client, codes):
    host = register_and_login(client)
    cid = client.post("/chargers", json=CHARGER, headers=host).json()["id"]
    h = register_and_login(client, "b@example.com", "Bala", approved=False)
    st = client.get("/verification/status", headers=h).json()
    assert [r["doc_type"] for r in st["required"]] == ["AADHAAR", "VEHICLE_RC"] and not st["can_submit"]

    miss = client.post("/verification/submit", headers=h, json={"consent": True})
    assert miss.status_code == 400
    client.post("/verification/otp/send", headers=h); client.post("/verification/otp/confirm", headers=h, json={"code": codes[-1]})
    assert client.put("/verification/vehicle", headers=h, json={"vehicle_number": "tn 45-ab 1234"}).json()["vehicle_number"] == "TN45AB1234"
    up(client, h, "AADHAAR"); up(client, h, "VEHICLE_RC")
    assert client.post("/verification/submit", headers=h, json={"consent": False}).status_code == 400
    sub = client.post("/verification/submit", headers=h, json={"consent": True})
    assert sub.status_code == 200 and sub.json()["status"] == "PENDING"
    assert up(client, h, "AADHAAR").status_code == 409  # locked while under review

    assert client.get("/admin/verifications", headers=h).status_code == 403
    admin = make_admin(client)
    queue = client.get("/admin/verifications", headers=admin).json()
    assert len(queue) == 1 and queue[0]["vehicle_number"] == "TN45AB1234" and len(queue[0]["documents"]) == 2
    doc_id = queue[0]["documents"][0]["id"]
    f = client.get(f"/admin/documents/{doc_id}/file", headers=admin)
    assert f.status_code == 200 and f.content == PDF and f.headers["cache-control"] == "no-store"
    assert client.get(f"/admin/documents/{doc_id}/file", headers=h).status_code == 403

    uid = queue[0]["user_id"]
    assert client.post(f"/admin/verifications/{uid}/decision", headers=admin, json={"approve": False}).status_code == 422
    rej = client.post(f"/admin/verifications/{uid}/decision", headers=admin, json={"approve": False, "reason": "RC photo is blurry"})
    assert rej.json()["status"] == "REJECTED"
    st = client.get("/verification/status", headers=h).json()
    assert st["status"] == "REJECTED" and st["rejection_reason"] == "RC photo is blurry" and st["can_submit"]
    book = {"charger_id": cid, "start_time": "2031-01-01T10:00:00+00:00", "end_time": "2031-01-01T11:00:00+00:00"}
    assert client.post("/bookings", json=book, headers=h).status_code == 403

    up(client, h, "VEHICLE_RC", PDF + b"clear")
    client.post("/verification/submit", headers=h, json={"consent": True})
    assert client.post(f"/admin/verifications/{uid}/decision", headers=admin, json={"approve": True}).json()["status"] == "APPROVED"
    assert client.get("/auth/me", headers=h).json()["verification_status"] == "APPROVED"
    assert client.post("/bookings", json={**book, "start_time": "2031-01-01T10:00:00+00:00"}, headers=h).status_code in (201, 422)  # now allowed past the gate


def test_admin_cannot_review_own_application_and_hub_docs_by_type(client):
    shop = register_and_login(client, "s@example.com", "Shop", role="HUB", approved=False)
    with client.session_factory() as db:
        db.query(User).filter_by(email="s@example.com").one().hub_type = __import__("app.models", fromlist=["HubType"]).HubType.SHOP
        db.commit()
    req = [r["doc_type"] for r in client.get("/verification/status", headers=shop).json()["required"]]
    assert req == ["HOUSE_DOCUMENT", "TAX_RECEIPT", "BUILDING_PLAN", "OCCUPANCY_CERT", "SHOP_LICENSE"]
    house = register_and_login(client, "hh@example.com", "House", role="HUB", approved=False)
    assert [r["doc_type"] for r in client.get("/verification/status", headers=house).json()["required"]] == ["HOUSE_DOCUMENT", "TAX_RECEIPT"]
