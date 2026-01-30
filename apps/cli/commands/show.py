"""`show` command group implementations."""
from __future__ import annotations

import uuid
from functools import wraps
from typing import Any, Dict, List, Optional

import click

from ..api_client import ApiClient
from ..auth import build_headers
from ..config import CliConfig
from ..errors import ApiError, CliError, ValidationError
from ..output import format_number, print_json, print_table
from ..parsing import ensure_month_bounds, parse_month_to_index


def _resolve_required(option: Optional[str], fallback: Optional[str], label: str) -> str:
    value = option or fallback
    if not value:
        raise ValidationError(f"{label} is required; provide a flag or set it in config")
    return value


def _with_client(config: CliConfig, timeout: float, verbose: bool) -> ApiClient:
    headers = build_headers(config)
    return ApiClient(config.base_url, headers=headers, timeout=timeout, verbose=verbose)


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except ValueError:
        return False


def _resolve_season_identifier(
    client: ApiClient,
    config: CliConfig,
    season_identifier: Optional[str],
    *,
    allow_passthrough: bool = True,
) -> str:
    resolved = _resolve_required(season_identifier, config.season_id, "season_id")
    if _is_uuid(resolved):
        return resolved

    if not config.game_id:
        if allow_passthrough:
            return resolved
        raise ValidationError("game_id is required to resolve season identifier")

    game_id = _resolve_required(config.game_id, None, "game_id")
    seasons = client.get(f"/api/seasons/games/{game_id}")
    if not isinstance(seasons, list):
        if allow_passthrough:
            return resolved
        raise CliError("Failed to resolve seasons list for game")

    matches: List[dict] = []
    for season in seasons:
        if not isinstance(season, dict):
            continue
        season_number = season.get("season_number")
        year_label = season.get("year_label")
        if season_number is not None and str(season_number) == str(resolved):
            matches.append(season)
        if year_label is not None and str(year_label) == str(resolved):
            matches.append(season)

    unique_matches = {m.get("id"): m for m in matches if m.get("id")}
    if not unique_matches:
        if allow_passthrough:
            return resolved
        raise CliError(f"Season not found for identifier: {resolved}")
    if len(unique_matches) > 1:
        raise CliError(f"Multiple seasons matched identifier: {resolved}; use UUID")

    resolved_id = next(iter(unique_matches.values())).get("id")
    if not resolved_id:
        raise CliError(f"Season missing id for identifier: {resolved}")
    return resolved_id


def _resolve_club_identifier(
    client: ApiClient,
    config: CliConfig,
    club_identifier: Optional[str],
    *,
    allow_passthrough: bool = True,
) -> str:
    resolved = _resolve_required(club_identifier, config.club_id, "club_id")
    if _is_uuid(resolved):
        return resolved

    if not config.game_id:
        if allow_passthrough:
            return resolved
        raise ValidationError("game_id is required to resolve club name")
    game_id = _resolve_required(config.game_id, None, "game_id")
    clubs = client.get(f"/api/games/{game_id}/clubs")
    if not isinstance(clubs, list):
        if allow_passthrough:
            return resolved
        raise CliError("Failed to resolve clubs list for game")

    matches = [
        club for club in clubs
        if isinstance(club, dict)
        and (club.get("name") == resolved or club.get("short_name") == resolved)
    ]
    if not matches:
        if allow_passthrough:
            return resolved
        raise CliError(f"Club not found for name: {resolved}")
    if len(matches) > 1:
        raise CliError(f"Multiple clubs matched name: {resolved}; use --club-id")
    resolved_id = matches[0].get("id")
    if not resolved_id:
        raise CliError(f"Club missing id for name: {resolved}")
    return resolved_id


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
@click.option("--season-id", help="Season UUID/season_number/year_label (defaults to config)")
@click.option("--club-id", help="Club UUID or name (defaults to config)")
@click.option("--month", help="Filter by YYYY-MM (mapped to month_index)")
@click.option("--month-index", type=int, help="Filter by month_index (1-12)")
@click.option("--json-output", is_flag=True, help="Print raw JSON")
@click.pass_context
def show_match(ctx: click.Context, season_id: Optional[str], club_id: Optional[str], month: Optional[str], month_index: Optional[int], json_output: bool) -> None:
    config: CliConfig = ctx.obj["config"]
    timeout: float = ctx.obj["timeout"]
    verbose: bool = ctx.obj["verbose"]

    with _with_client(config, timeout, verbose) as client:
        season_id = _resolve_season_identifier(client, config, season_id)
        club_id = _resolve_club_identifier(client, config, club_id)

        parsed_month_index = parse_month_to_index(month) if month else month_index
        parsed_month_index = ensure_month_bounds(parsed_month_index, "month_index")

        params: Dict[str, Any] = {}
        if parsed_month_index is not None:
            params["month_index"] = parsed_month_index

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

    print_table(rows, ["month", "home", "opponent", "status", "score", "weather", "attendance"], format_numbers=True)


