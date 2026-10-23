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
    unpaid_hold_minutes: int = 15  # unpaid bookings are released after this long; 0 disables
    default_timezone: str = "Asia/Kolkata"

    # payments: "mock" (no money moves, for development) or "razorpay"
    payment_provider: str = "mock"
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""

    @model_validator(mode="after")
    def _validate(self):
        if not self.secret_key:  # `EVSHARE_SECRET_KEY=` left blank in .env
            self.secret_key = DEV_SECRET
        if self.env != "dev" and (self.secret_key == DEV_SECRET or len(self.secret_key) < 32):
            raise ValueError("EVSHARE_SECRET_KEY must be a random string of 32+ characters when EVSHARE_ENV is not 'dev'")
        if self.payment_provider not in ("mock", "razorpay"):
            raise ValueError("EVSHARE_PAYMENT_PROVIDER must be 'mock' or 'razorpay'")
        if self.payment_provider == "razorpay" and not (self.razorpay_key_id and self.razorpay_key_secret):
            raise ValueError("Razorpay selected but EVSHARE_RAZORPAY_KEY_ID / EVSHARE_RAZORPAY_KEY_SECRET are not set")
        if self.payment_provider == "mock" and self.env != "dev":
            raise ValueError("The mock payment provider is only allowed when EVSHARE_ENV=dev")
        return self


settings = Settings()
