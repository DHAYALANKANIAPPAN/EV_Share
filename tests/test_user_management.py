from datetime import datetime, timedelta, timezone

import pytest

from app.routers import admin as admin_mod
from app.services.mailer import MailError

from .conftest import CHARGER, register_and_login
from .test_verification import make_admin


@pytest.fixture()
def mails(monkeypatch):
    sent = []
    monkeypatch.setattr(admin_mod, "send_mail", lambda to, subject, body: sent.append((to, subject, body)))
    return sent


def slot(hours=3):
    s = datetime.now(timezone.utc) + timedelta(hours=hours)
    return s.isoformat(), (s + timedelta(hours=1)).isoformat()


def book_and_pay(client, driver, charger_id):
    s, e = slot()
    b = client.post("/bookings", json={"charger_id": charger_id, "start_time": s, "end_time": e}, headers=driver).json()
    client.post("/payments/checkout", json={"booking_id": b["id"]}, headers=driver)
    client.post("/payments/confirm", json={"booking_id": b["id"]}, headers=driver)
    return b["id"]


def uid(client, h):
    return client.get("/auth/me", headers=h).json()["id"]


def test_user_list_filters_search_and_never_shows_reviewers(client):
    register_and_login(client)  # a@ hub
    register_and_login(client, "b@example.com", "Bala")
    register_and_login(client, "c@example.com", "Chitra")
    admin = make_admin(client)
    everyone = client.get("/admin/users", headers=admin).json()
    assert everyone["total"] == 3 and all(u["email"] != "root@example.com" for u in everyone["items"])
    assert [u["email"] for u in client.get("/admin/users", params={"role": "HUB"}, headers=admin).json()["items"]] == ["a@example.com"]
    assert client.get("/admin/users", params={"q": "chit"}, headers=admin).json()["total"] == 1
    assert client.get("/admin/users", params={"q": "%"}, headers=admin).json()["total"] == 0  # wildcards are not special
    page = client.get("/admin/users", params={"limit": 2, "offset": 2}, headers=admin).json()
    assert page["total"] == 3 and len(page["items"]) == 1
    assert client.get("/admin/users", headers=register_and_login(client, "d@example.com", "D")).status_code == 403


def test_removing_a_driver_blocks_login_cancels_and_refunds_and_emails(client, mails):
    host = register_and_login(client)
    cid = client.post("/chargers", json=CHARGER, headers=host).json()["id"]
    driver = register_and_login(client, "b@example.com", "Bala")
    bid = book_and_pay(client, driver, cid)
    admin = make_admin(client)
    driver_id = uid(client, driver)

    assert client.post(f"/admin/users/{driver_id}/remove", json={"reason": "no"}, headers=admin).status_code == 422
    r = client.post(f"/admin/users/{driver_id}/remove", json={"reason": "Documents did not match records"}, headers=admin)
    assert r.status_code == 200 and r.json()["cancelled_bookings"] == 1 and r.json()["email_sent"] is True and r.json()["user"]["is_active"] is False
    to, subject, body = mails[-1]
    assert to == "b@example.com" and "removed" in subject.lower() and "Documents did not match records" in body and "different email" in body

    booking = client.get("/bookings/charger/%d" % cid, headers=host).json()[0]
    assert booking["id"] == bid and booking["status"] == "CANCELLED" and booking["payment_status"] == "REFUNDED"
    assert client.get("/auth/me", headers=driver).status_code == 401  # existing session stops working
    assert client.post("/auth/login", data={"username": "b@example.com", "password": "wrong-password"}).status_code == 401
    blocked = client.post("/auth/login", data={"username": "b@example.com", "password": "password123"})
    assert blocked.status_code == 403 and "removed" in blocked.json()["detail"]
    assert client.post("/auth/register", json={"email": "b@example.com", "name": "B", "password": "password123"}).status_code == 409  # email stays reserved
    assert client.post(f"/admin/users/{driver_id}/remove", json={"reason": "again please"}, headers=admin).status_code == 409

    restored = client.post(f"/admin/users/{driver_id}/restore", headers=admin)
    assert restored.status_code == 200 and restored.json()["is_active"] is True
    assert mails[-1][1] == "Your EV Share account has been restored"
    assert client.post("/auth/login", data={"username": "b@example.com", "password": "password123"}).status_code == 200
    assert client.post(f"/admin/users/{driver_id}/restore", headers=admin).status_code == 409


def test_removing_a_hub_hides_its_chargers_and_cancels_bookings_on_them(client, mails):
    host = register_and_login(client)
    cid = client.post("/chargers", json=CHARGER, headers=host).json()["id"]
    driver = register_and_login(client, "b@example.com", "Bala")
    book_and_pay(client, driver, cid)
    admin = make_admin(client)
    assert len(client.get("/chargers").json()) == 1
    r = client.post(f"/admin/users/{uid(client, host)}/remove", json={"reason": "Property papers are not valid"}, headers=admin)
    assert r.json()["cancelled_bookings"] == 1
    assert client.get("/chargers").json() == []
    mine = client.get("/bookings/mine", headers=driver).json()
    assert mine[0]["status"] == "CANCELLED" and mine[0]["payment_status"] == "REFUNDED"
    s, e = slot(5)
    assert client.post("/chargers", json=CHARGER, headers=host).status_code == 401  # removed hub's session is dead


def test_reviewers_and_self_cannot_be_removed_and_mail_failure_is_reported(client, monkeypatch):
    register_and_login(client, "b@example.com", "Bala")
    admin = make_admin(client)
    admin_id = uid(client, admin)
    assert client.post(f"/admin/users/{admin_id}/remove", json={"reason": "removing myself"}, headers=admin).status_code == 403
    other_admin = make_admin(client, "second@example.com")
    assert client.post(f"/admin/users/{uid(client, other_admin)}/remove", json={"reason": "colleague test"}, headers=admin).status_code == 403
    assert client.post("/admin/users/9999/remove", json={"reason": "does not exist"}, headers=admin).status_code == 404

    def boom(*a):
        raise MailError("smtp down")
    monkeypatch.setattr(admin_mod, "send_mail", boom)
    r = client.post(f"/admin/users/{uid(client, client_headers(client))}/remove", json={"reason": "mail will fail here"}, headers=admin)
    assert r.status_code == 200 and r.json()["email_sent"] is False and r.json()["user"]["is_active"] is False


def client_headers(client):
    return {"Authorization": "Bearer " + client.post("/auth/login", data={"username": "b@example.com", "password": "password123"}).json()["access_token"]}
