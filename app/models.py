import enum
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import (Boolean, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, Time,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .config import settings
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


class PaymentStatus(str, enum.Enum):
    PENDING = "PENDING"
    PAID = "PAID"
    REFUNDED = "REFUNDED"


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
    # Daily availability window in the charger's local time. NULL/NULL means always available.
    # from > to means the window crosses midnight (e.g. 18:00 -> 08:00).
    timezone: Mapped[str] = mapped_column(String(64), default=lambda: settings.default_timezone)
    available_from: Mapped[time | None] = mapped_column(Time, nullable=True)
    available_to: Mapped[time | None] = mapped_column(Time, nullable=True)
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
    payment: Mapped["Payment | None"] = relationship(back_populates="booking", uselist=False)
    review: Mapped["Review | None"] = relationship(back_populates="booking", uselist=False)

    @property
    def payment_status(self) -> str:
        return self.payment.status.value if self.payment else "UNPAID"

    @property
    def hold_expires_at(self) -> datetime | None:
        """When an unpaid booking will be released; None once paid, free or cancelled."""
        if (self.status != BookingStatus.CONFIRMED or self.estimated_cost <= 0 or settings.unpaid_hold_minutes <= 0
                or (self.payment and self.payment.status == PaymentStatus.PAID)):
            return None
        return self.created_at + timedelta(minutes=settings.unpaid_hold_minutes)

    @property
    def charger_title(self) -> str:
        return self.charger.title

    @property
    def reviewed(self) -> bool:
        return self.review is not None


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"), unique=True)
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    provider: Mapped[str] = mapped_column(String(20))
    provider_order_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    provider_payment_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus), default=PaymentStatus.PENDING)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    booking: Mapped[Booking] = relationship(back_populates="payment")


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("booking_id", name="uq_reviews_booking"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"))
    charger_id: Mapped[int] = mapped_column(ForeignKey("chargers.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    booking: Mapped[Booking] = relationship(back_populates="review")
    user: Mapped[User] = relationship()

    @property
    def user_name(self) -> str:
        return self.user.name
