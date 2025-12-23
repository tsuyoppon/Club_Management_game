"""Game master (GM) command group implementations."""
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


def _resolve_turn_id(client: ApiClient, season_id: Optional[str], config_season_id: Optional[str], turn_id: Optional[str]) -> str:
    if turn_id:
        return turn_id
    resolved_season_id = _resolve_required(season_id, config_season_id, "season_id")
    turn_data = client.get(f"/api/turns/seasons/{resolved_season_id}/current")
    turn_id = turn_data.get("id") if isinstance(turn_data, dict) else None
    if not turn_id:
        raise CliError("No active turn found for this season")
    return turn_id


@click.group("gm")
@click.pass_context
def gm(ctx: click.Context) -> None:
    """Commands for game masters to manage turns."""
    pass


@gm.command("open")
@click.option("--turn-id", help="Turn UUID (optional; defaults to current season turn)")
@click.option("--season-id", help="Season UUID (defaults to config when turn-id omitted)")
@click.option("--json-output", is_flag=True, help="Print raw JSON response")
@click.pass_context
def open_turn(ctx: click.Context, turn_id: Optional[str], season_id: Optional[str], json_output: bool) -> None:
    """Open a turn for decision collection."""
    config: CliConfig = ctx.obj["config"]
    timeout: float = ctx.obj["timeout"]
    verbose: bool = ctx.obj["verbose"]

    with _with_client(config, timeout, verbose) as client:
        resolved_turn_id = _resolve_turn_id(client, season_id, config.season_id, turn_id)
        result = client.post(f"/api/turns/{resolved_turn_id}/open")

    if json_output:
        print_json(result)
    else:
        click.echo(f"Turn opened (id={resolved_turn_id}).")


@gm.command("lock")
@click.option("--turn-id", help="Turn UUID (optional; defaults to current season turn)")
@click.option("--season-id", help="Season UUID (defaults to config when turn-id omitted)")
@click.option("--json-output", is_flag=True, help="Print raw JSON response")
@click.pass_context
def lock_turn(ctx: click.Context, turn_id: Optional[str], season_id: Optional[str], json_output: bool) -> None:
    """Lock a turn after all decisions are committed."""
    config: CliConfig = ctx.obj["config"]
    timeout: float = ctx.obj["timeout"]
    verbose: bool = ctx.obj["verbose"]

    with _with_client(config, timeout, verbose) as client:
        resolved_turn_id = _resolve_turn_id(client, season_id, config.season_id, turn_id)
        result = client.post(f"/api/turns/{resolved_turn_id}/lock")

    if json_output:
        print_json(result)
    else:
        click.echo(f"Turn locked (id={resolved_turn_id}).")


@gm.command("resolve")
@click.option("--turn-id", help="Turn UUID (optional; defaults to current season turn)")
@click.option("--season-id", help="Season UUID (defaults to config when turn-id omitted)")
@click.option("--json-output", is_flag=True, help="Print raw JSON response")
@click.pass_context
def resolve_turn(ctx: click.Context, turn_id: Optional[str], season_id: Optional[str], json_output: bool) -> None:
    """Resolve a locked turn (apply simulations)."""
    config: CliConfig = ctx.obj["config"]
    timeout: float = ctx.obj["timeout"]
    verbose: bool = ctx.obj["verbose"]

    with _with_client(config, timeout, verbose) as client:
        resolved_turn_id = _resolve_turn_id(client, season_id, config.season_id, turn_id)
        result = client.post(f"/api/turns/{resolved_turn_id}/resolve")

    if json_output:
        print_json(result)
    else:
        click.echo(f"Turn resolved (id={resolved_turn_id}).")


@gm.command("advance")
@click.option("--turn-id", help="Turn UUID (optional; defaults to current season turn)")
@click.option("--season-id", help="Season UUID (defaults to config when turn-id omitted)")
@click.option("--json-output", is_flag=True, help="Print raw JSON response")
@click.pass_context
def advance_turn(ctx: click.Context, turn_id: Optional[str], season_id: Optional[str], json_output: bool) -> None:
    """Advance the season to the next turn (after all acks)."""
    config: CliConfig = ctx.obj["config"]
    timeout: float = ctx.obj["timeout"]
    verbose: bool = ctx.obj["verbose"]

    with _with_client(config, timeout, verbose) as client:
        resolved_turn_id = _resolve_turn_id(client, season_id, config.season_id, turn_id)
        result = client.post(f"/api/turns/{resolved_turn_id}/advance")

    if json_output:
        print_json(result)
    else:
        click.echo(f"Turn advanced (id={resolved_turn_id}).")
