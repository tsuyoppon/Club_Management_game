"""Staff management commands (hiring/firing in May)."""
from __future__ import annotations

from typing import Dict, Optional

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


def _resolve_turn_id(client: ApiClient, season_id: str, turn_id: Optional[str]) -> str:
    if turn_id:
        return turn_id
    turn_data = client.get(f"/api/turns/seasons/{season_id}/current")
    resolved = turn_data.get("id") if isinstance(turn_data, Dict) else None
    if not resolved:
        raise CliError("No active turn found for this season")
    return resolved


@click.group("staff")
@click.pass_context
def staff(ctx: click.Context) -> None:
    """Manage staff plan (May only)."""
    pass


@staff.command("plan")
@click.option(
    "--role",
    required=True,
    type=click.Choice(
        [
            "sales",
            "hometown",
            "operations",
            "promotion",
            "administration",
            "topteam",
            "academy",
        ],
        case_sensitive=False,
    ),
    help="Staff role",
)
@click.option("--count", required=True, type=int, help="Target headcount (>=1)")
@click.option("--club-id", help="Club UUID (defaults to config)")
@click.option("--season-id", help="Season UUID (defaults to config)")
@click.option("--turn-id", help="Turn UUID (defaults to current turn)")
@click.option("--json-output", is_flag=True, help="Print raw JSON response")
@click.pass_context
def set_staff_plan(ctx: click.Context, role: str, count: int, club_id: Optional[str], season_id: Optional[str], turn_id: Optional[str], json_output: bool) -> None:
    """Request hiring/firing for next season (allowed in May only)."""
    config: CliConfig = ctx.obj["config"]
    timeout: float = ctx.obj["timeout"]
    verbose: bool = ctx.obj["verbose"]

    season_id = _resolve_required(season_id, config.season_id, "season_id")
    club_id = _resolve_required(club_id, config.club_id, "club_id")

    if count < 1:
        raise ValidationError("count must be >= 1")

    payload = {"role": role.lower(), "count": count}

    with _with_client(config, timeout, verbose) as client:
        resolved_turn_id = _resolve_turn_id(client, season_id, turn_id)
        result = client.post(
            f"/api/clubs/{club_id}/management/staff/plan",
            params={"turn_id": resolved_turn_id},
            json_body=payload,
        )

    if json_output:
        print_json({"request": {"turn_id": resolved_turn_id, **payload}, "response": result})
    else:
        click.echo(f"Staff plan updated: role={role.lower()}, count={count}, turn={resolved_turn_id}")


def dispatch_errors(func):
    from functools import wraps

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except CliError as exc:
            raise click.ClickException(str(exc))

    return wrapper


for command in list(staff.commands.values()):
    if isinstance(command, click.core.Command):
        command.callback = dispatch_errors(command.callback)
