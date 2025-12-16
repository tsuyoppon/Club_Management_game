# J-League Club Management Training Game (Prototype)

This monorepo hosts a turn-based J-league club management business game for internal training. Development is staged across PR0–PR3; this snapshot corresponds to **PR0 (scaffold)** with Docker-based infrastructure, placeholder Alembic migrations, and minimal API/UI shells.

## Stack
- Backend: FastAPI-style app (offline-friendly stub), SQLAlchemy-style ORM scaffold, Alembic migration scaffold
- Frontend: Next.js-style layout (static placeholder server for offline environments)
- Database: PostgreSQL (Docker image)
- Container orchestration: Docker Compose

## Getting Started
1. Copy `.env.example` to `.env` and adjust if needed.
2. Build and start the stack:
   ```bash
   docker compose up --build
   ```
   - The `web` service is optional and gated behind the `web` profile for offline compatibility.
3. Access services:
   - API: http://localhost:8000 (docs at `/docs` placeholder)
   - Web: http://localhost:3000

## Development
- Python path is configured via `pytest.ini`; vendored lightweight stubs allow local execution without networked package installs.
- Run tests: `pytest`
- Alembic migrations: `alembic -c apps/api/alembic.ini upgrade head` (scaffold only in PR0)

Subsequent PRs will introduce the full game domain models, turn loop, fixtures generation, and simulation logic.
