"""Game command group implementations."""
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


@click.group("game")
@click.pass_context
def game(ctx: click.Context) -> None:
    """Game-level commands (GM only)."""
    pass


@game.command("add-member")
@click.option("--game-id", help="Game UUID (defaults to config)")
@click.option("--email", required=True, help="Email of the user to add")
@click.option("--display-name", help="Display name for the user")
@click.option(
    "--role",
    required=True,
    type=click.Choice(["gm", "club_owner", "club_viewer"], case_sensitive=False),
    help="Membership role to assign",
)
@click.option("--club-id", help="Club UUID (required for club roles)")
@click.option("--json-output", is_flag=True, help="Print raw JSON response")
@click.pass_context
def add_member(
    ctx: click.Context,
    game_id: Optional[str],
    email: str,
    display_name: Optional[str],
    role: str,
    club_id: Optional[str],
    json_output: bool,
) -> None:
    """Add a membership to a game (GM only)."""
    config: CliConfig = ctx.obj["config"]
    timeout: float = ctx.obj["timeout"]
    verbose: bool = ctx.obj["verbose"]

    resolved_game_id = _resolve_required(game_id, config.game_id, "game_id")
    normalized_role = role.lower()

    if normalized_role == "gm" and club_id:
        raise ValidationError("club_id must not be provided when role is gm")
    if normalized_role != "gm" and not club_id:
        raise ValidationError("club_id is required when role is club_owner or club_viewer")

    payload = {
        "email": email,
        "display_name": display_name,
        "role": normalized_role,
        "club_id": club_id,
    }

    with _with_client(config, timeout, verbose) as client:
        result = client.post(f"/api/games/{resolved_game_id}/memberships", json_body=payload)

    if json_output:
        print_json(result)
    else:
        member_id = result.get("id") if isinstance(result, dict) else None
        suffix = f" (id={member_id})" if member_id else ""
        click.echo(f"Membership created for {email} as {normalized_role}{suffix}.")


def dispatch_errors(func):
    from functools import wraps

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except CliError as exc:
            raise click.ClickException(str(exc)) from exc

    return wrapper


add_member.callback = dispatch_errors(add_member.callback)
