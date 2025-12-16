from typing import Generator

from sqlalchemy.orm import Session

from .db import get_session_local


SessionLocal = get_session_local()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
