from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import models  # noqa: F401  (register tables)
from .routers import auth, bookings, chargers, payments, reviews

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# Schema is managed by Alembic: run `alembic upgrade head` (see README).
app = FastAPI(title="EV Share", description="Peer-to-peer EV charger sharing.", version="0.2.0")
for r in (auth, chargers, bookings, reviews, payments):
    app.include_router(r.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/classic", include_in_schema=False)
def classic():
    """Previous Leaflet UI (adds charger sharing, reviews, owner tools) until they are ported."""
    return FileResponse(STATIC_DIR / "classic.html")
