import hashlib
import hmac
from datetime import datetime, time, timedelta, timezone

import pytest

from app.config import Settings
from app.models import Booking, BookingStatus
from app.services import payments as pay_mod
from app.services.availability import fits_window

from .conftest import CHARGER, register_and_login


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


def future(hours=2, length=1):
    s = datetime.now(timezone.utc) + timedelta(hours=hours)
    return s, s + timedelta(hours=length)


def make_past_booking(client, charger_id, user_id, status=BookingStatus.CONFIRMED):
    with client.session_factory() as db:
        end = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
        b = Booking(charger_id=charger_id, user_id=user_id, start_time=end - timedelta(hours=1), end_time=end,
                    estimated_cost=50.0, status=status)
        db.add(b)
        db.commit()
        return b.id


# ---------- availability windows ----------
class FakeCharger:
    timezone = "Asia/Kolkata"

    def __init__(self, f, t):
        self.available_from, self.available_to = f, t


def utc_naive(y, mo, d, h, mi, tz_offset_min=330):
    """Local IST wall time -> naive UTC."""
    return datetime(y, mo, d, h, mi) - timedelta(minutes=tz_offset_min)


def test_daytime_window():
    c = FakeCharger(time(9), time(18))
    assert fits_window(c, utc_naive(2030, 1, 1, 9, 0), utc_naive(2030, 1, 1, 18, 0))
    assert not fits_window(c, utc_naive(2030, 1, 1, 8, 30), utc_naive(2030, 1, 1, 10, 0))
    assert not fits_window(c, utc_naive(2030, 1, 1, 17, 0), utc_naive(2030, 1, 1, 19, 0))


def test_overnight_window():
    c = FakeCharger(time(18), time(8))
    assert fits_window(c, utc_naive(2030, 1, 1, 22, 0), utc_naive(2030, 1, 2, 2, 0))   # crosses midnight
    assert fits_window(c, utc_naive(2030, 1, 2, 1, 0), utc_naive(2030, 1, 2, 7, 0))    # early morning, window began prev. evening
    assert not fits_window(c, utc_naive(2030, 1, 1, 7, 0), utc_naive(2030, 1, 1, 10, 0))
    assert not fits_window(c, utc_naive(2030, 1, 1, 12, 0), utc_naive(2030, 1, 1, 13, 0))


def test_no_window_means_always():
    assert fits_window(FakeCharger(None, None), utc_naive(2030, 1, 1, 3, 0), utc_naive(2030, 1, 1, 4, 0))


def test_booking_rejected_outside_window_and_validation(client):
    owner, driver = register_and_login(client), register_and_login(client, "b@example.com", "Bala")
    # window = the full day except one hour, defined around "now" in UTC to keep the test deterministic
    s, e = future(hours=48, length=1)
    local = s.astimezone(timezone.utc)
    wf, wt = (local + timedelta(hours=3)).time().replace(second=0, microsecond=0), \
             (local + timedelta(hours=6)).time().replace(second=0, microsecond=0)
    ch = {**CHARGER, "timezone": "UTC", "available_from": wf.isoformat(), "available_to": wt.isoformat()}
    cid = client.post("/chargers", json=ch, headers=owner).json()["id"]
    r = client.post("/bookings", json={"charger_id": cid, "start_time": iso(s), "end_time": iso(e)}, headers=driver)
    assert r.status_code == 422 and "only available" in r.json()["detail"]
    s2 = s + timedelta(hours=3, minutes=30)
    ok = client.post("/bookings", json={"charger_id": cid, "start_time": iso(s2), "end_time": iso(s2 + timedelta(hours=1))},
                     headers=driver)
    assert ok.status_code == 201

    assert client.post("/chargers", json={**CHARGER, "available_from": "09:00:00"}, headers=owner).status_code == 422
    assert client.post("/chargers", json={**CHARGER, "timezone": "Mars/Base"}, headers=owner).status_code == 422
    assert client.patch(f"/chargers/{cid}", json={"available_to": None}, headers=owner).status_code == 422


# ---------- reviews ----------
def test_review_flow_and_rating_aggregates(client):
    owner, driver = register_and_login(client), register_and_login(client, "b@example.com", "Bala")
    other = register_and_login(client, "c@example.com", "Chitra")
    cid = client.post("/chargers", json=CHARGER, headers=owner).json()["id"]
    driver_id = client.get("/auth/me", headers=driver).json()["id"]

    fs, fe = future()
    live = client.post("/bookings", json={"charger_id": cid, "start_time": iso(fs), "end_time": iso(fe)},
                       headers=driver).json()["id"]
    assert client.post("/reviews", json={"booking_id": live, "rating": 5}, headers=driver).status_code == 400  # not ended

    past = make_past_booking(client, cid, driver_id)
    assert client.post("/reviews", json={"booking_id": past, "rating": 6}, headers=driver).status_code == 422
    assert client.post("/reviews", json={"booking_id": past, "rating": 4}, headers=other).status_code == 404
    ok = client.post("/reviews", json={"booking_id": past, "rating": 4, "comment": " Smooth "}, headers=driver)
    assert ok.status_code == 201 and ok.json()["comment"] == "Smooth" and ok.json()["user_name"] == "Bala"
    assert client.post("/reviews", json={"booking_id": past, "rating": 5}, headers=driver).status_code == 409

    ch = client.get(f"/chargers/{cid}").json()
    assert ch["avg_rating"] == 4.0 and ch["review_count"] == 1
    assert client.get("/chargers", params={"min_rating": 4.5}).json() == []
    assert len(client.get("/chargers", params={"min_rating": 4}).json()) == 1
    assert len(client.get(f"/reviews/charger/{cid}").json()) == 1
    mine = client.get("/bookings/mine", headers=driver).json()
    assert {b["id"]: b["reviewed"] for b in mine}[past] is True


