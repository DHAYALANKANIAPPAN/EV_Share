import logging

from .mailer import MailError, send_mail

log = logging.getLogger("evshare.notify")


def notify(to: str, subject: str, body: str) -> None:
    """Best-effort email: a mail problem must never break a booking."""
    try:
        send_mail(to, subject, body)
    except MailError:
        log.exception("could not email %s", to)
