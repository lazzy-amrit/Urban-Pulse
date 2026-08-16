"""
Auth business logic: registration, login, profile updates, password change,
and the password-reset (OTP) flow. OTP delivery goes through Brevo
(app/auth/email_brevo.py).
"""

import logging
import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.auth import email_brevo
from app.auth.security import hash_password, verify_password, create_access_token
from app.core.config import OTP_LENGTH, OTP_EXPIRE_MINUTES, OTP_MAX_ATTEMPTS
from app.core.errors import conflict, unauthorized, bad_request
from app.database.models import User, PasswordResetOTP

logger = logging.getLogger("urban_pulse.auth")


# ---------------------------------------------------------------------------
# Registration / login
# ---------------------------------------------------------------------------

def register_user(db: Session, email: str, password: str) -> tuple[User, str]:
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise conflict("An account with this email already exists.")

    user = User(email=email, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id)
    logger.info("user registered: %s", user.id)
    return user, token


def login_user(db: Session, email: str, password: str) -> tuple[User, str]:
    user = db.query(User).filter(User.email == email).first()
    if user is None or not verify_password(password, user.password_hash):
        logger.info("login failure for email domain: %s", email.split("@")[-1])
        raise unauthorized("Invalid email or password.")

    token = create_access_token(user.id)
    logger.info("user logged in: %s", user.id)
    return user, token


# ---------------------------------------------------------------------------
# Profile updates
# ---------------------------------------------------------------------------

def update_email(db: Session, user: User, new_email: str, current_password: str) -> User:
    if not verify_password(current_password, user.password_hash):
        raise unauthorized("Current password is incorrect.")

    existing = db.query(User).filter(User.email == new_email, User.id != user.id).first()
    if existing:
        raise conflict("An account with this email already exists.")

    user.email = new_email
    db.commit()
    db.refresh(user)
    return user


def change_password(db: Session, user: User, current_password: str, new_password: str) -> None:
    if not verify_password(current_password, user.password_hash):
        raise unauthorized("Current password is incorrect.")

    user.password_hash = hash_password(new_password)
    db.commit()


# ---------------------------------------------------------------------------
# Password reset (OTP)
# ---------------------------------------------------------------------------

def _generate_otp() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(OTP_LENGTH))


def send_otp_email(email: str, otp: str) -> None:
    email_brevo.send_otp_email(email, otp)


def request_password_reset(db: Session, email: str) -> None:
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        # Do not reveal account existence.
        return

    otp = _generate_otp()
    record = PasswordResetOTP(
        user_id=user.id,
        otp_hash=hash_password(otp),
        expires_at=datetime.utcnow() + timedelta(minutes=OTP_EXPIRE_MINUTES),
    )
    db.add(record)
    db.commit()

    send_otp_email(user.email, otp)
    logger.info("password reset OTP generated for user: %s", user.id)


def reset_password(db: Session, email: str, otp: str, new_password: str) -> None:
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise bad_request("Invalid or expired code.")

    record = (
        db.query(PasswordResetOTP)
        .filter(PasswordResetOTP.user_id == user.id, PasswordResetOTP.used == False)  # noqa: E712
        .order_by(PasswordResetOTP.created_at.desc())
        .first()
    )
    if record is None:
        raise bad_request("Invalid or expired code.")

    if record.used:
        raise bad_request("Invalid or expired code.")

    if datetime.utcnow() > record.expires_at:
        raise bad_request("Invalid or expired code.")

    if record.attempt_count >= OTP_MAX_ATTEMPTS:
        raise bad_request("Too many attempts. Request a new code.")

    if not verify_password(otp, record.otp_hash):
        record.attempt_count += 1
        db.commit()
        raise bad_request("Invalid or expired code.")

    user.password_hash = hash_password(new_password)
    record.used = True
    db.commit()
    logger.info("password reset completed for user: %s", user.id)
