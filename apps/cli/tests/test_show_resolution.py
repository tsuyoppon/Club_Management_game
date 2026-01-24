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
            }
        ),
        encoding="utf-8",
    )
    return cfg


class MockApiClient:
    """Mock API client capturing params for verification."""

    def __init__(self):
        self.calls: list[tuple[str, str, Optional[Dict[str, Any]]]] = []
        self.responses: Dict[tuple[str, str], Any] = {}

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        self.calls.append(("GET", path, params))
        return self.responses.get(("GET", path), {})

    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def test_show_match_resolves_season_and_club_identifiers(tmp_path, monkeypatch):
    cfg = _write_config(tmp_path)
    mock_client = MockApiClient()
    mock_client.responses[("GET", "/api/seasons/games/g1")] = [
        {"id": "s1", "season_number": 1, "year_label": "2024"},
        {"id": "s2", "season_number": 2, "year_label": "2025"},
    ]
    mock_client.responses[("GET", "/api/games/g1/clubs")] = [
        {"id": "c1", "name": "Club Alpha", "short_name": "Alpha"},
        {"id": "c2", "name": "Club Beta", "short_name": "Beta"},
    ]
    mock_client.responses[("GET", "/api/seasons/s2/clubs/c2/schedule")] = []

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
            "match",
            "--season-id",
            "2025",
            "--club-id",
            "Club Beta",
            "--month-index",
            "1",
        ],
    )

    assert result.exit_code == 0
    assert ("GET", "/api/seasons/games/g1", None) in mock_client.calls
    assert ("GET", "/api/games/g1/clubs", None) in mock_client.calls
    assert ("GET", "/api/seasons/s2/clubs/c2/schedule", {"month_index": 1}) in mock_client.calls


def test_show_table_resolves_season_number(tmp_path, monkeypatch):
    cfg = _write_config(tmp_path)
    mock_client = MockApiClient()
    mock_client.responses[("GET", "/api/seasons/games/g1")] = [
        {"id": "s1", "season_number": 1, "year_label": "2024"},
        {"id": "s2", "season_number": 2, "year_label": "2025"},
    ]
    mock_client.responses[("GET", "/api/turns/seasons/s2/current")] = {"month_index": 1, "month_name": "Aug"}
    mock_client.responses[("GET", "/api/seasons/s2/bankrupt-clubs")] = []
    mock_client.responses[("GET", "/api/seasons/s2/standings")] = [
        {
            "rank": 1,
            "club_name": "Alpha",
            "played": 1,
            "won": 1,
            "drawn": 0,
            "lost": 0,
            "gf": 2,
            "ga": 0,
            "gd": 2,
            "points": 3,
        }
    ]

    def mock_with_client(*args, **kwargs):
        return mock_client

    monkeypatch.setattr("apps.cli.commands.show._with_client", mock_with_client)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--config-path", str(cfg), "show", "table", "--season-id", "2"],
    )

    assert result.exit_code == 0
    assert "Alpha" in result.output
    assert ("GET", "/api/seasons/games/g1", None) in mock_client.calls
    assert ("GET", "/api/seasons/s2/standings", None) in mock_client.calls


def test_show_final_standings_prefers_club_id_over_name(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    cfg.write_text(
        json.dumps(
            {
                "base_url": "http://example.invalid",
                "user_email": "user@example.com",
                "club_id": "c1",
            }
        ),
        encoding="utf-8",
    )
    mock_client = MockApiClient()
    mock_client.responses[("GET", "/api/clubs/11111111-1111-1111-1111-111111111111/final-standings")] = [
        {
            "season_id": "s1",
            "season_number": 1,
            "year_label": "2024",
            "finalized_at": "2025-05-31T00:00:00Z",
            "club_id": "11111111-1111-1111-1111-111111111111",
            "club_name": "Club Gamma",
            "rank": 1,
            "points": 24,
            "played": 10,
            "won": 7,
            "drawn": 3,
            "lost": 0,
            "gf": 18,
            "ga": 6,
            "gd": 12,
        }
    ]

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
            "final_standings",
            "--club-id",
            "11111111-1111-1111-1111-111111111111",
            "--club-name",
            "Club Beta",
        ],
    )

    assert result.exit_code == 0
    assert "Club Gamma" in result.output
    assert ("GET", "/api/clubs/11111111-1111-1111-1111-111111111111/final-standings", None) in mock_client.calls
    assert not any(call[1] == "/api/games/g1/clubs" for call in mock_client.calls)
