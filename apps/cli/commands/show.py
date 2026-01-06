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
        opponent_display = item.get("opponent_name") or item.get("opponent") or "(bye)"
        rows.append(
            {
                "month": f"{item.get('month_name', '')} ({item.get('month_index', '')})",
                "opponent": opponent_display,
                "home": "H" if home else ("A" if item.get("opponent") else "-"),
                "status": item.get("status") or "-",
                "score": score,
                "weather": item.get("weather") or "-",
                "attendance": item.get("total_attendance"),
            }
        )

    print_table(rows, ["month", "home", "opponent", "status", "score", "weather", "attendance"])


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
        turn = client.get(f"/api/turns/seasons/{season_id}/current")
        bankrupt_clubs = client.get(f"/api/seasons/{season_id}/bankrupt-clubs")
        data = client.get(f"/api/seasons/{season_id}/standings")

    if json_output:
        print_json({"as_of": turn, "standings": data})
        return

    if isinstance(turn, dict):
        click.echo(f"As of {_format_season_turn_label(turn)}")

    messages: List[str] = []
    if isinstance(bankrupt_clubs, list):
        for item in bankrupt_clubs:
            penalty_points = item.get("penalty_points")
            if item.get("is_bankrupt") and penalty_points is not None and penalty_points < 0:
                club_name = item.get("club_name") or "-"
                messages.append(f"{club_name}チームは勝ち点を{abs(penalty_points)}点剥奪されている")

    for message in messages:
        click.echo(message)

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


