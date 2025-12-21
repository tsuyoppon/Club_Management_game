"""`show` command group implementations."""
from __future__ import annotations

from functools import wraps
from typing import Any, Dict, List, Optional

import click

from ..api_client import ApiClient
from ..auth import build_headers
from ..config import CliConfig
from ..errors import ApiError, CliError, ValidationError
from ..output import print_json, print_table
from ..parsing import ensure_month_bounds, parse_month_to_index


def _resolve_required(option: Optional[str], fallback: Optional[str], label: str) -> str:
    value = option or fallback
    if not value:
        raise ValidationError(f"{label} is required; provide a flag or set it in config")
    return value


def _with_client(config: CliConfig, timeout: float, verbose: bool) -> ApiClient:
    headers = build_headers(config)
    return ApiClient(config.base_url, headers=headers, timeout=timeout, verbose=verbose)


@click.group()
@click.pass_context
def show(ctx: click.Context) -> None:
    """Read-only reference commands."""
    pass


@show.command("match")
@click.option("--season-id", help="Season UUID (defaults to config)")
@click.option("--club-id", help="Club UUID (defaults to config)")
@click.option("--month", help="Filter by YYYY-MM (mapped to month_index)")
@click.option("--month-index", type=int, help="Filter by month_index (1-12)")
@click.option("--json-output", is_flag=True, help="Print raw JSON")
@click.pass_context
def show_match(ctx: click.Context, season_id: Optional[str], club_id: Optional[str], month: Optional[str], month_index: Optional[int], json_output: bool) -> None:
    config: CliConfig = ctx.obj["config"]
    timeout: float = ctx.obj["timeout"]
    verbose: bool = ctx.obj["verbose"]

    season_id = _resolve_required(season_id, config.season_id, "season_id")
    club_id = _resolve_required(club_id, config.club_id, "club_id")

    parsed_month_index = parse_month_to_index(month) if month else month_index
    parsed_month_index = ensure_month_bounds(parsed_month_index, "month_index")

    params: Dict[str, Any] = {}
    if parsed_month_index is not None:
        params["month_index"] = parsed_month_index

    with _with_client(config, timeout, verbose) as client:
        data = client.get(f"/api/seasons/{season_id}/clubs/{club_id}/schedule", params=params)

    if json_output:
        print_json(data)
        return

    rows: List[Dict[str, Any]] = []
    for item in data:
        home = item.get("home")
        home_goals = item.get("home_goals")
        away_goals = item.get("away_goals")
        if home_goals is not None and away_goals is not None:
            score = f"{home_goals}-{away_goals}" if home else f"{away_goals}-{home_goals}"
        else:
            score = "-"
        rows.append(
            {
                "month": f"{item.get('month_name', '')} ({item.get('month_index', '')})",
                "opponent": item.get("opponent") or "(bye)",
                "home": "H" if home else ("A" if item.get("opponent") else "-"),
                "status": item.get("status") or "-",
                "score": score,
                "attendance": item.get("total_attendance"),
            }
        )

    print_table(rows, ["month", "home", "opponent", "status", "score", "attendance"])


@show.command("table")
@click.option("--season-id", help="Season UUID (defaults to config)")
@click.option("--json-output", is_flag=True, help="Print raw JSON")
@click.pass_context
def show_table(ctx: click.Context, season_id: Optional[str], json_output: bool) -> None:
    config: CliConfig = ctx.obj["config"]
    timeout: float = ctx.obj["timeout"]
    verbose: bool = ctx.obj["verbose"]
    season_id = _resolve_required(season_id, config.season_id, "season_id")

    with _with_client(config, timeout, verbose) as client:
        data = client.get(f"/api/seasons/{season_id}/standings")

    if json_output:
        print_json(data)
        return

    rows = [
        {
            "rank": row.get("rank"),
            "club": row.get("club_name"),
            "played": row.get("played"),
            "won": row.get("won"),
            "drawn": row.get("drawn"),
            "lost": row.get("lost"),
            "gf": row.get("gf"),
            "ga": row.get("ga"),
            "gd": row.get("gd"),
            "pts": row.get("points"),
        }
        for row in data
    ]
    print_table(rows, ["rank", "club", "played", "won", "drawn", "lost", "gf", "ga", "gd", "pts"])


@show.command("team_power")
@click.option("--season-id", help="Season UUID (defaults to config)")
@click.option("--json-output", is_flag=True, help="Print raw JSON")
@click.pass_context
def show_team_power(ctx: click.Context, season_id: Optional[str], json_output: bool) -> None:
    config: CliConfig = ctx.obj["config"]
    timeout: float = ctx.obj["timeout"]
    verbose: bool = ctx.obj["verbose"]
    season_id = _resolve_required(season_id, config.season_id, "season_id")

    with _with_client(config, timeout, verbose) as client:
        data = client.get(f"/api/seasons/{season_id}/team-power")

    if json_output:
        print_json(data)
        return

    payload = data.get("disclosed_data") if isinstance(data, dict) else None
    clubs = payload.get("clubs") if isinstance(payload, dict) else None
    if clubs:
        rows = [
            {
                "club": entry.get("club_name"),
                "team_power": entry.get("team_power"),
            }
            for entry in clubs
        ]
        print_table(rows, ["club", "team_power"])
    else:
        print_json(data)


