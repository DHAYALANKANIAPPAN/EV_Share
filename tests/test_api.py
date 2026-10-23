from datetime import datetime, timedelta, timezone

from .conftest import CHARGER, register_and_login


def slot(hours_from_now=2, length=2):
    start = datetime.now(timezone.utc) + timedelta(hours=hours_from_now)
    return start.isoformat(), (start + timedelta(hours=length)).isoformat()


def test_auth_flow(client):
    h = register_and_login(client)
    assert client.get("/auth/me", headers=h).json()["email"] == "a@example.com"
    dup = client.post("/auth/register", json={"email": "A@example.com", "name": "x", "password": "password123"})
    assert dup.status_code == 409
    bad = client.post("/auth/login", data={"username": "a@example.com", "password": "wrong-pass"})
    assert bad.status_code == 401
    assert client.get("/auth/me").status_code == 401


def test_charger_crud_and_ownership(client):
    owner, other = register_and_login(client), register_and_login(client, "b@example.com", "Bala")
    cid = client.post("/chargers", json=CHARGER, headers=owner).json()["id"]
    assert client.patch(f"/chargers/{cid}", json={"price_per_kwh": 12}, headers=other).status_code == 403
    r = client.patch(f"/chargers/{cid}", json={"price_per_kwh": 12}, headers=owner)
    assert r.json()["price_per_kwh"] == 12
    assert client.post("/chargers", json=CHARGER).status_code == 401


def test_search_by_distance_and_filters(client):
    h = register_and_login(client)
    client.post("/chargers", json=CHARGER, headers=h)
    far = {**CHARGER, "title": "Far", "latitude": 13.08, "longitude": 80.27, "connector_type": "CCS2"}
    client.post("/chargers", json=far, headers=h)
    near = client.get("/chargers", params={"lat": 10.79, "lon": 78.70, "radius_km": 20}).json()
    assert [c["title"] for c in near] == ["Home Type2"] and near[0]["distance_km"] < 1
    assert len(client.get("/chargers", params={"connector_type": "CCS2"}).json()) == 1
    assert client.get("/chargers", params={"lat": 10}).status_code == 422


def test_booking_rules(client):
    owner, driver = register_and_login(client), register_and_login(client, "b@example.com", "Bala")
    cid = client.post("/chargers", json=CHARGER, headers=owner).json()["id"]
    s, e = slot()

    assert client.post("/bookings", json={"charger_id": cid, "start_time": s, "end_time": e}, headers=owner).status_code == 400
    ok = client.post("/bookings", json={"charger_id": cid, "start_time": s, "end_time": e}, headers=driver)
    assert ok.status_code == 201 and ok.json()["estimated_cost"] == round(7.4 * 2 * 10, 2)

    overlap_s, overlap_e = slot(hours_from_now=3, length=2)
    assert client.post("/bookings", json={"charger_id": cid, "start_time": overlap_s, "end_time": overlap_e}, headers=driver).status_code == 409
    adj_s, adj_e = slot(hours_from_now=4, length=1)  # back-to-back is allowed
    assert client.post("/bookings", json={"charger_id": cid, "start_time": adj_s, "end_time": adj_e}, headers=driver).status_code == 201

    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    assert client.post("/bookings", json={"charger_id": cid, "start_time": past, "end_time": s}, headers=driver).status_code == 422
    naive = {"charger_id": cid, "start_time": "2030-01-01T10:00:00", "end_time": "2030-01-01T11:00:00"}
    assert client.post("/bookings", json=naive, headers=driver).status_code == 422
    long_s, long_e = slot(hours_from_now=24, length=9)
    assert client.post("/bookings", json={"charger_id": cid, "start_time": long_s, "end_time": long_e}, headers=driver).status_code == 422


def test_cancel_frees_slot(client):
    owner, driver = register_and_login(client), register_and_login(client, "b@example.com", "Bala")
    stranger = register_and_login(client, "c@example.com", "Chitra")
    cid = client.post("/chargers", json=CHARGER, headers=owner).json()["id"]
    s, e = slot()
    bid = client.post("/bookings", json={"charger_id": cid, "start_time": s, "end_time": e}, headers=driver).json()["id"]

    assert client.post(f"/bookings/{bid}/cancel", headers=stranger).status_code == 403
    assert client.get(f"/bookings/charger/{cid}", headers=stranger).status_code == 403
    assert len(client.get(f"/bookings/charger/{cid}", headers=owner).json()) == 1
    assert client.post(f"/bookings/{bid}/cancel", headers=driver).json()["status"] == "CANCELLED"
    assert client.post(f"/bookings/{bid}/cancel", headers=driver).status_code == 409
    assert client.post("/bookings", json={"charger_id": cid, "start_time": s, "end_time": e}, headers=stranger).status_code == 201
