from app.config import settings

from .conftest import CHARGER, register_and_login
from .test_lifecycle import paid_booking, start_now


def _finished_paid_session(client):
    host = register_and_login(client)
    cid = client.post("/chargers", json=CHARGER, headers=host).json()["id"]
    driver = register_and_login(client, "p@example.com", "Pooja")
    bid = paid_booking(client, host, driver, cid)
    start_now(client, bid)
    assert client.post(f"/bookings/{bid}/finish", headers=driver).status_code == 200
    return host, driver, bid


def test_finishing_a_paid_session_creates_a_pending_host_payout(client):
    host, driver, bid = _finished_paid_session(client)
    summary = client.get("/payouts/mine", headers=host).json()
    assert summary["pending"] == 59.2 and summary["paid"] == 0       # 80% of Rs 74 after commission
    assert len(summary["items"]) == 1 and summary["items"][0]["status"] == "PENDING"


def test_admin_marks_a_payout_paid_once(client):
    host, driver, bid = _finished_paid_session(client)
    admin = register_and_login(client, "admin@example.com", "Admin")
    with client.session_factory() as db:
        from app.models import User
        db.query(User).filter_by(email="admin@example.com").one().is_admin = True
        db.commit()
    pid = client.get("/payouts/mine", headers=host).json()["items"][0]["id"]
    assert client.post(f"/payouts/{pid}/mark-paid", json={"reference": "NEFT123456"}, headers=host).status_code == 403
    ok = client.post(f"/payouts/{pid}/mark-paid", json={"reference": "NEFT123456"}, headers=admin)
    assert ok.status_code == 200 and ok.json()["status"] == "PAID" and ok.json()["reference"] == "NEFT123456"
    again = client.post(f"/payouts/{pid}/mark-paid", json={"reference": "NEFT999999"}, headers=admin)
    assert again.status_code == 409
    summary = client.get("/payouts/mine", headers=host).json()
    assert summary["pending"] == 0 and summary["paid"] == 59.2


def test_dashboard_shows_pending_and_paid(client):
    host, driver, bid = _finished_paid_session(client)
    d = client.get("/hub/dashboard", headers=host).json()
    assert d["pending_payout"] == 59.2 and d["paid_out"] == 0


def test_only_hosts_see_payouts(client):
    driver = register_and_login(client, "p@example.com", "Pooja")
    assert client.get("/payouts/mine", headers=driver).status_code == 403


def test_admin_sees_every_payout_with_the_host_and_the_charger(client):
    host, driver, bid = _finished_paid_session(client)
    admin = register_and_login(client, "admin@example.com", "Admin")
    with client.session_factory() as db:
        from app.models import User
        db.query(User).filter_by(email="admin@example.com").one().is_admin = True
        db.commit()
    rows = client.get("/payouts/queue", headers=admin).json()
    assert len(rows) == 1
    assert rows[0]["hub_name"] == "Asha" and rows[0]["charger_title"] == CHARGER["title"]
    assert rows[0]["status"] == "PENDING" and rows[0]["amount"] == 59.2
    assert client.get("/payouts/queue", headers=host).status_code == 403