@show.command("staff")
@click.option("--club-id", help="Club UUID (defaults to config)")
@click.option("--json-output", is_flag=True, help="Print raw JSON")
@click.pass_context
def show_staff(ctx: click.Context, club_id: Optional[str], json_output: bool) -> None:
    config: CliConfig = ctx.obj["config"]
    timeout: float = ctx.obj["timeout"]
    verbose: bool = ctx.obj["verbose"]
    club_id = _resolve_required(club_id, config.club_id, "club_id")

    with _with_client(config, timeout, verbose) as client:
        data = client.get(f"/api/clubs/{club_id}/management/staff")

    if json_output:
        print_json(data)
        return

    rows = [
        {
            "role": row.get("role"),
            "count": row.get("count"),
            "salary": row.get("salary_per_person"),
            "next": row.get("next_count"),
            "hiring_target": row.get("hiring_target"),
            "updated_at": row.get("updated_at"),
        }
        for row in data
    ]
    print_table(rows, ["role", "count", "salary", "next", "hiring_target", "updated_at"])


@show.command("staff_history")
@click.option("--club-id", help="Club UUID (defaults to config)")
@click.option("--season-id", help="Season UUID (optional filter)")
@click.option("--from", "from_month", help="From YYYY-MM (mapped to month_index)")
@click.option("--to", "to_month", help="To YYYY-MM (mapped to month_index)")
@click.option("--json-output", is_flag=True, help="Print raw JSON")
@click.pass_context
def show_staff_history(ctx: click.Context, club_id: Optional[str], season_id: Optional[str], from_month: Optional[str], to_month: Optional[str], json_output: bool) -> None:
    config: CliConfig = ctx.obj["config"]
    timeout: float = ctx.obj["timeout"]
    verbose: bool = ctx.obj["verbose"]
    club_id = _resolve_required(club_id, config.club_id, "club_id")
    season_id = season_id or config.season_id

    params: Dict[str, Any] = {}
    if season_id:
        params["season_id"] = season_id
    fm = ensure_month_bounds(parse_month_to_index(from_month) if from_month else None, "from_month")
    tm = ensure_month_bounds(parse_month_to_index(to_month) if to_month else None, "to_month")
    if fm is not None:
        params["from_month"] = fm
    if tm is not None:
        params["to_month"] = tm

    with _with_client(config, timeout, verbose) as client:
        data = client.get(f"/api/clubs/{club_id}/management/staff/history", params=params)

    if json_output:
        print_json(data)
        return

    rows = [
        {
            "season": entry.get("season_id"),
            "month": entry.get("month_index"),
            "month_name": entry.get("month_name"),
            "total_cost": entry.get("total_cost"),
            "created_at": entry.get("created_at"),
        }
        for entry in data
    ]
    print_table(rows, ["season", "month", "month_name", "total_cost", "created_at"])


@show.command("current_input")
@click.option("--season-id", help="Season UUID (defaults to config)")
@click.option("--club-id", help="Club UUID (defaults to config)")
@click.option("--json-output", is_flag=True, help="Print raw JSON")
@click.pass_context
def show_current_input(ctx: click.Context, season_id: Optional[str], club_id: Optional[str], json_output: bool) -> None:
    config: CliConfig = ctx.obj["config"]
    timeout: float = ctx.obj["timeout"]
    verbose: bool = ctx.obj["verbose"]
    season_id = _resolve_required(season_id, config.season_id, "season_id")
    club_id = _resolve_required(club_id, config.club_id, "club_id")

    with _with_client(config, timeout, verbose) as client:
        data = client.get(f"/api/turns/seasons/{season_id}/decisions/{club_id}/current")

    if data is None:
        click.echo("No current input found (maybe all turns acked?)")
        return

    if json_output:
        print_json(data)
        return

    payload = data.get("payload") if isinstance(data, dict) else None
    summary = {"month_index": data.get("month_index"), "month_name": data.get("month_name"), "decision_state": data.get("decision_state"), "committed_at": data.get("committed_at")}
    click.echo("Turn:")
    print_table([summary], ["month_index", "month_name", "decision_state", "committed_at"])
    if payload:
        click.echo("Payload:")
        print_json(payload)


