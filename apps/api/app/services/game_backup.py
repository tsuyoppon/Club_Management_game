"""Portable, verified, game-scoped backups.

Application archive state is intentionally separate from this module.  A backup
is only considered complete after the ZIP and its sidecar manifest have both
been written and verified.
"""

from __future__ import annotations

import enum
import hashlib
import json
import os
import secrets
import string
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import DateTime, Enum, Numeric, inspect, select, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db import models


FORMAT_VERSION = 1

GAME_OWNED_TABLES = {
    "games",
    "clubs",
    "memberships",
    "seasons",
    "season_final_standings",
    "turns",
    "turn_decisions",
    "turn_acks",
    "game_rooms",
    "game_completions",
    "game_room_members",
    "web_turn_drafts",
    "fixtures",
    "matches",
    "club_financial_profiles",
    "club_financial_states",
    "club_financial_ledgers",
    "club_financial_snapshots",
    "club_sponsor_states",
    "club_academies",
    "club_reinforcement_plans",
    "club_staffs",
    "club_fanbase_states",
    "club_sales_allocations",
    "club_point_penalties",
    "club_bankruptcy_states",
    "season_public_disclosures",
    "game_final_results",
}
SHARED_TABLES = {"users", "web_sessions"}
EXCLUDED_TABLES: set[str] = set()

# Parents must precede children so the same order can be used during restore.
RESTORE_ORDER = [
    "users",
    "games",
    "game_completions",
    "clubs",
    "seasons",
    "turns",
    "fixtures",
    "memberships",
    "turn_decisions",
    "turn_acks",
    "game_rooms",
    "game_room_members",
    "web_sessions",
    "web_turn_drafts",
    "matches",
    "season_final_standings",
    "club_financial_profiles",
    "club_financial_states",
    "club_financial_ledgers",
    "club_financial_snapshots",
    "club_sponsor_states",
    "club_academies",
    "club_reinforcement_plans",
    "club_staffs",
    "club_fanbase_states",
    "club_sales_allocations",
    "club_point_penalties",
    "club_bankruptcy_states",
    "season_public_disclosures",
    "game_final_results",
]

USER_REFERENCE_COLUMNS = {
    ("memberships", "user_id"),
    ("turn_decisions", "committed_by_user_id"),
    ("turn_acks", "user_id"),
    ("game_rooms", "host_user_id"),
    ("game_completions", "completed_by_user_id"),
    ("game_completions", "reopened_by_user_id"),
    ("game_room_members", "user_id"),
    ("web_sessions", "user_id"),
    ("web_turn_drafts", "user_id"),
}


class GameBackupError(RuntimeError):
    """Raised when a game backup cannot be safely created or restored."""


def assert_table_classification() -> None:
    known = GAME_OWNED_TABLES | SHARED_TABLES | EXCLUDED_TABLES
    model_tables = set(Base.metadata.tables)
    missing = model_tables - known
    stale = known - model_tables
    if missing or stale:
        raise GameBackupError(
            f"Backup table classification mismatch: missing={sorted(missing)}, stale={sorted(stale)}"
        )


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    raise GameBackupError(f"Unsupported backup value type: {type(value).__name__}")