@show.command("finance")
@click.option("--season-id", help="Season UUID (defaults to config)")
@click.option("--club-id", help="Club UUID (defaults to config)")
@click.option("--month-index", type=int, help="Filter by month_index (1-12)")
@click.option("--json-output", is_flag=True, help="Print raw JSON")
@click.pass_context
def show_finance(ctx: click.Context, season_id: Optional[str], club_id: Optional[str], month_index: Optional[int], json_output: bool) -> None:
    """Show financial state and ledger for a club."""
    config: CliConfig = ctx.obj["config"]
    timeout: float = ctx.obj["timeout"]
    verbose: bool = ctx.obj["verbose"]

    season_id = _resolve_required(season_id, config.season_id, "season_id")
    club_id = _resolve_required(club_id, config.club_id, "club_id")

    params = {"season_id": season_id}
    if month_index is not None:
        params["month_index"] = month_index

    with _with_client(config, timeout, verbose) as client:
        state = client.get(f"/api/clubs/{club_id}/finance/state")
        ledger = client.get(f"/api/clubs/{club_id}/finance/ledger", params=params)
        season = client.get(f"/api/seasons/{season_id}")

    if json_output:
        print_json({"state": state, "ledger": ledger})
        return

    balance = state.get("balance") if isinstance(state, dict) else None
    last_turn = state.get("last_applied_turn_id") if isinstance(state, dict) else None
    season_index = season.get("season_number") if isinstance(season, dict) else None

    def round_amount(value: Optional[float]) -> Optional[int]:
        if value is None:
            return None
        return int(round(value))

    # Prepare ledger grouping
    if not ledger:
        click.echo(f"Season index: {season_index}")
        click.echo(f"Balance: {round_amount(balance)}")
        click.echo(f"Last applied turn: {last_turn}")
        click.echo("No ledger entries found.")
        return

    # Latest month when not specified
    all_months = sorted({e.get("month_index") for e in ledger if e.get("month_index") is not None})
    target_month = month_index if month_index is not None else (all_months[-1] if all_months else None)

    # Map for normalization of kinds (merge fixture-specific keys)
    def normalize_kind(kind: str) -> str:
        prefixes = [
            "match_operation_cost",
            "merchandise_cost",
            "merchandise_rev",
            "ticket_rev",
        ]
        for pref in prefixes:
            if kind.startswith(pref):
                return pref
        return kind

    month_name_lookup = {
        1: "August", 2: "September", 3: "October", 4: "November", 5: "December",
        6: "January", 7: "February", 8: "March", 9: "April", 10: "May", 11: "June", 12: "July",
    }
    month_label = month_name_lookup.get(target_month, "-") if target_month else "-"

    click.echo(f"Season index: {season_index}")
    click.echo(f"Balance: {round_amount(balance)}")
    click.echo(f"Last applied turn: {last_turn}, month_index={target_month} ({month_label})")

    # Filter ledger for target month
    month_entries = [e for e in ledger if e.get("month_index") == target_month]

    # Monthly per-item breakdown
    monthly_by_kind: Dict[str, float] = {}
    for entry in month_entries:
        kind = normalize_kind(entry.get("kind") or "(unknown)")
        amt = entry.get("amount", 0)
        monthly_by_kind[kind] = monthly_by_kind.get(kind, 0) + amt

    monthly_table = []
    for k, v in sorted(monthly_by_kind.items()):
        monthly_table.append({
            "kind": k,
            "income": round_amount(v) if v > 0 else 0,
            "expense": round_amount(v) if v < 0 else 0,
            "net": round_amount(v),
        })

    if monthly_table:
        income_total = sum(v for v in monthly_by_kind.values() if v > 0)
        expense_total = sum(v for v in monthly_by_kind.values() if v < 0)
        net_total = sum(monthly_by_kind.values())
        monthly_table.append(
            {
                "kind": "TOTAL",
                "income": round_amount(income_total),
                "expense": round_amount(expense_total),
                "net": round_amount(net_total),
            }
        )
        click.echo("Current month breakdown (by item):")
        print_table(monthly_table, ["kind", "income", "expense", "net"])
    else:
        click.echo("No entries for the target month.")

    # Season cumulative by normalized kind
    kind_rows: Dict[str, float] = {}
    for entry in ledger:
        kind = normalize_kind(entry.get("kind") or "(unknown)")
        amount = entry.get("amount", 0)
        kind_rows[kind] = kind_rows.get(kind, 0) + amount

    income_rows = []
    expense_rows = []
    for k, v in sorted(kind_rows.items()):
        row = {
            "kind": k,
            "income": round_amount(v) if v > 0 else 0,
            "expense": round_amount(v) if v < 0 else 0,
            "net": round_amount(v),
        }
        if v > 0:
            income_rows.append(row)
        elif v < 0:
            expense_rows.append(row)
        else:
            # zero rows can go with expense side for stability
            expense_rows.append(row)

    cumulative_table = income_rows + expense_rows
    if cumulative_table:
        income_total = sum(v for v in kind_rows.values() if v > 0)
        expense_total = sum(v for v in kind_rows.values() if v < 0)
        net_total = sum(kind_rows.values())
        cumulative_table.append(
            {
                "kind": "TOTAL",
                "income": round_amount(income_total),
                "expense": round_amount(expense_total),
                "net": round_amount(net_total),
            }
        )

    click.echo("Season cumulative by item:")
    print_table(cumulative_table, ["kind", "income", "expense", "net"])


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
    summary = {
        "season_number": data.get("season_number"),
        "month_index": data.get("month_index"),
        "month_name": data.get("month_name"),
        "decision_state": data.get("decision_state"),
        "committed_at": data.get("committed_at"),
    }
    click.echo("Turn:")
    print_table([summary], ["season_number", "month_index", "month_name", "decision_state", "committed_at"])
    available = data.get("available_inputs") if isinstance(data, dict) else None
    if available:
        click.echo("Available inputs this turn:")
        for val in available:
            click.echo(f"- {val}")
    actions = data.get("available_actions") if isinstance(data, dict) else None
    if actions:
        click.echo("Available actions this turn:")
        for act in actions:
            click.echo(f"- {act}")
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
@click.option("--club-id", "club_id", help="Club UUID (defaults to config)")
@click.option("--club", "club_override", help="Club identifier (alias; uses UUID in current API)")
@click.option("--season-id", help="Season UUID (defaults to config)")
@click.option("--from", "from_month", help="From YYYY-MM (mapped to month_index; optional)")
@click.option("--to", "to_month", help="To YYYY-MM (mapped to month_index; optional)")
@click.option("--json-output", is_flag=True, help="Print raw JSON")
@click.pass_context
def show_fan_indicator(ctx: click.Context, club_id: Optional[str], club_override: Optional[str], season_id: Optional[str], from_month: Optional[str], to_month: Optional[str], json_output: bool) -> None:
    config: CliConfig = ctx.obj["config"]
    timeout: float = ctx.obj["timeout"]
    verbose: bool = ctx.obj["verbose"]
    season_id = _resolve_required(season_id, config.season_id, "season_id")
    resolved_club = club_override or club_id or config.club_id
    resolved_club = _resolve_required(resolved_club, None, "club_id/club")

    params: Dict[str, Any] = {"season_id": season_id}
    fm = ensure_month_bounds(parse_month_to_index(from_month) if from_month else None, "from_month")
    tm = ensure_month_bounds(parse_month_to_index(to_month) if to_month else None, "to_month")
    if fm is not None:
        params["from_month"] = fm
    if tm is not None:
        params["to_month"] = tm

    with _with_client(config, timeout, verbose) as client:
        standings = client.get(f"/api/seasons/{season_id}/standings")
        data = client.get(f"/api/clubs/{resolved_club}/fan_indicator", params=params)

    club_map: Dict[str, str] = {}
    if isinstance(standings, list):
        for entry in standings:
            cid = entry.get("club_id")
            if cid:
                club_map[str(cid)] = entry.get("club_name") or entry.get("club") or str(cid)

    if isinstance(data, dict):
        club_id_val = str(data.get("club_id")) if data.get("club_id") else str(resolved_club)
        club_name = club_map.get(club_id_val, club_id_val)
        rendered = {"club": club_name, "followers": data.get("followers"), "club_id": club_id_val}
    else:
        rendered = None

    if json_output:
        print_json({"params": params, "data": data, "club_name": rendered.get("club") if rendered else None})
        return

    rows = [rendered] if rendered else []
    print_table(rows, ["club", "followers"])


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
