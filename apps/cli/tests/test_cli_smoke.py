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
        if path == "/api/turns/seasons/s1/current":
            return {"month_index": 1, "month_name": "Aug"}
        if path == "/api/seasons/s1/bankrupt-clubs":
            return []
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
            "opponent_name": "Club X",
            "home": True,
            "status": "scheduled",
            "home_goals": None,
            "away_goals": None,
            "weather": "Clear",
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


def test_show_finance_smoke(tmp_path, monkeypatch):
    cfg = _write_config(tmp_path)

    state = {"balance": 1000, "last_applied_turn_id": "t1"}
    ledger = [
        {"turn_id": "t1", "month_index": 1, "kind": "sponsor", "amount": 2000, "meta": {}},
        {"turn_id": "t1", "month_index": 1, "kind": "cost", "amount": -1000, "meta": {}},
    ]

    def fake_get(self, path, params=None):  # noqa: ANN001
        if path.endswith("/finance/state"):
            return state
        if path.endswith("/finance/ledger"):
            return ledger
        if path == "/api/seasons/s1":
            return {"season_number": 1}
        raise AssertionError(f"Unexpected path {path}")

    monkeypatch.setattr(ApiClient, "get", fake_get)

    runner = CliRunner()
    result = runner.invoke(cli, ["--config-path", str(cfg), "show", "finance"])

    assert result.exit_code == 0
    assert "Balance" in result.output
    assert "sponsor" in result.output
    assert "cost" in result.output


def test_show_final_standings_by_name(tmp_path, monkeypatch):
    cfg = _write_config(tmp_path)
    cfg.write_text(
        json.dumps(
            {
                "base_url": "http://example.invalid",
                "user_email": "user@example.com",
                "season_id": "s1",
                "club_id": "c1",
                "game_id": "g1",
            }
        ),
        encoding="utf-8",
    )

    clubs = [
        {"id": "c1", "name": "Club Alpha", "short_name": "Alpha"},
        {"id": "c2", "name": "Club Beta", "short_name": "Beta"},
    ]
    standings = [
        {
            "season_id": "s1",
            "season_number": 1,
            "year_label": "2024",
            "finalized_at": "2025-05-31T00:00:00Z",
            "club_id": "c2",
            "club_name": "Club Beta",
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

    def fake_get(self, path, params=None):  # noqa: ANN001
        if path == "/api/games/g1/clubs":
            return clubs
        if path == "/api/clubs/c2/final-standings":
            return standings
        raise AssertionError(f"Unexpected path {path}")

    monkeypatch.setattr(ApiClient, "get", fake_get)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--config-path", str(cfg), "show", "final_standings", "--club-name", "Beta"],
    )

    assert result.exit_code == 0
    assert "Final standings history for Club Beta" in result.output
    assert "2024" in result.output


def test_show_disclosure_financial_summary_table(tmp_path, monkeypatch):
    cfg = _write_config(tmp_path)
    disclosure = {
        "disclosed_data": {
            "clubs": [
                {
                    "club_id": "e04b6e9a-2201-4ac4-8241-64f6dad18a13",
                    "club_name": "FC_TOKYO",
                    "net_income": 189041949,
                    "fiscal_year": "2026",
                    "total_expense": -390931251,
                    "total_revenue": 579973200,
                    "ending_balance": 331618107,
                },
                {
                    "club_id": "bd5b3e4d-66e8-4f69-b96a-daed42c32f0f",
                    "club_name": "FC_NAGOYA",
                    "net_income": -112971163,
                    "fiscal_year": "2026",
                    "total_expense": -520669163,
                    "total_revenue": 407698000,
                    "ending_balance": 213975395,
                },
            ]
        }
    }

    def fake_get(self, path, params=None):  # noqa: ANN001
        if path == "/api/seasons/s1/disclosures/financial_summary":
            return disclosure
        if path == "/api/seasons/s1":
            return {"year_label": "2026", "season_number": 5}
        raise AssertionError(f"Unexpected path {path}")

    monkeypatch.setattr(ApiClient, "get", fake_get)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--config-path", str(cfg), "show", "disclosure", "--type", "financial_summary"],
    )

    assert result.exit_code == 0
    assert "対象シーズン: 2026 (season5)" in result.output
    assert "item" in result.output
    assert "FC_TOKYO" in result.output
    assert "FC_NAGOYA" in result.output
    assert "club_id" not in result.output
