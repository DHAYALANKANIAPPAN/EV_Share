"""Check that the Razorpay keys in .env work, without taking any payment.
Usage: python -m scripts.check_razorpay
Where to run: the project folder, with the virtual environment active.
"""
import sys

import httpx

from app.config import settings

API = "https://api.razorpay.com/v1/orders?count=1"


def main() -> int:
    key_id, secret = settings.razorpay_key_id, settings.razorpay_key_secret
    if not key_id or not secret:
        print("EVSHARE_RAZORPAY_KEY_ID or EVSHARE_RAZORPAY_KEY_SECRET is empty in .env.")
        return 1
    mode = "TEST" if key_id.startswith("rzp_test_") else "LIVE" if key_id.startswith("rzp_live_") else "UNKNOWN"
    print(f"Key mode: {mode}")
    if mode == "LIVE":
        print("This is a LIVE key. Use test keys until you have finished Razorpay's account verification.")
    try:
        r = httpx.get(API, auth=(key_id, secret), timeout=15)
    except httpx.HTTPError as exc:
        print(f"FAILED: could not reach Razorpay ({exc.__class__.__name__}). Check your internet connection.")
        return 1
    if r.status_code == 200:
        print("OK: Razorpay accepted the keys.")
        return 0
    if r.status_code == 401:
        print("FAILED: Razorpay rejected the key id or secret. Copy them again from the dashboard, with no spaces.")
    else:
        print(f"FAILED: Razorpay answered with status {r.status_code}.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
