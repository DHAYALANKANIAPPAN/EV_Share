from datetime import timedelta

from app.models import Booking, utcnow
from app.routers import hub as hub_mod

from .conftest import CHARGER, accept, register_and_login
from .test_lifecycle import paid_booking, start_now


def test_dashboard_counts_completed_sessions_earnings_and_ratings(client):
    host = register_and_login(client)
    cid = client.post("/chargers", json=CHARGER, headers=host).json()["id"]
    driver = register_and_login(client, "b@example.com", "Bala")
    bid = paid_booking(client, host, driver, cid)  # 7.4 kW x 1 h x Rs10 = Rs74
    d0 = client.get("/hub/dashboard", headers=host).json()
    assert d0["sessions_total"] == 0 and d0["earnings_total"] == 0 and d0["chargers"][0]["title"] == CHARGER["title"]

    start_now(client, bid)
    client.post(f"/bookings/{bid}/finish", headers=driver)
    client.post("/reviews", json={"booking_id": bid, "rating": 4, "comment": "Good"}, headers=driver)
    d = client.get("/hub/dashboard", headers=host).json()
    assert d["sessions_total"] == 1 and d["sessions_30d"] == 1 and d["earnings_total"] == 74.0 and d["earnings_30d"] == 74.0
    assert d["avg_rating"] == 4.0 and d["review_count"] == 1
    assert d["chargers"][0]["sessions"] == 1 and d["chargers"][0]["avg_rating"] == 4.0


def test_dashboard_separates_last_30_days(client):
    host = register_and_login(client)
    cid = client.post("/chargers", json=CHARGER, headers=host).json()["id"]
    driver = register_and_login(client, "b@example.com", "Bala")
    bid = paid_booking(client, host, driver, cid)
    start_now(client, bid)
    client.post(f"/bookings/{bid}/finish", headers=driver)
    with client.session_factory() as db:
        b = db.get(Booking, bid)
        b.end_time = utcnow() - timedelta(days=45)
        db.commit()
    d = client.get("/hub/dashboard", headers=host).json()
    assert d["sessions_total"] == 1 and d["sessions_30d"] == 0 and d["earnings_total"] == 74.0 and d["earnings_30d"] == 0


def test_dashboard_is_for_approved_hubs_only(client):
    driver = register_and_login(client, "b@example.com", "Bala")
    assert client.get("/hub/dashboard", headers=driver).status_code == 403
    assert client.get("/hub/dashboard").status_code == 401


def test_order_counts_and_stream_frame(client):
    host = register_and_login(client)
    cid = client.post("/chargers", json=CHARGER, headers=host).json()["id"]
    driver = register_and_login(client, "b@example.com", "Bala")
    from .test_lifecycle import request
    req = request(client, driver, cid).json()["id"]
    with client.session_factory() as db:
        uid = client.get("/auth/me", headers=host).json()["id"]
        assert hub_mod.order_counts(db, uid) == {"pending": 1, "upcoming": 0, "running": 0}
    accept(client, host, req)
    with client.session_factory() as db:
        assert hub_mod.order_counts(db, uid) == {"pending": 0, "upcoming": 1, "running": 0}
    frame = hub_mod.sse_frame("orders", {"pending": 0})
    assert frame == 'event: orders\ndata: {"pending": 0}\n\n'


def test_stream_route_is_event_stream_and_requires_an_approved_hub(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/hub/stream" in paths and "/hub/dashboard" in paths
    driver = register_and_login(client, "b@example.com", "Bala")
    assert client.get("/hub/stream", headers=driver).status_code == 403
    assert client.get("/hub/stream").status_code == 401


def test_dashboard_has_14_days_that_add_up(client):
    host = register_and_login(client)
    cid = client.post("/chargers", json=CHARGER, headers=host).json()["id"]
    driver = register_and_login(client, "b@example.com", "Bala")
    bid = paid_booking(client, host, driver, cid)
    start_now(client, bid)
    client.post(f"/bookings/{bid}/finish", headers=driver)
    d = client.get("/hub/dashboard", headers=host).json()
    assert len(d["daily"]) == 14
    assert sum(x["sessions"] for x in d["daily"]) == d["sessions_30d"] == 1
    assert round(sum(x["earnings"] for x in d["daily"]), 2) == d["earnings_30d"] == 74.0
    days = [x["day"] for x in d["daily"]]
    assert days == sorted(days)
