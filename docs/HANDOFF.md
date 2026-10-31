# EV Share: handoff document

## 1. What the product is
EV Share is a peer-to-peer EV charger marketplace. **Hubs** (a house or shop with a charger) list chargers. **Drivers** find chargers that are **live right now**, send a booking request, the hub accepts or declines, the driver pays, and then charges. **Reviewers** (staff) verify hubs and drivers against official records and manage accounts, from a separate hidden portal.

Stack: Python 3.12+, FastAPI, SQLAlchemy 2, Alembic, SQLite (dev) or Postgres (prod), vanilla JavaScript ES modules, Tailwind (CDN) plus a plain CSS file, Leaflet/OpenStreetMap for the street map, Razorpay for payments (or a mock), Docker for deployment.

## 2. Repository layout
```
app/
  main.py            FastAPI app, routers, security headers, /staff and /classic routes
  config.py          every setting, read from EVSHARE_* environment variables (validated)
  database.py        SQLAlchemy engine and session
  models.py          User, Charger, Booking, Payment, Review, Document, OtpCode, enums
  schemas.py         request and response shapes
  security.py        password hashing (PBKDF2), JWT, cookie name
  deps.py            current user; role/approval guards (ApprovedDriver, ApprovedHub, AdminUser)
  routers/
    auth.py          register, login (public), staff/login (reviewers), logout, me
    verification.py  OTP, vehicle number, document upload, submit, status
    admin.py         reviewer queue, document download, user list, remove/restore
    chargers.py      search (live_only, near me), create, edit, busy times
    bookings.py      request, list mine, cancel, finish session
    hub.py           Go live/offline, orders (accept/decline)
    payments.py      checkout, confirm
    reviews.py       leave a review, list reviews
  services/
    availability.py  daily opening window incl. overnight windows
    bookings.py      cancel + refund (shared)
    documents.py     content-sniffed uploads, encrypted before storage
    expiry.py        releases unanswered requests and unpaid acceptances
    geo.py           distance, bounding box
    live.py          "is this hub live and close enough to this charger"
    mailer.py        SMTP mail (or console log in dev)
    notify.py        best-effort email that never breaks a booking
    otp.py           email one-time codes (hashed, expiring, attempt-limited)
    payments.py      mock and Razorpay providers, HMAC signature check
    ratelimit.py     failed-login limiter (in memory)
    retention.py     automatic deletion of documents past retention
    storage.py       local disk or S3 for encrypted blobs
    verification.py  which documents each account type needs
migrations/          Alembic; versions 0001 to 0006
scripts/
  seed.py            demo hub, driver, reviewer (dev only)
  create_admin.py    create a reviewer account (interactive, hidden password)
  make_admin.py      promote an existing account to reviewer (numbered list)
  list_users.py      list accounts
  reset_verification.py  put an account back to "not verified" (testing)
  purge_documents.py delete documents past retention (run daily; --dry-run)
static/
  index.html         public app shell (Login/Register, Find, Bookings, Orders, Share, Verify)
  staff.html         reviewer portal shell (not linked from anywhere)
  css/app.css        design tokens (light and dark), components, animations
  js/main.js         public app logic
  js/staff.js        reviewer portal logic
  js/api.js          every backend call, with CSRF header
  js/ui.js           helpers: DOM builder, toasts, countdowns, progress, confirm dialog
  js/tailwind-config.js
  app.js, style.css, classic.html   OLD interface, kept at /classic only; safe to delete
tests/               72 tests (see section 6)
docs/SELF_HOSTING.md how to run it on a server with Docker
.github/workflows/   ci.yml (tests + migration checks on SQLite and Postgres), release.yml (tests, Docker image, GitHub release on tags)
Dockerfile, docker-compose.prod.yml, .dockerignore
requirements.txt, requirements-dev.txt, requirements-postgres.txt, requirements-s3.txt, requirements-redis.txt
.env.example, README.md, CONTRIBUTING.md, SECURITY.md, CHANGELOG.md
```