def _db_value(column, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(column.type, PGUUID):
        return uuid.UUID(value)
    if isinstance(column.type, DateTime):
        return datetime.fromisoformat(value)
    if isinstance(column.type, Numeric):
        return Decimal(value)
    if isinstance(column.type, Enum):
        return value
    return value


def _table_rows(db: Session, table_name: str, criterion) -> list[dict[str, Any]]:
    table = Base.metadata.tables[table_name]
    rows = db.execute(select(table).where(criterion)).mappings().all()
    primary_keys = [column.name for column in table.primary_key.columns]
    serialized = [{key: _json_value(value) for key, value in row.items()} for row in rows]
    return sorted(serialized, key=lambda row: tuple(str(row.get(key, "")) for key in primary_keys))


def _collect_rows(db: Session, game_id: uuid.UUID) -> dict[str, list[dict[str, Any]]]:
    tables = Base.metadata.tables
    game = db.get(models.Game, game_id)
    if game is None:
        raise GameBackupError("Game not found")

    club_ids = list(db.scalars(select(models.Club.id).where(models.Club.game_id == game_id)))
    season_ids = list(db.scalars(select(models.Season.id).where(models.Season.game_id == game_id)))
    turn_ids = (
        list(db.scalars(select(models.Turn.id).where(models.Turn.season_id.in_(season_ids))))
        if season_ids
        else []
    )
    fixture_ids = (
        list(db.scalars(select(models.Fixture.id).where(models.Fixture.season_id.in_(season_ids))))
        if season_ids
        else []
    )
    room_ids = list(db.scalars(select(models.GameRoom.id).where(models.GameRoom.game_id == game_id)))

    rows: dict[str, list[dict[str, Any]]] = {}
    rows["games"] = _table_rows(db, "games", tables["games"].c.id == game_id)
    rows["game_completions"] = _table_rows(
        db, "game_completions", tables["game_completions"].c.game_id == game_id
    )
    rows["clubs"] = _table_rows(db, "clubs", tables["clubs"].c.game_id == game_id)
    rows["memberships"] = _table_rows(db, "memberships", tables["memberships"].c.game_id == game_id)
    rows["seasons"] = _table_rows(db, "seasons", tables["seasons"].c.game_id == game_id)

    by_season = {
        "turns": "season_id",
        "fixtures": "season_id",
        "season_final_standings": "season_id",
        "club_financial_snapshots": "season_id",
        "club_sponsor_states": "season_id",
        "club_academies": "season_id",
        "club_reinforcement_plans": "season_id",
        "club_fanbase_states": "season_id",
        "club_sales_allocations": "season_id",
        "club_point_penalties": "season_id",
        "club_bankruptcy_states": "season_id",
        "season_public_disclosures": "season_id",
    }
    for table_name, column_name in by_season.items():
        rows[table_name] = (
            _table_rows(db, table_name, tables[table_name].c[column_name].in_(season_ids))
            if season_ids
            else []
        )

    by_turn = {
        "turn_decisions": "turn_id",
        "turn_acks": "turn_id",
        "web_turn_drafts": "turn_id",
        "club_financial_ledgers": "turn_id",
    }
    for table_name, column_name in by_turn.items():
        rows[table_name] = (
            _table_rows(db, table_name, tables[table_name].c[column_name].in_(turn_ids))
            if turn_ids
            else []
        )

    rows["matches"] = (
        _table_rows(db, "matches", tables["matches"].c.fixture_id.in_(fixture_ids))
        if fixture_ids
        else []
    )
    rows["game_rooms"] = _table_rows(db, "game_rooms", tables["game_rooms"].c.game_id == game_id)
    rows["game_room_members"] = (
        _table_rows(db, "game_room_members", tables["game_room_members"].c.room_id.in_(room_ids))
        if room_ids
        else []
    )

    by_club = {
        "club_financial_profiles": "club_id",
        "club_financial_states": "club_id",
        "club_staffs": "club_id",
    }
    for table_name, column_name in by_club.items():
        rows[table_name] = (
            _table_rows(db, table_name, tables[table_name].c[column_name].in_(club_ids))
            if club_ids
            else []
        )
    rows["game_final_results"] = _table_rows(
        db, "game_final_results", tables["game_final_results"].c.game_id == game_id
    )

    user_ids: set[uuid.UUID] = set()
    for table_name, column_name in USER_REFERENCE_COLUMNS:
        if table_name in {"users", "web_sessions"}:
            continue
        for row in rows.get(table_name, []):
            if row.get(column_name):
                user_ids.add(uuid.UUID(row[column_name]))
    rows["users"] = (
        _table_rows(db, "users", tables["users"].c.id.in_(user_ids)) if user_ids else []
    )

    exclusive_guest_ids: list[uuid.UUID] = []
    for user_row in rows["users"]:
        if user_row.get("email") is not None:
            continue
        user_id = uuid.UUID(user_row["id"])
        other_game_memberships = db.scalar(
            select(models.Membership.id)
            .where(models.Membership.user_id == user_id, models.Membership.game_id != game_id)
            .limit(1)
        )
        other_room_memberships = db.scalar(
            select(models.GameRoomMember.id)
            .join(models.GameRoom, models.GameRoom.id == models.GameRoomMember.room_id)
            .where(models.GameRoomMember.user_id == user_id, models.GameRoom.game_id != game_id)
            .limit(1)
        )
        if other_game_memberships is None and other_room_memberships is None:
            exclusive_guest_ids.append(user_id)
    rows["web_sessions"] = (
        _table_rows(db, "web_sessions", tables["web_sessions"].c.user_id.in_(exclusive_guest_ids))
        if exclusive_guest_ids
        else []
    )
    return {table_name: rows.get(table_name, []) for table_name in RESTORE_ORDER}


def _safe_root(root: Path) -> Path:
    root = root.expanduser().resolve()
    if root.name in {"", "/"}:
        raise GameBackupError("Refusing unsafe backup root")
    for child in ("games", "manifests", "tmp"):
        path = root / child
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(path, 0o700)
    return root


def _alembic_revision(db: Session) -> str:
    if inspect(db.get_bind()).has_table("alembic_version"):
        return db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    database_name = db.execute(text("SELECT current_database()")).scalar_one()
    if database_name.endswith("_test"):
        return "unversioned-test-schema"
    raise GameBackupError("alembic_version is missing from a non-test database")


def create_game_backup(db: Session, game_id: uuid.UUID, backup_root: str | Path, reason: str) -> dict[str, Any]:
    assert_table_classification()
    root = _safe_root(Path(backup_root))
    engine = db.get_bind()
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        with Session(bind=connection, autoflush=False, future=True) as snapshot_db:
            rows = _collect_rows(snapshot_db, game_id)
            alembic_revision = _alembic_revision(snapshot_db)
    now = datetime.now(timezone.utc)
    backup_id = f"{now.strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(4)}"
    game_dir = root / "games" / str(game_id)
    game_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(game_dir, 0o700)
    final_path = game_dir / f"{backup_id}.clubgame.zip"

    manifest = {
        "format_version": FORMAT_VERSION,
        "backup_id": backup_id,
        "game_id": str(game_id),
        "created_at": now.isoformat(),
        "reason": reason,
        "alembic_revision": alembic_revision,
        "counts": {name: len(table_rows) for name, table_rows in rows.items()},
        "included_tables": RESTORE_ORDER,
        "excluded": ["shared-user web_sessions", "plaintext browser cookies", "database credentials"],
    }

    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=root / "tmp", prefix=f"{backup_id}-", suffix=".partial"
    )
    os.close(file_descriptor)
    temporary_path = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2))
            for table_name in RESTORE_ORDER:
                content = "".join(
                    json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows[table_name]
                )
                archive.writestr(f"data/{table_name}.jsonl", content)
        os.chmod(temporary_path, 0o600)
        verified = verify_game_backup(temporary_path)
        if verified["counts"] != manifest["counts"]:
            raise GameBackupError("Backup row counts changed during verification")
        os.replace(temporary_path, final_path)
        os.chmod(final_path, 0o600)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()

    sha256 = hashlib.sha256(final_path.read_bytes()).hexdigest()
    persisted_sidecar = {
        **manifest,
        "sha256": sha256,
        "size_bytes": final_path.stat().st_size,
        "archive_relative_path": str(final_path.relative_to(root)),
        "verified": True,
    }
    sidecar_path = root / "manifests" / f"{backup_id}.game.json"
    temporary_sidecar = root / "tmp" / f"{backup_id}.game.json.partial"
    temporary_sidecar.write_text(
        json.dumps(persisted_sidecar, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary_sidecar, 0o600)
    os.replace(temporary_sidecar, sidecar_path)
    os.chmod(sidecar_path, 0o600)
    return {**persisted_sidecar, "archive_path": str(final_path)}


def _validate_references(rows: dict[str, list[dict[str, Any]]]) -> None:
    available: dict[tuple[str, str], set[str]] = {}
    for table_name, table_rows in rows.items():
        table = Base.metadata.tables[table_name]
        for column in table.columns:
            available[(table_name, column.name)] = {
                str(row[column.name]) for row in table_rows if row.get(column.name) is not None
            }
    for table_name, table_rows in rows.items():
        table = Base.metadata.tables[table_name]
        for column in table.columns:
            for foreign_key in column.foreign_keys:
                target = (foreign_key.column.table.name, foreign_key.column.name)
                if target not in available:
                    raise GameBackupError(
                        f"Backup reference target is not included: {table_name}.{column.name} -> {target}"
                    )
                for row in table_rows:
                    value = row.get(column.name)
                    if value is not None and str(value) not in available[target]:
                        raise GameBackupError(
                            f"Broken backup reference: {table_name}.{column.name}={value} -> {target}"
                        )


def verify_game_backup(path: str | Path, expected_sha256: str | None = None) -> dict[str, Any]:
    archive_path = Path(path)
    if expected_sha256:
        actual_sha256 = hashlib.sha256(archive_path.read_bytes()).hexdigest()
        if not secrets.compare_digest(actual_sha256, expected_sha256):
            raise GameBackupError("Game backup SHA-256 mismatch")
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            if archive.testzip() is not None:
                raise GameBackupError("Corrupt member in game backup")
            manifest = json.loads(archive.read("manifest.json"))
            if manifest.get("format_version") != FORMAT_VERSION:
                raise GameBackupError("Unsupported game backup format")
            actual_counts: dict[str, int] = {}
            rows: dict[str, list[dict[str, Any]]] = {}
            for table_name in manifest["included_tables"]:
                raw = archive.read(f"data/{table_name}.jsonl").decode("utf-8")
                rows[table_name] = [json.loads(line) for line in raw.splitlines() if line]
                actual_counts[table_name] = len(rows[table_name])
            if actual_counts != manifest["counts"]:
                raise GameBackupError("Game backup row-count mismatch")
            _validate_references(rows)
    except (KeyError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        raise GameBackupError(f"Invalid game backup: {exc}") from exc
    return manifest


def latest_game_backup(backup_root: str | Path, game_id: uuid.UUID) -> dict[str, Any] | None:
    root = Path(backup_root).expanduser().resolve()
    candidates: list[dict[str, Any]] = []
    for path in (root / "manifests").glob("*.game.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("game_id") == str(game_id) and data.get("verified") is True:
            candidates.append(data)
    return max(candidates, key=lambda item: item["created_at"], default=None)


def _archive_rows(path: Path) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    manifest = verify_game_backup(path)
    rows: dict[str, list[dict[str, Any]]] = {}
    with zipfile.ZipFile(path, "r") as archive:
        for table_name in manifest["included_tables"]:
            raw = archive.read(f"data/{table_name}.jsonl").decode("utf-8")
            rows[table_name] = [json.loads(line) for line in raw.splitlines() if line]
    return manifest, rows


def _new_invite_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(8))


def restore_game_backup(db: Session, path: str | Path) -> dict[str, Any]:
    """Restore one verified game into the connected DB, initially archived.

    The caller owns the transaction and must commit only after any additional
    validation required by the operator workflow.
    """

    assert_table_classification()
    archive_path = Path(path)
    manifest, rows = _archive_rows(archive_path)
    game_id = uuid.UUID(manifest["game_id"])
    if db.get(models.Game, game_id) is not None:
        raise GameBackupError(f"Game {game_id} already exists")

    tables = Base.metadata.tables
    user_map: dict[str, uuid.UUID] = {}
    for serialized in rows["users"]:
        source_id = serialized["id"]
        existing = None
        if serialized.get("email"):
            existing = db.execute(
                select(tables["users"]).where(tables["users"].c.email == serialized["email"])
            ).mappings().first()
        if existing is None:
            existing = db.execute(
                select(tables["users"]).where(tables["users"].c.id == uuid.UUID(source_id))
            ).mappings().first()
        if existing is not None:
            user_map[source_id] = existing["id"]
            continue
        values = {
            column.name: _db_value(column, serialized[column.name])
            for column in tables["users"].columns
            if column.name in serialized
        }
        db.execute(tables["users"].insert().values(**values))
        user_map[source_id] = values["id"]

    restored_invite_code: str | None = None
    for table_name in RESTORE_ORDER:
        if table_name == "users":
            continue
        table = tables[table_name]
        for serialized in rows[table_name]:
            values = {
                column.name: _db_value(column, serialized[column.name])
                for column in table.columns
                if column.name in serialized
            }
            for reference_table, column_name in USER_REFERENCE_COLUMNS:
                if reference_table == table_name and values.get(column_name) is not None:
                    values[column_name] = user_map[str(values[column_name])]
            if table_name == "games":
                values["status"] = models.GameStatus.archived.value
            if table_name == "game_rooms":
                values["status"] = "archived"
                invite_exists = db.execute(
                    select(tables["game_rooms"].c.id).where(
                        tables["game_rooms"].c.invite_code == values["invite_code"]
                    )
                ).first()
                if invite_exists:
                    code = _new_invite_code()
                    while db.execute(
                        select(tables["game_rooms"].c.id).where(tables["game_rooms"].c.invite_code == code)
                    ).first():
                        code = _new_invite_code()
                    values["invite_code"] = code
                restored_invite_code = values["invite_code"]
            if table_name == "web_sessions":
                token_exists = db.execute(
                    select(tables["web_sessions"].c.id).where(
                        tables["web_sessions"].c.token_hash == values["token_hash"]
                    )
                ).first()
                if token_exists:
                    continue
            db.execute(table.insert().values(**values))

    return {
        "game_id": str(game_id),
        "backup_id": manifest["backup_id"],
        "room_invite_code": restored_invite_code,
        "status": "archived",
        "counts": manifest["counts"],
    }
