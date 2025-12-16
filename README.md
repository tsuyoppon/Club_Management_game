# J-League Club Management Training Game (Prototype)

This monorepo hosts a turn-based J-league club management business game for internal training. Development is staged across PR0–PR3; this snapshot corresponds to **PR1 (game skeleton)** with runnable infrastructure, database migrations, and initial gameplay APIs.

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
  - API: http://localhost:8000 (docs at `/docs`, API prefix `/api`)
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
  curl http://localhost:8000/api/health
  ```

## Core API sequence (PR1)

All requests must send `X-User-Email` to identify the acting user. The first user to create a game becomes its GM.

```bash
# 1) Create a game as GM
curl -X POST http://localhost:8000/api/games \
  -H 'Content-Type: application/json' \
  -H 'X-User-Email: gm@example.com' \
  -d '{"name":"Training League"}'

# 2) Add clubs (max 5 per game)
curl -X POST http://localhost:8000/api/games/<game_id>/clubs \
  -H 'X-User-Email: gm@example.com' \
  -H 'Content-Type: application/json' \
  -d '{"name":"Osaka Eleven","short_name":"OSA"}'

# 3) Add memberships
curl -X POST http://localhost:8000/api/games/<game_id>/memberships \
  -H 'X-User-Email: gm@example.com' \
  -H 'Content-Type: application/json' \
  -d '{"email":"owner@example.com","role":"club_owner","club_id":"<club_id>"}'

# 4) Create a season (generates 12 turns Aug→Jul)
curl -X POST http://localhost:8000/api/seasons/games/<game_id> \
  -H 'X-User-Email: gm@example.com' \
  -H 'Content-Type: application/json' \
  -d '{"year_label":"2025"}'

# 5) Generate fixtures for Aug→May (10 match months)
curl -X POST http://localhost:8000/api/seasons/<season_id>/fixtures/generate \
  -H 'X-User-Email: gm@example.com' -d '{}'

# 6) View schedule
curl -X GET http://localhost:8000/api/seasons/<season_id>/clubs/<club_id>/schedule \
  -H 'X-User-Email: owner@example.com'

# 7) Turn lifecycle (simplified)
# Open -> commit -> lock -> resolve -> ack -> advance
curl -X GET http://localhost:8000/api/turns/seasons/<season_id>/current -H 'X-User-Email: owner@example.com'
curl -X POST http://localhost:8000/api/turns/<turn_id>/decisions/<club_id>/commit \
  -H 'X-User-Email: owner@example.com' -H 'Content-Type: application/json' -d '{"payload":{}}'
curl -X POST http://localhost:8000/api/turns/<turn_id>/lock -H 'X-User-Email: gm@example.com'
curl -X POST http://localhost:8000/api/turns/<turn_id>/resolve -H 'X-User-Email: gm@example.com'
curl -X POST http://localhost:8000/api/turns/<turn_id>/ack \
  -H 'X-User-Email: owner@example.com' -H 'Content-Type: application/json' -d '{"club_id":"<club_id>","ack":true}'
curl -X POST http://localhost:8000/api/turns/<turn_id>/advance -H 'X-User-Email: gm@example.com'
```

Subsequent PRs will introduce simulation, ledgers, fanbase, sponsor modeling, and UI templates.
