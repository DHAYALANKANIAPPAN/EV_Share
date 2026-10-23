from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from .config import settings
from .models import BookingStatus, ConnectorType


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _check_tz(v: str) -> str:
    try:
        ZoneInfo(v)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise ValueError(f"unknown timezone '{v}' (use an IANA name such as Asia/Kolkata)")
    return v


def _check_window(f: time | None, t: time | None) -> None:
    if (f is None) != (t is None):
        raise ValueError("available_from and available_to must be set together")
    if f is not None and f == t:
        raise ValueError("available_from and available_to must differ")


# ---- auth ----
class UserCreate(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)


class UserOut(ORM):
    id: int
    email: EmailStr
    name: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---- chargers ----
class ChargerBase(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    address: str = Field(min_length=1, max_length=255)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    connector_type: ConnectorType
    power_kw: float = Field(gt=0, le=350)
    price_per_kwh: float = Field(ge=0)
    timezone: str = Field(default_factory=lambda: settings.default_timezone)
    available_from: time | None = None
    available_to: time | None = None

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v):
        return _check_tz(v)

    @model_validator(mode="after")
    def _window(self):
        _check_window(self.available_from, self.available_to)
        return self


class ChargerCreate(ChargerBase):
    pass


class ChargerUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    address: str | None = Field(default=None, min_length=1, max_length=255)
    connector_type: ConnectorType | None = None
    power_kw: float | None = Field(default=None, gt=0, le=350)
    price_per_kwh: float | None = Field(default=None, ge=0)
    is_active: bool | None = None
    timezone: str | None = None
    available_from: time | None = None
    available_to: time | None = None

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v):
        return _check_tz(v) if v is not None else v


class ChargerOut(ChargerBase, ORM):
    id: int
    owner_id: int
    is_active: bool
    distance_km: float | None = None
    avg_rating: float | None = None
    review_count: int = 0


# ---- bookings ----
class BookingCreate(BaseModel):
    charger_id: int
    start_time: datetime
    end_time: datetime

    @field_validator("start_time", "end_time")
    @classmethod
    def _require_tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("timestamp must include a timezone, e.g. 2026-11-01T10:00:00+05:30")
        return v.astimezone(timezone.utc).replace(tzinfo=None)


class BookingOut(ORM):
    id: int
    charger_id: int
    user_id: int
    start_time: datetime
    end_time: datetime
    status: BookingStatus
    estimated_cost: float
    charger_title: str
    payment_status: str
    reviewed: bool


# ---- reviews ----
class ReviewCreate(BaseModel):
    booking_id: int
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=1000)


class ReviewOut(ORM):
    id: int
    booking_id: int
    charger_id: int
    rating: int
    comment: str | None
    user_name: str
    created_at: datetime


# ---- payments ----
class CheckoutRequest(BaseModel):
    booking_id: int


class CheckoutOut(BaseModel):
    booking_id: int
    provider: str
    order_id: str | None
    amount: float
    currency: str
    key_id: str | None = None
    status: str


class ConfirmRequest(BaseModel):
    booking_id: int
    payment_id: str = "mock_payment"
    signature: str = "mock_signature"
