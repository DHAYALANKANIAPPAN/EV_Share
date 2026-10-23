"""Create a few demo users and chargers.  Usage: python -m scripts.seed"""
from app import models  # noqa: F401
from app.database import Base, SessionLocal, engine
from app.models import Charger, ConnectorType, User
from app.security import hash_password

DEMO_CHARGERS = [
    ("Anna Nagar home charger", "Anna Nagar, Chennai", 13.0850, 80.2101, ConnectorType.TYPE2, 7.4, 9.0),
    ("Cantonment fast DC", "Cantonment, Tiruchirappalli", 10.8050, 78.6856, ConnectorType.CCS2, 30.0, 18.0),
    ("Srirangam driveway", "Srirangam, Tiruchirappalli", 10.8631, 78.6898, ConnectorType.BHARAT_AC001, 3.3, 7.5),
]

Base.metadata.create_all(engine)
with SessionLocal() as db:
    if db.query(User).filter_by(email="host@example.com").first():
        print("Seed data already present.")
    else:
        host = User(email="host@example.com", name="Demo Host", password_hash=hash_password("password123"))
        db.add(host)
        db.flush()
        for title, addr, lat, lon, conn, kw, price in DEMO_CHARGERS:
            db.add(Charger(owner_id=host.id, title=title, address=addr, latitude=lat, longitude=lon,
                           connector_type=conn, power_kw=kw, price_per_kwh=price))
        db.add(User(email="driver@example.com", name="Demo Driver", password_hash=hash_password("password123")))
        db.commit()
        print("Seeded: host@example.com / driver@example.com (password: password123)")
