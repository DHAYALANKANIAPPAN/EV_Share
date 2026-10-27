"""Create a new reviewer (admin) account.  Usage: python -m scripts.create_admin"""
import getpass

from app import models  # noqa: F401
from app.database import SessionLocal
from app.models import Role, User, VerificationStatus
from app.security import hash_password

email = input("Reviewer email: ").strip().lower()
name = input("Reviewer name: ").strip() or "Reviewer"
password = getpass.getpass("Password (min 8 characters, hidden): ")
if "@" not in email or len(password) < 8:
    raise SystemExit("Enter a valid email and a password of at least 8 characters. Nothing was created.")
if password != getpass.getpass("Repeat password: "):
    raise SystemExit("Passwords did not match. Nothing was created.")
with SessionLocal() as db:
    if db.query(User).filter_by(email=email).first():
        raise SystemExit("That email already has an account. Use: python -m scripts.make_admin")
    db.add(User(email=email, name=name, password_hash=hash_password(password), role=Role.DRIVER, is_admin=True,
                email_verified=True, verification_status=VerificationStatus.APPROVED))
    db.commit()
print(f"Reviewer {email} created. Sign in with 'Reviewer sign in' at the bottom of the site.")
