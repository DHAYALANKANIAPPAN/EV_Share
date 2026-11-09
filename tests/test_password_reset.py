from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.config import settings
from app.models import User
from app.services import otp as otp_mod

from .conftest import register_and_login


@pytest.fixture()
def codes(monkeypatch):
    sent = []

    class Capture:
        def send(self, email, code):
            sent.append((email, code))
    monkeypatch.setattr(otp_mod, "get_sender", lambda: Capture())
    return sent


def other(code):
    return "000000" if code != "000000" else "111111"


def test_forgot_answers_the_same_for_known_and_unknown_emails(client, codes):
    register_and_login(client, "u@example.com", "User")
    known = client.post("/auth/password/forgot", json={"email": "u@example.com"})
    unknown = client.post("/auth/password/forgot", json={"email": "nobody@example.com"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert [e for e, _ in codes] == ["u@example.com"]  # only the real account got a code
    assert client.post("/auth/password/forgot", json={"email": "not-an-email"}).status_code == 422


def test_reset_with_the_code_changes_the_password(client, codes):
    register_and_login(client, "u@example.com", "User")
    client.post("/auth/password/forgot", json={"email": "u@example.com"})
    code = codes[-1][1]
    bad = client.post("/auth/password/reset", json={"email": "u@example.com", "code": other(code), "new_password": "brand-new-pass"})
    assert bad.status_code == 400
    ok = client.post("/auth/password/reset", json={"email": "u@example.com", "code": code, "new_password": "brand-new-pass"})
    assert ok.status_code == 204
    assert client.post("/auth/login", data={"username": "u@example.com", "password": "password123"}).status_code == 401
    assert client.post("/auth/login", data={"username": "u@example.com", "password": "brand-new-pass"}).status_code == 200
    assert client.post("/auth/password/reset", json={"email": "u@example.com", "code": code, "new_password": "another-pass"}).status_code == 400  # single use


def test_a_session_from_before_the_reset_stops_working(client, codes):
    h = register_and_login(client, "u@example.com", "User")
    assert client.get("/auth/me", headers=h).status_code == 200
    client.post("/auth/password/forgot", json={"email": "u@example.com"})
    client.post("/auth/password/reset", json={"email": "u@example.com", "code": codes[-1][1], "new_password": "brand-new-pass"})
    assert client.get("/auth/me", headers=h).status_code == 401  # the old token is void
    fresh = client.post("/auth/login", data={"username": "u@example.com", "password": "brand-new-pass"}).json()["access_token"]
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {fresh}"}).status_code == 200


def test_a_token_bound_to_an_old_password_hash_is_rejected(client):
    from app.security import password_fingerprint
    h = register_and_login(client, "u@example.com", "User")
    uid = client.get("/auth/me", headers=h).json()["id"]
    with client.session_factory() as db:
        current = db.get(User, uid).password_hash
    now = datetime.now(timezone.utc)
    stale = jwt.encode({"sub": str(uid), "pwd": password_fingerprint("an-older-hash"), "exp": now + timedelta(minutes=30)}, settings.secret_key, algorithm="HS256")
    current_ok = jwt.encode({"sub": str(uid), "pwd": password_fingerprint(current), "exp": now + timedelta(minutes=30)}, settings.secret_key, algorithm="HS256")
    no_fingerprint = jwt.encode({"sub": str(uid), "exp": now + timedelta(minutes=30)}, settings.secret_key, algorithm="HS256")  # tokens from before this rule
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {stale}"}).status_code == 401
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {no_fingerprint}"}).status_code == 401
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {current_ok}"}).status_code == 200


def test_wrong_codes_lock_the_reset_after_five_attempts(client, codes):
    register_and_login(client, "u@example.com", "User")
    client.post("/auth/password/forgot", json={"email": "u@example.com"})
    good = codes[-1][1]
    for _ in range(5):
        assert client.post("/auth/password/reset", json={"email": "u@example.com", "code": other(good), "new_password": "brand-new-pass"}).status_code == 400
    assert client.post("/auth/password/reset", json={"email": "u@example.com", "code": good, "new_password": "brand-new-pass"}).status_code == 429


def test_a_verification_code_cannot_be_used_to_reset_and_vice_versa(client, codes):
    register_and_login(client, "u@example.com", "User")
    client.post("/auth/password/forgot", json={"email": "u@example.com"})
    reset_code = codes[-1][1]
    with client.session_factory() as db:  # a code sent for email verification
        u = db.query(User).filter_by(email="u@example.com").one()
        otp_mod.send_otp(db, u, purpose="verify")
    verify_code = codes[-1][1]
    assert client.post("/auth/password/reset", json={"email": "u@example.com", "code": verify_code, "new_password": "brand-new-pass"}).status_code == 400
    assert client.post("/auth/password/reset", json={"email": "u@example.com", "code": reset_code, "new_password": "brand-new-pass"}).status_code == 400  # superseded by the newer code


def test_cooldown_stops_repeat_requests_silently(client, codes, monkeypatch):
    monkeypatch.setattr(otp_mod.settings, "otp_resend_seconds", 60)
    register_and_login(client, "u@example.com", "User")
    assert client.post("/auth/password/forgot", json={"email": "u@example.com"}).status_code == 202
    assert client.post("/auth/password/forgot", json={"email": "u@example.com"}).status_code == 202  # same answer
    assert len(codes) == 1  # but no second email
