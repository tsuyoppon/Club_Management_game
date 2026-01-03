"""`view` command for showing current input (alias for show current_input)."""
from __future__ import annotations

from typing import Optional

import click

from ..api_client import ApiClient
from ..auth import build_headers
from ..config import CliConfig
from ..errors import CliError, ValidationError
from ..output import print_json, print_table
from ..draft import load_draft


def _resolve_required(option: Optional[str], fallback: Optional[str], label: str) -> str:
    value = option or fallback
    if not value:
        raise ValidationError(f"{label} is required; provide a flag or set it in config")
    return value


def _with_client(config: CliConfig, timeout: float, verbose: bool) -> ApiClient:
    headers = build_headers(config)
    return ApiClient(config.base_url, headers=headers, timeout=timeout, verbose=verbose)


def _format_season_turn_label(turn: Optional[dict]) -> str:
    if not isinstance(turn, dict):
        return "-"
    season_number = turn.get("season_number")
    month_name = turn.get("month_name") or "-"
    month_index = turn.get("month_index")
    turn_label = month_index if month_index is not None else "?"
    if season_number is None:
        return f"{month_name}({turn_label})"
    return f"season{season_number}-{month_name}({turn_label})"


@click.command("view")
@click.option("--season-id", help="Season UUID (defaults to config)")
@click.option("--club-id", help="Club UUID (defaults to config)")
@click.option("--json-output", is_flag=True, help="Print raw JSON response")
@click.pass_context
def view_cmd(
    ctx: click.Context,
    season_id: Optional[str],
    club_id: Optional[str],
    json_output: bool,
) -> None:
    """View current turn input (same as `show current_input`)."""
    config: CliConfig = ctx.obj["config"]
    timeout: float = ctx.obj["timeout"]
    verbose: bool = ctx.obj["verbose"]
    config_dir = ctx.obj["config_dir"]

    season_id = _resolve_required(season_id, config.season_id, "season_id")
    club_id = _resolve_required(club_id, config.club_id, "club_id")

    draft = load_draft(config_dir, season_id, club_id)

    with _with_client(config, timeout, verbose) as client:
        data = client.get(f"/api/turns/seasons/{season_id}/decisions/{club_id}/current")

    if data is None:
        click.echo("No current input found (maybe all turns acked?)")
        return

    if json_output:
        print_json({"api": data, "draft": draft.payload if draft else None})
        return

    payload = data.get("payload") if isinstance(data, dict) else None
    summary = {
        "season_turn": _format_season_turn_label(data),
        "month_index": data.get("month_index"),
        "month_name": data.get("month_name"),
        "decision_state": data.get("decision_state"),
        "committed_at": data.get("committed_at"),
        "payload_source": "draft+api" if draft else "api",
    }
    click.echo("Turn:")
    print_table([summary], ["season_turn", "month_index", "month_name", "decision_state", "committed_at", "payload_source"])
    if payload:
        click.echo("Payload (server):")
        print_json(payload)
    else:
        click.echo("Payload (server): (empty)")

    if draft:
        click.echo("Draft overrides (not committed):")
        print_json(draft.payload)


def dispatch_errors(func):
    """Decorator to surface CliError as ClickException."""
    from functools import wraps

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except CliError as exc:
            raise click.ClickException(str(exc)) from exc

    return wrapper


view_cmd.callback = dispatch_errors(view_cmd.callback)
