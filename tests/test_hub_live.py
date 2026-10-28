from datetime import datetime, timedelta, timezone

from app.models import User, utcnow

from .conftest import CHARGER, register_and_login


def slot(hours=3):
    s = datetime.now(timezone.utc) + timedelta(hours=hours)
    return s.isoformat(), (s + timedelta(hours=1)).isoformat()


def hub_with_charger(client, **extra):
    host = register_and_login(client)
    cid = client.post("/chargers", json={**CHARGER, **extra}, headers=host).json()["id"]
    client.post("/hub/offline", headers=host)  # the test helper starts hubs live; start these offline
    return host, cid


def book(client, driver, cid):
    s, e = slot()
    return client.post("/bookings", json={"charger_id": cid, "start_time": s, "end_time": e}, headers=driver)


def test_offline_hub_cannot_take_orders_until_it_goes_live(client):
    host, cid = hub_with_charger(client)
    driver = register_and_login(client, "b@example.com", "Bala")
    assert client.get(f"/chargers/{cid}").json()["is_live"] is False
    off = book(client, driver, cid)
    assert off.status_code == 409 and "offline" in off.json()["detail"]

    live = client.post("/hub/live", json={"latitude": CHARGER["latitude"], "longitude": CHARGER["longitude"]}, headers=host)
    assert live.status_code == 200 and live.json()["is_live"] and live.json()["chargers_live"] == 1 and live.json()["chargers_total"] == 1
    assert client.get(f"/chargers/{cid}").json()["is_live"] is True
    assert book(client, driver, cid).status_code == 201

    assert client.post("/hub/offline", headers=host).json()["is_live"] is False
    assert book(client, driver, cid).status_code == 409


def test_must_be_at_the_charger_to_go_live(client):
    host, cid = hub_with_charger(client)
    far = client.post("/hub/live", json={"latitude": 13.08, "longitude": 80.27}, headers=host)  # a different city
    assert far.status_code == 400 and "at your charger" in far.json()["detail"]
    assert client.get("/hub/live", headers=host).json()["is_live"] is False
    near = client.post("/hub/live", json={"latitude": CHARGER["latitude"] + 0.003, "longitude": CHARGER["longitude"]}, headers=host)  # about 330 m
    assert near.status_code == 200
    too_far = client.post("/hub/live", json={"latitude": CHARGER["latitude"] + 0.02, "longitude": CHARGER["longitude"]}, headers=host)  # about 2.2 km
    assert too_far.status_code == 400
    assert client.get("/hub/live", headers=host).json()["is_live"] is False  # a failed ping clears the old position


def test_only_chargers_near_the_ping_are_live(client):
    host, near_id = hub_with_charger(client)
    far_id = client.post("/chargers", json={**CHARGER, "title": "Branch", "latitude": 13.08, "longitude": 80.27}, headers=host).json()["id"]
    out = client.post("/hub/live", json={"latitude": CHARGER["latitude"], "longitude": CHARGER["longitude"]}, headers=host).json()
    assert out["chargers_live"] == 1 and out["chargers_total"] == 2
    flags = {c["id"]: c["is_live"] for c in client.get("/chargers").json()}
    assert flags == {near_id: True, far_id: False}
    assert [c["id"] for c in client.get("/chargers").json()][0] == near_id  # live ones are listed first
    assert [c["id"] for c in client.get("/chargers", params={"live_only": True}).json()] == [near_id]
    driver = register_and_login(client, "b@example.com", "Bala")
    assert book(client, driver, far_id).status_code == 409


def test_live_expires_without_pings_and_pings_extend_it(client):
    host, cid = hub_with_charger(client)
    body = {"latitude": CHARGER["latitude"], "longitude": CHARGER["longitude"]}
    client.post("/hub/live", json=body, headers=host)
    with client.session_factory() as db:
        u = db.query(User).filter_by(email="a@example.com").one()
        u.live_until = utcnow() - timedelta(minutes=1)  # the page stopped pinging
        db.commit()
    assert client.get("/hub/live", headers=host).json()["is_live"] is False
    assert client.get(f"/chargers/{cid}").json()["is_live"] is False
    first = client.post("/hub/live", json=body, headers=host).json()["live_until"]
    assert client.post("/hub/live", json=body, headers=host).json()["live_until"] >= first  # heartbeat


def test_only_approved_hubs_can_go_live_and_need_a_charger(client):
    body = {"latitude": 10.79, "longitude": 78.70}
    pending = register_and_login(client, "p@example.com", "P", role="HUB", approved=False)
    driver = register_and_login(client, "d@example.com", "D")
    assert client.post("/hub/live", json=body, headers=pending).status_code == 403
    assert client.post("/hub/live", json=body, headers=driver).status_code == 403
    assert client.post("/hub/live", json=body).status_code == 401
    empty = register_and_login(client, "h2@example.com", "H2", role="HUB")
    r = client.post("/hub/live", json=body, headers=empty)
    assert r.status_code == 400 and "List a charger first" in r.json()["detail"]
    assert client.post("/hub/live", json={"latitude": 123, "longitude": 0}, headers=empty).status_code == 422
