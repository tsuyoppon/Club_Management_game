"""Tests for staff commands with mocked API."""
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
                "season_id": "s1",
                "club_id": "c1",
            }
        ),
        encoding="utf-8",
    )
    return cfg


class MockApiClient:
    """Mock API client for staff command tests."""

    def __init__(self):
        self.calls: list[tuple[str, str, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]] = []
        self.responses: Dict[str, Any] = {}

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


def test_staff_plan_delta_uses_current_count(tmp_path, monkeypatch):
    cfg = _write_config(tmp_path)

    mock_client = MockApiClient()
    mock_client.responses[("GET", "/api/turns/seasons/s1/current")] = {"id": "turn-1"}
    mock_client.responses[("GET", "/api/clubs/c1/management/staff")] = [
        {"role": "sales", "count": 3},
    ]
    mock_client.responses[("POST", "/api/clubs/c1/management/staff/plan")] = {"status": "ok"}

    def mock_with_client(*args, **kwargs):
        return mock_client

    monkeypatch.setattr("apps.cli.commands.staff._with_client", mock_with_client)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--config-path", str(cfg),
            "staff",
            "plan",
            "--role",
            "sales",
            "--count",
            "+2",
        ],
    )

    assert result.exit_code == 0
    post_calls = [c for c in mock_client.calls if c[0] == "POST"]
    assert post_calls[0][2]["count"] == 5


def test_staff_plan_absolute_count(tmp_path, monkeypatch):
    cfg = _write_config(tmp_path)

    mock_client = MockApiClient()
    mock_client.responses[("GET", "/api/turns/seasons/s1/current")] = {"id": "turn-1"}
    mock_client.responses[("POST", "/api/clubs/c1/management/staff/plan")] = {"status": "ok"}

    def mock_with_client(*args, **kwargs):
        return mock_client

    monkeypatch.setattr("apps.cli.commands.staff._with_client", mock_with_client)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--config-path", str(cfg),
            "staff",
            "plan",
            "--role",
            "sales",
            "--count",
            "4",
        ],
    )

    assert result.exit_code == 0
    post_calls = [c for c in mock_client.calls if c[0] == "POST"]
    assert post_calls[0][2]["count"] == 4
