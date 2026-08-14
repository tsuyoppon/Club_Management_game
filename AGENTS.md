# Club Management Game: mandatory engineering and database safety rules

This file must be read before modifying, testing, migrating, deploying, or
operating this repository. It records the database-loss incident of 2026-08-14
and defines mandatory controls for preventing a recurrence.

## Scope and precedence

- These rules apply to every agent and developer working in this repository.
- Re-read this file before any command that can connect to PostgreSQL, run API
  tests, change schemas, manipulate Docker volumes, or deploy the application.
- If a requested operation conflicts with these rules, stop and obtain explicit
  user approval after explaining the exact database, volume, and data at risk.
- Never assume that an application archive is a backup.

## Incident record: 2026-08-14 live database loss

### What happened

While implementing and validating the revised next-home-game promotion effect,
the following form of command was run inside the normal API service container:

```sh
docker compose exec -T api pytest ...
```

The API service inherited its normal Compose environment:

```text
DATABASE_URL=postgresql+psycopg2://postgres:postgres@db:5432/club_game
```

At that time, `apps/api/tests/conftest.py` contained an autouse fixture that ran
the following for every test:

```python
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)
```

Because `DATABASE_URL` was already set by the API container, the test setup did
not replace it with a test database URL. The first test therefore dropped and
recreated the ORM-managed tables in the live `club_game` database. Subsequent
tests inserted synthetic test records into the newly recreated schema.

### Impact

Immediately before the incident, the live database included:

- 6 games
- 156 turns
- 312 turn decisions
- 130 fixtures
- 130 matches
- 2,143 financial ledger rows
- 270 financial snapshots
- Room `DQ23CP7M`, with 2 clubs, 4 seasons, and 48 turns

Immediately after the destructive test run, the database contained only the
synthetic test state, including one `Test Game`, two fixtures, and two matches.
The original games, including `DQ23CP7M`, were no longer logically present.

Archived games were also lost. The application's archive endpoint only changed
`game.status` and `room.status` to `archived` in the same database. It did not
copy game data to another table, database, file, or object store.

### Technical cause

The direct cause was destructive pytest setup running against the live database.
The underlying control failures were:

1. Tests and the running application shared the same database endpoint and
   credentials when pytest was executed inside the API container.
2. The test fixture had destructive `drop_all`/`create_all` behavior without a
   fail-closed check on the target database name.
3. The test command did not explicitly provide an isolated `DATABASE_URL`.
4. There was no preflight confirmation of `current_database()` before pytest.
5. There was no restorable external PostgreSQL backup or pre-incident base
   backup, and PostgreSQL WAL archiving was disabled.
6. The application archive feature was treated as lifecycle state, but there
   was no separate durable backup for archived games.

The promotion formula itself did not cause the data loss.

### Containment and recovery investigation

After discovery:

1. The database container was stopped.
2. A read-only filesystem-level copy of the post-incident PostgreSQL volume was
   created and checksummed.
3. A separate forensic Docker volume was created from that copy; the preserved
   source was not used for experiments.
4. WAL and PostgreSQL control data were inspected.
5. The WAL showed the destructive drop transaction, but the old relation files
   were already unlinked and absent from the preserved volume.
6. Standard point-in-time recovery was not possible because there was no
   pre-drop base backup and WAL archiving had been disabled.
7. No usable Time Machine/APFS data snapshot was found.

The user subsequently chose to abandon recovery. The production database was
recreated from an empty database through the complete Alembic migration chain,
and the API and web services were restarted. The preservation archive remains
outside Git under `.recovery/`.

## Controls already implemented

Commit `e564e93` changed `apps/api/tests/conftest.py` so that:

- the local default database is `club_game_test`, not `club_game`; and
- pytest raises an error before importing the application when the database
  name does not end in `_test`.

This guard is mandatory and must not be weakened, bypassed, monkeypatched, or
removed to make a test command more convenient.

## Mandatory test procedure

### Prohibited command

Never run this command, or an equivalent command that inherits the normal API
service database URL:

```sh
docker compose exec api pytest
```

Adding pytest paths or flags does not make the command safe.

### Required isolated database

All PostgreSQL-backed tests must use a dedicated database whose name ends in
`_test`. The normal repository database is `club_game`; it is never a test
target. A standard isolated invocation is:

```sh
docker compose run --rm \
  -e DATABASE_URL=postgresql+psycopg2://postgres:postgres@db:5432/club_game_test \
  api pytest -q
```

Before running it:

1. Verify the resolved URL contains the expected `_test` database name.
2. Verify the database is disposable and contains no user game data.
3. If the identity or ownership of the target is uncertain, stop; do not run
   pytest to discover what happens.
4. Never point a test at `club_game`, even for a single test or read-only-looking
   test. The autouse fixture is destructive.

When practical, use a separate PostgreSQL container or disposable volume in
addition to a separate database name. Do not use the production Docker volume
for migration rehearsals or destructive integration tests.

## Mandatory database and deployment procedure

Before migrations, schema changes, data repair, or deployment:

1. Resolve and report the exact Compose project, container, database name, and
   Docker volume involved.
2. Determine whether the action is read-only, additive, or destructive.
3. For any operation capable of modifying persistent data, create a restorable
   backup first and verify its integrity. For material production changes,
   perform a restore rehearsal on an isolated target.
4. Rehearse migrations and smoke tests on an isolated database.
5. Run relevant tests only with an explicitly isolated `_test` URL.
6. Apply Alembic migrations; do not use ORM `create_all` as a substitute for
   production migration history.
7. Restart services only after database state and migration revision have been
   verified.
8. Confirm API health, web response, web-to-API connectivity, and a bounded
   smoke flow appropriate to the change.
9. Confirm that production row counts did not unexpectedly decrease.

The following require explicit user authorization and a verified exact target:

- `dropdb`, `DROP DATABASE`, `DROP SCHEMA`, or table drops
- `Base.metadata.drop_all`
- destructive Alembic downgrades
- Docker volume deletion, replacement, pruning, or reinitialization
- deletion or overwrite of backups
- bulk deletion or rewriting of game records

Never use a production-like database as a convenient test fixture.

## Backup and archive requirements

- Application-level `archived` status is not a backup and must never be
  described as one.
- Before relying on a backup, verify that it can be restored and that expected
  game, turn, fixture, match, finance, and archive records are present.
- Maintain automated PostgreSQL backups outside the active Docker volume.
- Keep backup retention sufficient to recover from delayed discovery.
- Add WAL archiving or another point-in-time-recovery mechanism when production
  durability warrants it.
- Periodically perform a documented restore drill.

## Required incident response if data loss is suspected

1. Stop write-producing application services.
2. Stop the database cleanly if doing so will not worsen the incident.
3. Do not restart, vacuum, recreate, migrate, or run tests against the affected
   storage.
4. Preserve the exact volume or disk read-only and record checksums.
5. Perform all investigation on copies.
6. Record commands, timestamps, database counts, WAL state, and conclusions.
7. State uncertainty honestly; do not claim recoverability without a verified
   restore.

## Pre-change checklist for future work

Before declaring any implementation complete, explicitly confirm:

- [ ] This file was read for the current task.
- [ ] The production database and test database were positively distinguished.
- [ ] Every pytest invocation used a database ending in `_test`.
- [ ] No persistent data or archive state was modified unless requested.
- [ ] Relevant targeted tests passed in isolation.
- [ ] Any unrelated full-suite failures were reported rather than hidden.
- [ ] Migration and deployment steps were validated in proportion to risk.
- [ ] Backups and recovery artifacts were not staged or committed accidentally.

