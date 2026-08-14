import os
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

# Default to a dedicated local test database before importing app modules.
if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = (
        "postgresql+psycopg2://postgres:postgres@localhost:5432/club_game_test"
    )

test_database_name = make_url(os.environ["DATABASE_URL"]).database or ""
if not test_database_name.endswith("_test"):
    raise RuntimeError(
        "Refusing to run destructive tests against a database whose name does not end "
        "with '_test'."
    )

from app.db import Base
from app.db.session import engine
import app.db.models  # noqa: F401


@pytest.fixture(autouse=True)
def clean_database():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except OperationalError:
        pytest.skip("PostgreSQL is not available for API tests.")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield

from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def auth_headers():
    return {"X-User-Email": "test@example.com", "X-User-Name": "Test User"}

from app.db.session import SessionLocal

@pytest.fixture
def db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Compatibility alias for tests expecting a db_session fixture
@pytest.fixture
def db_session(db):
    return db
