from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import service
from app.auth.dependencies import get_current_user
from app.auth.schemas import (
    RegisterRequest,
    LoginRequest,
    AuthResponse,
    UserOut,
    UpdateMeRequest,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    ResetPasswordRequest,
)
from app.database.database import get_db
from app.database.models import User

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse, status_code=201)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    user, token = service.register_user(db, body.email, body.password)
    return AuthResponse(user=UserOut.model_validate(user), access_token=token)


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user, token = service.login_user(db, body.email, body.password)
    return AuthResponse(user=UserOut.model_validate(user), access_token=token)


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return UserOut.model_validate(current_user)


@router.patch("/me", response_model=UserOut)
def update_me(
    body: UpdateMeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    updated = service.update_email(db, current_user, body.email, body.current_password)
    return UserOut.model_validate(updated)


@router.post("/change-password", status_code=204)
def change_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service.change_password(db, current_user, body.current_password, body.new_password)
    return None


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(body: ForgotPasswordRequest, db: Session = Depends(get_db)):
    service.request_password_reset(db, body.email)
    return ForgotPasswordResponse(
        message="If the account exists, a password reset code has been sent."
    )


@router.post("/reset-password", status_code=204)
def reset_password(body: ResetPasswordRequest, db: Session = Depends(get_db)):
    service.reset_password(db, body.email, body.otp, body.new_password)
    return None
