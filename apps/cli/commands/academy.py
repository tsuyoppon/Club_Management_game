"""Academy management commands (May only)."""
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


def _resolve_turn_and_month(client: ApiClient, season_id: str, turn_id: Optional[str]) -> tuple[str, int]:
    turn_data = client.get(f"/api/turns/seasons/{season_id}/current")
    resolved_turn_id = turn_id
    if not resolved_turn_id and isinstance(turn_data, Dict):
        resolved_turn_id = turn_data.get("id")
    if not resolved_turn_id:
        raise CliError("No active turn found for this season")
    month_index = turn_data.get("month_index") if isinstance(turn_data, Dict) else None
    if month_index is None:
        raise CliError("No month_index found for current turn")
    return resolved_turn_id, month_index


@click.group("academy")
@click.pass_context
def academy(ctx: click.Context) -> None:
    """Manage academy decisions (May only)."""
    pass


@academy.command("budget")
@click.option("--annual-budget", required=True, type=int, help="Annual academy budget (>=0)")
@click.option("--club-id", help="Club UUID (defaults to config)")
@click.option("--season-id", help="Season UUID (defaults to config)")
@click.option("--turn-id", help="Turn UUID (defaults to current turn)")
@click.option("--json-output", is_flag=True, help="Print raw JSON response")
@click.pass_context
def set_academy_budget(
    ctx: click.Context,
    annual_budget: int,
    club_id: Optional[str],
    season_id: Optional[str],
    turn_id: Optional[str],
    json_output: bool,
) -> None:
    """Submit academy budget for next season (allowed in May only)."""
    config: CliConfig = ctx.obj["config"]
    timeout: float = ctx.obj["timeout"]
    verbose: bool = ctx.obj["verbose"]

    season_id = _resolve_required(season_id, config.season_id, "season_id")
    club_id = _resolve_required(club_id, config.club_id, "club_id")

    if annual_budget < 0:
        raise ValidationError("annual_budget must be >= 0")

    payload = {"annual_budget": annual_budget}

    with _with_client(config, timeout, verbose) as client:
        resolved_turn_id, month_index = _resolve_turn_and_month(client, season_id, turn_id)
        if month_index != 10:
            raise ValidationError("Academy budget can only be submitted in May (month_index=10)")
        result = client.post(
            f"/api/clubs/{club_id}/management/academy/budget",
            params={"season_id": season_id},
            json_body=payload,
        )

    if json_output:
        print_json({"request": {"season_id": season_id, "turn_id": resolved_turn_id, **payload}, "response": result})
    else:
        click.echo(
            "Academy budget updated: "
            f"annual_budget={annual_budget}, season={season_id}, turn={resolved_turn_id}"
        )


def dispatch_errors(func):
    from functools import wraps

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except CliError as exc:
            raise click.ClickException(str(exc))

    return wrapper


for command in list(academy.commands.values()):
    if isinstance(command, click.core.Command):
        command.callback = dispatch_errors(command.callback)
