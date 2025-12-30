"""Tests for game command group (membership management)."""
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
                "game_id": "g1",
            }
        ),
        encoding="utf-8",
    )
    return cfg


class MockApiClient:
    def __init__(self):
        self.calls: list[tuple[str, str, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]] = []
        self.responses: Dict[tuple[str, str], Any] = {}

    def post(self, path: str, json_body: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None) -> Any:
        self.calls.append(("POST", path, json_body, params))
        return self.responses.get(("POST", path), {})

    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def test_add_member_owner_success(tmp_path, monkeypatch):
    cfg = _write_config(tmp_path)

    mock_client = MockApiClient()
    mock_client.responses[("POST", "/api/games/g1/memberships")] = {"id": "m1"}

    def mock_with_client(*args, **kwargs):  # noqa: ANN001
        return mock_client

    monkeypatch.setattr("apps.cli.commands.game._with_client", mock_with_client)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--config-path",
            str(cfg),
            "game",
            "add-member",
            "--email",
            "player@example.com",
            "--role",
            "club_owner",
            "--club-id",
            "club-1",
        ],
    )

    assert result.exit_code == 0
    assert "Membership created" in result.output
    assert (
        "POST",
        "/api/games/g1/memberships",
        {
            "email": "player@example.com",
            "display_name": None,
            "role": "club_owner",
            "club_id": "club-1",
        },
        None,
    ) in mock_client.calls


def test_add_member_requires_club_for_owner(tmp_path):
    cfg = _write_config(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--config-path",
            str(cfg),
            "game",
            "add-member",
            "--email",
            "player@example.com",
            "--role",
            "club_owner",
        ],
    )

    assert result.exit_code != 0
    assert "club_id is required" in result.output


def test_add_member_rejects_club_for_gm(tmp_path):
    cfg = _write_config(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--config-path",
            str(cfg),
            "game",
            "add-member",
            "--email",
            "gm2@example.com",
            "--role",
            "gm",
            "--club-id",
            "club-x",
        ],
    )

    assert result.exit_code != 0
    assert "must not be provided when role is gm" in result.output
