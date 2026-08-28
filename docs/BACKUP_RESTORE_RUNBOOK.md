# Backup and Restore Runbook

This runbook implements the database-safety requirements in `AGENTS.md`.
Application `archived` state is not a backup.

## Fixed local targets

```text
Compose project: club_management_game
Database service: db
Database: club_game
Docker volume: club_management_game_pgdata
Backup root: /Users/scide_furusawa/.club-management-game/backups
```

Before every operation, confirm that the running container and mounted volume
still match these values. Stop if they do not. The backup manager performs the
same checks before `pg_dump`.

The backup root is outside Git, the repository, the Codex worktree, and the
PostgreSQL volume. It protects against logical database loss and Docker-volume
loss, but it does not protect against failure or loss of the host disk.

## Initial setup

Create the root and its owner-only directories:

```bash
mkdir -p /Users/scide_furusawa/.club-management-game/backups/{database,games,manifests,status,rehearsals,tmp}
chmod 700 /Users/scide_furusawa/.club-management-game \
  /Users/scide_furusawa/.club-management-game/backups \
  /Users/scide_furusawa/.club-management-game/backups/{database,games,manifests,status,rehearsals,tmp}
```

Set the local, Git-ignored `.env` values:

```text
COMPOSE_PROJECT_NAME=club_management_game
CLUB_GAME_PGDATA_VOLUME=club_management_game_pgdata
CLUB_GAME_BACKUP_DIR=/Users/scide_furusawa/.club-management-game/backups
```

Do not guess the volume name. Resolve it from the currently running DB
container before setting or changing this value.

## Database backups

Create and verify a new immutable backup:

```bash
python3 scripts/backup_manager.py db create --reason manual
python3 scripts/backup_manager.py db verify
python3 scripts/backup_manager.py db status
```

Every invocation creates a new timestamped custom-format `pg_dump`; it never
overwrites an older archive. The sidecar manifest records SHA-256, Alembic
revision, exact Compose/DB/volume identity, and critical row counts.

Perform an isolated restore rehearsal in a disposable tmpfs PostgreSQL
container:

```bash
python3 scripts/backup_manager.py db rehearse
```

The rehearsal database is always named `club_game_restore_test` and never uses
`club_management_game_pgdata`.

## Hourly scheduling on macOS

Install the launchd job only after this branch has been integrated into the
main checkout at `/Users/scide_furusawa/Documents/Club_Management_game` and a
manual backup plus rehearsal have both passed.

```bash
cp ops/com.club-management-game.backup.plist.example \
  /Users/scide_furusawa/Library/LaunchAgents/com.club-management-game.backup.plist
launchctl bootstrap gui/$(id -u) \
  /Users/scide_furusawa/Library/LaunchAgents/com.club-management-game.backup.plist
```

The job runs once when loaded and then every 3600 seconds. It can run while no
player is using the game, but the host Mac, Docker Desktop, and the `db`
container must be running. Missed backups while the Mac or DB is stopped are
not synthesized; `RunAtLoad` creates a fresh backup after the job is loaded
again.

Check the job and backup freshness:

```bash
launchctl print gui/$(id -u)/com.club-management-game.backup
python3 scripts/backup_manager.py db status
```

`db status` fails when the last successful backup is older than 65 minutes,
the most recent run failed, integrity verification fails, or free space is too
low.

## Game-scoped backups and deletion

The game host can create a verified backup through:

```text
POST /api/games/{game_id}/backups
GET  /api/games/{game_id}/backups/latest
```

Permanent deletion automatically creates another game backup. If storage or
verification fails, the DELETE returns HTTP 503 and the database transaction is
rolled back. The backup includes all game-owned records and only the exclusive
guest sessions needed for browser resumption; plaintext cookies are never
stored.

Operator inspection:

```bash
python3 scripts/backup_manager.py game list
python3 scripts/backup_manager.py game verify --backup-id <backup_id>
python3 scripts/backup_manager.py game rehearse --backup-id <backup_id>
```

The rehearsal creates a separate tmpfs PostgreSQL database ending in `_test`,
applies the Alembic chain, restores the game as archived, verifies counts, and
writes a rehearsal receipt.

## Live game restore

Never restore directly before a successful rehearsal. The live command requires
the rehearsal receipt, typed database and game confirmations, and automatically
creates a verified full-DB backup immediately before inserting anything:

```bash
python3 scripts/backup_manager.py game restore \
  --backup-id <backup_id> \
  --database-url postgresql+psycopg2://postgres:postgres@db:5432/club_game \
  --live \
  --confirm-database club_game \
  --confirm-game <game_uuid>
```

The restored game remains archived. After the operator and host verify it, the
host can use `POST /api/games/{game_id}/unarchive` to make it playable. Existing
game IDs are never overwritten.

## Retention

The implemented retention bands are hourly for 48 hours, daily for 30 days,
monthly for 12 months, and pre-delete game backups for 12 months. Automatic
deletion is disabled. Preview candidates first:

```bash
python3 scripts/backup_manager.py db prune
```

Deletion requires explicit operator authorization and the exact resolved root:

```bash
python3 scripts/backup_manager.py db prune \
  --apply \
  --confirm-root /Users/scide_furusawa/.club-management-game/backups
```

## Incident response

If data loss is suspected, stop application writers, preserve the exact DB
volume read-only, and investigate copies only. Do not run tests, migrations,
vacuum, reset, restore, or restart against the affected storage. Follow the full
incident-response sequence in `AGENTS.md`.
