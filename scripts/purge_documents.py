"""Delete identity documents that passed their retention period. Run it daily (cron / a scheduled job).
Usage: python -m scripts.purge_documents [--dry-run]"""
import sys

from app import models  # noqa: F401
from app.database import SessionLocal
from app.services.retention import purge_expired_documents

with SessionLocal() as db:
    r = purge_expired_documents(db, dry_run="--dry-run" in sys.argv)
print(("Would delete" if r["dry_run"] else "Deleted") + f" {r['documents']} document(s) of {r['users']} user(s).")
