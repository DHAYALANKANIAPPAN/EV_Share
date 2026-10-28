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


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("Permissions-Policy", "geolocation=(self)")
    if settings.env != "dev":
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return resp


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


@app.get("/classic", include_in_schema=False)
def classic():
    """Previous Leaflet UI (adds charger sharing, reviews, owner tools) until they are ported."""
    return FileResponse(STATIC_DIR / "classic.html")
