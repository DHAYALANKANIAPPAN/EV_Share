import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    """Naive UTC timestamp (SQLite does not keep tzinfo)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ConnectorType(str, enum.Enum):
    TYPE2 = "TYPE2"
    CCS2 = "CCS2"
    CHADEMO = "CHADEMO"
    BHARAT_AC001 = "BHARAT_AC001"
    BHARAT_DC001 = "BHARAT_DC001"
    GBT = "GBT"


class BookingStatus(str, enum.Enum):
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Charger(Base):
    __tablename__ = "chargers"
    __table_args__ = (Index("ix_chargers_lat_lon", "latitude", "longitude"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    address: Mapped[str] = mapped_column(String(255))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    connector_type: Mapped[ConnectorType] = mapped_column(Enum(ConnectorType))
    power_kw: Mapped[float] = mapped_column(Float)
    price_per_kwh: Mapped[float] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    owner: Mapped[User] = relationship()


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (Index("ix_bookings_charger_time", "charger_id", "start_time", "end_time"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    charger_id: Mapped[int] = mapped_column(ForeignKey("chargers.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    start_time: Mapped[datetime] = mapped_column(DateTime)
    end_time: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[BookingStatus] = mapped_column(Enum(BookingStatus), default=BookingStatus.CONFIRMED)
    estimated_cost: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    charger: Mapped[Charger] = relationship()
