"""Tests for input/commit/view commands with mocked API."""
import json
from pathlib import Path
from typing import Any, Dict, Optional

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


class MockApiClient:
    """Mock API client for testing input commands."""

    def __init__(self):
        self.calls: list[tuple[str, str, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]] = []
        self.responses: Dict[str, Any] = {}

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


def test_input_basic(tmp_path, monkeypatch):
    """Test input command with basic expenses."""
    cfg = _write_config(tmp_path)

    mock_client = MockApiClient()
    mock_client.responses[("GET", "/api/turns/seasons/s1/current")] = {
        "id": "turn-1",
        "month_index": 1,
        "month_name": "Aug",
    }
    mock_client.responses[("PUT", "/api/turns/turn-1/decisions/c1")] = {"status": "ok"}

    def mock_with_client(*args, **kwargs):
        return mock_client

    monkeypatch.setattr("apps.cli.commands.input._with_client", mock_with_client)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--config-path", str(cfg),
            "input",
            "--sales-expense", "1000000",
            "--promo-expense", "500000",
            "--hometown-expense", "300000",
        ],
    )

    assert result.exit_code == 0
    assert "Input submitted successfully" in result.output

    # Verify PUT call
    put_calls = [c for c in mock_client.calls if c[0] == "PUT"]
    assert len(put_calls) == 1
    assert put_calls[0][1] == "/api/turns/turn-1/decisions/c1"
    payload = put_calls[0][2]["payload"]
    assert payload["sales_expense"] == 1000000.0
    assert payload["promo_expense"] == 500000.0
    assert payload["hometown_expense"] == 300000.0


def test_input_no_options_fails(tmp_path, monkeypatch):
    """Test input command fails when no options provided."""
    cfg = _write_config(tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli, ["--config-path", str(cfg), "input"])

    assert result.exit_code != 0
    assert "No input provided" in result.output


def test_input_negative_value_fails(tmp_path, monkeypatch):
    """Test input command fails with negative values."""
    cfg = _write_config(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--config-path", str(cfg), "input", "--sales-expense", "-1000"],
    )

    assert result.exit_code != 0
    assert "non-negative" in result.output


def test_commit_with_confirmation(tmp_path, monkeypatch):
    """Test commit command shows confirmation."""
    cfg = _write_config(tmp_path)

    mock_client = MockApiClient()
    mock_client.responses[("GET", "/api/turns/seasons/s1/current")] = {
        "id": "turn-1",
        "month_index": 1,
        "month_name": "Aug",
    }
    mock_client.responses[("GET", "/api/turns/seasons/s1/decisions/c1/current")] = {
        "month_index": 1,
        "month_name": "Aug",
        "decision_state": "draft",
        "payload": {"sales_expense": 1000000},
    }
    mock_client.responses[("POST", "/api/turns/turn-1/decisions/c1/commit")] = {"status": "committed"}

    def mock_with_client(*args, **kwargs):
        return mock_client

    monkeypatch.setattr("apps.cli.commands.commit._with_client", mock_with_client)

    runner = CliRunner()
    # Use -y to skip confirmation
    result = runner.invoke(
        cli,
        ["--config-path", str(cfg), "commit", "-y"],
    )

    assert result.exit_code == 0
    assert "committed successfully" in result.output

    # Verify POST call
    post_calls = [c for c in mock_client.calls if c[0] == "POST"]
    assert len(post_calls) == 1
    assert "/commit" in post_calls[0][1]


def test_commit_abort(tmp_path, monkeypatch):
    """Test commit command can be aborted."""
    cfg = _write_config(tmp_path)

    mock_client = MockApiClient()
    mock_client.responses[("GET", "/api/turns/seasons/s1/current")] = {
        "id": "turn-1",
        "month_index": 1,
        "month_name": "Aug",
    }
    mock_client.responses[("GET", "/api/turns/seasons/s1/decisions/c1/current")] = {
        "month_index": 1,
        "month_name": "Aug",
        "decision_state": "draft",
        "payload": {},
    }

    def mock_with_client(*args, **kwargs):
        return mock_client

    monkeypatch.setattr("apps.cli.commands.commit._with_client", mock_with_client)

    runner = CliRunner()
    # Input 'n' to abort
    result = runner.invoke(
        cli,
        ["--config-path", str(cfg), "commit"],
        input="n\n",
    )

    assert result.exit_code == 0
    assert "Aborted" in result.output

    # Verify no POST call
    post_calls = [c for c in mock_client.calls if c[0] == "POST"]
    assert len(post_calls) == 0


def test_view_command(tmp_path, monkeypatch):
    """Test view command displays current input."""
    cfg = _write_config(tmp_path)

    mock_client = MockApiClient()
    mock_client.responses[("GET", "/api/turns/seasons/s1/decisions/c1/current")] = {
        "month_index": 1,
        "month_name": "Aug",
        "decision_state": "draft",
        "committed_at": None,
        "payload": {"sales_expense": 1000000},
    }

    def mock_with_client(*args, **kwargs):
        return mock_client

    monkeypatch.setattr("apps.cli.commands.view._with_client", mock_with_client)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--config-path", str(cfg), "view"],
    )

    assert result.exit_code == 0
    assert "Aug" in result.output
    assert "sales_expense" in result.output


def test_rho_new_validation(tmp_path, monkeypatch):
    """Test rho-new must be between 0.0 and 1.0."""
    cfg = _write_config(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--config-path", str(cfg), "input", "--rho-new", "1.5"],
    )

    assert result.exit_code != 0
    assert "between 0.0 and 1.0" in result.output
