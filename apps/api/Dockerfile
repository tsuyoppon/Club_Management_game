FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY ../../fastapi /app/fastapi
COPY ../../pydantic /app/pydantic
COPY ../../sqlalchemy /app/sqlalchemy
COPY ../../alembic /app/alembic_stub
COPY ../../uvicorn /app/uvicorn

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
