"""Put an existing account back to 'not verified' so you can test the registration flow.
Usage: python -m scripts.reset_verification you@example.com"""
import sys

from app import models  # noqa: F401
from app.database import SessionLocal
from app.models import User, VerificationStatus

if len(sys.argv) != 2:
    sys.exit("usage: python -m scripts.reset_verification EMAIL")
with SessionLocal() as db:
    u = db.query(User).filter_by(email=sys.argv[1].lower()).first()
    if not u:
        sys.exit("No account with that email. Run: python -m scripts.list_users")
    if u.is_admin:
        sys.exit("That account is an admin; reset a normal account instead.")
    u.verification_status, u.email_verified, u.rejection_reason, u.submitted_at = VerificationStatus.NOT_SUBMITTED, False, None, None
    db.commit()
    print(f"{u.email} must now complete verification (documents already uploaded are kept; the email code is needed again).")
