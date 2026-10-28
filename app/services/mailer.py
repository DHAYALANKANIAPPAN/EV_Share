import logging
import smtplib
from email.message import EmailMessage

from ..config import settings

log = logging.getLogger("evshare.mail")


class MailError(Exception):
    pass


def send_mail(to: str, subject: str, body: str) -> None:
    """Send a plain-text email. With EVSHARE_OTP_PROVIDER=console (dev only) it is written to the server log instead."""
    if settings.otp_provider != "smtp":
        log.warning("DEV ONLY: email to %s | %s\n%s", to, subject, body)
        return
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, settings.smtp_from, to
    msg.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as s:
            s.starttls()
            if settings.smtp_user:
                s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)
    except (OSError, smtplib.SMTPException) as exc:
        raise MailError(str(exc)) from exc
