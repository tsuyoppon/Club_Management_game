from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.db.base import Base

settings = get_settings()

engine = create_engine(settings.database_url, future=True)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


__all__ = ["engine", "SessionLocal", "get_db", "Base"]