def test_cancelled_booking_cannot_be_reviewed(client):
    owner, driver = register_and_login(client), register_and_login(client, "b@example.com", "Bala")
    cid = client.post("/chargers", json=CHARGER, headers=owner).json()["id"]
    uid = client.get("/auth/me", headers=driver).json()["id"]
    bid = make_past_booking(client, cid, uid, status=BookingStatus.CANCELLED)
    assert client.post("/reviews", json={"booking_id": bid, "rating": 3}, headers=driver).status_code == 400


# ---------- payments (mock) ----------
def test_mock_payment_and_refund_on_cancel(client):
    owner, driver = register_and_login(client), register_and_login(client, "b@example.com", "Bala")
    stranger = register_and_login(client, "c@example.com", "Chitra")
    cid = client.post("/chargers", json=CHARGER, headers=owner).json()["id"]
    s, e = future()
    bid = client.post("/bookings", json={"charger_id": cid, "start_time": iso(s), "end_time": iso(e)},
                      headers=driver).json()["id"]

    assert client.post("/payments/checkout", json={"booking_id": bid}, headers=stranger).status_code == 404
    co = client.post("/payments/checkout", json={"booking_id": bid}, headers=driver).json()
    assert co["provider"] == "mock" and co["amount"] == 74.0 and co["status"] == "PENDING"
    assert client.post("/payments/checkout", json={"booking_id": bid}, headers=driver).json()["order_id"] == co["order_id"]
    paid = client.post("/payments/confirm", json={"booking_id": bid}, headers=driver).json()
    assert paid["payment_status"] == "PAID"
    assert client.post("/payments/checkout", json={"booking_id": bid}, headers=driver).status_code == 409

    cancelled = client.post(f"/bookings/{bid}/cancel", headers=driver).json()
    assert cancelled["status"] == "CANCELLED" and cancelled["payment_status"] == "REFUNDED"


def test_free_charger_is_paid_immediately(client):
    owner, driver = register_and_login(client), register_and_login(client, "b@example.com", "Bala")
    cid = client.post("/chargers", json={**CHARGER, "price_per_kwh": 0}, headers=owner).json()["id"]
    s, e = future()
    bid = client.post("/bookings", json={"charger_id": cid, "start_time": iso(s), "end_time": iso(e)},
                      headers=driver).json()["id"]
    assert client.post("/payments/checkout", json={"booking_id": bid}, headers=driver).json()["status"] == "PAID"


# ---------- payments (razorpay, HTTP mocked) ----------
def test_razorpay_signature_flow(client, monkeypatch):
    secret = "rzp_secret_value"
    monkeypatch.setattr(pay_mod.settings, "payment_provider", "razorpay")
    monkeypatch.setattr(pay_mod.settings, "razorpay_key_id", "rzp_test_key")
    monkeypatch.setattr(pay_mod.settings, "razorpay_key_secret", secret)

    calls = []

    class Resp:
        def __init__(self, data): self._d = data
        def raise_for_status(self): pass
        def json(self): return self._d

    def fake_post(url, json=None, auth=None, timeout=None):
        calls.append((url, json, auth))
        return Resp({"id": "order_ABC123"} if url.endswith("/orders") else {"id": "rfnd_1"})

    monkeypatch.setattr(pay_mod.httpx, "post", fake_post)

    owner, driver = register_and_login(client), register_and_login(client, "b@example.com", "Bala")
    cid = client.post("/chargers", json=CHARGER, headers=owner).json()["id"]
    s, e = future()
    bid = client.post("/bookings", json={"charger_id": cid, "start_time": iso(s), "end_time": iso(e)},
                      headers=driver).json()["id"]

    co = client.post("/payments/checkout", json={"booking_id": bid}, headers=driver).json()
    assert co["order_id"] == "order_ABC123" and co["key_id"] == "rzp_test_key"
    assert calls[0][1]["amount"] == 7400 and calls[0][1]["currency"] == "INR" and calls[0][2] == ("rzp_test_key", secret)

    bad = client.post("/payments/confirm", json={"booking_id": bid, "payment_id": "pay_1", "signature": "nope"},
                      headers=driver)
    assert bad.status_code == 400
    sig = hmac.new(secret.encode(), b"order_ABC123|pay_1", hashlib.sha256).hexdigest()
    ok = client.post("/payments/confirm", json={"booking_id": bid, "payment_id": "pay_1", "signature": sig}, headers=driver)
    assert ok.status_code == 200 and ok.json()["payment_status"] == "PAID"

    client.post(f"/bookings/{bid}/cancel", headers=driver)
    assert calls[-1][0].endswith("/payments/pay_1/refund") and calls[-1][1]["amount"] == 7400


# ---------- config safety ----------
def test_production_requires_strong_secret_and_real_payments():
    with pytest.raises(ValueError):
        Settings(env="production", secret_key="short")
    with pytest.raises(ValueError):
        Settings(env="production", secret_key="x" * 40, payment_provider="mock")
    with pytest.raises(ValueError):
        Settings(env="production", secret_key="x" * 40, payment_provider="razorpay")
    Settings(env="production", secret_key="x" * 40, payment_provider="razorpay",
             razorpay_key_id="a", razorpay_key_secret="b")
