from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from ..config import settings
from ..deps import DB, CurrentUser
from ..models import User
from ..schemas import ForgotIn, ResetIn, Token, UserCreate, UserOut
from ..security import COOKIE_NAME, create_access_token, hash_password, verify_password
from ..services.otp import confirm_otp, send_otp
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


def _authenticate(request: Request, response: Response, form, db, staff: bool, expected_role: str | None = None) -> Token:
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
    if expected_role is not None and user.role.value != expected_role:
        other = "hub" if user.role.value == "HUB" else "driver"
        chosen = "Hub" if other == "hub" else "Driver"
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"This is a {other} account. Choose {chosen} to log in instead.")
    login_limiter.reset(key)
    token = create_access_token(user.id, user.password_hash)
    response.set_cookie(COOKIE_NAME, token, max_age=settings.access_token_minutes * 60, httponly=True,
                        samesite="lax", secure=settings.env != "dev", path="/")
    return Token(access_token=token)


@router.post("/login", response_model=Token)
def login(request: Request, response: Response, form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DB,
          expected_role: Annotated[str | None, Form()] = None):
    """expected_role (DRIVER or HUB) is the option the person picked on the sign-in screen. A mismatch is refused."""
    if expected_role not in (None, "DRIVER", "HUB"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "expected_role must be DRIVER or HUB")
    return _authenticate(request, response, form, db, staff=False, expected_role=expected_role)


@router.post("/staff/login", response_model=Token, include_in_schema=False)
def staff_login(request: Request, response: Response, form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DB):
    return _authenticate(request, response, form, db, staff=True)


@router.post("/password/forgot", status_code=status.HTTP_202_ACCEPTED)
def forgot_password(body: ForgotIn, db: DB):
    """Always answers the same way, so the form cannot be used to find out which emails have accounts."""
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user and user.is_active:
        try:
            send_otp(db, user, purpose="reset")
        except HTTPException:
            pass  # cooldown or mail trouble: stay silent, the same answer is given
    return {"detail": "If an account exists for that email, we've sent a code to it."}


@router.post("/password/reset", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(body: ResetIn, db: DB):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That code isn't right, or it has expired. Ask for a new one.")
    confirm_otp(db, user, body.code, purpose="reset")
    user.password_hash = hash_password(body.new_password)  # every session signed in before this stops working
    db.commit()


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser):
    return user
