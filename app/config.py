import re

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
    live_ttl_minutes: int = 30  # a hub stays live this long after its last location ping (the page pings every 5 min)
    live_radius_m: int = 500    # a charger counts as live only if the hub pinged from within this distance
    staff_path: str = "/staff"  # unlinked reviewer portal page; pick something less guessable in production
    login_max_failures: int = 5  # per (client IP, email) within the window
    login_window_minutes: int = 15
    ratelimit_backend: str = "memory"  # memory | redis (multi-instance/production)
    redis_url: str = ""
    max_active_bookings: int = 1  # open requests/sessions a driver may hold at once; 0 = no limit
    hub_response_minutes: int = 20  # a booking request the hub has not answered in this time is cancelled; 0 disables
    unpaid_hold_minutes: int = 15  # unpaid bookings are released after this long; 0 disables
    default_timezone: str = "Asia/Kolkata"

    # identity verification (documents are encrypted at rest; OTP is emailed)
    storage_backend: str = "local"  # local = files on this server's disk | s3 = any S3-compatible bucket (AWS S3, Cloudflare R2, MinIO)
    allow_local_storage: bool = False  # production refuses disk storage unless you say it is intentional (most hosts wipe the disk on redeploy)
    s3_bucket: str = ""
    s3_prefix: str = "documents/"
    s3_region: str = ""
    s3_endpoint_url: str = ""  # only for non-AWS providers
    docs_retention_days: int = 30           # approved users' documents are deleted this long after approval (also after account removal)
    docs_rejected_retention_days: int = 90  # rejected applicants' documents; abandoned, never-submitted uploads use docs_retention_days
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
        if not re.fullmatch(r"/[A-Za-z0-9_-]{2,40}", self.staff_path) or self.staff_path.lstrip("/") in {
                "static", "auth", "admin", "docs", "redoc", "openapi", "health", "chargers", "bookings", "payments", "reviews", "verification", "classic"}:
            raise ValueError("EVSHARE_STAFF_PATH must look like /my-secret-portal and must not clash with an existing route")
        if self.storage_backend not in ("local", "s3"):
            raise ValueError("EVSHARE_STORAGE_BACKEND must be 'local' or 's3'")
        if self.storage_backend == "s3" and not self.s3_bucket:
            raise ValueError("S3 storage selected but EVSHARE_S3_BUCKET is not set")
        if self.env != "dev" and self.storage_backend == "local" and not self.allow_local_storage:
            raise ValueError("Outside dev, uploaded documents need persistent storage: set EVSHARE_STORAGE_BACKEND=s3, or EVSHARE_ALLOW_LOCAL_STORAGE=true if you really want the server disk")
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
        if self.ratelimit_backend not in ("memory", "redis"):
            raise ValueError("EVSHARE_RATELIMIT_BACKEND must be 'memory' or 'redis'")
        if self.ratelimit_backend == "redis" and not self.redis_url:
            raise ValueError("Redis rate limiting selected but EVSHARE_REDIS_URL is not set")
        if self.payment_provider not in ("mock", "razorpay"):
            raise ValueError("EVSHARE_PAYMENT_PROVIDER must be 'mock' or 'razorpay'")
        if self.payment_provider == "razorpay" and not (self.razorpay_key_id and self.razorpay_key_secret):
            raise ValueError("Razorpay selected but EVSHARE_RAZORPAY_KEY_ID / EVSHARE_RAZORPAY_KEY_SECRET are not set")
        if self.payment_provider == "mock" and self.env != "dev":
            raise ValueError("The mock payment provider is only allowed when EVSHARE_ENV=dev")
        return self


settings = Settings()
