from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import User
from .security import COOKIE_NAME, decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

DB = Annotated[Session, Depends(get_db)]
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def get_current_user(request: Request, bearer: Annotated[str | None, Depends(oauth2_scheme)], db: DB) -> User:
    """Authenticate via `Authorization: Bearer` (API clients) or the HttpOnly session cookie (browser UI).

    Cookie-authenticated requests that change data must carry `X-Requested-With: evshare`. A custom header
    cannot be sent by a cross-site form, which closes the CSRF hole that cookies would otherwise open.
    """
    token, via_cookie = bearer, False
    if not token:
        token = request.cookies.get(COOKIE_NAME)
        via_cookie = token is not None
    if via_cookie and request.method not in SAFE_METHODS and request.headers.get("x-requested-with") != "evshare":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing X-Requested-With header")
    user_id = decode_access_token(token) if token else None
    user = db.get(User, user_id) if user_id is not None else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token",
                            headers={"WWW-Authenticate": "Bearer"})
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
