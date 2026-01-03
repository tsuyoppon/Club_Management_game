"""`ack` command for confirming resolved turns."""
from __future__ import annotations

from typing import Optional

import click

from ..api_client import ApiClient
from ..auth import build_headers
from ..config import CliConfig
from ..errors import CliError, ValidationError
from ..output import print_json


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


@click.command("ack")
@click.option("--turn-id", help="Turn UUID (optional; defaults to current season turn)")
@click.option("--season-id", help="Season UUID (defaults to config when turn-id omitted)")
@click.option("--club-id", help="Club UUID (defaults to config)")
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation prompt")
@click.option("--json-output", is_flag=True, help="Print raw JSON response")
@click.pass_context
def ack_cmd(
    ctx: click.Context,
    turn_id: Optional[str],
    season_id: Optional[str],
    club_id: Optional[str],
    yes: bool,
    json_output: bool,
) -> None:
    """ACK a resolved turn for a club (club owner or GM)."""
    config: CliConfig = ctx.obj["config"]
    timeout: float = ctx.obj["timeout"]
    verbose: bool = ctx.obj["verbose"]

    club_id = _resolve_required(club_id, config.club_id, "club_id")

    with _with_client(config, timeout, verbose) as client:
        if turn_id:
            resolved_turn_id = turn_id
            turn_data = None
        else:
            season_id = _resolve_required(season_id, config.season_id, "season_id")
            turn_data = client.get(f"/api/turns/seasons/{season_id}/current")
            resolved_turn_id = turn_data.get("id") if isinstance(turn_data, dict) else None

        if not resolved_turn_id:
            raise CliError("No active turn found for this season")

        month_name = turn_data.get("month_name") if isinstance(turn_data, dict) else None
        turn_state = turn_data.get("turn_state") if isinstance(turn_data, dict) else None
        season_turn_label = _format_season_turn_label(turn_data)

        if not yes:
            click.echo(f"Turn: {season_turn_label} (state={turn_state or 'unknown'})")
            if not click.confirm("ACK this turn for the club?"):
                click.echo("Aborted.")
                return

        result = client.post(
            f"/api/turns/{resolved_turn_id}/ack",
            json_body={"club_id": club_id, "ack": True},
        )

    if json_output:
        print_json(result)
    else:
        click.echo("Turn ACK sent successfully.")


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


ack_cmd.callback = dispatch_errors(ack_cmd.callback)
