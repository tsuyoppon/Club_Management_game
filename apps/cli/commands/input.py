"""`input` command for submitting monthly decisions."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional

import click

from ..api_client import ApiClient
from ..auth import build_headers
from ..config import CliConfig
from ..errors import CliError, ValidationError
from ..draft import load_draft, save_draft, clear_draft


def _resolve_required(option: Optional[str], fallback: Optional[str], label: str) -> str:
    value = option or fallback
    if not value:
        raise ValidationError(f"{label} is required; provide a flag or set it in config")
    return value


def _with_client(config: CliConfig, timeout: float, verbose: bool) -> ApiClient:
    headers = build_headers(config)
    return ApiClient(config.base_url, headers=headers, timeout=timeout, verbose=verbose)


def _parse_decimal(value: Optional[str], label: str) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        d = Decimal(value)
        if d < 0:
            raise ValidationError(f"{label} must be non-negative")
        return d
    except InvalidOperation:
        raise ValidationError(f"{label} must be a valid decimal number")


def _parse_float_ratio(value: Optional[float], label: str) -> Optional[float]:
    if value is None:
        return None
    if value < 0.0 or value > 1.0:
        raise ValidationError(f"{label} must be between 0.0 and 1.0")
    return value


@click.command("input")
@click.option("--season-id", help="Season UUID (defaults to config)")
@click.option("--club-id", help="Club UUID (defaults to config)")
@click.option("--sales-expense", type=str, help="Sales expense (Decimal)")
@click.option("--promo-expense", type=str, help="Promotion expense (Decimal)")
@click.option("--hometown-expense", type=str, help="Hometown activity expense (Decimal)")
@click.option("--next-home-promo", type=str, help="Next-month home promo (Decimal, conditional)")
@click.option("--additional-reinforcement", type=str, help="Additional reinforcement (Decimal, Dec only)")
@click.option("--rho-new", type=float, help="New sponsor allocation ratio 0.0-1.0 (Q-start months only)")
@click.option("--clear", is_flag=True, help="Clear local draft for this season/club")
@click.option("--json-output", is_flag=True, help="Print raw JSON response")
@click.pass_context
def input_cmd(
    ctx: click.Context,
    season_id: Optional[str],
    club_id: Optional[str],
    sales_expense: Optional[str],
    promo_expense: Optional[str],
    hometown_expense: Optional[str],
    next_home_promo: Optional[str],
    additional_reinforcement: Optional[str],
    rho_new: Optional[float],
    clear: bool,
    json_output: bool,
) -> None:
    """Submit monthly input (decision payload)."""
    config: CliConfig = ctx.obj["config"]
    timeout: float = ctx.obj["timeout"]
    verbose: bool = ctx.obj["verbose"]
    config_dir = ctx.obj["config_dir"]

    season_id = _resolve_required(season_id, config.season_id, "season_id")
    club_id = _resolve_required(club_id, config.club_id, "club_id")

    if clear:
        clear_draft(config_dir, season_id, club_id)
        click.echo("Draft cleared.")
        return

    # Build overrides
    overrides: Dict[str, Any] = {}

    se = _parse_decimal(sales_expense, "sales-expense")
    if se is not None:
        overrides["sales_expense"] = float(se)

    pe = _parse_decimal(promo_expense, "promo-expense")
    if pe is not None:
        overrides["promo_expense"] = float(pe)

    he = _parse_decimal(hometown_expense, "hometown-expense")
    if he is not None:
        overrides["hometown_expense"] = float(he)

    nhp = _parse_decimal(next_home_promo, "next-home-promo")
    if nhp is not None:
        overrides["next_home_promo"] = float(nhp)

    ar = _parse_decimal(additional_reinforcement, "additional-reinforcement")
    if ar is not None:
        overrides["additional_reinforcement"] = float(ar)

    rn = _parse_float_ratio(rho_new, "rho-new")
    if rn is not None:
        overrides["rho_new"] = rn

    if not overrides:
        raise ValidationError("No input provided. Use --help for available options.")

    # Determine base payload
    draft = load_draft(config_dir, season_id, club_id)
    base_payload: Dict[str, Any]
    base_source = "draft" if draft else "api"

    if draft:
        base_payload = dict(draft.payload)
    else:
        with _with_client(config, timeout, verbose) as client:
            current = client.get(f"/api/turns/seasons/{season_id}/decisions/{club_id}/current")
        if current and isinstance(current, dict) and isinstance(current.get("payload"), dict):
            base_payload = dict(current.get("payload") or {})
        else:
            base_payload = {}

    merged = {**base_payload, **overrides}
    path = save_draft(config_dir, season_id, club_id, merged, base_source=base_source)

    if json_output:
        import json
        click.echo(json.dumps({"payload": merged, "draft_path": str(path)}, indent=2, default=str))
    else:
        click.echo("Draft updated locally (not committed).")
        click.echo(f"Draft path: {path}")
        click.echo(f"Payload: {merged}")


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


input_cmd.callback = dispatch_errors(input_cmd.callback)
