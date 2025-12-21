import json
from pathlib import Path

from click.testing import CliRunner

from apps.cli.main import cli
from apps.cli.api_client import ApiClient


def _write_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "config.json"
    cfg.write_text(
        json.dumps(
            {
                "base_url": "http://example.invalid",
                "user_email": "user@example.com",
                "season_id": "s1",
                "club_id": "c1",
            }
        ),
        encoding="utf-8",
    )
    return cfg


def test_show_table_smoke(tmp_path, monkeypatch):
    cfg = _write_config(tmp_path)
    standings = [
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

    def fake_get(self, path, params=None):  # noqa: ANN001
        assert path == "/api/seasons/s1/standings"
        return standings

    monkeypatch.setattr(ApiClient, "get", fake_get)

    runner = CliRunner()
    result = runner.invoke(cli, ["--config-path", str(cfg), "show", "table"])

    assert result.exit_code == 0
    assert "Alpha" in result.output


def test_show_match_month_mapping(tmp_path, monkeypatch):
    cfg = _write_config(tmp_path)
    schedule = [
        {
            "month_index": 9,
            "month_name": "Apr",
            "opponent": "club-x",
            "home": True,
            "status": "scheduled",
            "home_goals": None,
            "away_goals": None,
            "total_attendance": None,
        }
    ]

    def fake_get(self, path, params=None):  # noqa: ANN001
        assert path == "/api/seasons/s1/clubs/c1/schedule"
        assert params == {"month_index": 9}
        return schedule

    monkeypatch.setattr(ApiClient, "get", fake_get)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--config-path", str(cfg), "show", "match", "--month", "2026-04"],
    )

    assert result.exit_code == 0
    assert "Apr" in result.output