from datetime import timedelta

from app.config import Settings, settings

from .conftest import CHARGER, accept, register_and_login
from .test_lifecycle import paid_booking, request, start_now


def setup(client):
    host = register_and_login(client)
    cid = client.post("/chargers", json=CHARGER, headers=host).json()["id"]
    return host, cid, register_and_login(client, "b@example.com", "Bala"), register_and_login(client, "c@example.com", "Chitra")


def test_default_rules_are_one_at_a_time_and_one_charger():
    assert Settings.model_fields["max_active_bookings"].default == 1
    assert Settings.model_fields["max_active_hub_bookings"].default == 1
    assert Settings.model_fields["max_chargers_per_hub"].default == 1


def test_limits_endpoint_reports_the_rules(client):
    body = client.get("/limits").json()
    assert set(body) == {"max_active_bookings", "max_active_hub_bookings", "max_chargers_per_hub"}


def test_a_driver_holds_one_open_booking(client, monkeypatch):
    monkeypatch.setattr(settings, "max_active_bookings", 1)
    host, cid, driver, other = setup(client)
    first = request(client, driver, cid, hours=3)
    assert first.status_code == 201
    second = request(client, driver, cid, hours=6)
    assert second.status_code == 409 and "active booking" in second.json()["detail"]
    client.post(f"/bookings/{first.json()['id']}/cancel", headers=driver)
    assert request(client, driver, cid, hours=6).status_code == 201


def test_a_hub_accepts_one_booking_at_a_time(client, monkeypatch):
    monkeypatch.setattr(settings, "max_active_hub_bookings", 1)
    host, cid, driver, other = setup(client)
    first = paid_booking(client, host, driver, cid)          # accepted and paid, not started yet
    second = request(client, other, cid, hours=6).json()["id"]
    refused = client.post(f"/hub/orders/{second}/accept", headers=host)
    assert refused.status_code == 409 and "accepted booking" in refused.json()["detail"]
    client.post(f"/bookings/{first}/cancel", headers=driver)  # cancelling frees the hub
    assert client.post(f"/hub/orders/{second}/accept", headers=host).status_code == 200


def test_a_finished_session_frees_the_hub(client, monkeypatch):
    monkeypatch.setattr(settings, "max_active_hub_bookings", 1)
    host, cid, driver, other = setup(client)
    first = paid_booking(client, host, driver, cid)
    start_now(client, first)
    client.post(f"/bookings/{first}/finish", headers=driver)
    second = request(client, other, cid, hours=6).json()["id"]
    assert client.post(f"/hub/orders/{second}/accept", headers=host).status_code == 200


def test_a_hub_account_lists_one_charger(client, monkeypatch):
    monkeypatch.setattr(settings, "max_chargers_per_hub", 1)
    host = register_and_login(client)
    assert client.post("/chargers", json=CHARGER, headers=host).status_code == 201
    second = client.post("/chargers", json={**CHARGER, "title": "Another place"}, headers=host)
    assert second.status_code == 409 and "one charger" in second.json()["detail"]
    monkeypatch.setattr(settings, "max_chargers_per_hub", 0)
    assert client.post("/chargers", json={**CHARGER, "title": "Another place"}, headers=host).status_code == 201
