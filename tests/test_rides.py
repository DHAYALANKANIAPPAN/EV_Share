from datetime import timedelta

from app.config import settings
from app.models import Booking, utcnow

from .conftest import CHARGER, register_and_login

HUB_LAT, HUB_LON = CHARGER["latitude"], CHARGER["longitude"]
FAR_LAT, FAR_LON = 13.08, 80.27   # Chennai, many kilometres away


def _setup(client):
    host = register_and_login(client)
    cid = client.post("/chargers", json=CHARGER, headers=host).json()["id"]
    driver = register_and_login(client, "rider@example.com", "Ravi")
    return host, cid, driver


def _request(client, driver, cid, lat=HUB_LAT, lon=HUB_LON, range_km=50):
    return client.post("/rides", json={"charger_id": cid, "latitude": lat, "longitude": lon, "range_km": range_km}, headers=driver)


def _ride_on_the_way(client, host, driver, cid):
    rid = _request(client, driver, cid).json()["id"]
    assert client.post(f"/hub/orders/{rid}/accept", headers=host).status_code == 200
    return rid


def test_full_ride_from_request_to_completed(client):
    host, cid, driver = _setup(client)
    req = _request(client, driver, cid)
    assert req.status_code == 201
    ride = req.json()
    assert ride["kind"] == "ride" and ride["status"] == "REQUESTED"
    assert ride["estimated_cost"] == 100.0 and ride["platform_fee"] == 20.0 and ride["hub_amount"] == 80.0
    rid = ride["id"]

    assert client.post(f"/hub/orders/{rid}/accept", headers=host).status_code == 200
    assert client.post(f"/rides/{rid}/location", json={"latitude": HUB_LAT, "longitude": HUB_LON}, headers=driver).status_code == 200
    assert client.post(f"/rides/{rid}/arrived", headers=driver).json()["ride_stage"] == "ARRIVED"
    assert client.post(f"/rides/{rid}/confirm-arrival", headers=host).json()["ride_stage"] == "ARRIVAL_CONFIRMED"

    quote = client.post(f"/rides/{rid}/duration", json={"minutes": 30}, headers=driver)
    assert quote.status_code == 200
    assert quote.json() == {"minutes": 30, "amount": 100.0, "platform_fee": 20.0, "hub_amount": 80.0}

    checkout = client.post("/payments/checkout", json={"booking_id": rid}, headers=driver)
    assert checkout.status_code == 200 and checkout.json()["amount"] == 100.0
    # the mock provider accepts any signature; the live provider checks a real one
    paid = client.post("/payments/confirm", json={"booking_id": rid, "payment_id": "pay_test_1", "signature": "mock"}, headers=driver)
    assert paid.status_code == 200

    detail = client.get(f"/rides/{rid}", headers=driver).json()
    assert detail["ride_stage"] == "CHARGING" and detail["payment_status"] == "PAID"
    messages = [e["message"] for e in detail["events"]]
    assert any("Ride requested" in m for m in messages)
    assert any("Charging time chosen: 30 minutes" in m for m in messages)
    assert any("Payment of Rs 100 received" in m for m in messages)

    assert client.post(f"/bookings/{rid}/finish", headers=driver).status_code == 200
    assert client.get(f"/rides/{rid}", headers=driver).json()["status"] == "COMPLETED"
    d = client.get("/hub/dashboard", headers=host).json()
    assert d["earnings_total"] == 80.0  # the host's share of Rs 100


def test_driver_cannot_mark_arrival_from_far_away(client):
    host, cid, driver = _setup(client)
    rid = _ride_on_the_way(client, host, driver, cid)
    client.post(f"/rides/{rid}/location", json={"latitude": FAR_LAT, "longitude": FAR_LON}, headers=driver)
    r = client.post(f"/rides/{rid}/arrived", headers=driver)
    assert r.status_code == 409 and "from the hub" in r.json()["detail"]


def test_arrival_needs_a_recent_location(client):
    host, cid, driver = _setup(client)
    rid = _ride_on_the_way(client, host, driver, cid)
    with client.session_factory() as db:
        b = db.get(Booking, rid)
        b.driver_location_at = utcnow() - timedelta(hours=1)
        db.commit()
    r = client.post(f"/rides/{rid}/arrived", headers=driver)
    assert r.status_code == 409 and "location" in r.json()["detail"]


