import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt

from .config import settings

_ITERATIONS = 240_000
_ALGO = "HS256"
COOKIE_NAME = "evshare_session"


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), _ITERATIONS)
    return hmac.compare_digest(digest.hex(), digest_hex)


def password_fingerprint(password_hash: str) -> str:
    """Short, non-reversible tag of the current password hash. A token carries it; changing the password changes
    it, which voids every session issued before the change (no clock comparisons involved)."""
    return hashlib.sha256(password_hash.encode()).hexdigest()[:24]


def create_access_token(user_id: int, password_hash: str) -> str:
    claims = {"sub": str(user_id), "pwd": password_fingerprint(password_hash),
              "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_minutes)}
    return jwt.encode(claims, settings.secret_key, algorithm=_ALGO)


def read_access_token(token: str) -> tuple[int | None, str | None]:
    """(user id, password fingerprint) if the signature and expiry are valid, otherwise (None, None)."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[_ALGO])
        return int(payload["sub"]), payload.get("pwd")
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        return None, None


def decode_access_token(token: str) -> int | None:
    return read_access_token(token)[0]
