# ⚡ EV Share

[![XERJ Corpus Hub contributor](https://hub.xerj.org/contributors/DHAYALANKANIAPPAN/badge.svg)](https://hub.xerj.org/contributors/DHAYALANKANIAPPAN)
[![License: BSD-2-Clause](https://img.shields.io/badge/License-BSD_2--Clause-blue.svg)](LICENSE)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Corpus](https://img.shields.io/badge/XERJ_Corpus_Hub-Selected_Reference-8A2BE2)](https://hub.xerj.org/corpus/dhayalankaniappan--ev-share)

Peer-to-peer EV charger sharing. Owners list a home or workplace charger; drivers find one on a map, book a slot, pay, and review it afterwards.

> **Selected for XERJ Corpus Hub**: The UI redesign and architecture implementation of EV_Share has been selected as an open reference implementation for AI coding agents. View the indexed corpus entry on [XERJ Corpus Hub](https://hub.xerj.org/corpus/dhayalankaniappan--ev-share).
Peer-to-peer EV charger sharing. Owners list a home or workplace charger; drivers find one on a map, book a slot, pay, and review it afterwards.

## Features

- **Map search**: Leaflet + OpenStreetMap, "use my location", search by radius, connector, power, price and rating
- **Verified accounts**: drivers and hubs upload documents, confirm their email with an OTP, and are approved by a reviewer before they can book or list
- **Accounts**: register / login (JWT bearer tokens, PBKDF2-hashed passwords)
- **Chargers**: list, edit, pause; optional daily **availability window** with timezone (overnight windows like 18:00 → 08:00 supported)
- **Bookings**: unpaid bookings are released after 15 min (`EVSHARE_UNPAID_HOLD_MINUTES`), conflict-free slots (back-to-back allowed), future-only, max 8 h, no self-booking, cancel by driver or owner
- **Payments**: `mock` provider for development, `razorpay` provider (Orders API + signature verification); paid bookings are refunded on cancellation
- **Reviews**: 1–5 stars + comment, only for your own ended, non-cancelled bookings; average rating shown in search
- **Migrations**: Alembic; SQLite by default; Postgres tested (migrations and a full booking/payment flow)

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

### Razorpay

1. Create a Razorpay account and copy your **test-mode** key id and secret from the dashboard.
2. In `.env`: `EVSHARE_PAYMENT_PROVIDER=razorpay`, `EVSHARE_RAZORPAY_KEY_ID=...`, `EVSHARE_RAZORPAY_KEY_SECRET=...` (never commit `.env`).
3. Restart the app. "Reserve and pay" and "Pay now" open Razorpay's checkout; use Razorpay's test cards/UPI from their docs.

### Postgres

```bash
docker compose up -d                              # local Postgres (docker-compose.yml)
pip install -r requirements-postgres.txt
# in .env: EVSHARE_DATABASE_URL=postgresql+psycopg://evshare:evshare@localhost:5432/evshare
alembic upgrade head
```

### Deploying

The repo ships a `Dockerfile` (runs `alembic upgrade head`, then serves on `$PORT`). On a host such as Render, Railway or Fly.io:

1. Create a managed **Postgres** database.
2. Create a web service from this repo using the Dockerfile.
3. Set these environment variables on the service:

| Variable | Value |
|---|---|
| `EVSHARE_ENV` | `production` |
| `EVSHARE_SECRET_KEY` | a random 48+ character string (`python -c "import secrets; print(secrets.token_urlsafe(48))"`) |
| `EVSHARE_DATABASE_URL` | the database URL from your host (`postgres://...` is accepted) |
| `EVSHARE_PAYMENT_PROVIDER` | `razorpay` (production refuses the mock provider) |
| `EVSHARE_DOCS_ENCRYPTION_KEY` | a Fernet key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `EVSHARE_OTP_PROVIDER`, `EVSHARE_SMTP_HOST`, `EVSHARE_SMTP_PORT`, `EVSHARE_SMTP_USER`, `EVSHARE_SMTP_PASSWORD`, `EVSHARE_SMTP_FROM` | `smtp` and your mail service details (production refuses the console provider) |
| `EVSHARE_RAZORPAY_KEY_ID` / `EVSHARE_RAZORPAY_KEY_SECRET` | start with **test-mode** keys |

4. Deploy and open `/health` to confirm it responds. Do **not** run `scripts.seed` in production.

HTTPS is provided by the host. Keep secrets in the host's environment settings, never in the repo.
The Docker image itself has not been built in this project's development environment, so expect to fix small things on the first deploy.

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

## Account verification

Everyone registers as a **driver** or a **hub** (house or shop) and must be approved before using the marketplace:

| Account | Needs |
|---|---|
| Driver | email OTP, vehicle registration number, **masked** Aadhaar, vehicle RC |
| Hub: house | email OTP, house documents, property tax receipt |
| Hub: shop | the above plus sanctioned building plan, occupancy certificate, shop & establishment licence |

Flow: register, confirm email with a 6-digit code (expires in 10 min, 5 attempts, single use, resend cooldown), upload documents, agree to the consent statement, submit. A **reviewer** (an account with `is_admin`) opens each document, checks it against the official portals, and approves or asks for changes with a reason. Until approved, drivers cannot book, hubs cannot list, and an unapproved hub's chargers are hidden from search.

- Registration is one guided flow: create account, confirm email, upload documents, then review. The required documents are listed before the user signs up.
- **Reviewer (admin) accounts cannot be created from the website** (that would let anyone approve themselves). Create one from the terminal: `python -m scripts.create_admin` (new account) or `python -m scripts.make_admin` (pick an existing account from a list). Reviewers do **not** use the public Login. They sign in on a separate, unlinked **reviewer portal** at `/staff` (change it with `EVSHARE_STAFF_PATH`, e.g. `/review-x7k2`). The backend also enforces the split: a reviewer account is refused by the public login, and a normal account is refused by the portal login. A hidden address is not a lock, so keep strong reviewer passwords; both logins share the failed-attempt limit. The seed script also creates `admin@example.com`.
- Re-test the flow with an existing account: `python -m scripts.reset_verification you@example.com`.
- Files are validated by content (PDF/JPG/PNG, 5 MB), stored under random names and **encrypted at rest** (Fernet). Set `EVSHARE_DOCS_ENCRYPTION_KEY` outside dev. Only reviewers can read them.
- **Aadhaar:** the app never stores the number. Ask users to upload a masked copy. Rules for private entities handling Aadhaar are strict, so get legal advice before going live.
- The OTP is emailed (`EVSHARE_OTP_PROVIDER=smtp`); in dev it is printed in the server log. Every sign-up and OTP screen shows a notice that EV Share never asks for OTPs by call, text or email.
- Existing accounts are treated as approved when you upgrade (migration `0002`); accounts that already own chargers become house hubs.

### How a booking works

1. A **driver** sees only chargers whose hub is **live now** (optionally "Chargers near me", nearest first) and sends a **request** for a time slot. The slot is held.
2. The **hub** sees it under **Orders** (new requests are checked every 20 s and counted in the menu) and **accepts or declines** within `EVSHARE_HUB_RESPONSE_MINUTES` (default 20), otherwise the request is cancelled. Both sides are emailed.
3. After acceptance the driver sees the exact address and a **Directions** link and **pays** within `EVSHARE_UNPAID_HOLD_MINUTES` (default 15), otherwise the slot is released. Declined or cancelled requests are never charged; paid cancellations are refunded.

4. During the session the hub's Orders page shows it under **In progress** and the driver's bookings show **Session in progress**. Either side can **end the session** when charging is done: the booking becomes *Completed*, the rest of the slot is freed, and the driver can leave a review. While a session runs the charger shows **In use until ...** to other drivers. A driver holds **one open booking at a time** (`EVSHARE_MAX_ACTIVE_BOOKINGS`, default 1): they can book again once it is finished, cancelled or declined.

Hubs only get **Orders, My chargers and Share a charger** (plus the Go live bar); drivers only get **Find chargers and My bookings**.

### Hubs: Go live

Approved hubs see a **Go live** bar at the bottom of every page. Pressing it sends the device's location; the hub goes live only if it is within `EVSHARE_LIVE_RADIUS_M` (default 500 m) of one of its chargers, and only those nearby chargers are live. While the page stays open it re-checks the location every 5 minutes; if the pings stop, the hub goes offline `EVSHARE_LIVE_TTL_MINUTES` (default 30) after the last one, and a ping from away from every charger takes it offline immediately. Drivers can only reserve **live** chargers (offline ones are listed as "Hub offline"); bookings that already exist are not affected. `GET /chargers?live_only=true` returns just the live ones.

### Managing users (reviewer portal)

The portal has two tabs: **Applications** and **Users**. Users lists every driver and hub (search by name or email, filter by type and status). **Remove** asks for a reason, then:
- the user is emailed the reason and their login stops working (sessions end immediately);
- upcoming bookings (as driver, or on the hub's chargers) are cancelled and refunded;
- the hub's chargers disappear from search;
- the email address stays reserved: the person must register again with a different email and verify again.

**Restore** reverses a removal. If the email cannot be sent, the removal still happens and the reviewer is told to contact the person another way. The mail settings are the same `EVSHARE_SMTP_*` values used for OTP codes.

## Security

- Browser sessions use an **HttpOnly, SameSite=Lax cookie** (`Secure` outside dev); the token is never exposed to page JavaScript. Cookie-authenticated writes also need the `X-Requested-With: evshare` header (CSRF defence). API clients can keep using `Authorization: Bearer`.
- **Login attempts are limited** per (IP, email): 5 failures in 15 minutes returns 429. The counter lives in memory, so use Redis or a database table if you run several instances.
- Standard headers are set on every response (`nosniff`, `X-Frame-Options: DENY`, referrer and permissions policies, HSTS outside dev).
- Not done yet: email verification and password reset (they need an email provider), a Content-Security-Policy (the page currently loads Tailwind from a CDN), registration throttling.

## Front-end notes

`static/css/app.css` holds the design tokens (light and dark colours as CSS variables), then buttons, forms, rows, status pills, drawer/dialog/toast styles and animations, in numbered sections. Tailwind utilities (CDN build, settings in `static/js/tailwind-config.js`) handle layout. Live countdowns and progress bars come from one shared timer in `static/js/ui.js`, and animations switch off for people who prefer reduced motion. The CDN Tailwind build is fine for development; compile it before a high-traffic launch.

## Known limitations

- **Billing is a flat slot price** (full power × hours × ₹/kWh), not metered energy.
- **Uploaded documents are stored on the server disk.** Most hosts wipe that disk on redeploy, so use a persistent volume or move storage to S3-style object storage before real users. Documents are also never auto-deleted yet; add a retention rule.
- **Verification is manual.** A person checks each document. Automatic checks need a licensed verification provider.
- **No owner payouts yet**: payments are collected on your gateway account; splitting money to hosts is not built.
- Razorpay support follows the documented API but has only been tested with mocked HTTP. Test with Razorpay test keys before going live.
- The page loads Leaflet from cdnjs and map tiles from OpenStreetMap; the JWT is kept in `localStorage`.

## License

See [LICENSE](LICENSE).
