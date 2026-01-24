"""Tests for help command and fan_indicator options."""
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
                "user_email": "user@example.com",
                "game_id": "g1",
                "season_id": "s1",
                "club_id": "c1",
            }
        ),
        encoding="utf-8",
    )
    return cfg


class MockApiClient:
    """Mock API client capturing params for verification."""

    def __init__(self):
        self.calls: list[tuple[str, str, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]] = []
        self.responses: Dict[tuple[str, str], Any] = {}

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        self.calls.append(("GET", path, None, params))
        return self.responses.get(("GET", path), {})

    def post(self, path: str, json_body: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None) -> Any:
        self.calls.append(("POST", path, json_body, params))
        return self.responses.get(("POST", path), {})

    def put(self, path: str, json_body: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None) -> Any:
        self.calls.append(("PUT", path, json_body, params))
        return self.responses.get(("PUT", path), {})

    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def test_help_top_level(tmp_path):
    cfg = _write_config(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["--config-path", str(cfg), "help"])
    assert result.exit_code == 0
    assert "Usage" in result.output
    assert "show" in result.output


def test_help_subcommand(tmp_path):
    cfg = _write_config(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["--config-path", str(cfg), "help", "show"])
    assert result.exit_code == 0
    assert "fan_indicator" in result.output


def test_help_unknown_command(tmp_path):
    cfg = _write_config(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["--config-path", str(cfg), "help", "unknown"])
    assert result.exit_code != 0
    assert "Unknown command" in result.output


def test_show_fan_indicator_with_filters(tmp_path, monkeypatch):
    cfg = _write_config(tmp_path)

    mock_client = MockApiClient()
    mock_client.responses[("GET", "/api/games/g1/seasons")] = [{"id": "s1", "season_number": 1, "year_label": "2024"}]
    mock_client.responses[("GET", "/api/games/g1/clubs")] = [
        {"id": "c1", "name": "Alpha", "short_name": "Alpha"},
        {"id": "c2", "name": "Club Two", "short_name": "c2"},
    ]
    mock_client.responses[("GET", "/api/seasons/s1/standings")] = [
        {"club_id": "c2", "club_name": "Club Two"}
    ]
    mock_client.responses[("GET", "/api/clubs/c2/fan_indicator")] = {"club_id": "c2", "followers": 12345}

    def mock_with_client(*args, **kwargs):
        return mock_client

    monkeypatch.setattr("apps.cli.commands.show._with_client", mock_with_client)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--config-path",
            str(cfg),
            "show",
            "fan_indicator",
            "--club",
            "c2",
            "--from",
            "2025-08",
            "--to",
            "2025-10",
        ],
    )

    assert result.exit_code == 0
    assert "followers" in result.output
    # Validate params were forwarded
    method, path, _, params = mock_client.calls[-1]
    assert method == "GET" and path == "/api/clubs/c2/fan_indicator"
    assert params is not None and "from_month" in params and "to_month" in params


def test_show_fan_indicator_json_output(tmp_path, monkeypatch):
    cfg = _write_config(tmp_path)

    mock_client = MockApiClient()
    mock_client.responses[("GET", "/api/games/g1/seasons")] = [{"id": "s1", "season_number": 1, "year_label": "2024"}]
    mock_client.responses[("GET", "/api/games/g1/clubs")] = [
        {"id": "c1", "name": "Alpha", "short_name": "Alpha"},
    ]
    mock_client.responses[("GET", "/api/seasons/s1/standings")] = [
        {"club_id": "c1", "club_name": "Alpha"}
    ]
    mock_client.responses[("GET", "/api/clubs/c1/fan_indicator")] = {"club_id": "c1", "followers": 999}

    def mock_with_client(*args, **kwargs):
        return mock_client

    monkeypatch.setattr("apps.cli.commands.show._with_client", mock_with_client)

    runner = CliRunner()
    result = runner.invoke(cli, ["--config-path", str(cfg), "show", "fan_indicator", "--json-output"])

    assert result.exit_code == 0
    assert "params" in result.output
    assert "followers" in result.output
