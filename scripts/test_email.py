"""Send one test email using the SMTP settings in .env.
Usage: python -m scripts.test_email you@example.com
Where to run: the project folder, with the virtual environment active.
"""
import sys

from app.config import settings
from app.services.mailer import MailError, send_mail


def main() -> int:
    if len(sys.argv) != 2 or "@" not in sys.argv[1]:
        print("Usage: python -m scripts.test_email you@example.com")
        return 2
    if settings.otp_provider != "smtp":
        print("EVSHARE_OTP_PROVIDER is not 'smtp', so nothing will be sent.")
        print("Set EVSHARE_OTP_PROVIDER=smtp in .env (see docs/SETUP_EMAIL_PAYMENTS.md), then run this again.")
        return 1
    missing = [k for k, v in {"EVSHARE_SMTP_HOST": settings.smtp_host, "EVSHARE_SMTP_USER": settings.smtp_user,
                              "EVSHARE_SMTP_PASSWORD": settings.smtp_password, "EVSHARE_SMTP_FROM": settings.smtp_from}.items() if not v]
    if missing:
        print("Missing in .env: " + ", ".join(missing))
        return 1
    try:
        send_mail(sys.argv[1], "EV Share test email", "This is a test email from EV Share. If you can read this, email works.")
    except MailError as exc:
        print(f"FAILED: {exc}")
        print("Check the SMTP host, port, login and SMTP key in .env, and that the sender address is verified.")
        return 1
    print(f"OK: test email sent to {sys.argv[1]}. Check the inbox and the spam folder.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
