import os
import pytest

# Force DB host to localhost for local testing BEFORE importing app modules
# This assumes the developer is running tests from the host machine against a port-forwarded DB
if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:postgres@localhost:5432/club_game"

from app.db import Base
from app.db.session import engine
import app.db.models  # noqa: F401


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

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
