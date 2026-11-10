import pytest

from app.config import settings
from scripts import check_razorpay, test_email


def test_test_email_refuses_when_smtp_is_off(monkeypatch, capsys):
    monkeypatch.setattr(settings, "otp_provider", "console")
    monkeypatch.setattr("sys.argv", ["x", "a@example.com"])
    assert test_email.main() == 1
    assert "not 'smtp'" in capsys.readouterr().out


def test_test_email_lists_missing_settings(monkeypatch, capsys):
    monkeypatch.setattr(settings, "otp_provider", "smtp")
    monkeypatch.setattr(settings, "smtp_host", "")
    monkeypatch.setattr("sys.argv", ["x", "a@example.com"])
    assert test_email.main() == 1
    assert "EVSHARE_SMTP_HOST" in capsys.readouterr().out


def test_test_email_sends_through_the_app_mailer(monkeypatch, capsys):
    sent = []
    monkeypatch.setattr(settings, "otp_provider", "smtp")
    monkeypatch.setattr(settings, "smtp_host", "smtp-relay.brevo.com")
    monkeypatch.setattr(settings, "smtp_user", "u")
    monkeypatch.setattr(settings, "smtp_password", "p")
    monkeypatch.setattr(settings, "smtp_from", "from@example.com")
    monkeypatch.setattr(test_email, "send_mail", lambda to, subj, body: sent.append((to, subj)))
    monkeypatch.setattr("sys.argv", ["x", "a@example.com"])
    assert test_email.main() == 0
    assert sent == [("a@example.com", "EV Share test email")]


def test_razorpay_check_needs_keys(monkeypatch, capsys):
    monkeypatch.setattr(settings, "razorpay_key_id", "")
    assert check_razorpay.main() == 1
    assert "empty" in capsys.readouterr().out


def test_razorpay_check_reports_rejected_keys(monkeypatch, capsys):
    class R:
        status_code = 401
    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_test_abc")
    monkeypatch.setattr(settings, "razorpay_key_secret", "wrong")
    monkeypatch.setattr(check_razorpay.httpx, "get", lambda *a, **k: R())
    assert check_razorpay.main() == 1
    out = capsys.readouterr().out
    assert "Key mode: TEST" in out and "rejected" in out