@show.command("history")
@click.option("--season-id", help="Season UUID (defaults to config)")
@click.option("--club-id", help="Club UUID (defaults to config)")
@click.option("--from", "from_month", help="From YYYY-MM (mapped to month_index)")
@click.option("--to", "to_month", help="To YYYY-MM (mapped to month_index)")
@click.option("--json-output", is_flag=True, help="Print raw JSON")
@click.pass_context
def show_history(ctx: click.Context, season_id: Optional[str], club_id: Optional[str], from_month: Optional[str], to_month: Optional[str], json_output: bool) -> None:
    config: CliConfig = ctx.obj["config"]
    timeout: float = ctx.obj["timeout"]
    verbose: bool = ctx.obj["verbose"]
    season_id = _resolve_required(season_id, config.season_id, "season_id")
    club_id = _resolve_required(club_id, config.club_id, "club_id")

    params: Dict[str, Any] = {}
    fm = ensure_month_bounds(parse_month_to_index(from_month) if from_month else None, "from_month")
    tm = ensure_month_bounds(parse_month_to_index(to_month) if to_month else None, "to_month")
    if fm is not None:
        params["from_month"] = fm
    if tm is not None:
        params["to_month"] = tm

    with _with_client(config, timeout, verbose) as client:
        data = client.get(f"/api/turns/seasons/{season_id}/decisions/{club_id}", params=params)

    if json_output:
        print_json(data)
        return

    rows = [
        {
            "month": entry.get("month_index"),
            "month_name": entry.get("month_name"),
            "state": entry.get("decision_state"),
            "committed_at": entry.get("committed_at"),
        }
        for entry in data
    ]
    print_table(rows, ["month", "month_name", "state", "committed_at"])


@show.command("fan_indicator")
@click.option("--club-id", help="Club UUID (defaults to config)")
@click.option("--season-id", help="Season UUID (defaults to config)")
@click.option("--json-output", is_flag=True, help="Print raw JSON")
@click.pass_context
def show_fan_indicator(ctx: click.Context, club_id: Optional[str], season_id: Optional[str], json_output: bool) -> None:
    config: CliConfig = ctx.obj["config"]
    timeout: float = ctx.obj["timeout"]
    verbose: bool = ctx.obj["verbose"]
    season_id = _resolve_required(season_id, config.season_id, "season_id")
    club_id = _resolve_required(club_id, config.club_id, "club_id")

    params = {"season_id": season_id}
    with _with_client(config, timeout, verbose) as client:
        data = client.get(f"/api/clubs/{club_id}/fan_indicator", params=params)

    if json_output:
        print_json(data)
        return

    rows = [{"club_id": data.get("club_id"), "followers": data.get("followers")}]
    print_table(rows, ["club_id", "followers"])


@show.command("sponsor_status")
@click.option("--club-id", help="Club UUID (defaults to config)")
@click.option("--season-id", help="Season UUID (defaults to config)")
@click.option("--pipeline", is_flag=True, help="Show pipeline status (default)")
@click.option("--next", "next_flag", is_flag=True, help="Show next-year sponsor info")
@click.option("--json-output", is_flag=True, help="Print raw JSON")
@click.pass_context
def show_sponsor_status(ctx: click.Context, club_id: Optional[str], season_id: Optional[str], pipeline: bool, next_flag: bool, json_output: bool) -> None:
    config: CliConfig = ctx.obj["config"]
    timeout: float = ctx.obj["timeout"]
    verbose: bool = ctx.obj["verbose"]
    season_id = _resolve_required(season_id, config.season_id, "season_id")
    club_id = _resolve_required(club_id, config.club_id, "club_id")

    endpoint: str
    if next_flag:
        endpoint = f"/api/sponsors/seasons/{season_id}/clubs/{club_id}/next-sponsor"
    else:
        endpoint = f"/api/sponsors/seasons/{season_id}/clubs/{club_id}/pipeline"

    with _with_client(config, timeout, verbose) as client:
        data = client.get(endpoint)

    if json_output:
        print_json(data)
        return

    if next_flag:
        rows = [{
            "next_total": data.get("next_sponsors_total"),
            "next_exist": data.get("next_sponsors_exist"),
            "next_new": data.get("next_sponsors_new"),
            "unit_price": data.get("unit_price"),
            "expected_revenue": data.get("expected_revenue"),
            "finalized": data.get("is_finalized"),
        }]
        print_table(rows, ["next_total", "next_exist", "next_new", "unit_price", "expected_revenue", "finalized"])
    else:
        rows = [{
            "current": data.get("current_sponsors"),
            "confirmed_exist": data.get("confirmed_exist"),
            "confirmed_new": data.get("confirmed_new"),
            "total_confirmed": data.get("total_confirmed"),
            "next_exist_target": data.get("next_exist_target"),
            "next_new_target": data.get("next_new_target"),
            "next_total": data.get("next_total"),
        }]
        print_table(rows, ["current", "confirmed_exist", "confirmed_new", "total_confirmed", "next_exist_target", "next_new_target", "next_total"])


def dispatch_errors(func):
    """Decorator to surface CliError as ClickException."""

    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except CliError as exc:
            raise click.ClickException(str(exc)) from exc
    return wraps(func)(wrapper)


# Wrap all commands to translate exceptions once.
for command in list(show.commands.values()):
    if isinstance(command, click.core.Command):
        command.callback = dispatch_errors(command.callback)
