#!/usr/bin/env python3
"""Fail-closed backup and restore tooling for Club Management Game."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BACKUP_ROOT = Path("/Users/scide_furusawa/.club-management-game/backups")
EXPECTED_PROJECT = "club_management_game"
EXPECTED_DATABASE = "club_game"
EXPECTED_VOLUME = "club_management_game_pgdata"
POSTGRES_IMAGE = "postgres:15-alpine"
CRITICAL_COUNT_TABLES = (
    "games",
    "turns",
    "turn_decisions",
    "fixtures",
    "matches",
    "club_financial_ledgers",
    "club_financial_snapshots",
)


class BackupManagerError(RuntimeError):
    pass


def run(command: list[str], *, capture: bool = False, binary_stdout=None) -> str:
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=False,
        stdout=binary_stdout if binary_stdout is not None else (subprocess.PIPE if capture else None),
        stderr=subprocess.PIPE,
        text=binary_stdout is None,
    )
    if result.returncode:
        stderr = result.stderr.decode("utf-8", errors="replace") if isinstance(result.stderr, bytes) else result.stderr
        raise BackupManagerError(f"Command failed ({result.returncode}): {' '.join(command)}\n{stderr.strip()}")
    if capture:
        return result.stdout.strip()
    return ""


def backup_root() -> Path:
    return Path(os.environ.get("CLUB_GAME_BACKUP_DIR", DEFAULT_BACKUP_ROOT)).expanduser().resolve()


def ensure_layout(root: Path) -> None:
    if root == Path("/") or root == Path.home():
        raise BackupManagerError(f"Refusing unsafe backup root: {root}")
    for path in (root, *(root / name for name in ("database", "games", "manifests", "status", "rehearsals", "tmp"))):
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.chmod(0o700)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    os.replace(temporary, path)
    path.chmod(0o600)


def compose_project() -> str:
    output = run(["docker", "compose", "ps", "--format", "json"], capture=True)
    if not output:
        raise BackupManagerError("Compose stack is not running")
    projects = {json.loads(line)["Project"] for line in output.splitlines()}
    if projects != {EXPECTED_PROJECT}:
        raise BackupManagerError(f"Unexpected Compose projects: {sorted(projects)}")
    return projects.pop()


def db_container() -> str:
    container = run(["docker", "compose", "ps", "-q", "db"], capture=True)
    if not container:
        raise BackupManagerError("Database container is not running")
    return container


def mounted_volume(container: str) -> str:
    raw = run(["docker", "inspect", container, "--format", "{{json .Mounts}}"], capture=True)
    mounts = json.loads(raw)
    matching = [mount for mount in mounts if mount.get("Destination") == "/var/lib/postgresql/data"]
    if len(matching) != 1 or matching[0].get("Type") != "volume":
        raise BackupManagerError("Could not positively identify the PostgreSQL volume")
    volume = matching[0]["Name"]
    expected = os.environ.get("CLUB_GAME_PGDATA_VOLUME", EXPECTED_VOLUME)
    if volume != expected:
        raise BackupManagerError(f"PostgreSQL volume mismatch: mounted={volume}, expected={expected}")
    return volume


def database_snapshot() -> dict:
    count_sql = " UNION ALL ".join(
        f"SELECT '{table}', count(*)::text FROM {table}" for table in CRITICAL_COUNT_TABLES
    )
    sql = (
        "SELECT 'database', current_database() UNION ALL "
        "SELECT 'user', current_user UNION ALL "
        "SELECT 'recovery', pg_is_in_recovery()::text UNION ALL "
        "SELECT 'alembic_revision', version_num FROM alembic_version UNION ALL "
        f"{count_sql} UNION ALL "
        "SELECT 'archived_games', count(*)::text FROM games WHERE status='archived'"
    )
    output = run(
        ["docker", "compose", "exec", "-T", "db", "psql", "-U", "postgres", "-d", EXPECTED_DATABASE, "-At", "-F", "|", "-c", sql],
        capture=True,
    )
    values = dict(line.split("|", 1) for line in output.splitlines() if "|" in line)
    if values.get("database") != EXPECTED_DATABASE:
        raise BackupManagerError(f"Database mismatch: {values.get('database')}")
    if values.get("recovery") != "false" and values.get("recovery") != "f":
        raise BackupManagerError("Refusing to back up a database in recovery")
    return {
        "database": values["database"],
        "database_user": values["user"],
        "alembic_revision": values["alembic_revision"],
        "counts": {name: int(values[name]) for name in (*CRITICAL_COUNT_TABLES, "archived_games")},
    }


def preflight() -> dict:
    project = compose_project()
    container = db_container()
    volume = mounted_volume(container)
    snapshot = database_snapshot()
    return {"compose_project": project, "db_container": container, "volume": volume, **snapshot}


def write_status(root: Path, *, ok: bool, operation: str, detail: str, backup_id: str | None = None) -> None:
    atomic_json(
        root / "status" / "last-run.json",
        {
            "ok": ok,
            "operation": operation,
            "detail": detail,
            "backup_id": backup_id,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def verify_pg_archive(root: Path, archive: Path) -> None:
    relative = archive.resolve().relative_to(root)
    run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{root}:/backups:ro",
            POSTGRES_IMAGE,
            "pg_restore",
            "--list",
            f"/backups/{relative}",
        ],
        capture=True,
    )


def db_create(reason: str = "scheduled") -> dict:
    root = backup_root()
    ensure_layout(root)
    backup_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    partial = root / "tmp" / f"{backup_id}.dump.partial"
    final = root / "database" / f"{backup_id}.dump"
    try:
        facts = preflight()
        with partial.open("wb") as output:
            partial.chmod(0o600)
            run(
                [
                    "docker",
                    "compose",
                    "exec",
                    "-T",
                    "db",
                    "pg_dump",
                    "-U",
                    "postgres",
                    "-d",
                    EXPECTED_DATABASE,
                    "--format=custom",
                    "--no-owner",
                    "--no-privileges",
                ],
                binary_stdout=output,
            )
        if partial.stat().st_size == 0:
            raise BackupManagerError("pg_dump produced an empty archive")
        verify_pg_archive(root, partial)
        digest = sha256_file(partial)
        os.replace(partial, final)
        final.chmod(0o600)
        manifest = {
            "format_version": 1,
            "kind": "database",
            "backup_id": backup_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
            "sha256": digest,
            "size_bytes": final.stat().st_size,
            "archive_path": str(final),
            "verified": True,
            **facts,
        }
        atomic_json(root / "manifests" / f"{backup_id}.db.json", manifest)
        write_status(root, ok=True, operation="db-create", detail="verified", backup_id=backup_id)
        return manifest
    except Exception as exc:
        if partial.exists():
            partial.unlink()
        write_status(root, ok=False, operation="db-create", detail=str(exc), backup_id=backup_id)
        raise


def load_manifest(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BackupManagerError(f"Invalid manifest {path}: {exc}") from exc


def newest_manifest(root: Path, suffix: str) -> tuple[Path, dict]:
    candidates = sorted((root / "manifests").glob(f"*.{suffix}.json"))
    if not candidates:
        raise BackupManagerError(f"No {suffix} backup manifests found")
    path = candidates[-1]
    return path, load_manifest(path)


def db_verify(backup_id: str | None = None) -> dict:
    root = backup_root()
    ensure_layout(root)
    if backup_id:
        manifest_path = root / "manifests" / f"{backup_id}.db.json"
        manifest = load_manifest(manifest_path)
    else:
        manifest_path, manifest = newest_manifest(root, "db")
    archive = Path(manifest["archive_path"])
    if not archive.is_file():
        raise BackupManagerError(f"Archive missing: {archive}")
    digest = sha256_file(archive)
    if digest != manifest["sha256"]:
        raise BackupManagerError("Database backup SHA-256 mismatch")
    verify_pg_archive(root, archive)
    return {**manifest, "verified_at": datetime.now(timezone.utc).isoformat()}


def db_status() -> dict:
    root = backup_root()
    ensure_layout(root)
    status_path = root / "status" / "last-run.json"
    if not status_path.exists():
        raise BackupManagerError("No backup status has been recorded")
    status = load_manifest(status_path)
    if not status.get("ok"):
        raise BackupManagerError(f"Last backup failed: {status.get('detail')}")
    recorded = datetime.fromisoformat(status["recorded_at"])
    age = datetime.now(timezone.utc) - recorded
    if age > timedelta(minutes=65):
        raise BackupManagerError(f"Last successful backup is stale: {age}")
    verified = db_verify(status.get("backup_id"))
    free_bytes = os.statvfs(root).f_bavail * os.statvfs(root).f_frsize
    if free_bytes < max(1024 * 1024 * 1024, verified["size_bytes"] * 3):
        raise BackupManagerError("Backup filesystem is below the minimum free-space threshold")
    return {"status": status, "latest_backup": verified, "free_bytes": free_bytes}


def wait_ready(container: str, database: str) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["docker", "exec", container, "pg_isready", "-U", "postgres", "-d", database],
            cwd=REPO_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            return
        time.sleep(1)
    raise BackupManagerError(f"Timed out waiting for isolated database {database}")


def db_rehearse(backup_id: str | None = None) -> dict:
    root = backup_root()
    verified = db_verify(backup_id)
    archive = Path(verified["archive_path"])
    relative = archive.relative_to(root)
    container = f"club-game-db-rehearsal-{uuid.uuid4().hex[:8]}"
    database = "club_game_restore_test"
    run(
        [
            "docker",
            "run",
            "-d",
            "--rm",
            "--name",
            container,
            "--tmpfs",
            "/var/lib/postgresql/data:rw,noexec,nosuid,size=1g",
            "-e",
            "POSTGRES_USER=postgres",
            "-e",
            "POSTGRES_PASSWORD=postgres",
            "-e",
            f"POSTGRES_DB={database}",
            "-v",
            f"{root}:/backups:ro",
            POSTGRES_IMAGE,
        ],
        capture=True,
    )
    try:
        wait_ready(container, database)
        run(
            [
                "docker",
                "exec",
                container,
                "pg_restore",
                "-U",
                "postgres",
                "-d",
                database,
                "--no-owner",
                "--no-privileges",
                "--exit-on-error",
                f"/backups/{relative}",
            ]
        )
        count_sql = " UNION ALL ".join(
            f"SELECT '{table}', count(*)::text FROM {table}" for table in CRITICAL_COUNT_TABLES
        ) + " UNION ALL SELECT 'archived_games', count(*)::text FROM games WHERE status='archived'"
        output = run(
            ["docker", "exec", container, "psql", "-U", "postgres", "-d", database, "-At", "-F", "|", "-c", count_sql],
            capture=True,
        )
        restored_counts = {name: int(value) for name, value in (line.split("|", 1) for line in output.splitlines())}
        if restored_counts != verified["counts"]:
            raise BackupManagerError(
                f"Restore rehearsal count mismatch: restored={restored_counts}, expected={verified['counts']}"
            )
        receipt = {
            "kind": "database-rehearsal",
            "backup_id": verified["backup_id"],
            "database": database,
            "counts": restored_counts,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "verified": True,
        }
        receipt_path = root / "rehearsals" / f"{verified['backup_id']}.db.json"
        atomic_json(receipt_path, receipt)
        return receipt
    finally:
        subprocess.run(["docker", "stop", container], cwd=REPO_ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def retention_candidates(root: Path) -> list[tuple[Path, Path]]:
    now = datetime.now(timezone.utc)
    manifests = [(path, load_manifest(path)) for path in (root / "manifests").glob("*.db.json")]
    manifests.sort(key=lambda item: item[1]["created_at"], reverse=True)
    keep: set[Path] = set()
    daily: dict[str, Path] = {}
    monthly: dict[str, Path] = {}
    for path, manifest in manifests:
        created = datetime.fromisoformat(manifest["created_at"])
        age = now - created
        if age <= timedelta(hours=48):
            keep.add(path)
        elif age <= timedelta(days=30):
            daily.setdefault(created.date().isoformat(), path)
        elif age <= timedelta(days=365):
            monthly.setdefault(created.strftime("%Y-%m"), path)
    keep.update(daily.values())
    keep.update(monthly.values())
    if manifests:
        keep.add(manifests[0][0])
    candidates: list[tuple[Path, Path]] = []
    for path, manifest in manifests:
        if path not in keep:
            candidates.append((path, Path(manifest["archive_path"])))
    for path in (root / "manifests").glob("*.game.json"):
        manifest = load_manifest(path)
        created = datetime.fromisoformat(manifest["created_at"])
        if now - created > timedelta(days=365):
            candidates.append((path, game_archive_path(root, manifest)))
    return candidates


def prune(*, apply: bool, confirm_root: str | None) -> dict:
    root = backup_root()
    ensure_layout(root)
    candidates = retention_candidates(root)
    if apply:
        if confirm_root != str(root):
            raise BackupManagerError("--confirm-root must exactly match the resolved backup root")
        for manifest, archive in candidates:
            archive.unlink(missing_ok=False)
            manifest.unlink(missing_ok=False)
    return {
        "applied": apply,
        "backup_root": str(root),
        "candidates": [{"manifest": str(manifest), "archive": str(archive)} for manifest, archive in candidates],
    }


def game_manifests(root: Path) -> list[dict]:
    manifests = [load_manifest(path) for path in (root / "manifests").glob("*.game.json")]
    return sorted(manifests, key=lambda item: item["created_at"], reverse=True)


def game_archive_path(root: Path, manifest: dict) -> Path:
    relative = manifest.get("archive_relative_path")
    if relative:
        return root / relative
    legacy = Path(manifest["archive_path"])
    if legacy.is_relative_to(Path("/backups")):
        return root / legacy.relative_to(Path("/backups"))
    return legacy


def game_verify(backup_id: str) -> dict:
    root = backup_root()
    manifest = load_manifest(root / "manifests" / f"{backup_id}.game.json")
    archive = game_archive_path(root, manifest)
    if sha256_file(archive) != manifest["sha256"]:
        raise BackupManagerError("Game backup SHA-256 mismatch")
    import zipfile

    with zipfile.ZipFile(archive, "r") as bundle:
        bad_member = bundle.testzip()
        if bad_member:
            raise BackupManagerError(f"Corrupt game backup member: {bad_member}")
        embedded = json.loads(bundle.read("manifest.json"))
        actual = {}
        for table_name in embedded["included_tables"]:
            actual[table_name] = len(
                [line for line in bundle.read(f"data/{table_name}.jsonl").decode("utf-8").splitlines() if line]
            )
        if actual != embedded["counts"] or actual != manifest["counts"]:
            raise BackupManagerError("Game backup row-count mismatch")
    return {**manifest, "archive_path": str(archive), "verified_at": datetime.now(timezone.utc).isoformat()}


def database_name_from_url(url: str) -> str:
    return urlparse(url.replace("postgresql+psycopg2://", "postgresql://", 1)).path.lstrip("/")


def run_game_restore(archive: Path, database_url: str, *, live: bool = False) -> dict:
    root = backup_root()
    relative = archive.relative_to(root)
    command = [
            "docker",
            "compose",
            "run",
            "--rm",
            "-T",
            "-e",
            f"DATABASE_URL={database_url}",
    ]
    if live:
        command.extend(["-e", "ALLOW_LIVE_GAME_RESTORE=club_game"])
    command.extend(
        [
            "api",
            "python",
            "-m",
            "app.services.game_backup_cli",
            "restore",
            "--archive",
            f"/backups/{relative}",
        ]
    )
    output = run(
        command,
        capture=True,
    )
    return json.loads(output.splitlines()[-1])


def game_restore(args) -> dict:
    verified = game_verify(args.backup_id)
    database_name = database_name_from_url(args.database_url)
    if database_name.endswith("_test"):
        return run_game_restore(Path(verified["archive_path"]), args.database_url)
    if not args.live:
        raise BackupManagerError("Non-test restore requires --live")
    if database_name != EXPECTED_DATABASE or args.confirm_database != EXPECTED_DATABASE:
        raise BackupManagerError("Live database confirmation did not match club_game")
    if args.confirm_game != verified["game_id"]:
        raise BackupManagerError("Live game confirmation did not match the backup game ID")
    receipt = backup_root() / "rehearsals" / f"{args.backup_id}.game.json"
    if not receipt.is_file() or not load_manifest(receipt).get("verified"):
        raise BackupManagerError("A verified game rehearsal receipt is required before live restore")
    db_create(reason=f"pre-game-restore:{args.backup_id}")
    return run_game_restore(Path(verified["archive_path"]), args.database_url, live=True)


def game_rehearse(backup_id: str) -> dict:
    root = backup_root()
    verified = game_verify(backup_id)
    container = f"club-game-game-rehearsal-{uuid.uuid4().hex[:8]}"
    network = f"{EXPECTED_PROJECT}_default"
    database = "club_game_restore_test"
    run(
        [
            "docker",
            "run",
            "-d",
            "--rm",
            "--name",
            container,
            "--network",
            network,
            "--tmpfs",
            "/var/lib/postgresql/data:rw,noexec,nosuid,size=1g",
            "-e",
            "POSTGRES_USER=postgres",
            "-e",
            "POSTGRES_PASSWORD=postgres",
            "-e",
            f"POSTGRES_DB={database}",
            POSTGRES_IMAGE,
        ],
        capture=True,
    )
    database_url = f"postgresql+psycopg2://postgres:postgres@{container}:5432/{database}"
    try:
        wait_ready(container, database)
        run(
            [
                "docker",
                "compose",
                "run",
                "--rm",
                "-T",
                "-e",
                f"DATABASE_URL={database_url}",
                "api",
                "alembic",
                "upgrade",
                "head",
            ]
        )
        restored = run_game_restore(Path(verified["archive_path"]), database_url)
        receipt = {
            "kind": "game-rehearsal",
            "backup_id": backup_id,
            "game_id": verified["game_id"],
            "database": database,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "restore": restored,
            "verified": restored.get("counts") == verified["counts"],
        }
        if not receipt["verified"]:
            raise BackupManagerError("Game restore rehearsal count mismatch")
        atomic_json(root / "rehearsals" / f"{backup_id}.game.json", receipt)
        return receipt
    finally:
        subprocess.run(["docker", "stop", container], cwd=REPO_ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    groups = parser.add_subparsers(dest="group", required=True)
    db = groups.add_parser("db")
    db_commands = db.add_subparsers(dest="command", required=True)
    create = db_commands.add_parser("create")
    create.add_argument("--reason", default="manual")
    verify = db_commands.add_parser("verify")
    verify.add_argument("--backup-id")
    db_commands.add_parser("status")
    rehearse = db_commands.add_parser("rehearse")
    rehearse.add_argument("--backup-id")
    prune_parser = db_commands.add_parser("prune")
    prune_parser.add_argument("--apply", action="store_true")
    prune_parser.add_argument("--confirm-root")

    game = groups.add_parser("game")
    game_commands = game.add_subparsers(dest="command", required=True)
    game_commands.add_parser("list")
    game_verify_parser = game_commands.add_parser("verify")
    game_verify_parser.add_argument("--backup-id", required=True)
    game_rehearse_parser = game_commands.add_parser("rehearse")
    game_rehearse_parser.add_argument("--backup-id", required=True)
    restore = game_commands.add_parser("restore")
    restore.add_argument("--backup-id", required=True)
    restore.add_argument("--database-url", required=True)
    restore.add_argument("--live", action="store_true")
    restore.add_argument("--confirm-database")
    restore.add_argument("--confirm-game")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.group == "db" and args.command == "create":
            result = db_create(args.reason)
        elif args.group == "db" and args.command == "verify":
            result = db_verify(args.backup_id)
        elif args.group == "db" and args.command == "status":
            result = db_status()
        elif args.group == "db" and args.command == "rehearse":
            result = db_rehearse(args.backup_id)
        elif args.group == "db" and args.command == "prune":
            result = prune(apply=args.apply, confirm_root=args.confirm_root)
        elif args.group == "game" and args.command == "list":
            result = {"backups": game_manifests(backup_root())}
        elif args.group == "game" and args.command == "verify":
            result = game_verify(args.backup_id)
        elif args.group == "game" and args.command == "rehearse":
            result = game_rehearse(args.backup_id)
        elif args.group == "game" and args.command == "restore":
            result = game_restore(args)
        else:
            raise BackupManagerError("Unsupported command")
    except (BackupManagerError, OSError, json.JSONDecodeError) as exc:
        print(f"backup_manager.py: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
