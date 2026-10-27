"""Show accounts (use it to find the email to pass to make_admin).  Usage: python -m scripts.list_users"""
from app import models  # noqa: F401
from app.database import SessionLocal
from app.models import User

with SessionLocal() as db:
    for u in db.query(User).order_by(User.id):
        print(f"{u.id:>3}  {u.email:<32} {u.role.value:<7} {u.verification_status.value:<14} admin={u.is_admin}")
