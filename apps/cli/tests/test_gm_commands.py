"""Tests for GM CLI commands."""
import json
from pathlib import Path
from typing import Any, Dict, Optional

from click.testing import CliRunner

from apps.cli.main import cli


def _write_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "config.json"
    cfg.write_text(
        json.dumps(
            {
                "base_url": "http://example.invalid",
                "user_email": "gm@example.com",
                "season_id": "s1",
            }
        ),
        encoding="utf-8",
    )
    return cfg


class MockApiClient:
    """Mock API client for GM command tests."""

    def __init__(self):
        self.calls: list[tuple[str, str, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]] = []
        self.responses: Dict[tuple[str, str], Any] = {}

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        self.calls.append(("GET", path, None, params))
        return self.responses.get(("GET", path), {})

    def post(self, path: str, json_body: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None) -> Any:
        self.calls.append(("POST", path, json_body, params))
        return self.responses.get(("POST", path), {})

    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def test_gm_lock_uses_current_turn(tmp_path, monkeypatch):
    cfg = _write_config(tmp_path)

    mock_client = MockApiClient()
    mock_client.responses[("GET", "/api/turns/seasons/s1/current")] = {"id": "turn-1"}
    mock_client.responses[("POST", "/api/turns/turn-1/lock")] = {"state": "locked"}

    def mock_with_client(*args, **kwargs):
        return mock_client

    monkeypatch.setattr("apps.cli.commands.gm._with_client", mock_with_client)

    runner = CliRunner()
    result = runner.invoke(cli, ["--config-path", str(cfg), "gm", "lock"])

    assert result.exit_code == 0
    assert "Turn locked" in result.output
    assert ("GET", "/api/turns/seasons/s1/current", None, None) in mock_client.calls
    assert ("POST", "/api/turns/turn-1/lock", None, None) in mock_client.calls


def test_gm_resolve_with_turn_id(tmp_path, monkeypatch):
    cfg = _write_config(tmp_path)

    mock_client = MockApiClient()
    mock_client.responses[("POST", "/api/turns/turn-9/resolve")] = {"state": "resolved"}

    def mock_with_client(*args, **kwargs):
        return mock_client

    monkeypatch.setattr("apps.cli.commands.gm._with_client", mock_with_client)

    runner = CliRunner()
    result = runner.invoke(cli, ["--config-path", str(cfg), "gm", "resolve", "--turn-id", "turn-9"])

    assert result.exit_code == 0
    assert "Turn resolved" in result.output
    assert ("POST", "/api/turns/turn-9/resolve", None, None) in mock_client.calls
