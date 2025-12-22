"""Local draft storage helpers for CLI inputs."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .errors import CliError


@dataclass
class DraftData:
    payload: Dict[str, Any]
    updated_at: str
    base_source: str  # "draft" or "api"


def _draft_path(base_dir: Path, season_id: str, club_id: str) -> Path:
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / f"draft_{season_id}_{club_id}.json"


def load_draft(base_dir: Path, season_id: str, club_id: str) -> Optional[DraftData]:
    path = _draft_path(base_dir, season_id, club_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        payload = data.get("payload")
        if not isinstance(payload, dict):
            return None
        return DraftData(payload=payload, updated_at=str(data.get("updated_at", "")), base_source=str(data.get("base_source", "draft")))
    except Exception as exc:
        raise CliError(f"Failed to read draft at {path}: {exc}") from exc


def save_draft(base_dir: Path, season_id: str, club_id: str, payload: Dict[str, Any], base_source: str) -> Path:
    path = _draft_path(base_dir, season_id, club_id)
    record = {
        "payload": payload,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "base_source": base_source,
    }
    try:
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        raise CliError(f"Failed to write draft at {path}: {exc}") from exc
    return path


def clear_draft(base_dir: Path, season_id: str, club_id: str) -> None:
    path = _draft_path(base_dir, season_id, club_id)
    if path.exists():
        try:
            path.unlink()
        except Exception as exc:
            raise CliError(f"Failed to delete draft at {path}: {exc}") from exc


__all__ = ["DraftData", "load_draft", "save_draft", "clear_draft"]
