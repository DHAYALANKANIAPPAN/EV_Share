"""Turn an existing account into a reviewer (admin).
Usage:  python -m scripts.make_admin            (lists accounts, you pick a number)
        python -m scripts.make_admin me@example.com
To create a brand-new reviewer account instead, use: python -m scripts.create_admin"""
import sys

from app import models  # noqa: F401
from app.database import SessionLocal
from app.models import User, VerificationStatus

with SessionLocal() as db:
    users = db.query(User).order_by(User.id).all()
    if len(sys.argv) == 2:
        user = next((u for u in users if u.email == sys.argv[1].lower()), None)
        if not user:
            sys.exit("No account with that email. Run this command without an email to pick from a list.")
    else:
        if not users:
            sys.exit("No accounts yet. Create one with: python -m scripts.create_admin")
        for i, u in enumerate(users, 1):
            print(f"{i:>3}  {u.email:<32} {u.role.value:<7} {u.verification_status.value:<14} admin={u.is_admin}")
        pick = input("Number of the account to make a reviewer: ").strip()
        if not pick.isdigit() or not 1 <= int(pick) <= len(users):
            sys.exit("Not a valid number. Nothing changed.")
        user = users[int(pick) - 1]
    user.is_admin, user.email_verified, user.verification_status = True, True, VerificationStatus.APPROVED
    db.commit()
    print(f"{user.email} is now a reviewer. Sign in on the reviewer portal (default address: /staff).")