## 3. Business rules (what the code enforces)
**Accounts and verification**
- Register as a driver, or as a hub of type HOUSE or SHOP. Registration then asks for an email code, the documents, and a consent tick.
- Driver documents: Aadhaar (masked copy only), vehicle registration certificate (RC), and a vehicle number (stored in capitals).
- House hub: house/property documents and a property tax receipt. Shop hub: the same plus sanctioned building plan, occupancy certificate and shop & establishment licence.
- An account can only book (driver) or list/go live/take orders (hub) after a reviewer **approves** it. Until then the menu shows only "Verify account".
- Reviewers reject with a reason; the applicant sees it and can resubmit.
- A reviewer can **remove** an account: it is emailed the reason, its login and sessions stop, upcoming bookings are cancelled and refunded, a hub's chargers disappear from search, and the email stays reserved. **Restore** reverses it.
- Reviewer accounts are never listed to others and never use the public login.

**Hubs**
- A hub is **live** only when it presses Go live while within `EVSHARE_LIVE_RADIUS_M` (500 m) of one of its chargers. It stays live `EVSHARE_LIVE_TTL_MINUTES` (30) after its last ping. The page re-pings every 5 minutes. Going out of range takes it offline immediately.
- Only chargers whose hub is live are bookable. Offline chargers are shown as "Hub offline".
- Orders page: **New requests** (accept or decline, with optional reason), **In progress** (mark session done), **Accepted** (waiting for payment, with a countdown), **History**.

