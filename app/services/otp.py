import hashlib
import hmac
import logging
import secrets
import smtplib
from datetime import timedelta
from email.message import EmailMessage

from fastapi import HTTPException
from sqlalchemy import func, select

from ..config import settings
from ..models import OtpCode, User, utcnow

log = logging.getLogger("evshare.otp")

NOTICE = ("EV Share will never call, text or email you to ask for this code. Enter it only inside the EV Share app, "
          "on the screen that asks for it. If anyone asks you to read it out, it is a scam.")


class ConsoleSender:
    def send(self, email: str, code: str) -> None:
        log.warning("DEV ONLY: verification code for %s is %s", email, code)


class SmtpSender:
    def send(self, email: str, code: str) -> None:
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = "Your EV Share verification code", settings.smtp_from, email
        msg.set_content(f"Your EV Share verification code is {code}. It expires in {settings.otp_ttl_minutes} minutes.\n\n{NOTICE}")
        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as s:
                s.starttls()
                if settings.smtp_user:
                    s.login(settings.smtp_user, settings.smtp_password)
                s.send_message(msg)
        except (OSError, smtplib.SMTPException) as exc:
            raise HTTPException(502, "We couldn't send the code. Try again in a minute.") from exc


def get_sender():
    return SmtpSender() if settings.otp_provider == "smtp" else ConsoleSender()


def _hash(user_id: int, code: str) -> str:
    return hmac.new(settings.secret_key.encode(), f"{user_id}:{code}".encode(), hashlib.sha256).hexdigest()


def send_otp(db, user: User) -> None:
    now = utcnow()
    last = db.scalar(select(func.max(OtpCode.created_at)).where(OtpCode.user_id == user.id))
    if last and (now - last).total_seconds() < settings.otp_resend_seconds:
        raise HTTPException(429, f"Please wait {settings.otp_resend_seconds} seconds before asking for another code.")
    recent = db.scalar(select(func.count(OtpCode.id)).where(OtpCode.user_id == user.id, OtpCode.created_at > now - timedelta(hours=1)))
    if recent >= settings.otp_max_per_hour:
        raise HTTPException(429, "Too many code requests. Try again later.")
    for old in db.scalars(select(OtpCode).where(OtpCode.user_id == user.id, OtpCode.consumed.is_(False))):
        old.consumed = True
    code = f"{secrets.randbelow(10**6):06d}"
    db.add(OtpCode(user_id=user.id, code_hash=_hash(user.id, code), expires_at=now + timedelta(minutes=settings.otp_ttl_minutes)))
    db.commit()
    get_sender().send(user.email, code)


def confirm_otp(db, user: User, code: str) -> None:
    otp = db.scalar(select(OtpCode).where(OtpCode.user_id == user.id, OtpCode.consumed.is_(False),
                                          OtpCode.expires_at > utcnow()).order_by(OtpCode.id.desc()).limit(1))
    if otp is None:
        raise HTTPException(400, "That code has expired. Ask for a new one.")
    if otp.attempts >= settings.otp_max_attempts:
        otp.consumed = True
        db.commit()
        raise HTTPException(429, "Too many wrong attempts. Ask for a new code.")
    otp.attempts += 1
    if not hmac.compare_digest(otp.code_hash, _hash(user.id, code)):
        db.commit()
        raise HTTPException(400, "That code isn't right. Check it and try again.")
    otp.consumed = True
    user.email_verified = True
    db.commit()
