import os

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

TURSO_DATABASE_URL = os.environ["TURSO_DATABASE_URL"]
TURSO_AUTH_TOKEN = os.environ["TURSO_AUTH_TOKEN"]

engine = create_engine(
    f"sqlite+{TURSO_DATABASE_URL}?secure=true",
    connect_args={
        "auth_token": TURSO_AUTH_TOKEN,
    },
    poolclass=NullPool,
)

Base = declarative_base()

LocalSession = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


def get_db():
    session = LocalSession()
    try:
        yield session
    finally:
        session.close()
