from fastapi import APIRouter, HTTPException, status

from ..deps import DB, CurrentUser
from ..models import Booking, BookingStatus, Payment, PaymentStatus
from ..schemas import BookingOut, CheckoutOut, CheckoutRequest, ConfirmRequest
from ..services.expiry import expire_unpaid
from ..services.payments import get_provider

router = APIRouter(prefix="/payments", tags=["payments"])
CURRENCY = "INR"


def _own_booking(db, booking_id: int, user) -> Booking:
    expire_unpaid(db)
    booking = db.get(Booking, booking_id)
    if not booking or booking.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")
    if booking.status != BookingStatus.CONFIRMED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This booking was cancelled or its payment window ended. Reserve the slot again.")
    return booking


@router.post("/checkout", response_model=CheckoutOut)
def checkout(body: CheckoutRequest, db: DB, user: CurrentUser):
    """Start (or resume) payment for a booking. Free slots are marked paid immediately."""
    booking = _own_booking(db, body.booking_id, user)
    payment = booking.payment
    if payment and payment.status == PaymentStatus.PAID:
        raise HTTPException(status.HTTP_409_CONFLICT, "Booking is already paid")

    provider = get_provider()
    if booking.estimated_cost <= 0:
        payment = payment or Payment(booking_id=booking.id, amount=0, currency=CURRENCY, provider="free")
        payment.status = PaymentStatus.PAID
        db.add(payment)
        db.commit()
        return CheckoutOut(booking_id=booking.id, provider="free", order_id=None, amount=0,
                           currency=CURRENCY, status="PAID")

    if payment is None:
        order_id = provider.create_order(booking.id, booking.estimated_cost, CURRENCY)
        payment = Payment(booking_id=booking.id, amount=booking.estimated_cost, currency=CURRENCY,
                          provider=provider.name, provider_order_id=order_id)
        db.add(payment)
        db.commit()
    return CheckoutOut(booking_id=booking.id, provider=payment.provider, order_id=payment.provider_order_id,
                       amount=payment.amount, currency=payment.currency, key_id=provider.key_id,
                       status=payment.status.value)


@router.post("/confirm", response_model=BookingOut)
def confirm(body: ConfirmRequest, db: DB, user: CurrentUser):
    """Verify the provider's signature, then mark the booking paid."""
    booking = _own_booking(db, body.booking_id, user)
    payment = booking.payment
    if payment is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Start checkout first")
    if payment.status == PaymentStatus.PAID:
        return booking
    provider = get_provider()
    if payment.provider != provider.name or not provider.verify(payment.provider_order_id, body.payment_id,
                                                                body.signature):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Payment verification failed")
    payment.provider_payment_id = body.payment_id
    payment.status = PaymentStatus.PAID
    db.commit()
    return booking
