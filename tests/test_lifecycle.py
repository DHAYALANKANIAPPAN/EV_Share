from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.models import Booking, utcnow

from .conftest import CHARGER, accept, register_and_login


def slot(hours=3, length=1):
    s = datetime.now(timezone.utc) + timedelta(hours=hours)
    return s.isoformat(), (s + timedelta(hours=length)).isoformat()


def request(client, driver, cid, hours=3, length=1):
    s, e = slot(hours, length)
    return client.post("/bookings", json={"charger_id": cid, "start_time": s, "end_time": e}, headers=driver)


def start_now(client, bid, minutes_ago=30, length=60):
    """Pretend the session began a while ago (the API only accepts future starts)."""
    with client.session_factory() as db:
        b = db.get(Booking, bid)
        b.start_time = utcnow() - timedelta(minutes=minutes_ago)
        b.end_time = b.start_time + timedelta(minutes=length)
        db.commit()


def paid_booking(client, host, driver, cid, **kw):
    bid = request(client, driver, cid, **kw).json()["id"]
    accept(client, host, bid)
    client.post("/payments/checkout", json={"booking_id": bid}, headers=driver)
    client.post("/payments/confirm", json={"booking_id": bid}, headers=driver)
    return bid


def setup(client):
    host = register_and_login(client)
    cid = client.post("/chargers", json=CHARGER, headers=host).json()["id"]
    return host, cid, register_and_login(client, "b@example.com", "Bala"), register_and_login(client, "c@example.com", "Chitra")


def test_running_session_makes_the_charger_busy_until_it_is_finished(client):
    host, cid, driver, other = setup(client)
    bid = paid_booking(client, host, driver, cid)
    assert client.get(f"/chargers/{cid}").json()["busy_until"] is None  # accepted but not started yet
    start_now(client, bid)
    assert client.get(f"/chargers/{cid}").json()["busy_until"] is not None
    slots = client.get(f"/chargers/{cid}/busy").json()
    assert len(slots) == 1 and slots[0]["in_progress"] is True and "user" not in str(slots[0])

    r = client.post(f"/bookings/{bid}/finish", headers=driver)
    assert r.status_code == 200 and r.json()["status"] == "COMPLETED"
    assert client.get(f"/chargers/{cid}").json()["busy_until"] is None
    assert client.get(f"/chargers/{cid}/busy").json() == []
    assert request(client, other, cid, hours=0.2, length=0.5).status_code == 201  # the rest of the slot is free for someone else
    assert client.post(f"/bookings/{bid}/finish", headers=driver).status_code == 409  # already done
    assert client.post(f"/bookings/{bid}/cancel", headers=driver).status_code == 409


def test_hub_can_finish_too_and_outsiders_cannot(client):
    host, cid, driver, other = setup(client)
    bid = paid_booking(client, host, driver, cid)
    start_now(client, bid)
    assert client.post(f"/bookings/{bid}/finish", headers=other).status_code == 403
    assert client.post(f"/bookings/{bid}/finish", headers=host).json()["status"] == "COMPLETED"
    assert [o["status"] for o in client.get("/hub/orders", params={"scope": "past"}, headers=host).json()] == ["COMPLETED"]


def test_cannot_finish_before_start_or_before_paying_or_a_request(client):
    host, cid, driver, other = setup(client)
    bid = request(client, driver, cid).json()["id"]
    assert client.post(f"/bookings/{bid}/finish", headers=driver).status_code == 409  # still a request
    accept(client, host, bid)
    assert client.post(f"/bookings/{bid}/finish", headers=driver).status_code == 400  # not started
    start_now(client, bid)
    assert client.post(f"/bookings/{bid}/finish", headers=driver).status_code == 400  # accepted but unpaid
    assert client.post("/bookings/9999/finish", headers=driver).status_code == 404


def test_review_after_a_completed_session(client):
    host, cid, driver, other = setup(client)
    bid = paid_booking(client, host, driver, cid)
    assert client.post("/reviews", json={"booking_id": bid, "rating": 5}, headers=driver).status_code == 400  # not over yet
    start_now(client, bid)
    client.post(f"/bookings/{bid}/finish", headers=driver)
    assert client.post("/reviews", json={"booking_id": bid, "rating": 5, "comment": "Quick"}, headers=driver).status_code == 201


def test_a_driver_holds_one_active_booking_at_a_time(client, monkeypatch):
    monkeypatch.setattr(settings, "max_active_bookings", 1)
    host, cid, driver, other = setup(client)
    first = request(client, driver, cid, hours=3)
    assert first.status_code == 201
    second = request(client, driver, cid, hours=6)
    assert second.status_code == 409 and "active booking" in second.json()["detail"]
    assert request(client, other, cid, hours=6).status_code == 201  # another driver is not affected

    client.post(f"/bookings/{first.json()['id']}/cancel", headers=driver)  # cancelling frees the driver
    again = request(client, driver, cid, hours=9)
    assert again.status_code == 201

    bid = again.json()["id"]  # a finished session frees them too
    accept(client, host, bid)
    client.post("/payments/checkout", json={"booking_id": bid}, headers=driver); client.post("/payments/confirm", json={"booking_id": bid}, headers=driver)
    assert request(client, driver, cid, hours=12).status_code == 409
    start_now(client, bid); client.post(f"/bookings/{bid}/finish", headers=driver)
    assert request(client, driver, cid, hours=12).status_code == 201

    other_id = request(client, other, cid, hours=20)  # hub declines -> the driver is free again
    assert other_id.status_code == 409  # `other` still holds the earlier request
    pending = client.get("/hub/orders", headers=host).json()
    for o in pending:
        if o["driver_name"] == "Chitra":
            client.post(f"/hub/orders/{o['id']}/decline", json={}, headers=host)
    assert request(client, other, cid, hours=20).status_code == 201
