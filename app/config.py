from cryptography.fernet import Fernet
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET = "dev-only-secret-key-do-not-use-in-production-0123456789"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EVSHARE_", env_file=".env", extra="ignore")

    env: str = "dev"  # dev | production
    secret_key: str = DEV_SECRET
    database_url: str = "sqlite:///./evshare.db"
    access_token_minutes: int = 60
    max_booking_hours: int = 8
    login_max_failures: int = 5  # per (client IP, email) within the window
    login_window_minutes: int = 15
    unpaid_hold_minutes: int = 15  # unpaid bookings are released after this long; 0 disables
    default_timezone: str = "Asia/Kolkata"

    # identity verification (documents are encrypted at rest; OTP is emailed)
    upload_dir: str = "./uploads"
    docs_max_mb: int = 5
    docs_encryption_key: str = ""  # Fernet key; required when ENV != dev (Fernet.generate_key())
    otp_provider: str = "console"  # "console" prints the code to the server log (dev only) | "smtp"
    otp_ttl_minutes: int = 10
    otp_max_attempts: int = 5
    otp_resend_seconds: int = 60
    otp_max_per_hour: int = 5
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    # payments: "mock" (no money moves, for development) or "razorpay"
    payment_provider: str = "mock"
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""

    @model_validator(mode="after")
    def _validate(self):
        # Hosting platforms hand out `postgres://...`; SQLAlchemy needs an explicit driver.
        for prefix in ("postgres://", "postgresql://"):
            if self.database_url.startswith(prefix):
                self.database_url = "postgresql+psycopg://" + self.database_url[len(prefix):]
        if not self.secret_key:  # `EVSHARE_SECRET_KEY=` left blank in .env
            self.secret_key = DEV_SECRET
        if self.env != "dev" and (self.secret_key == DEV_SECRET or len(self.secret_key) < 32):
            raise ValueError("EVSHARE_SECRET_KEY must be a random string of 32+ characters when EVSHARE_ENV is not 'dev'")
        if self.otp_provider not in ("console", "smtp"):
            raise ValueError("EVSHARE_OTP_PROVIDER must be 'console' or 'smtp'")
        if self.otp_provider == "smtp" and not (self.smtp_host and self.smtp_from):
            raise ValueError("SMTP selected but EVSHARE_SMTP_HOST / EVSHARE_SMTP_FROM are not set")
        if self.env != "dev":
            if self.otp_provider != "smtp":
                raise ValueError("Outside dev, EVSHARE_OTP_PROVIDER must be 'smtp' (the console provider would leak codes into logs)")
            try:
                Fernet(self.docs_encryption_key.encode())
            except Exception:
                raise ValueError("EVSHARE_DOCS_ENCRYPTION_KEY must be a valid Fernet key when EVSHARE_ENV is not 'dev'")
        if self.payment_provider not in ("mock", "razorpay"):
            raise ValueError("EVSHARE_PAYMENT_PROVIDER must be 'mock' or 'razorpay'")
        if self.payment_provider == "razorpay" and not (self.razorpay_key_id and self.razorpay_key_secret):
            raise ValueError("Razorpay selected but EVSHARE_RAZORPAY_KEY_ID / EVSHARE_RAZORPAY_KEY_SECRET are not set")
        if self.payment_provider == "mock" and self.env != "dev":
            raise ValueError("The mock payment provider is only allowed when EVSHARE_ENV=dev")
        return self


settings = Settings()
