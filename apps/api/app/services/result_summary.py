from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.db import models
from app.services.standings import StandingsCalculator


SUMMARY_SCHEMA_VERSION = 1
DECISION_FIELDS = (
    "sales_expense",
    "promo_expense",
    "hometown_expense",
    "next_home_promo",
    "sales_allocation_new",
    "additional_reinforcement",
    "reinforcement_budget",
    "staff_plan",
    "academy_budget",
)


def _number(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _rank_optional(rows: list[dict[str, Any]], value_key: str, rank_key: str) -> None:
    ranked = sorted(
        (row for row in rows if row.get(value_key) is not None),
        key=lambda row: row[value_key],
        reverse=True,
    )
    previous = object()
    current_rank = 0
    for index, row in enumerate(ranked, start=1):
        value = row[value_key]
        if value != previous:
            current_rank = index
            previous = value
        row[rank_key] = current_rank
    for row in rows:
        row.setdefault(rank_key, None)


def active_completion(db: Session, game_id: UUID) -> Optional[models.GameCompletion]:
    return (
        db.query(models.GameCompletion)
        .filter(
            models.GameCompletion.game_id == game_id,
            models.GameCompletion.reopened_at.is_(None),
        )
        .order_by(models.GameCompletion.completed_at.desc())
        .first()
    )


def completion_eligibility(db: Session, room: models.GameRoom) -> dict[str, Any]:
    blockers: list[str] = []
    if room.game.status != models.GameStatus.active or room.status != "active":
        blockers.append("game_not_active")

    season = (
        db.query(models.Season)
        .filter(models.Season.game_id == room.game_id)
        .order_by(models.Season.season_number.desc(), models.Season.created_at.desc())
        .first()
    )
    turn = None
    if not season:
        blockers.append("season_missing")
    else:
        turn = (
            db.query(models.Turn)
            .filter(models.Turn.season_id == season.id, models.Turn.month_index == 12)
            .first()
        )
        if not turn:
            blockers.append("july_turn_missing")
        elif turn.turn_state != models.TurnState.resolved:
            blockers.append("july_not_resolved")

    clubs = db.query(models.Club.id).filter(models.Club.game_id == room.game_id).all()
    club_ids = {row.id for row in clubs}
    acked_ids: set[UUID] = set()
    if turn:
        acked_ids = {
            row.club_id
            for row in db.query(models.TurnAck.club_id)
            .filter(models.TurnAck.turn_id == turn.id, models.TurnAck.ack.is_(True))
            .distinct()
            .all()
        }
    if club_ids and acked_ids != club_ids:
        blockers.append("clubs_not_acknowledged")

    if season:
        from app.services.season_finalize import SeasonFinalizer

        status = SeasonFinalizer(db, season.id).get_status()
        if not status["is_completed"]:
            blockers.append("matches_incomplete")

    return {
        "eligible": not blockers,
        "blockers": blockers,
        "season_id": str(season.id) if season else None,
        "turn_id": str(turn.id) if turn else None,
    }


def _team_power_by_club(db: Session, season_id: UUID) -> dict[str, float]:
    disclosure = (
        db.query(models.SeasonPublicDisclosure)
        .filter(
            models.SeasonPublicDisclosure.season_id == season_id,
            models.SeasonPublicDisclosure.disclosure_type == "team_power_july",
        )
        .first()
    )
    if not disclosure:
        return {}
    return {
        str(row.get("club_id")): float(row.get("team_power"))
        for row in (disclosure.disclosed_data or {}).get("clubs", [])
        if row.get("club_id") and row.get("team_power") is not None
    }


def _season_metric(
    db: Session,
    season: models.Season,
    club: models.Club,
    standing: Optional[dict[str, Any]],
) -> dict[str, Any]:
    snapshots = (
        db.query(models.ClubFinancialSnapshot)
        .filter(
            models.ClubFinancialSnapshot.season_id == season.id,
            models.ClubFinancialSnapshot.club_id == club.id,
        )
        .order_by(models.ClubFinancialSnapshot.month_index)
        .all()
    )
    income = sum((_number(row.income_total) or 0) for row in snapshots)
    expense = sum((_number(row.expense_total) or 0) for row in snapshots)
    closing = _number(snapshots[-1].closing_balance) if snapshots else None
    home_fixtures = (
        db.query(models.Fixture)
        .filter(
            models.Fixture.season_id == season.id,
            models.Fixture.home_club_id == club.id,
            models.Fixture.is_bye.is_(False),
        )
        .all()
    )
    attendances = [
        fixture.home_attendance
        for fixture in home_fixtures
        if fixture.home_attendance is not None
    ]
    fanbase = db.query(models.ClubFanbaseState).filter_by(club_id=club.id, season_id=season.id).first()
    sponsor = db.query(models.ClubSponsorState).filter_by(club_id=club.id, season_id=season.id).first()
    bankruptcy = db.query(models.ClubBankruptcyState).filter_by(club_id=club.id, season_id=season.id).first()
    penalty = (
        db.query(models.ClubPointPenalty)
        .filter_by(club_id=club.id, season_id=season.id)
        .all()
    )
    team_power = _team_power_by_club(db, season.id).get(str(club.id))
    return {
        "season_id": str(season.id),
        "season_number": season.season_number,
        "year_label": season.year_label,
        "rank": standing.get("rank") if standing else None,
        "points": standing.get("points") if standing else None,
        "revenue": income if snapshots else None,
        "expense": expense if snapshots else None,
        "net": income + expense if snapshots else None,
        "closing_balance": closing,
        "average_home_attendance": (
            int(sum(attendances) / len(attendances)) if attendances else None
        ),
        "fanbase": fanbase.fb_count if fanbase else None,
        "followers": fanbase.followers_public if fanbase else None,
        "sponsor_count": sponsor.count if sponsor else None,
        "next_sponsor_count": sponsor.next_count if sponsor else None,
        "team_power": team_power,
        "bankrupt": bool(bankruptcy and bankruptcy.is_bankrupt),
        "points_penalty": sum(row.points_deducted for row in penalty),
    }


def _decision_rows(db: Session, season: models.Season, club: models.Club) -> list[dict[str, Any]]:
    records = (
        db.query(models.TurnDecision, models.Turn)
        .join(models.Turn, models.Turn.id == models.TurnDecision.turn_id)
        .filter(
            models.Turn.season_id == season.id,
            models.TurnDecision.club_id == club.id,
            models.TurnDecision.decision_state.in_([
                models.DecisionState.committed,
                models.DecisionState.locked,
            ]),
        )
        .order_by(models.Turn.month_index)
        .all()
    )
    result: list[dict[str, Any]] = []
    for decision, turn in records:
        payload = decision.payload_json or {}
        snapshot = db.query(models.ClubFinancialSnapshot).filter_by(club_id=club.id, turn_id=turn.id).first()
        match_rows = (
            db.query(models.Fixture, models.Match)
            .outerjoin(models.Match, models.Match.fixture_id == models.Fixture.id)
            .filter(
                models.Fixture.season_id == season.id,
                models.Fixture.match_month_index == turn.month_index,
                models.Fixture.is_bye.is_(False),
                (models.Fixture.home_club_id == club.id) | (models.Fixture.away_club_id == club.id),
            )
            .all()
        )
        matches = []
        for fixture, match in match_rows:
            opponent = fixture.away_club if fixture.home_club_id == club.id else fixture.home_club
            matches.append(
                {
                    "opponent": opponent.name if opponent else None,
                    "home": fixture.home_club_id == club.id,
                    "score_for": (
                        match.home_goals if fixture.home_club_id == club.id else match.away_goals
                    ) if match else None,
                    "score_against": (
                        match.away_goals if fixture.home_club_id == club.id else match.home_goals
                    ) if match else None,
                }
            )
        standings = StandingsCalculator(db, season.id).calculate(up_to_month=turn.month_index)
        standing = next((row for row in standings if str(row["club_id"]) == str(club.id)), None)
        result.append(
            {
                "season_id": str(season.id),
                "season_number": season.season_number,
                "year_label": season.year_label,
                "turn_id": str(turn.id),
                "month_index": turn.month_index,
                "month_name": turn.month_name,
                "decision_state": decision.decision_state.value,
                "inputs": {key: payload.get(key) for key in DECISION_FIELDS if key in payload},
                "committed_by": decision.committed_by.display_name if decision.committed_by else None,
                "committed_at": decision.committed_at.isoformat() if decision.committed_at else None,
                "income": _number(snapshot.income_total) if snapshot else None,
                "expense": _number(snapshot.expense_total) if snapshot else None,
                "closing_balance": _number(snapshot.closing_balance) if snapshot else None,
                "rank": standing.get("rank") if standing else None,
                "points": standing.get("points") if standing else None,
                "matches": matches,
            }
        )
    return result


def _highlights(club_name: str, metrics: list[dict[str, Any]], decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    highlights: list[dict[str, Any]] = []

    ranked = [row for row in metrics if row.get("rank") is not None]
    if ranked:
        best = min(ranked, key=lambda row: row["rank"])
        worst = max(ranked, key=lambda row: row["rank"])
        highlights.append({"category": "sporting", "message": f"最高順位はSeason {best['season_number']}の{best['rank']}位でした。"})
        if worst is not best:
            highlights.append({"category": "sporting", "message": f"最低順位はSeason {worst['season_number']}の{worst['rank']}位でした。"})

    balances = [row for row in metrics if row.get("closing_balance") is not None]
    if balances:
        peak = max(balances, key=lambda row: row["closing_balance"])
        bottom = min(balances, key=lambda row: row["closing_balance"])
        highlights.append({"category": "finance", "message": f"期末残高の最高値はSeason {peak['season_number']}の{int(peak['closing_balance']):,}円でした。"})
        highlights.append({"category": "finance", "message": f"期末残高の最低値はSeason {bottom['season_number']}の{int(bottom['closing_balance']):,}円でした。"})

    transitions = list(zip(metrics, metrics[1:]))
    rank_changes = [
        (previous["rank"] - current["rank"], current)
        for previous, current in transitions
        if previous.get("rank") is not None and current.get("rank") is not None
    ]
    if rank_changes:
        delta, current = max(rank_changes, key=lambda item: abs(item[0]))
        if delta:
            highlights.append({"category": "turning_point", "message": f"最大の順位変動はSeason {current['season_number']}の{abs(delta)}つ{'上昇' if delta > 0 else '低下'}でした。"})

    revenue_changes = [
        (current["revenue"] - previous["revenue"], current)
        for previous, current in transitions
        if previous.get("revenue") is not None and current.get("revenue") is not None
    ]
    if revenue_changes:
        delta, current = max(revenue_changes, key=lambda item: item[0])
        highlights.append({"category": "finance", "message": f"最大の売上成長はSeason {current['season_number']}の前期比{int(delta):+,}円でした。"})

    fan_changes = [
        (current["fanbase"] - previous["fanbase"], current)
        for previous, current in transitions
        if previous.get("fanbase") is not None and current.get("fanbase") is not None
    ]
    if fan_changes:
        increase, increased = max(fan_changes, key=lambda item: item[0])
        decrease, decreased = min(fan_changes, key=lambda item: item[0])
        highlights.append({"category": "fanbase", "message": f"最大のファン増加はSeason {increased['season_number']}の前期比{increase:+,}でした。"})
        if decrease != increase:
            highlights.append({"category": "fanbase", "message": f"最大のファン減少はSeason {decreased['season_number']}の前期比{decrease:+,}でした。"})

    attendances = [row for row in metrics if row.get("average_home_attendance") is not None]
    if attendances:
        highest = max(attendances, key=lambda row: row["average_home_attendance"])
        highlights.append({"category": "attendance", "message": f"ホーム平均入場者数の最高値はSeason {highest['season_number']}の{highest['average_home_attendance']:,}人でした。"})

    bankrupt = next((row for row in metrics if row.get("bankrupt")), None)
    if bankrupt:
        highlights.append({"category": "risk", "message": f"Season {bankrupt['season_number']}に債務超過が記録されました。"})

    spend_rows = []
    for row in decisions:
        total = sum(
            float(value)
            for key, value in row.get("inputs", {}).items()
            if key in {"sales_expense", "promo_expense", "hometown_expense", "next_home_promo", "additional_reinforcement", "reinforcement_budget"}
            and isinstance(value, (int, float))
        )
        spend_rows.append((total, row))
    allocation_changes = [
        (current[0] - previous[0], current[1])
        for previous, current in zip(spend_rows, spend_rows[1:])
    ]
    if allocation_changes:
        delta, row = max(allocation_changes, key=lambda item: abs(item[0]))
        highlights.append({"category": "decision", "message": f"最大の資源配分変更はSeason {row['season_number']} {row['month_name']}の前月比{int(delta):+,}円でした（結果との因果を示すものではありません）。"})

    for highlight in highlights:
        highlight["club_name"] = club_name
    return highlights


def build_summary(db: Session, game: models.Game, completed_at: datetime) -> dict[str, Any]:
    from app.services.final_results import get_final_results

    clubs = db.query(models.Club).filter(models.Club.game_id == game.id).order_by(models.Club.created_at).all()
    seasons = (
        db.query(models.Season)
        .filter(models.Season.game_id == game.id, models.Season.is_finalized.is_(True))
        .order_by(models.Season.season_number)
        .all()
    )
    final_results = {row["club_id"]: row for row in get_final_results(db, game.id)}
    final_season = seasons[-1] if seasons else None

    overall: list[dict[str, Any]] = []
    season_standings: list[dict[str, Any]] = []
    standings_by_season: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for season in seasons:
        rows = StandingsCalculator(db, season.id).calculate()
        for row in rows:
            serialized = {
                "season_id": str(season.id),
                "season_number": season.season_number,
                "year_label": season.year_label,
                **{key: row.get(key) for key in ("club_id", "club_name", "rank", "played", "won", "drawn", "lost", "gf", "ga", "gd", "points")},
            }
            serialized["club_id"] = str(serialized["club_id"])
            season_standings.append(serialized)
            standings_by_season[str(season.id)][serialized["club_id"]] = serialized

    club_reviews = []
    all_highlights = []
    for club in clubs:
        metrics = [
            _season_metric(db, season, club, standings_by_season[str(season.id)].get(str(club.id)))
            for season in seasons
        ]
        decisions = [row for season in seasons for row in _decision_rows(db, season, club)]
        highlights = _highlights(club.name, metrics, decisions)
        all_highlights.extend({"club_id": str(club.id), **row} for row in highlights)
        club_reviews.append(
            {
                "club_id": str(club.id),
                "club_name": club.name,
                "season_metrics": metrics,
                "decisions": decisions,
                "highlights": highlights,
            }
        )

        base = dict(final_results.get(str(club.id), {}))
        base.setdefault("club_id", str(club.id))
        base.setdefault("club_name", club.name)
        final_metric = metrics[-1] if metrics and final_season else {}
        base.update(
            {
                "final_fanbase": final_metric.get("fanbase"),
                "final_followers": final_metric.get("followers"),
                "final_sponsor_count": final_metric.get("sponsor_count"),
                "next_sponsor_count": final_metric.get("next_sponsor_count"),
            }
        )
        overall.append(base)

    for value_key, rank_key in (
        ("final_fanbase", "fanbase_rank"),
        ("final_followers", "followers_rank"),
        ("final_sponsor_count", "sponsor_rank"),
    ):
        _rank_optional(overall, value_key, rank_key)

    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "game": {
            "id": str(game.id),
            "name": game.name,
            "created_at": game.created_at.isoformat(),
            "started_at": (
                game.room.started_at.isoformat()
                if game.room and game.room.started_at
                else game.created_at.isoformat()
            ),
            "completed_at": completed_at.isoformat(),
            "seasons_played": len(seasons),
        },
        "overall_results": overall,
        "season_standings": season_standings,
        "club_reviews": club_reviews,
        "highlights": all_highlights,
    }


def filter_summary_for_viewer(
    summary: dict[str, Any],
    *,
    is_host: bool,
    club_id: Optional[UUID],
) -> dict[str, Any]:
    visible = dict(summary)
    if is_host:
        visible["viewer_scope"] = "host_all"
        return visible
    club_key = str(club_id) if club_id else None
    visible["club_reviews"] = [
        review for review in summary.get("club_reviews", []) if review.get("club_id") == club_key
    ]
    visible["highlights"] = [
        row for row in summary.get("highlights", []) if row.get("club_id") == club_key
    ]
    visible["viewer_scope"] = f"club:{club_key}" if club_key else "common_only"
    return visible
