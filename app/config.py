from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EVSHARE_", env_file=".env", extra="ignore")

    secret_key: str = "dev-only-secret-change-me"
    database_url: str = "sqlite:///./evshare.db"
    access_token_minutes: int = 60
    max_booking_hours: int = 8


settings = Settings()
