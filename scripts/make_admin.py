"""Promote an existing account to reviewer/admin.  Usage: python -m scripts.make_admin you@example.com"""
import sys

from app import models  # noqa: F401
from app.database import SessionLocal
from app.models import User, VerificationStatus

if len(sys.argv) != 2:
    sys.exit("usage: python -m scripts.make_admin EMAIL")
with SessionLocal() as db:
    user = db.query(User).filter_by(email=sys.argv[1].lower()).first()
    if not user:
        sys.exit("No account with that email. Register it first.")
    user.is_admin, user.email_verified, user.verification_status = True, True, VerificationStatus.APPROVED
    db.commit()
    print(f"{user.email} is now an admin.")
