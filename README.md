# ⚡ EV Share

Peer-to-peer EV charger sharing. Owners list a home or workplace charger; drivers find one on a map, book a slot, pay, and review it afterwards.

## Features

- **Map search**: Leaflet + OpenStreetMap, "use my location", search by radius, connector, power, price and rating
- **Accounts**: register / login (JWT bearer tokens, PBKDF2-hashed passwords)
- **Chargers**: list, edit, pause; optional daily **availability window** with timezone (overnight windows like 18:00 → 08:00 supported)
- **Bookings**: unpaid bookings are released after 15 min (`EVSHARE_UNPAID_HOLD_MINUTES`), conflict-free slots (back-to-back allowed), future-only, max 8 h, no self-booking, cancel by driver or owner
- **Payments**: `mock` provider for development, `razorpay` provider (Orders API + signature verification); paid bookings are refunded on cancellation
- **Reviews**: 1–5 stars + comment, only for your own ended, non-cancelled bookings; average rating shown in search
- **Migrations**: Alembic; SQLite by default, Postgres supported

## Quick start

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"   # paste into EVSHARE_SECRET_KEY in .env
alembic upgrade head            # create / update the database schema
python -m scripts.seed          # optional demo data
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000> (app) or <http://127.0.0.1:8000/docs> (API docs).
Demo logins after seeding: `host@example.com` / `driver@example.com`, password `password123`.

Upgrading from v0.1? The schema changed, so for a dev database delete `evshare.db`, then run `alembic upgrade head` and the seed again.

Run the tests with `pytest`.

## Configuration (`.env`, all prefixed `EVSHARE_`)

| Variable | Default | Notes |
|---|---|---|
| `ENV` | `dev` | `production` enforces a 32+ char secret and a real payment provider |
| `SECRET_KEY` | dev key | JWT signing key. Set your own, always |
| `DATABASE_URL` | `sqlite:///./evshare.db` | Postgres: `postgresql+psycopg://user:pass@host/db` |
| `PAYMENT_PROVIDER` | `mock` | `mock` or `razorpay` |
| `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` | – | Use Razorpay **test-mode** keys first |
| `DEFAULT_TIMEZONE` | `Asia/Kolkata` | Default for new chargers |

### Postgres

```bash
docker compose up -d                              # local Postgres (docker-compose.yml)
pip install -r requirements-postgres.txt
# in .env: EVSHARE_DATABASE_URL=postgresql+psycopg://evshare:evshare@localhost:5432/evshare
alembic upgrade head
```

### Changing the schema

Edit `app/models.py`, then `alembic revision --autogenerate -m "describe change"`, review the generated file in `migrations/versions/`, and `alembic upgrade head`.

## API overview

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/auth/register`, `/auth/login` | – | Create account / get token (login is a form: `username`=email, `password`) |
| GET | `/auth/me` | ✓ | Current user |
| POST | `/chargers` | ✓ | List a charger |
| GET | `/chargers` | – | Search (`lat`, `lon`, `radius_km`, `connector_type`, `min_power_kw`, `max_price_per_kwh`, `min_rating`) |
| GET | `/chargers/mine`, `/chargers/{id}` | ✓ / – | My chargers / one charger |
| PATCH | `/chargers/{id}` | owner | Edit, pause, change availability window |
| POST | `/bookings` | ✓ | Book a slot (timestamps need a timezone) |
| GET | `/bookings/mine`, `/bookings/charger/{id}` | ✓ / owner | My bookings / bookings on my charger |
| POST | `/bookings/{id}/cancel` | driver/owner | Cancel (refunds if paid) |
| POST | `/payments/checkout`, `/payments/confirm` | ✓ | Start payment / verify and mark paid |
| POST | `/reviews` | ✓ | Review an ended booking |
| GET | `/reviews/charger/{id}` | – | Reviews for a charger |

## Project layout

```
app/            FastAPI app: routers/, services/ (geo, availability, payments), models, schemas, security
migrations/     Alembic environment + versions/
static/         index.html, style.css, app.js (vanilla JS + Leaflet, no build step)
scripts/seed.py demo data
tests/          pytest suite (in-memory SQLite)
```

## Known limitations

- **Billing is a flat slot price** (full power × hours × ₹/kWh), not metered energy.
- **No owner payouts yet**: payments are collected on your gateway account; splitting money to hosts is not built.
- Razorpay support follows the documented API but has only been tested with mocked HTTP. Test with Razorpay test keys before going live.
- The page loads Leaflet from cdnjs and map tiles from OpenStreetMap; the JWT is kept in `localStorage`.

## License

See [LICENSE](LICENSE).
