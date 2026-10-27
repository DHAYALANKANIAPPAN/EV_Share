from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from .config import settings
from .models import BookingStatus, ConnectorType, DocType, HubType, Role, VerificationStatus


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
    role: Role = Role.DRIVER
    hub_type: HubType | None = None

    @model_validator(mode="after")
    def _hub(self):
        if self.role == Role.HUB and self.hub_type is None:
            raise ValueError("hub_type (HOUSE or SHOP) is required for hub accounts")
        if self.role == Role.DRIVER:
            self.hub_type = None
        return self


class UserOut(ORM):
    id: int
    email: EmailStr
    name: str
    role: Role
    hub_type: HubType | None
    is_admin: bool
    email_verified: bool
    verification_status: VerificationStatus


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
    hold_expires_at: datetime | None = None


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


# ---- verification ----
class RequiredDoc(BaseModel):
    doc_type: DocType
    label: str
    uploaded: bool
    original_name: str | None = None


class VerificationOut(BaseModel):
    role: Role
    hub_type: HubType | None
    status: VerificationStatus
    rejection_reason: str | None
    email_verified: bool
    vehicle_number: str | None
    required: list[RequiredDoc]
    can_submit: bool


class VehicleIn(BaseModel):
    vehicle_number: str = Field(min_length=6, max_length=20)

    @field_validator("vehicle_number")
    @classmethod
    def _plate(cls, v: str) -> str:
        import re
        v = re.sub(r"[\s-]", "", v).upper()
        if not re.fullmatch(r"[A-Z0-9]{6,12}", v):
            raise ValueError("enter the registration number using letters and digits, e.g. TN45AB1234")
        return v


class OtpConfirm(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


class SubmitIn(BaseModel):
    consent: bool


class DocumentOut(ORM):
    id: int
    doc_type: DocType
    original_name: str
    size: int


class DecisionIn(BaseModel):
    approve: bool
    reason: str | None = Field(default=None, max_length=500)


class AdminVerificationOut(BaseModel):
    user_id: int
    name: str
    email: EmailStr
    role: Role
    hub_type: HubType | None
    vehicle_number: str | None
    status: VerificationStatus
    submitted_at: datetime | None
    documents: list[DocumentOut]