@show.command("table")
@click.option("--season-id", help="Season UUID/season_number/year_label (defaults to config)")
@click.option("--json-output", is_flag=True, help="Print raw JSON")
@click.pass_context
def show_table(ctx: click.Context, season_id: Optional[str], json_output: bool) -> None:
    config: CliConfig = ctx.obj["config"]
    timeout: float = ctx.obj["timeout"]
    verbose: bool = ctx.obj["verbose"]
    with _with_client(config, timeout, verbose) as client:
        season_id = _resolve_season_identifier(client, config, season_id)
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
                formatted_penalty = format_number(abs(penalty_points))
                messages.append(f"{club_name}チームは勝ち点を{formatted_penalty}点剥奪されている")

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
    print_table(rows, ["rank", "club", "played", "won", "drawn", "lost", "gf", "ga", "gd", "pts"], format_numbers=True)


@show.command("final_standings")
@click.option("--club-id", help="Club UUID or name (defaults to config)")
@click.option("--club-name", help="Club name (resolved within the configured game)")
@click.option("--json-output", is_flag=True, help="Print raw JSON")
@click.pass_context
def show_final_standings(
    ctx: click.Context,
    club_id: Optional[str],
    club_name: Optional[str],
    json_output: bool,
) -> None:
    """Show finalized standings history for a club."""
    config: CliConfig = ctx.obj["config"]
    timeout: float = ctx.obj["timeout"]
    verbose: bool = ctx.obj["verbose"]
    with _with_client(config, timeout, verbose) as client:
        if club_id:
            resolved_club_id = _resolve_club_identifier(client, config, club_id)
        elif club_name:
            resolved_club_id = _resolve_club_identifier(client, config, club_name, allow_passthrough=False)
        else:
            resolved_club_id = _resolve_club_identifier(client, config, config.club_id)
        data = client.get(f"/api/clubs/{resolved_club_id}/final-standings")

    if json_output:
        print_json(data)
        return

    if not data:
        click.echo("No finalized seasons found for this club.")
        return

    club_name = data[0].get("club_name") if isinstance(data[0], dict) else None
    if club_name:
        click.echo(f"Final standings history for {club_name}")

    rows = [
        {
            "season": f"{row.get('year_label')} (#{row.get('season_number')})",
            "rank": row.get("rank"),
            "pts": row.get("points"),
            "played": row.get("played"),
            "won": row.get("won"),
            "drawn": row.get("drawn"),
            "lost": row.get("lost"),
            "gf": row.get("gf"),
            "ga": row.get("ga"),
            "gd": row.get("gd"),
        }
        for row in data
    ]
    print_table(rows, ["season", "rank", "pts", "played", "won", "drawn", "lost", "gf", "ga", "gd"], format_numbers=True)


