"""Configuration loader for the CLI."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .errors import ConfigError

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None  # Optional dependency; JSON works without it.


DEFAULT_CONFIG_PATH = Path.home() / ".club-game" / "config"


@dataclass
class CliConfig:
    base_url: str
    user_email: str
    game_id: Optional[str] = None
    season_id: Optional[str] = None
    club_id: Optional[str] = None

    @classmethod
    def from_mapping(cls, data: Dict[str, Any]) -> "CliConfig":
        base_url = data.get("base_url")
        user_email = data.get("user_email")
        if not base_url:
            raise ConfigError("Missing `base_url` in config")
        if not user_email:
            raise ConfigError("Missing `user_email` in config")
        return cls(
            base_url=str(base_url),
            user_email=str(user_email),
            game_id=data.get("game_id"),
            season_id=data.get("season_id"),
            club_id=data.get("club_id"),
        )


def load_config(path: Optional[Path] = None) -> CliConfig:
    cfg_path = path or DEFAULT_CONFIG_PATH
    cfg_path = cfg_path.expanduser()
    if not cfg_path.exists():
        raise ConfigError(
            f"Config not found at {cfg_path}. Create it with keys: base_url, user_email"
        )

    try:
        raw = cfg_path.read_text(encoding="utf-8")
    except Exception as exc:  # pragma: no cover
        raise ConfigError(f"Failed to read config file: {exc}") from exc

    data: Dict[str, Any]

    # Try JSON first for minimal dependencies.
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        if yaml is None:
            raise ConfigError(
                "Config is not valid JSON and PyYAML is not installed; install pyyaml or use JSON"
            )
        try:
            loaded = yaml.safe_load(raw)
            if not isinstance(loaded, dict):
                raise ConfigError("Config must be a mapping")
            data = loaded
        except Exception as exc:
            raise ConfigError(f"Failed to parse config as YAML: {exc}") from exc
    except Exception as exc:  # pragma: no cover
        raise ConfigError(f"Failed to parse config: {exc}") from exc

    return CliConfig.from_mapping(data)

