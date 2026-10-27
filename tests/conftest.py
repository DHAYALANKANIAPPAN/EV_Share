import os
import tempfile

os.environ["EVSHARE_ENV"] = "dev"
os.environ["EVSHARE_SECRET_KEY"] = "test-secret-key-that-is-definitely-long-enough-123"
os.environ["EVSHARE_DATABASE_URL"] = "sqlite://"
os.environ["EVSHARE_PAYMENT_PROVIDER"] = "mock"
os.environ["EVSHARE_UPLOAD_DIR"] = tempfile.mkdtemp(prefix="evshare-test-uploads-")
os.environ["EVSHARE_OTP_RESEND_SECONDS"] = "0"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import database
from app.main import app
from app.services.ratelimit import login_limiter


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    database.Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[database.get_db] = override
    login_limiter.reset_all()
    with TestClient(app) as c:
        c.session_factory = Session  # lets tests insert fixtures (e.g. past bookings) directly
        yield c
    app.dependency_overrides.clear()


def register_and_login(client, email="a@example.com", name="Asha", password="password123", role=None, approved=True):
    """Register + log in. Convention: a@example.com is the host (HUB); everyone else is a DRIVER.
    approved=True marks the account verified directly in the database (verification has its own tests)."""
    role = role or ("HUB" if email == "a@example.com" else "DRIVER")
    body = {"email": email, "name": name, "password": password, "role": role}
    if role == "HUB":
        body["hub_type"] = "HOUSE"
    client.post("/auth/register", json=body)
    if approved:
        from app.models import User, VerificationStatus
        with client.session_factory() as db:
            u = db.query(User).filter_by(email=email).one()
            u.verification_status, u.email_verified = VerificationStatus.APPROVED, True
            db.commit()
    r = client.post("/auth/login", data={"username": email, "password": password})
    client.cookies.clear()  # tests authenticate explicitly with Bearer headers
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


CHARGER = {"title": "Home Type2", "address": "12 Main St", "latitude": 10.79, "longitude": 78.70,
           "connector_type": "TYPE2", "power_kw": 7.4, "price_per_kwh": 10}
