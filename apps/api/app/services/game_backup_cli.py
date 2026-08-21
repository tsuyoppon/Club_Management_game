"""Container-side game restore entry point used by backup_manager.py."""

from __future__ import annotations

import argparse
import json
import os
import uuid

from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.config import get_settings
from app.db.session import SessionLocal
from app.services.game_backup import GameBackupError, create_game_backup, restore_game_backup


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["create", "restore"])
    parser.add_argument("--archive")
    parser.add_argument("--game-id")
    parser.add_argument("--reason", default="operator")
    args = parser.parse_args()

    configured_database = make_url(get_settings().database_url).database or ""
    if args.command == "restore" and not configured_database.endswith("_test"):
        if configured_database != "club_game" or os.environ.get("ALLOW_LIVE_GAME_RESTORE") != "club_game":
            raise SystemExit("Refusing non-test game restore without the operator live-restore gate")

    db = SessionLocal()
    try:
        actual_database = db.execute(text("SELECT current_database()")).scalar_one()
        if actual_database != configured_database:
            raise GameBackupError(
                f"Connected database mismatch: configured={configured_database}, actual={actual_database}"
            )
        if args.command == "create":
            if not args.game_id:
                raise GameBackupError("--game-id is required for create")
            result = create_game_backup(
                db,
                uuid.UUID(args.game_id),
                get_settings().game_backup_root,
                reason=args.reason,
            )
            db.rollback()
        else:
            if not args.archive:
                raise GameBackupError("--archive is required for restore")
            result = restore_game_backup(db, args.archive)
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
