from ..models import Booking, BookingStatus, PaymentStatus
from .payments import get_provider


def cancel_with_refund(booking: Booking) -> None:
    """Cancel a booking and refund it if paid. The gateway call happens first, so a gateway failure leaves the
    booking untouched. The caller commits."""
    payment = booking.payment
    if payment and payment.status == PaymentStatus.PAID and payment.amount > 0 and payment.provider != "free":
        get_provider().refund(payment.provider_payment_id, payment.amount)
    if payment and payment.status == PaymentStatus.PAID:
        payment.status = PaymentStatus.REFUNDED
    booking.status = BookingStatus.CANCELLED
