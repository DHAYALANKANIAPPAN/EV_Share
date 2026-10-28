from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from ..config import settings
from ..deps import DB, CurrentUser
from ..models import User
from ..schemas import Token, UserCreate, UserOut
from ..security import COOKIE_NAME, create_access_token, hash_password, verify_password
from ..services.ratelimit import login_limiter

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(body: UserCreate, db: DB):
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = User(email=email, name=body.name, password_hash=hash_password(body.password),
                role=body.role, hub_type=body.hub_type)
    db.add(user)
    db.commit()
    return user


def _authenticate(request: Request, response: Response, form, db, staff: bool) -> Token:
    """Shared by both entrances. Reviewers can only use the staff entrance, everyone else only the public one.
    A wrong entrance gets the same 'incorrect email or password' answer, so it reveals nothing."""
    email = form.username.lower()
    key = f"{request.client.host if request.client else '?'}|{email}"
    login_limiter.check(key)
    user = db.scalar(select(User).where(User.email == email))
    if not user or user.is_admin != staff or not verify_password(form.password, user.password_hash):
        login_limiter.fail(key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    if not user.is_active:  # only revealed after the password was right
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been removed. Check your email for the reason, or register again with a different email address.")
    login_limiter.reset(key)
    token = create_access_token(user.id)
    response.set_cookie(COOKIE_NAME, token, max_age=settings.access_token_minutes * 60, httponly=True,
                        samesite="lax", secure=settings.env != "dev", path="/")
    return Token(access_token=token)


@router.post("/login", response_model=Token)
def login(request: Request, response: Response, form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DB):
    return _authenticate(request, response, form, db, staff=False)


@router.post("/staff/login", response_model=Token, include_in_schema=False)
def staff_login(request: Request, response: Response, form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DB):
    return _authenticate(request, response, form, db, staff=True)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser):
    return user
