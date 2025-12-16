# J-League Club Management Training Game (Prototype)

This monorepo hosts a turn-based J-league club management business game for internal training. Development is staged across PR0–PR3; this snapshot corresponds to **PR0 (scaffold)** with Docker-based infrastructure and minimal API/UI shells.

## Stack
- Backend: FastAPI app, SQLAlchemy ORM, Alembic migrations
- Frontend: Next.js layout (static placeholder server)
- Database: PostgreSQL (Docker image)
- Container orchestration: Docker Compose

## Getting Started
1. Copy `.env.example` to `.env` and adjust if needed.
2. Build and start the stack:
   ```bash
   docker compose up --build
   ```
   - The `web` service is optional and gated behind the `web` profile.
3. Access services:
   - API: http://localhost:8000 (docs at `/docs`)
   - Web: http://localhost:3000

## Development
- Run Alembic migrations (inside the API container):
  ```bash
  docker compose exec api alembic upgrade head
  ```
- Run tests (inside the API container):
  ```bash
  docker compose exec api pytest
  ```
- Health check locally (after `docker compose up`):
  ```bash
  curl http://localhost:8000/health
  ```

Subsequent PRs will introduce the full game domain models, turn loop, fixtures generation, and simulation logic.