def test_host_must_confirm_arrival_before_pricing(client):
    host, cid, driver = _setup(client)
    rid = _ride_on_the_way(client, host, driver, cid)
    assert client.post(f"/rides/{rid}/duration", json={"minutes": 30}, headers=driver).status_code == 409
    assert client.post(f"/rides/{rid}/confirm-arrival", headers=host).status_code == 409


def test_charging_time_is_sold_in_30_minute_steps(client):
    host, cid, driver = _setup(client)
    rid = _ride_on_the_way(client, host, driver, cid)
    client.post(f"/rides/{rid}/location", json={"latitude": HUB_LAT, "longitude": HUB_LON}, headers=driver)
    client.post(f"/rides/{rid}/arrived", headers=driver)
    client.post(f"/rides/{rid}/confirm-arrival", headers=host)
    assert client.post(f"/rides/{rid}/duration", json={"minutes": 45}, headers=driver).status_code == 422
    two = client.post(f"/rides/{rid}/duration", json={"minutes": 60}, headers=driver).json()
    assert two["amount"] == 200.0 and two["hub_amount"] == 160.0


def test_host_has_two_minutes_to_accept(client):
    host, cid, driver = _setup(client)
    rid = _request(client, driver, cid).json()["id"]
    with client.session_factory() as db:
        b = db.get(Booking, rid)
        b.response_deadline = utcnow() - timedelta(seconds=5)
        db.commit()
    assert client.post(f"/hub/orders/{rid}/accept", headers=host).status_code == 409
    assert client.get(f"/rides/{rid}", headers=driver).json()["status"] == "CANCELLED"


def test_a_ride_the_driver_never_reaches_is_released(client, monkeypatch):
    host, cid, driver = _setup(client)
    rid = _ride_on_the_way(client, host, driver, cid)
    with client.session_factory() as db:
        b = db.get(Booking, rid)
        b.accepted_at = utcnow() - timedelta(minutes=settings.ride_en_route_max_minutes + 5)
        db.commit()
    detail = client.get(f"/rides/{rid}", headers=driver).json()
    assert detail["status"] == "CANCELLED" and "didn't reach" in detail["decline_reason"]


def test_unpaid_arrival_is_released_after_the_payment_window(client):
    host, cid, driver = _setup(client)
    rid = _ride_on_the_way(client, host, driver, cid)
    client.post(f"/rides/{rid}/location", json={"latitude": HUB_LAT, "longitude": HUB_LON}, headers=driver)
    client.post(f"/rides/{rid}/arrived", headers=driver)
    client.post(f"/rides/{rid}/confirm-arrival", headers=host)
    with client.session_factory() as db:
        b = db.get(Booking, rid)
        b.arrival_confirmed_at = utcnow() - timedelta(minutes=settings.unpaid_hold_minutes + 2)
        db.commit()
    detail = client.get(f"/rides/{rid}", headers=driver).json()
    assert detail["status"] == "CANCELLED" and "Payment wasn't completed" in detail["decline_reason"]


def test_driver_range_limits_the_hubs_they_can_ask(client):
    host, cid, driver = _setup(client)
    r = _request(client, driver, cid, lat=FAR_LAT, lon=FAR_LON, range_km=50)
    assert r.status_code == 422 and "car's range" in r.json()["detail"]


def test_one_ride_at_a_time_when_limited(client, monkeypatch):
    monkeypatch.setattr(settings, "max_active_bookings", 1)
    host, cid, driver = _setup(client)
    assert _request(client, driver, cid).status_code == 201
    assert _request(client, driver, cid).status_code == 409


def test_only_the_driver_and_the_host_see_a_ride(client):
    host, cid, driver = _setup(client)
    rid = _request(client, driver, cid).json()["id"]
    other = register_and_login(client, "other@example.com", "Other")
    other_host = register_and_login(client, "h2@example.com", "Another host", role="HUB")
    assert client.get(f"/rides/{rid}", headers=other).status_code == 403
    assert client.get(f"/rides/{rid}", headers=host).status_code == 200
    assert client.post(f"/rides/{rid}/confirm-arrival", headers=other_host).status_code == 404
    assert client.post(f"/rides/{rid}/confirm-arrival", headers=other).status_code == 403
