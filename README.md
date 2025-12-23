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

## デモプレイ手順

### APIベース
- ゲーム作成: `POST /api/games`（GMユーザーで作成）
- クラブ追加: `POST /api/games/{game_id}/clubs`
- シーズン生成: `POST /api/seasons/games/{game_id}`
- 試合生成: `POST /api/seasons/{season_id}/fixtures/generate`
- ターン進行: `open → commit → lock → resolve → ack → advance`（`/api/turns/...`）

### CLIベース
- config作成: `~/.club-game/config` に `base_url`/`user_email`/`season_id`/`club_id` を設定
- show/input/commit:
  - `python -m apps.cli.main show ...`
  - `python -m apps.cli.main input ...`
  - `python -m apps.cli.main commit ...`
- GM操作:
  - `python -m apps.cli.main gm open|lock|resolve|advance ...`

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

## Reference APIs added for CLI (PR9.1 prep)

All endpoints require `X-User-Email` with appropriate role checks.

- Staff snapshot: `GET /api/clubs/{club_id}/management/staff`
- Staff history (ledger-derived): `GET /api/clubs/{club_id}/management/staff/history?season_id=...&from_month=...&to_month=...`
- Current decision for active turn: `GET /api/turns/seasons/{season_id}/decisions/{club_id}/current`
- Specific turn decision: `GET /api/turns/{turn_id}/decisions/{club_id}`
- Decision history (season, optional month filter): `GET /api/turns/seasons/{season_id}/decisions/{club_id}?from_month=...&to_month=...`
- Season schedule with optional month filter: `GET /api/seasons/{season_id}/schedule?month_index=...`
- Club schedule with optional month filter: `GET /api/seasons/{season_id}/clubs/{club_id}/schedule?month_index=...`

Month index is 1–12 mapped to Aug–Jul.

## CLI (PR10 read-only)

- Install deps: `pip install -r apps/cli/requirements.txt`
- Config: create `~/.club-game/config` (JSON or YAML) with at least:
  ```json
  {"base_url": "http://localhost:8000", "user_email": "owner@example.com", "season_id": "<season>", "club_id": "<club>"}
  ```
- Run: `python -m apps.cli.main show table` (uses config defaults)
- Examples:
  - `python -m apps.cli.main show match --month 2026-04`
  - `python -m apps.cli.main show current_input --json-output`
  - `python -m apps.cli.main gm lock --season-id <season>` (GM only)
  - `python -m apps.cli.main gm resolve --turn-id <turn>` (GM only)
  - `python -m apps.cli.main gm advance --season-id <season>` (GM only)
- Flags: `--verbose` prints HTTP status; `--json-output` returns raw JSON; `--month` is mapped to `month_index` (Aug=1 … Jul=12).

## PR3.2 Note: Hidden Variables
As of PR3.2, the game uses a deterministic model for staff hiring/firing.
- **Hiring Success Rate**: Currently 100%. Probabilistic success will be introduced in PR4+.
- **Firing Penalty**: Currently only financial (severance pay). Cumulative morale/reputation penalties will be introduced in PR4+.