@show.command("finance")
@click.option("--season-id", help="Season UUID/season_number/year_label (defaults to config)")
@click.option("--club-id", help="Club UUID or name (defaults to config)")
@click.option("--month-index", type=int, help="Filter by month_index (1-12)")
@click.option("--json-output", is_flag=True, help="Print raw JSON")
@click.pass_context
def show_finance(ctx: click.Context, season_id: Optional[str], club_id: Optional[str], month_index: Optional[int], json_output: bool) -> None:
    """Show financial state and ledger for a club."""
    config: CliConfig = ctx.obj["config"]
    timeout: float = ctx.obj["timeout"]
    verbose: bool = ctx.obj["verbose"]

    with _with_client(config, timeout, verbose) as client:
        season_id = _resolve_season_identifier(client, config, season_id)
        club_id = _resolve_club_identifier(client, config, club_id)

        params = {"season_id": season_id}
        if month_index is not None:
            params["month_index"] = month_index

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

    # Latest month when not specified
    all_months = sorted({e.get("month_index") for e in ledger or [] if e.get("month_index") is not None})
    target_month = month_index if month_index is not None else (all_months[-1] if all_months else None)

    # Map for normalization of kinds (merge fixture-specific keys)
    def normalize_kind(kind: str) -> str:
        # Hide internal marker entries
        if kind == "additional_reinforcement_applied":
            return None

        if kind == "next_home_promo_expense":
            return "promo_expense"
        
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

    click.echo(f"Season : {format_number(season_index)}")
    click.echo(f"{month_label}(month_index={format_number(target_month)})")
    click.echo(f"Balance: {format_number(round_amount(balance))}")

    # Prepare ledger grouping
    if not ledger:
        click.echo("No ledger entries found.")
        return

    # Filter ledger for target month
    month_entries = [e for e in ledger if e.get("month_index") == target_month]

    # Monthly per-item breakdown
    monthly_by_kind: Dict[str, float] = {}
    for entry in month_entries:
        kind = normalize_kind(entry.get("kind") or "(unknown)")
        if kind is None:  # Skip hidden kinds
            continue
        amt = entry.get("amount", 0)
        monthly_by_kind[kind] = monthly_by_kind.get(kind, 0) + amt

    preferred_order = [
        "sponsor_annual",
        "sponsor",
        "ticket_rev",
        "merchandise_rev",
        "distribution_revenue",
        "prize_revenue",
        "academy_transfer_fee",
        "reinforcement_cost",
        "team_operation_cost",
        "academy_cost",
        "match_operation_cost",
        "sales_expense",
        "promo_expense",
        "merchandise_cost",
        "hometown_expense",
        "staff_cost",
        "admin_cost",
        "tax",
    ]
    preferred_index = {key: idx for idx, key in enumerate(preferred_order)}

    def sort_key(item: tuple[str, float]) -> tuple[int, str]:
        kind, _ = item
        return (preferred_index.get(kind, len(preferred_order)), kind)

    monthly_table = []
    for k, v in sorted(monthly_by_kind.items(), key=sort_key):
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
        print_table(monthly_table, ["kind", "income", "expense", "net"], format_numbers=True)
    else:
        click.echo("No entries for the target month.")

    # Season cumulative by normalized kind
    kind_rows: Dict[str, float] = {}
    for entry in ledger:
        kind = normalize_kind(entry.get("kind") or "(unknown)")
        if kind is None:  # Skip hidden kinds
            continue
        amount = entry.get("amount", 0)
        kind_rows[kind] = kind_rows.get(kind, 0) + amount

    income_rows = []
    expense_rows = []
    for k, v in sorted(kind_rows.items(), key=sort_key):
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
    print_table(cumulative_table, ["kind", "income", "expense", "net"], format_numbers=True)


@show.command("tax")
@click.option("--season-id", help="Season UUID/season_number/year_label (defaults to config)")
@click.option("--club-id", help="Club UUID or name (defaults to config)")
@click.option("--json-output", is_flag=True, help="Print raw JSON")
@click.pass_context
def show_tax(ctx: click.Context, season_id: Optional[str], club_id: Optional[str], json_output: bool) -> None:
    """Show tax due for the current season (based on previous season profit)."""
    config: CliConfig = ctx.obj["config"]
    timeout: float = ctx.obj["timeout"]
    verbose: bool = ctx.obj["verbose"]

    with _with_client(config, timeout, verbose) as client:
        season_id = _resolve_season_identifier(client, config, season_id)
        club_id = _resolve_club_identifier(client, config, club_id)
        data = client.get(f"/api/clubs/{club_id}/finance/tax-info", params={"season_id": season_id})

    if json_output:
        print_json(data)
        return

    if not isinstance(data, dict):
        print_json(data)
        return

    rows = [
        {
            "season": data.get("season_number"),
            "year_label": data.get("year_label"),
            "prev_season": data.get("previous_season_number"),
            "prev_year": data.get("previous_year_label"),
            "prev_profit": data.get("previous_season_profit"),
            "tax_rate": data.get("tax_rate"),
            "tax_due": data.get("tax_due"),
            "payment_month": f"{data.get('payment_month_name')}({data.get('payment_month_index')})",
        }
    ]
    print_table(rows, ["season", "year_label", "prev_season", "prev_year", "prev_profit", "tax_rate", "tax_due", "payment_month"], format_numbers=True)


