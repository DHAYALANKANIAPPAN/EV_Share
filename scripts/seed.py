"""Create demo users and chargers (run `alembic upgrade head` first).  Usage: python -m scripts.seed"""
from datetime import time

from app import models  # noqa: F401
from app.database import SessionLocal
from app.models import Charger, ConnectorType, User
from app.security import hash_password

# title, address, lat, lon, connector, kW, price/kWh, available_from, available_to
DEMO_CHARGERS = [
    ("Anna Nagar home charger", "Anna Nagar, Chennai", 13.0850, 80.2101, ConnectorType.TYPE2, 7.4, 9.0, None, None),
    ("Cantonment fast DC", "Cantonment, Tiruchirappalli", 10.8050, 78.6856, ConnectorType.CCS2, 30.0, 18.0, None, None),
    ("Srirangam driveway (nights)", "Srirangam, Tiruchirappalli", 10.8631, 78.6898, ConnectorType.BHARAT_AC001, 3.3, 7.5,
     time(18, 0), time(8, 0)),
    ("Thillai Nagar office lot", "Thillai Nagar, Tiruchirappalli", 10.8174, 78.6898, ConnectorType.TYPE2, 11.0, 12.0,
     time(9, 0), time(18, 0)),
]

with SessionLocal() as db:
    if db.query(User).filter_by(email="host@example.com").first():
        print("Seed data already present.")
    else:
        host = User(email="host@example.com", name="Demo Host", password_hash=hash_password("password123"))
        db.add(host)
        db.flush()
        for title, addr, lat, lon, conn, kw, price, af, at in DEMO_CHARGERS:
            db.add(Charger(owner_id=host.id, title=title, address=addr, latitude=lat, longitude=lon,
                           connector_type=conn, power_kw=kw, price_per_kwh=price, available_from=af, available_to=at))
        db.add(User(email="driver@example.com", name="Demo Driver", password_hash=hash_password("password123")))
        db.commit()
        print("Seeded: host@example.com / driver@example.com (password: password123)")
