# ⚡ EV Share

Peer-to-peer EV charger sharing. Owners list a home or workplace charger; drivers find one nearby and book a time slot.

## Features (v0.1)

- **Accounts**: register / login with JWT bearer tokens (PBKDF2-hashed passwords)
- **Chargers**: list, edit, deactivate; search by location radius, connector type, power and price
- **Bookings**: conflict-free time slots (back-to-back allowed), future-only, max 8 h, no self-booking, cancellable by driver or owner, upper-bound cost estimate
- **Web UI**: minimal single page at `/`, interactive API docs at `/docs`

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # set a real EVSHARE_SECRET_KEY
python -m scripts.seed          # optional demo data
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000> (UI) or <http://127.0.0.1:8000/docs> (API). Demo logins after seeding: `host@example.com` / `driver@example.com`, password `password123`.

Run tests: `pytest`

## API overview

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/auth/register` | – | Create account |
| POST | `/auth/login` | – | Get access token (form: `username`=email, `password`) |
| GET | `/auth/me` | ✓ | Current user |
| POST | `/chargers` | ✓ | List a charger |
| GET | `/chargers` | – | Search (`lat`, `lon`, `radius_km`, `connector_type`, `min_power_kw`, `max_price_per_kwh`) |
| GET | `/chargers/mine` | ✓ | My chargers |
| PATCH | `/chargers/{id}` | owner | Edit / deactivate |
| POST | `/bookings` | ✓ | Book a slot (timestamps must include a timezone) |
| GET | `/bookings/mine` | ✓ | My bookings |
| GET | `/bookings/charger/{id}` | owner | Bookings on my charger |
| POST | `/bookings/{id}/cancel` | driver/owner | Cancel |

## Project layout

```
app/
  main.py          FastAPI app, routers, static UI
  config.py        env-driven settings (EVSHARE_*)
  database.py      SQLAlchemy engine/session
  models.py        User, Charger, Booking
  schemas.py       request/response models
  security.py      password hashing, JWT
  deps.py          DB session + current-user dependencies
  routers/         auth, chargers, bookings
  services/geo.py  haversine + bounding box
static/            index.html + app.js (no build step)
scripts/seed.py    demo data
tests/             pytest suite (in-memory SQLite)
```

## Roadmap

- Payments and payouts (UPI / Razorpay) and real metered-energy billing
- Reviews and ratings, owner availability windows
- Map view, notifications, Postgres + Alembic migrations
- Rate limiting and email verification

## License

See [LICENSE](LICENSE).
