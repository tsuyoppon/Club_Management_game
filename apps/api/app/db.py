from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import get_settings


Base = declarative_base()


def get_engine(echo: bool = False):
    settings = get_settings()
    return create_engine(settings.database_url, echo=echo, future=True)


def get_session_local(echo: bool = False):
    engine = get_engine(echo=echo)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