@show.command("team_power")
@click.option("--season-id", help="Season UUID/season_number/year_label (defaults to config)")
@click.option("--json-output", is_flag=True, help="Print raw JSON")
@click.pass_context
def show_team_power(ctx: click.Context, season_id: Optional[str], json_output: bool) -> None:
    config: CliConfig = ctx.obj["config"]
    timeout: float = ctx.obj["timeout"]
    verbose: bool = ctx.obj["verbose"]
    with _with_client(config, timeout, verbose) as client:
        season_id = _resolve_season_identifier(client, config, season_id)
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
        print_table(rows, ["club", "team_power"], format_numbers=True)
    else:
        print_json(data)


@show.command("disclosure")
@click.option("--season-id", help="Season UUID/season_number/year_label (defaults to config)")
@click.option(
    "--type",
    "disclosure_type",
    type=click.Choice(["financial_summary", "team_power_december", "team_power_july"], case_sensitive=False),
    required=True,
    help="Disclosure type",
)
@click.option("--json-output", is_flag=True, help="Print raw JSON")
@click.pass_context
def show_disclosure(ctx: click.Context, season_id: Optional[str], disclosure_type: str, json_output: bool) -> None:
    config: CliConfig = ctx.obj["config"]
    timeout: float = ctx.obj["timeout"]
    verbose: bool = ctx.obj["verbose"]
    with _with_client(config, timeout, verbose) as client:
        season_id = _resolve_season_identifier(client, config, season_id)
        data = client.get(f"/api/seasons/{season_id}/disclosures/{disclosure_type}")
        season_info = None
        if not json_output and disclosure_type == "financial_summary":
            season_info = client.get(f"/api/seasons/{season_id}")

    if json_output:
        print_json(data)
        return

    payload = data.get("disclosed_data") if isinstance(data, dict) else None
    if payload is None:
        print_json(data)
        return

    if disclosure_type == "financial_summary":
        clubs = payload.get("clubs") if isinstance(payload, dict) else None
        if not clubs:
            print_json(payload)
            return

        season_label = season_info.get("year_label") if isinstance(season_info, dict) else None
        season_number = season_info.get("season_number") if isinstance(season_info, dict) else None
        if season_label or season_number is not None:
            if season_label and season_number is not None:
                click.echo(f"対象シーズン: {season_label} (season{season_number})")
            elif season_label:
                click.echo(f"対象シーズン: {season_label}")
            else:
                click.echo(f"対象シーズン: season{season_number}")

        entry_keys_set = set()
        for entry in clubs:
            if isinstance(entry, dict):
                entry_keys_set.update(entry.keys())
        entry_keys_set.difference_update({"club_id", "club_name"})
        entry_keys = list(entry_keys_set)

        preferred_order = ["fiscal_year", "total_revenue", "total_expense", "net_income", "ending_balance"]
        ordered_keys: List[str] = []
        for key in preferred_order:
            if key in entry_keys:
                ordered_keys.append(key)
        for key in entry_keys:
            if key not in ordered_keys:
                ordered_keys.append(key)

        club_names = [
            entry.get("club_name") or entry.get("club_id") or f"club_{idx + 1}"
            for idx, entry in enumerate(clubs)
            if isinstance(entry, dict)
        ]
        columns = ["item", *club_names]
        rows: List[Dict[str, Any]] = []
        for key in ordered_keys:
            row: Dict[str, Any] = {"item": key}
            for club_name, entry in zip(club_names, clubs):
                if isinstance(entry, dict):
                    row[club_name] = entry.get(key)
            rows.append(row)

        print_table(rows, columns, format_numbers=True)
        return

    if isinstance(payload, list):
        if payload and isinstance(payload[0], dict):
            columns = list(payload[0].keys())
            print_table(payload, columns, format_numbers=True)
            return
        print_json(payload)
        return

    if isinstance(payload, dict):
        print_table([payload], list(payload.keys()), format_numbers=True)
        return

    print_json(payload)


