"""CLI entrypoint."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import click

from .config import CliConfig, DEFAULT_CONFIG_PATH, load_config
from .errors import ConfigError, CliError
from .commands.show import show
from .commands.input import input_cmd
from .commands.commit import commit_cmd
from .commands.view import view_cmd
from .commands.gm import gm


@click.group()
@click.option("--config-path", type=click.Path(exists=False, dir_okay=False, path_type=Path), help="Path to config file (default: ~/.club-game/config)")
@click.option("--base-url", help="Override API base URL")
@click.option("--user-email", help="Override user email (X-User-Email)")
@click.option("--game-id", help="Default game UUID")
@click.option("--season-id", help="Default season UUID")
@click.option("--club-id", help="Default club UUID")
@click.option("--timeout", default=10.0, show_default=True, help="HTTP timeout (seconds)")
@click.option("--verbose", is_flag=True, help="Show HTTP status for debugging")
@click.pass_context
def cli(ctx: click.Context, config_path: Optional[Path], base_url: Optional[str], user_email: Optional[str], game_id: Optional[str], season_id: Optional[str], club_id: Optional[str], timeout: float, verbose: bool) -> None:
    try:
        resolved_path = (config_path or DEFAULT_CONFIG_PATH).expanduser()
        config = load_config(resolved_path)
    except ConfigError as exc:
        raise click.ClickException(str(exc))

    if base_url:
        config.base_url = base_url
    if user_email:
        config.user_email = user_email
    if game_id:
        config.game_id = game_id
    if season_id:
        config.season_id = season_id
    if club_id:
        config.club_id = club_id

    ctx.obj = {
        "config": config,
        "timeout": timeout,
        "verbose": verbose,
        "config_dir": resolved_path.parent,
    }


cli.add_command(show)
cli.add_command(input_cmd)
cli.add_command(commit_cmd)
cli.add_command(view_cmd)
cli.add_command(gm)


@cli.command("help")
@click.argument("command", required=False)
@click.argument("subcommand", required=False)
@click.pass_context
def help_cmd(ctx: click.Context, command: Optional[str], subcommand: Optional[str]) -> None:
    """Show help for the CLI or a specific (sub)command."""
    target = cli
    target_name = "club-game"

    if command:
        cmd = cli.commands.get(command)
        if not cmd:
            raise click.ClickException(f"Unknown command: {command}")
        target = cmd
        target_name = command
        if subcommand and isinstance(cmd, click.Group):
            sub = cmd.commands.get(subcommand)
            if not sub:
                raise click.ClickException(f"Unknown subcommand for {command}: {subcommand}")
            target = sub
            target_name = f"{command} {subcommand}"
        elif subcommand:
            raise click.ClickException(f"Command {command} has no subcommands")

    with click.Context(target, info_name=target_name, parent=ctx) as help_ctx:
        click.echo(target.get_help(help_ctx))


cli.add_command(help_cmd)


def main() -> None:
    try:
        cli(obj={})
    except CliError as exc:
        raise click.ClickException(str(exc))


if __name__ == "__main__":  # pragma: no cover
    main()
