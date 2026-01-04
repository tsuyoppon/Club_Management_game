"""Config command implementations."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import click

from ..api_client import ApiClient
from ..auth import build_headers
from ..config import CliConfig, save_config
from ..errors import CliError, ValidationError


def _resolve_required(option: Optional[str], fallback: Optional[str], label: str) -> str:
    value = option or fallback
    if not value:
        raise ValidationError(f"{label} is required; provide a flag or set it in config")
    return value


def _with_client(config: CliConfig, timeout: float, verbose: bool) -> ApiClient:
    headers = build_headers(config)
    return ApiClient(config.base_url, headers=headers, timeout=timeout, verbose=verbose)


@click.group("config")
@click.pass_context
def config_group(ctx: click.Context) -> None:
    """Config utilities."""
    pass


@config_group.command("set-season")
@click.option("--game-id", help="Game UUID (defaults to config)")
@click.option("--latest", is_flag=True, help="Resolve to latest running season for the game")
@click.pass_context
def set_season(ctx: click.Context, game_id: Optional[str], latest: bool) -> None:
    """Set season_id in the config.

    Use --latest to fetch the latest running season (fallback: most recent season) for the game.
    If game_id is not provided, it will be inferred from the current season_id.
    """
    config: CliConfig = ctx.obj["config"]
    timeout: float = ctx.obj["timeout"]
    verbose: bool = ctx.obj["verbose"]
    config_path: Path = ctx.obj["config_path"]

    # Try to resolve game_id from option, config, or current season
    resolved_game_id = game_id or config.game_id
    
    if not resolved_game_id and config.season_id:
        # Attempt to infer game_id from current season_id
        try:
            with _with_client(config, timeout, verbose) as client:
                season_data = client.get(f"/api/seasons/{config.season_id}")
                if isinstance(season_data, dict) and season_data.get("game_id"):
                    resolved_game_id = str(season_data["game_id"])
                    click.echo(f"Inferred game_id from current season: {resolved_game_id}")
        except Exception as e:
            pass  # If inference fails, we'll raise the error below
    
    if not resolved_game_id:
        raise click.ClickException(
            "game_id is required. Provide it via:\n"
            "  1. --game-id flag\n"
            "  2. Set 'game_id' in config file\n"
            "  3. Ensure 'season_id' is set to infer game_id automatically"
        )

    try:
        if latest:
            with _with_client(config, timeout, verbose) as client:
                season = client.get(f"/api/seasons/games/{resolved_game_id}/latest")
            if not isinstance(season, dict) or not season.get("id"):
                raise CliError("Failed to resolve latest season")
            config.season_id = str(season["id"])
            # If game_id was absent in config, set it for persistence
            if not config.game_id:
                config.game_id = resolved_game_id
            save_config(config, config_path)
            click.echo(f"season_id set to latest: {config.season_id}")
        else:
            raise ValidationError("Use --latest or provide season resolution logic")
    except CliError as exc:
        raise click.ClickException(str(exc)) from exc
    except ValidationError as exc:
        raise click.ClickException(str(exc)) from exc
