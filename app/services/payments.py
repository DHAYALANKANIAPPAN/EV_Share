"""Payment providers.

`mock`     – development only, no money moves.
`razorpay` – Razorpay Orders API. Server creates an order, the browser pays via Razorpay Checkout,
             then the server verifies the HMAC signature before marking the booking paid.
             NOTE: written against Razorpay's documented API but not exercised against the live service here;
             test with Razorpay *test mode* keys before going live.
"""
import hashlib
import hmac

import httpx
from fastapi import HTTPException

from ..config import settings

RAZORPAY_API = "https://api.razorpay.com/v1"


def to_minor_units(amount: float) -> int:
    return int(round(amount * 100))


class MockProvider:
    name = "mock"
    key_id = None

    def create_order(self, booking_id: int, amount: float, currency: str) -> str:
        return f"mock_order_{booking_id}"

    def verify(self, order_id: str, payment_id: str, signature: str) -> bool:
        return True

    def refund(self, payment_id: str, amount: float) -> None:
        return None


class RazorpayProvider:
    name = "razorpay"

    def __init__(self, key_id: str, key_secret: str):
        self.key_id = key_id
        self._secret = key_secret

    def _post(self, path: str, payload: dict) -> dict:
        try:
            r = httpx.post(f"{RAZORPAY_API}{path}", json=payload, auth=(self.key_id, self._secret), timeout=15)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as exc:
            raise HTTPException(502, f"Payment provider error: {exc.__class__.__name__}") from exc

    def create_order(self, booking_id: int, amount: float, currency: str) -> str:
        data = self._post("/orders", {"amount": to_minor_units(amount), "currency": currency,
                                      "receipt": f"booking_{booking_id}"})
        return data["id"]

    def verify(self, order_id: str, payment_id: str, signature: str) -> bool:
        expected = hmac.new(self._secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def refund(self, payment_id: str, amount: float) -> None:
        self._post(f"/payments/{payment_id}/refund", {"amount": to_minor_units(amount)})


def get_provider():
    if settings.payment_provider == "razorpay":
        return RazorpayProvider(settings.razorpay_key_id, settings.razorpay_key_secret)
    return MockProvider()
