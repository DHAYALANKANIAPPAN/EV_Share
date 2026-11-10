from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import models  # noqa: F401  (register tables)
from .config import settings
from .routers import admin, auth, bookings, chargers, hub, payments, reviews, verification

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# Schema is managed by Alembic: run `alembic upgrade head` (see README).
app = FastAPI(title="EV Share", description="Peer-to-peer EV charger sharing.", version="0.4.0")
for r in (auth, verification, admin, hub, chargers, bookings, reviews, payments):
    app.include_router(r.router)


CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' https://checkout.razorpay.com",  # Razorpay's checkout script; nothing else from outside
    "style-src 'self' 'unsafe-inline'",                  # Leaflet and the page's helpers set inline styles
    "font-src 'self'",
    "img-src 'self' data: https://*.tile.openstreetmap.org",  # OpenStreetMap map tiles
    "connect-src 'self' https://lumberjack.razorpay.com https://api.razorpay.com",
    "frame-src https://checkout.razorpay.com https://api.razorpay.com",
    "object-src 'none'", "base-uri 'self'", "form-action 'self'", "frame-ancestors 'none'",
])


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    if settings.csp_mode == "enforce":
        resp.headers["Content-Security-Policy"] = CSP
    elif settings.csp_mode == "report-only":
        resp.headers["Content-Security-Policy-Report-Only"] = CSP
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("Permissions-Policy", "geolocation=(self)")
    if settings.env != "dev":
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return resp


@app.get("/limits", tags=["meta"])
def limits():
    """Usage limits the interface follows. The server enforces them either way."""
    return {"max_active_bookings": settings.max_active_bookings,
            "max_active_hub_bookings": settings.max_active_hub_bookings,
            "max_chargers_per_hub": settings.max_chargers_per_hub}


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get(settings.staff_path, include_in_schema=False)
def staff_portal():
    """Reviewer portal. Not linked from the public site and kept out of search engines."""
    return FileResponse(STATIC_DIR / "staff.html", headers={"X-Robots-Tag": "noindex, nofollow", "Cache-Control": "no-store"})



