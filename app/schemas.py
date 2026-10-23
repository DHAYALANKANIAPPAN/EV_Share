from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .models import BookingStatus, ConnectorType


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


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


class ChargerCreate(ChargerBase):
    pass


class ChargerUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    address: str | None = Field(default=None, min_length=1, max_length=255)
    connector_type: ConnectorType | None = None
    power_kw: float | None = Field(default=None, gt=0, le=350)
    price_per_kwh: float | None = Field(default=None, ge=0)
    is_active: bool | None = None


class ChargerOut(ChargerBase, ORM):
    id: int
    owner_id: int
    is_active: bool
    distance_km: float | None = None


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