@show.command("staff")
@click.option("--club-id", help="Club UUID or name (defaults to config)")
@click.option("--json-output", is_flag=True, help="Print raw JSON")
@click.pass_context
def show_staff(ctx: click.Context, club_id: Optional[str], json_output: bool) -> None:
    config: CliConfig = ctx.obj["config"]
    timeout: float = ctx.obj["timeout"]
    verbose: bool = ctx.obj["verbose"]
    with _with_client(config, timeout, verbose) as client:
        club_id = _resolve_club_identifier(client, config, club_id)
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
    print_table(rows, ["role", "count", "salary", "next", "hiring_target", "updated_at"], format_numbers=True)


@show.command("staff_history")
@click.option("--club-id", help="Club UUID or name (defaults to config)")
@click.option("--season-id", help="Season UUID/season_number/year_label (optional filter)")
@click.option("--from", "from_month", help="From YYYY-MM (mapped to month_index)")
@click.option("--to", "to_month", help="To YYYY-MM (mapped to month_index)")
@click.option("--json-output", is_flag=True, help="Print raw JSON")
@click.pass_context
def show_staff_history(ctx: click.Context, club_id: Optional[str], season_id: Optional[str], from_month: Optional[str], to_month: Optional[str], json_output: bool) -> None:
    config: CliConfig = ctx.obj["config"]
    timeout: float = ctx.obj["timeout"]
    verbose: bool = ctx.obj["verbose"]
    with _with_client(config, timeout, verbose) as client:
        club_id = _resolve_club_identifier(client, config, club_id)
        resolved_season_id = _resolve_season_identifier(client, config, season_id) if season_id or config.season_id else None

        params: Dict[str, Any] = {}
        if resolved_season_id:
            params["season_id"] = resolved_season_id
        fm = ensure_month_bounds(parse_month_to_index(from_month) if from_month else None, "from_month")
        tm = ensure_month_bounds(parse_month_to_index(to_month) if to_month else None, "to_month")
        if fm is not None:
            params["from_month"] = fm
        if tm is not None:
            params["to_month"] = tm

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
    print_table(rows, ["season", "month", "month_name", "total_cost", "created_at"], format_numbers=True)


@show.command("current_input")
@click.option("--season-id", help="Season UUID/season_number/year_label (defaults to config)")
@click.option("--club-id", help="Club UUID or name (defaults to config)")
@click.option("--json-output", is_flag=True, help="Print raw JSON")
@click.pass_context
def show_current_input(ctx: click.Context, season_id: Optional[str], club_id: Optional[str], json_output: bool) -> None:
    config: CliConfig = ctx.obj["config"]
    timeout: float = ctx.obj["timeout"]
    verbose: bool = ctx.obj["verbose"]
    with _with_client(config, timeout, verbose) as client:
        season_id = _resolve_season_identifier(client, config, season_id)
        club_id = _resolve_club_identifier(client, config, club_id)
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
    print_table([summary], ["season_number", "month_index", "month_name", "decision_state", "committed_at"], format_numbers=True)
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
@click.option("--season-id", help="Season UUID/season_number/year_label (defaults to config)")
@click.option("--club-id", help="Club UUID or name (defaults to config)")
@click.option("--from", "from_month", help="From YYYY-MM (mapped to month_index)")
@click.option("--to", "to_month", help="To YYYY-MM (mapped to month_index)")
@click.option("--json-output", is_flag=True, help="Print raw JSON")
@click.pass_context
def show_history(ctx: click.Context, season_id: Optional[str], club_id: Optional[str], from_month: Optional[str], to_month: Optional[str], json_output: bool) -> None:
    config: CliConfig = ctx.obj["config"]
    timeout: float = ctx.obj["timeout"]
    verbose: bool = ctx.obj["verbose"]
    with _with_client(config, timeout, verbose) as client:
        season_id = _resolve_season_identifier(client, config, season_id)
        club_id = _resolve_club_identifier(client, config, club_id)

        params: Dict[str, Any] = {}
        fm = ensure_month_bounds(parse_month_to_index(from_month) if from_month else None, "from_month")
        tm = ensure_month_bounds(parse_month_to_index(to_month) if to_month else None, "to_month")
        if fm is not None:
            params["from_month"] = fm
        if tm is not None:
            params["to_month"] = tm

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
    print_table(rows, ["month", "month_name", "state", "committed_at"], format_numbers=True)


