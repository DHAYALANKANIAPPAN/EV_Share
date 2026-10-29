from datetime import datetime, timedelta, timezone

import pytest

from app.routers import bookings as bookings_mod
from app.routers import hub as hub_mod

from .conftest import CHARGER, register_and_login


@pytest.fixture()
def outbox(monkeypatch):
    sent = []
    fake = lambda to, subject, body: sent.append((to, subject, body))
    monkeypatch.setattr(hub_mod, "notify", fake)
    monkeypatch.setattr(bookings_mod, "notify", fake)
    return sent


def slot(hours=3):
    s = datetime.now(timezone.utc) + timedelta(hours=hours)
    return s.isoformat(), (s + timedelta(hours=1)).isoformat()


def request(client, driver, cid, hours=3):
    s, e = slot(hours)
    r = client.post("/bookings", json={"charger_id": cid, "start_time": s, "end_time": e}, headers=driver)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def setup(client):
    host = register_and_login(client)
    cid = client.post("/chargers", json=CHARGER, headers=host).json()["id"]
    driver = register_and_login(client, "b@example.com", "Bala")
    client.put("/verification/vehicle", json={"vehicle_number": "tn45ab1234"}, headers=driver)
    return host, cid, driver


def test_request_accept_pay_flow_with_emails(client, outbox):
    host, cid, driver = setup(client)
    bid = request(client, driver, cid)
    assert outbox[-1][0] == "a@example.com" and "New charging request" in outbox[-1][1]

    pending = client.get("/hub/orders", headers=host).json()
    assert [o["id"] for o in pending] == [bid] and pending[0]["driver_name"] == "Bala" and pending[0]["status"] == "REQUESTED"
    assert "email" not in pending[0] and pending[0]["charger_title"] == CHARGER["title"]
    assert client.get("/hub/orders", params={"scope": "upcoming"}, headers=host).json() == []
    mine = client.get("/bookings/mine", headers=driver).json()[0]
    assert mine["status"] == "REQUESTED" and mine["pickup_address"] is None  # no location until accepted
    assert client.post("/payments/checkout", json={"booking_id": bid}, headers=driver).status_code == 400

    ok = client.post(f"/hub/orders/{bid}/accept", headers=host)
    assert ok.status_code == 200 and ok.json()["status"] == "CONFIRMED"
    assert outbox[-1][0] == "b@example.com" and "accepted" in outbox[-1][1]
    assert client.get("/hub/orders", headers=host).json() == []
    assert [o["id"] for o in client.get("/hub/orders", params={"scope": "upcoming"}, headers=host).json()] == [bid]
    mine = client.get("/bookings/mine", headers=driver).json()[0]
    assert mine["status"] == "CONFIRMED" and mine["pickup_address"] == CHARGER["address"]

    client.post("/payments/checkout", json={"booking_id": bid}, headers=driver)
    client.post("/payments/confirm", json={"booking_id": bid}, headers=driver)
    assert client.get("/hub/orders", params={"scope": "upcoming"}, headers=host).json()[0]["payment_status"] == "PAID"


def test_decline_frees_the_slot_and_tells_the_driver(client, outbox):
    host, cid, driver = setup(client)
    other = register_and_login(client, "c@example.com", "Chitra")
    bid = request(client, driver, cid)
    r = client.post(f"/hub/orders/{bid}/decline", json={"reason": "Closed for maintenance"}, headers=host)
    assert r.status_code == 200 and r.json()["status"] == "DECLINED" and r.json()["decline_reason"] == "Closed for maintenance"
    assert "declined" in outbox[-1][1] and "Closed for maintenance" in outbox[-1][2] and "haven't been charged" in outbox[-1][2]
    mine = client.get("/bookings/mine", headers=driver).json()[0]
    assert mine["status"] == "DECLINED" and mine["decline_reason"] == "Closed for maintenance" and mine["pickup_address"] is None
    assert client.post("/payments/checkout", json={"booking_id": bid}, headers=driver).status_code == 400
    assert request(client, other, cid) > bid  # the slot is free again
    assert [o["status"] for o in client.get("/hub/orders", params={"scope": "past"}, headers=host).json()] == ["DECLINED"]


def test_only_the_owning_hub_can_answer_and_only_once(client, outbox):
    host, cid, driver = setup(client)
    other_hub = register_and_login(client, "h2@example.com", "H2", role="HUB")
    bid = request(client, driver, cid)
    assert client.post(f"/hub/orders/{bid}/accept", headers=other_hub).status_code == 404
    assert client.post(f"/hub/orders/{bid}/accept", headers=driver).status_code == 403
    assert client.get("/hub/orders", headers=driver).status_code == 403
    assert client.get("/hub/orders").status_code == 401
    assert client.get("/hub/orders", headers=other_hub).json() == []
    assert client.post(f"/hub/orders/{bid}/accept", headers=host).status_code == 200
    assert client.post(f"/hub/orders/{bid}/accept", headers=host).status_code == 409
    assert client.post(f"/hub/orders/{bid}/decline", json={}, headers=host).status_code == 409
    assert client.post("/hub/orders/9999/accept", headers=host).status_code == 404


def test_cancelling_a_request_and_refunding_an_accepted_paid_order(client, outbox):
    host, cid, driver = setup(client)
    first = request(client, driver, cid, hours=3)
    cancelled = client.post(f"/bookings/{first}/cancel", headers=driver).json()
    assert cancelled["status"] == "CANCELLED" and cancelled["payment_status"] == "UNPAID"  # nothing was charged
    assert client.post(f"/bookings/{first}/cancel", headers=driver).status_code == 409

    second = request(client, driver, cid, hours=6)
    client.post(f"/hub/orders/{second}/accept", headers=host)
    client.post("/payments/checkout", json={"booking_id": second}, headers=driver)
    client.post("/payments/confirm", json={"booking_id": second}, headers=driver)
    refunded = client.post(f"/bookings/{second}/cancel", headers=host).json()  # the hub cancels an accepted, paid order
    assert refunded["status"] == "CANCELLED" and refunded["payment_status"] == "REFUNDED"
    assert client.post(f"/hub/orders/{second}/decline", json={}, headers=host).status_code == 409
