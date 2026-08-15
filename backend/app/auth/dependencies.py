import logging

from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.auth.security import decode_access_token
from app.core.errors import unauthorized
from app.database.database import get_db
from app.database.models import User

logger = logging.getLogger("urban_pulse.auth")

_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise unauthorized("Missing bearer token.")

    payload = decode_access_token(credentials.credentials)
    if payload is None or "sub" not in payload:
        logger.info("auth failure: invalid or expired token")
        raise unauthorized("Invalid or expired token.")

    user = db.query(User).filter(User.id == payload["sub"]).first()
    if user is None:
        logger.info("auth failure: token subject does not exist")
        raise unauthorized("Invalid or expired token.")

    return user


def get_user_id_from_token(token: str, db: Session) -> str | None:
    """
    Used by WebSocket handlers, which cannot use the HTTPBearer dependency.
    Returns the user id if the token is valid and the user exists, else None.
    """
    payload = decode_access_token(token)
    if payload is None or "sub" not in payload:
        return None
    user = db.query(User).filter(User.id == payload["sub"]).first()
    return user.id if user else None