@show.command("fan_indicator")
@click.option("--club-id", "club_id", help="Club UUID or name (defaults to config)")
@click.option("--club", "club_override", help="Club identifier (alias; accepts UUID or name)")
@click.option("--season-id", help="Season UUID/season_number/year_label (defaults to config)")
@click.option("--from", "from_month", help="From YYYY-MM (mapped to month_index; optional)")
@click.option("--to", "to_month", help="To YYYY-MM (mapped to month_index; optional)")
@click.option("--json-output", is_flag=True, help="Print raw JSON")
@click.pass_context
def show_fan_indicator(ctx: click.Context, club_id: Optional[str], club_override: Optional[str], season_id: Optional[str], from_month: Optional[str], to_month: Optional[str], json_output: bool) -> None:
    config: CliConfig = ctx.obj["config"]
    timeout: float = ctx.obj["timeout"]
    verbose: bool = ctx.obj["verbose"]
    with _with_client(config, timeout, verbose) as client:
        season_id = _resolve_season_identifier(client, config, season_id)
        resolved_club = club_override or club_id or config.club_id
        resolved_club = _resolve_club_identifier(client, config, resolved_club)

        params: Dict[str, Any] = {"season_id": season_id}
        fm = ensure_month_bounds(parse_month_to_index(from_month) if from_month else None, "from_month")
        tm = ensure_month_bounds(parse_month_to_index(to_month) if to_month else None, "to_month")
        if fm is not None:
            params["from_month"] = fm
        if tm is not None:
            params["to_month"] = tm

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
    print_table(rows, ["club", "followers"], format_numbers=True)


@show.command("sponsor_status")
@click.option("--club-id", help="Club UUID or name (defaults to config)")
@click.option("--season-id", help="Season UUID/season_number/year_label (defaults to config)")
@click.option("--pipeline", is_flag=True, help="Show pipeline status (default)")
@click.option("--next", "next_flag", is_flag=True, help="Show next-year sponsor info")
@click.option("--json-output", is_flag=True, help="Print raw JSON")
@click.pass_context
def show_sponsor_status(ctx: click.Context, club_id: Optional[str], season_id: Optional[str], pipeline: bool, next_flag: bool, json_output: bool) -> None:
    config: CliConfig = ctx.obj["config"]
    timeout: float = ctx.obj["timeout"]
    verbose: bool = ctx.obj["verbose"]
    with _with_client(config, timeout, verbose) as client:
        season_id = _resolve_season_identifier(client, config, season_id)
        club_id = _resolve_club_identifier(client, config, club_id)

        endpoint: str
        if next_flag:
            endpoint = f"/api/sponsors/seasons/{season_id}/clubs/{club_id}/next-sponsor"
        else:
            endpoint = f"/api/sponsors/seasons/{season_id}/clubs/{club_id}/pipeline"

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
        print_table(rows, ["next_total", "next_exist", "next_new", "unit_price", "expected_revenue", "finalized"], format_numbers=True)
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
        print_table(rows, ["current", "confirmed_exist", "confirmed_new", "total_confirmed", "next_exist_target", "next_new_target", "next_total"], format_numbers=True)


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