**Drivers**
- Find shows only **live** chargers, with "Chargers near me" and a radius filter. Each shows "In use until ..." while a session runs.
- A driver sends a **request** for a time slot (max 8 hours, must be inside the charger's opening window, in the future). The request holds the slot.
- Only after the hub accepts can the driver **pay**, and then the exact address and a Directions link appear.
- A driver holds **one open booking** at a time (`EVSHARE_MAX_ACTIVE_BOOKINGS`, default 1).
- **Ending a session** (driver or hub, once started and paid) marks it Completed and frees the rest of the slot. Reviews are allowed after completion.

**Time limits (all configurable)**
- Unanswered request: cancelled after `EVSHARE_HUB_RESPONSE_MINUTES` (20).
- Accepted but unpaid: released after `EVSHARE_UNPAID_HOLD_MINUTES` (15) from acceptance.
- Free chargers (₹0/kWh) are paid immediately on accept.
- Checks happen lazily on reads and writes, so there is no background worker.

**Money**
- Price is a flat estimate: `power_kW × hours × ₹/kWh` (full power for the whole slot). No metering yet.
- Cancelling a paid booking refunds it. Declined or unpaid bookings are never charged.
- Providers: `mock` (dev only, production refuses it) or `razorpay` (Orders API, HMAC signature verified before a booking is marked paid).

**Documents and privacy**
- Uploads are checked by their real content (PDF, JPG, PNG) and limited to 5 MB.
- Encrypted with Fernet before storage; storage is `local` or `s3`; production refuses local disk unless `EVSHARE_ALLOW_LOCAL_STORAGE=true`.
- Only reviewers can download them, with `Cache-Control: no-store`.
- Hubs never see a driver's email, only name and vehicle number.
- Automatic deletion: approved and removed accounts after 30 days; rejected applicants after 90; never-submitted uploads after 30; applications under review are never touched.

## 4. Security (implemented)
- **Passwords:** PBKDF2-SHA256, 240,000 iterations, random 16-byte salt.
- **Sessions:** JWT (HS256), 60-minute expiry, in an **HttpOnly, SameSite=Lax cookie** (`Secure` outside dev). Never in JavaScript-readable storage.
- **CSRF:** cookie-authenticated writes must send `X-Requested-With: evshare`. Bearer-token clients (API) are exempt.
- **Login limits:** 5 failures per (IP, email) within 15 minutes returns 429 with `Retry-After`. Shared by the public and reviewer logins. In memory, so it resets on restart and isn't shared between servers.
- **Two entrances:** public `/auth/login` refuses reviewers; `/auth/staff/login` refuses normal users. Both give the same "Incorrect email or password" message.
- **Reviewer portal:** at `EVSHARE_STAFF_PATH` (default `/staff`), not linked, served with `X-Robots-Tag: noindex, nofollow`. Safe-path validation rejects clashes with real routes.
- **Headers on every response:** `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy: geolocation=(self)`, HSTS outside dev.
- **Production guards:** refuses to start with the dev secret, a secret under 32 characters, the mock payment provider, the console OTP provider, a missing encryption key, or local document storage without explicit permission.
- **Input validation:** Pydantic schemas; plate numbers normalised; coordinates range-checked; timezones validated.
- **Known gaps** (also in README): no email verification on password reset (there is none yet), no CSP (the page uses CDN scripts), login limiter is per process, a hidden URL is not a lock.

## 5. How to run it

### Development (SQLite, demo data)
```bash
cd EV_Share
python -m venv venv && source venv/bin/activate     # ALWAYS activate first in each new terminal
pip install -r requirements-dev.txt
cp .env.example .env                                 # leave the secrets blank for dev
alembic upgrade head                                 # creates/updates the database
python -m scripts.seed                               # demo accounts (below)
uvicorn app.main:app --reload
```
Open `http://127.0.0.1:8000` (public app) and `http://127.0.0.1:8000/staff` (reviewer portal). API docs: `/docs`.

Demo accounts (password `password123`): `host@example.com` (hub, live at Cantonment only), `driver@example.com` (verified driver), `admin@example.com` (reviewer).

Dev-only behaviour: OTP codes and all emails are printed to the `uvicorn` terminal (`DEV ONLY: verification code for ...`, `DEV ONLY: email to ...`).

Without activating the venv: `venv/bin/alembic`, `venv/bin/pytest`, `venv/bin/uvicorn`.

### Create a reviewer (needed to approve anyone)
```bash
python -m scripts.create_admin           # new reviewer: asks for email, name, hidden password
python -m scripts.make_admin             # or promote an existing account from a numbered list
python -m scripts.list_users             # see accounts
python -m scripts.reset_verification you@example.com   # send an account back to "not verified" (testing)
```

### Tests
```bash
pytest                       # 65 tests, expected: "65 passed"
pytest -q tests/test_security.py      # one file
pytest -q -k lockout          # by name
```
Expected output ends with `65 passed`. A `StarletteDeprecationWarning` about `httpx` is harmless.

### Browser tests used during development
These simulate the real screens in jsdom against a live server (kept outside the repo in the dev setup; re-create from the flows in section 3 if needed). The last run passed 39 of 39 UI steps.

### Database
```bash
alembic upgrade head        # apply all migrations
alembic check               # must say "No new upgrade operations detected"
alembic downgrade -1        # roll back one step (test it before relying on it)
```
Postgres: `docker compose up -d` (uses `docker-compose.yml`), then set `EVSHARE_DATABASE_URL=postgresql+psycopg://evshare:evshare@localhost:5432/evshare` and `pip install -r requirements-postgres.txt`.

### Production (Docker)
See `docs/SELF_HOSTING.md`. Summary: copy `.env.example` to `.env`, set `EVSHARE_ENV=production`, the secret key, `EVSHARE_DOCS_ENCRYPTION_KEY`, `POSTGRES_PASSWORD`, `EVSHARE_STAFF_PATH`, Razorpay keys, SMTP settings and storage. Then `docker compose -f docker-compose.prod.yml up -d`. Create a reviewer with `docker compose ... exec app python -m scripts.create_admin`. Run `scripts.purge_documents` daily. HTTPS through a reverse proxy (Caddy example in the guide).

### Settings reference (all are `EVSHARE_*` environment variables)
ENV (dev|production), SECRET_KEY, DATABASE_URL, ACCESS_TOKEN_MINUTES (60), MAX_BOOKING_HOURS (8), LIVE_TTL_MINUTES (30), LIVE_RADIUS_M (500), STAFF_PATH (/staff), LOGIN_MAX_FAILURES (5), LOGIN_WINDOW_MINUTES (15), MAX_ACTIVE_BOOKINGS (1, 0 = unlimited), HUB_RESPONSE_MINUTES (20), UNPAID_HOLD_MINUTES (15), DEFAULT_TIMEZONE (Asia/Kolkata), STORAGE_BACKEND (local|s3), ALLOW_LOCAL_STORAGE (false), S3_BUCKET, S3_PREFIX (documents/), S3_REGION, S3_ENDPOINT_URL, DOCS_RETENTION_DAYS (30), DOCS_REJECTED_RETENTION_DAYS (90), UPLOAD_DIR (./uploads), DOCS_MAX_MB (5), DOCS_ENCRYPTION_KEY, OTP_PROVIDER (console|smtp), OTP_TTL_MINUTES (10), OTP_MAX_ATTEMPTS (5), OTP_RESEND_SECONDS (60), OTP_MAX_PER_HOUR (5), SMTP_HOST, SMTP_PORT (587), SMTP_USER, SMTP_PASSWORD, SMTP_FROM, PAYMENT_PROVIDER (mock|razorpay), RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET.

## 6. Tests: what each file proves
| File | Tests | What it proves |
|---|---|---|
| test_api.py | 5 | auth flow; charger ownership; search by distance and filters; booking rules; cancel frees a slot |
| test_features.py | 14 | availability windows (day, overnight); verification gate; reviews and ratings; mock payments and refund; Razorpay signature flow; expiry of requests and unpaid acceptances; production config safety; Postgres URL normalisation |
| test_hub_live.py | 5 | offline hubs refuse bookings; must be at the charger to go live; only nearby chargers are live; live expires without pings; only approved hubs can go live |
| test_hub_orders.py | 4 | request → accept → pay with emails; decline frees the slot; only the owning hub can answer, once; cancel and refund rules |
| test_lifecycle.py | 5 | running session makes the charger busy until finished; hub or driver can finish, outsiders can't; can't finish early or unpaid; review after completion; one open booking per driver |
| test_ratelimit_redis.py | 7 | Redis-backed sliding window login limit; isolation; multi-worker coordination; reset |
| test_security.py | 7 | HttpOnly cookie; CSRF header required for cookie writes; Bearer exempt; logout ends session; login lockout; failed count resets on success; security headers |
| test_staff_portal.py | 10 | portal page noindex and unlinked; two entrances enforced; shared failed-login limit; unsafe portal paths rejected |
| test_storage.py | 3 | local storage round trip; S3 (mocked with moto) stores only ciphertext and deletes replaced files; retention rules delete only the right documents |
| test_user_management.py | 4 | user list excludes reviewers and filters; removal blocks login, cancels and refunds, emails; hub removal hides chargers; reviewers can't be removed; mail failure is reported |
| test_verification.py | 8 | registration roles; unverified can't book or list; unapproved hub hidden; OTP limits and expiry; resend cooldown; document validation and encryption; full driver journey with review; shop vs house requirements |

**Browser flow tests** (run outside the repo during development, 39 steps): register a hub, verify, upload, submit; reviewer rejects, applicant resubmits, reviewer approves; hub goes live from a checked location; driver sees only live chargers; request → accept → pay → directions → session in progress → end; removal emails the user and blocks login; restore.

## 7. Built so far (chronological, by feature branch)
1. **Core:** accounts, chargers with opening windows, bookings with conflict checks, reviews and ratings, mock and Razorpay payments, Alembic, Postgres support, CI.
2. **Security pass:** HttpOnly cookie sessions with CSRF header, login limits, security headers, production guards.
3. **Account verification:** role at sign-up, documents, email OTP, reviewer queue with approve or ask-for-changes, unverified users gated, unapproved hubs hidden.
4. **Reviewer portal:** separate hidden page and login, enforced in the backend.
5. **Branch `feature/vehicle-uppercase`:** vehicle numbers typed in capitals.
6. **Branch `feature/user-management`:** Users tab; remove with reason and email; restore; refunds; reserved emails.
7. **Branch `feature/hub-go-live`:** location-checked Go live bar, live-only chargers, then the request/accept/decline/pay flow, then the lifecycle: running sessions, end session, busy chargers, one booking per driver.
8. **Branch `feature/ui-polish`:** stylesheet split into `static/css/app.css`, status pills, countdowns, progress bars, spinners, animations, reduced-motion support.
9. **Branch `feature/document-storage`:** S3 or local storage, encrypted; automatic retention and `scripts.purge_documents`.
10. **Branch `chore/releases`:** release workflow (tests, Docker image to GHCR, GitHub release on tags), Dependabot, production compose file, self-hosting guide, CONTRIBUTING, SECURITY, CHANGELOG.
11. **Branch `fix/shared-login-limit`:** Redis-backed sliding-window login rate limiting (`RedisLoginLimiter`) across processes and servers, configurable via `EVSHARE_RATELIMIT_BACKEND=redis` and `EVSHARE_REDIS_URL`, backed by `fakeredis` in dev/tests, Redis container in docker compose.
12. **External:** the project is listed on the XERJ Corpus Hub as a *corpus contributor*, not a code contributor to XERJ.

## 8. Still to do (in priority order)
1. **Real-browser check:** all screens have only been tested in jsdom. Walk through every flow once in Chrome/Firefox, on a phone-width screen too.
2. **Email provider:** choose one (for example Resend, SendGrid, Amazon SES or Gmail SMTP) and set the `EVSHARE_SMTP_*` values. Production refuses the console OTP provider.
3. **Run the release pipeline:** push a tag, confirm the image builds and pushes to GHCR, make the package public, and check the release page. Expect small fixes.
4. **Run the Docker stack on a server** end to end, including `scripts.purge_documents` on a schedule and database backups.
5. **Email verification for password reset:** there is no "forgot password" yet.
6. **Content Security Policy:** compile Tailwind and vendor Leaflet/Tailwind so the page can use a strict CSP.
7. **Metered billing:** charge by energy delivered, not the flat slot estimate. Needs decisions on tariffs and how the hub reports energy.
9. **Host payouts:** split the payment between platform and hub. Needs commission rules, Razorpay Route or Payouts setup, and tax and KYC decisions.
10. **Real-time updates:** replace the 20-second order polling and the 30-second busy checks with server-sent events or WebSockets.
11. **Notifications:** push or SMS for new requests (SMS needs a registered provider in India).
12. **Ratings for hubs** (currently only charger ratings), and a hub dashboard with earnings.
13. **Accessibility audit** with a screen reader, and keyboard tests for the drawer and dialogs.
14. **Remove `/classic`** and the old `static/app.js` and `style.css` once confirmed unused.
15. **Clean up the tiny legacy shims** in `database.py` if any remain; run `ruff` or `flake8` across the codebase.
16. **Screenshots and a demo video** for the README and LinkedIn.
17. **Legal and compliance:** privacy policy and terms; Aadhaar handling advice (the app must not store the number); Indian data-protection obligations; payment-aggregator rules; electricity-selling rules for hubs (this may need a licence in some states).
18. **Growth:** support and contact page, admin analytics, and per-hub availability calendars.

## 9. Decisions and their reasons
- Aadhaar: the app asks for a **masked** copy and never stores the number, because private apps are restricted in handling it.
- Verification by **human review**, not automatic portal checks: government portals have no public API and scraping them isn't allowed.
- OTP by **email**, not SMS, because SMS in India needs paid, registered providers.
- Reviewers are **created from the terminal** and kept off the public site, so no one can approve themselves.
- Payment only after **acceptance**, so drivers don't pay for requests a hub never answers.
- Flat price estimate for now, because metering needs hardware or hub reporting that doesn't exist yet.

## 10. Git and branch workflow
- `main` is the protected release line. Every feature gets its own branch named `feature/…`, `fix/…`, `docs/…` or `chore/…`.
- Follow-up work on an existing feature goes in that feature's branch. Only a new feature starts a new branch.
- Each change: `git checkout -B <branch> origin/main` (or `git checkout -b` for a new branch), apply, `pytest`, `git status`, commit, `git push -u origin <branch>`, open a pull request, merge, then `git checkout main && git pull origin main`.
- Tag releases `vX.Y.Z` to trigger the release workflow.

## 11. Working agreements with the owner
- Deliver changes as **whole files in zips**, with exact commands to unzip, delete the zip, run tests, and commit.
- Always name the earlier zip to delete, and check the zips in the folder before a new one is sent.
- Be honest about what is untested (real browsers, Docker, the release pipeline, Razorpay live).
- Keep the wording of the XERJ credit accurate: a corpus contributor, not a code contributor.

---

**Immediate next steps for whoever picks this up:** (1) confirm `pytest` shows 65 passed; (2) run the development setup and walk the flows in section 3 in a real browser; (3) choose the email provider; (4) tag `v0.1.0` and check the release workflow.
