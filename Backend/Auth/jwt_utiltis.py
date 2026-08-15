import os
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HttpException
from fastapi.security import OAuth2PasswordBearer
import jwt
from dotenv import load_dotenv
from sqlalchemy.orm import Session


oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login"
)

load_dotenv()

SECRET_KEY = os.getenv("JWT")
ALGORITHM = os.getenv("JWT_ALGORITHM")


def create_access_token(user_id: int) -> str:

    payload = {
         "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
    }

    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def verify_access_token(token: str) -> dict | None:

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )
        return payload

    except jwt.ExpiredSignatureError:
        return None

    except jwt.InvalidTokenError:
        return None

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(database.get_db),
):
    payload = verify_access_token(token)

    if payload is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
        )

    user_id = int(payload["sub"])

    user = (
        db.query(models.User)
        .filter(models.User.id == user_id)
        .first()
    )

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="User not found",
        )

    return user