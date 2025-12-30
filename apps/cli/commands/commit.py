"""`commit` command for finalizing turn decisions."""
from __future__ import annotations

from typing import Optional

import click

from ..api_client import ApiClient
from ..auth import build_headers
from ..config import CliConfig
from ..errors import CliError, ValidationError
from ..output import print_json
from ..draft import load_draft, clear_draft


def _resolve_required(option: Optional[str], fallback: Optional[str], label: str) -> str:
    value = option or fallback
    if not value:
        raise ValidationError(f"{label} is required; provide a flag or set it in config")
    return value


def _with_client(config: CliConfig, timeout: float, verbose: bool) -> ApiClient:
    headers = build_headers(config)
    return ApiClient(config.base_url, headers=headers, timeout=timeout, verbose=verbose)


@click.command("commit")
@click.option("--season-id", help="Season UUID (defaults to config)")
@click.option("--club-id", help="Club UUID (defaults to config)")
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation prompt")
@click.option("--json-output", is_flag=True, help="Print raw JSON response")
@click.pass_context
def commit_cmd(
    ctx: click.Context,
    season_id: Optional[str],
    club_id: Optional[str],
    yes: bool,
    json_output: bool,
) -> None:
    """Commit (finalize) current turn decision."""
    config: CliConfig = ctx.obj["config"]
    timeout: float = ctx.obj["timeout"]
    verbose: bool = ctx.obj["verbose"]
    config_dir = ctx.obj["config_dir"]

    season_id = _resolve_required(season_id, config.season_id, "season_id")
    club_id = _resolve_required(club_id, config.club_id, "club_id")

    draft = load_draft(config_dir, season_id, club_id)

    with _with_client(config, timeout, verbose) as client:
        turn_data = client.get(f"/api/turns/seasons/{season_id}/current")
        turn_id = turn_data.get("id")
        if not turn_id:
            raise CliError("No active turn found for this season")

        decision_data = client.get(f"/api/turns/seasons/{season_id}/decisions/{club_id}/current")
        api_payload = decision_data.get("payload") if decision_data else None

        payload = draft.payload if draft else api_payload
        if not payload:
            raise CliError("No input found to commit. Provide input first.")

        click.echo(f"Turn: {turn_data.get('month_name')} (month_index={turn_data.get('month_index')})")
        click.echo(f"State: {decision_data.get('decision_state') if decision_data else 'unknown'}")
        source = "draft" if draft else "api"
        click.echo(f"Payload source: {source}")
        click.echo("Payload:")
        print_json(payload)

        if not yes:
            if not click.confirm("Commit this decision?"):
                click.echo("Aborted.")
                return

        result = client.post(
            f"/api/turns/{turn_id}/decisions/{club_id}/commit",
            json_body={"payload": payload},
        )

    if draft:
        clear_draft(config_dir, season_id, club_id)

    if json_output:
        print_json(result)
    else:
        click.echo("Decision committed successfully.")


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


commit_cmd.callback = dispatch_errors(commit_cmd.callback)
