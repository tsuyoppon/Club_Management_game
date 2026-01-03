from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db, require_role
from app.db.models import (
    Club,
    ClubFanbaseState,
    DecisionState,
    Fixture,
    Game,
    Match,
    MatchStatus,
    MembershipRole,
    Season,
    SeasonStatus,
    Turn,
    TurnDecision,
    TurnState,
    month_mappings,
)
from app.schemas import FixtureGenerateRequest, SeasonCreate, SeasonRead, StandingRead, SeasonStatusRead, FixtureView
from app.services.fixtures import generate_round_robin
from app.services.standings import StandingsCalculator
from app.services.season_finalize import SeasonFinalizer
from app.services import reinforcement, sponsor, academy
from app.services.public_disclosure import copy_team_power_july_to_new_season

router = APIRouter(prefix="/seasons", tags=["seasons"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _latest_running_season(db: Session, game_id: str) -> Optional[Season]:
    season = (
        db.query(Season)
        .filter(Season.game_id == game_id, Season.status == SeasonStatus.running)
        .order_by(Season.created_at.desc())
        .first()
    )
    if season:
        return season

    # Fallback: latest season regardless of status (e.g., all finished)
    return (
        db.query(Season)
        .filter(Season.game_id == game_id)
        .order_by(Season.created_at.desc())
        .first()
    )


@router.get("/games/{game_id}/latest", response_model=SeasonRead)
def get_latest_season(
    game_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    # Require at least viewer role for the game
    require_role(user, db, game_id, MembershipRole.club_viewer)

    season = _latest_running_season(db, game_id)
    if not season:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No seasons found for game")

    return season


# ---------------------------------------------------------------------------
# Internal helpers (used by API routes and auto-season transition)
# ---------------------------------------------------------------------------


def create_season_core(db: Session, game: Game, year_label: str) -> Season:
    """
    Create a new season with default turns/decisions.

    - First turn is set to `collecting` (opened)
    - All other turns start as `open`
    - If previous season exists (numeric year), propagate reinforcement budget and
      copy fanbase state forward so that hidden variables persist across seasons.
    - Idempotent per (game_id, year_label).
    """

    existing = db.query(Season).filter(Season.game_id == game.id, Season.year_label == year_label).first()
    if existing:
        return existing

    season = Season(game_id=game.id, year_label=year_label, status=SeasonStatus.running)
    db.add(season)
    db.commit()
    db.refresh(season)

    month_defs = month_mappings()
    turns: List[Turn] = []
    for month_index, month_name, month_number in month_defs:
        turn_state = TurnState.collecting if month_index == 1 else TurnState.open
        turn = Turn(
            season_id=season.id,
            month_index=month_index,
            month_name=month_name,
            month_number=month_number,
            turn_state=turn_state,
            opened_at=datetime.utcnow() if turn_state == TurnState.collecting else None,
        )
        turns.append(turn)
        db.add(turn)
    db.commit()

    clubs = db.query(Club).filter(Club.game_id == game.id).all()
    for turn in turns:
        for club in clubs:
            decision = TurnDecision(turn_id=turn.id, club_id=club.id, decision_state=DecisionState.draft)
            db.add(decision)
    db.commit()

    # 前季オフシーズン入力を新シーズンの強化費初期値に反映
    prev_season = None
    try:
        prev_label = str(int(year_label) - 1)
        prev_season = db.query(Season).filter(Season.game_id == game.id, Season.year_label == prev_label).first()
    except Exception:
        prev_season = None

    if prev_season:
        for club in clubs:
            prev_plan = reinforcement.ensure_reinforcement_plan(db, club.id, prev_season.id)
            plan = reinforcement.ensure_reinforcement_plan(db, club.id, season.id)
            plan.annual_budget = prev_plan.next_season_budget
        db.commit()

        # Fanbaseをシーズン跨ぎで引き継ぐ（初期値を前季終値で開始）
        prev_states = db.query(ClubFanbaseState).filter(ClubFanbaseState.season_id == prev_season.id).all()
        for prev_state in prev_states:
            copied = ClubFanbaseState(
                club_id=prev_state.club_id,
                season_id=season.id,
                fb_count=prev_state.fb_count,
                fb_rate=prev_state.fb_rate,
                cumulative_promo=prev_state.cumulative_promo,
                cumulative_ht=prev_state.cumulative_ht,
                last_ht_spend=prev_state.last_ht_spend,
                followers_public=prev_state.followers_public,
            )
            db.add(copied)
        db.commit()

        # Team Power July: 前シーズンの7月公開値を新シーズンに引き継ぐ
        copy_team_power_july_to_new_season(db, prev_season.id, season.id)
        db.commit()

    # Sponsor state: inherit final next_count (or count) and keep pipelines consistent with Section 10
    for club in clubs:
        sponsor.ensure_sponsor_state(db, club.id, season.id)

    # Academy state: carry cumulative investment and planned budget forward
    for club in clubs:
        academy.ensure_academy_state(db, club.id, season.id)

    db.commit()

    db.refresh(season)
    return season


def generate_fixtures_core(db: Session, season: Season, force: bool = False) -> int:
    """Generate fixtures and matches for a season. Returns count of fixtures."""
    existing = db.query(Fixture).filter(Fixture.season_id == season.id).all()
    if existing and not force:
        return len(existing)

    if existing and force:
        for row in existing:
            db.delete(row)
        db.commit()

    clubs = db.query(Club).filter(Club.game_id == season.game_id).all()
    if not clubs:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No clubs to schedule")

    specs = generate_round_robin([club.id for club in clubs], match_months=10)
    month_lookup: Dict[int, str] = {m[0]: m[1] for m in month_mappings()}

    for spec in specs:
        fixture = Fixture(
            season_id=season.id,
            match_month_index=spec.match_month_index,
            match_month_name=month_lookup.get(spec.match_month_index, ""),
            home_club_id=spec.home_club_id,
            away_club_id=spec.away_club_id,
            is_bye=spec.is_bye,
            bye_club_id=spec.bye_club_id,
        )
        db.add(fixture)
        db.flush()

        match = Match(fixture_id=fixture.id, status=MatchStatus.scheduled)
        db.add(match)

    db.commit()
    return db.query(Fixture).filter(Fixture.season_id == season.id).count()


@router.post("/games/{game_id}", response_model=SeasonRead)
def create_season(
    game_id: str,
    payload: SeasonCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    require_role(user, db, game_id, MembershipRole.gm)
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")

    return create_season_core(db, game, payload.year_label)


@router.post("/{season_id}/fixtures/generate", status_code=status.HTTP_201_CREATED)
def generate_fixtures(
    season_id: str,
    payload: FixtureGenerateRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    season = db.query(Season).filter(Season.id == season_id).first()
    if not season:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Season not found")

    require_role(user, db, season.game_id, MembershipRole.gm)

    count = generate_fixtures_core(db, season, force=payload.force)
    return {"fixtures": count}


@router.get("/{season_id}/schedule")
def season_schedule(
    season_id: str,
    month_index: Optional[int] = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    season = db.query(Season).filter(Season.id == season_id).first()
    if not season:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Season not found")
    require_role(user, db, season.game_id, MembershipRole.gm)

    fixtures_query = db.query(Fixture).filter(Fixture.season_id == season_id)
    if month_index is not None:
        fixtures_query = fixtures_query.filter(Fixture.match_month_index == month_index)

    fixtures = fixtures_query.order_by(Fixture.match_month_index).all()
    grouped: Dict[int, List[dict]] = defaultdict(list)
    for fixture in fixtures:
        grouped[fixture.match_month_index].append(
            {
                "home_club_id": str(fixture.home_club_id) if fixture.home_club_id else None,
                "away_club_id": str(fixture.away_club_id) if fixture.away_club_id else None,
                "bye_club_id": str(fixture.bye_club_id) if fixture.bye_club_id else None,
                "is_bye": fixture.is_bye,
                "match_id": str(fixture.match.id) if fixture.match else None,
                "fixture_id": str(fixture.id),
                "status": fixture.match.status if fixture.match else None,
                "home_goals": fixture.match.home_goals if fixture.match else None,
                "away_goals": fixture.match.away_goals if fixture.match else None,
                "weather": fixture.weather,
                "home_attendance": fixture.home_attendance,
                "away_attendance": fixture.away_attendance,
                "total_attendance": fixture.total_attendance,
            }
        )
    return grouped


@router.get("/{season_id}/clubs/{club_id}/schedule")
def club_schedule(
    season_id: str,
    club_id: str,
    month_index: Optional[int] = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    season = db.query(Season).filter(Season.id == season_id).first()
    if not season:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Season not found")
    require_role(user, db, season.game_id, MembershipRole.club_viewer, club_id)

    club_uuid = uuid.UUID(str(club_id))
    fixtures_query = db.query(Fixture).filter(
        Fixture.season_id == season_id,
        ((Fixture.home_club_id == club_uuid) | (Fixture.away_club_id == club_uuid) | (Fixture.bye_club_id == club_uuid)),
    )
    if month_index is not None:
        fixtures_query = fixtures_query.filter(Fixture.match_month_index == month_index)

    fixtures = fixtures_query.order_by(Fixture.match_month_index).all()

    # Preload club names to enrich opponent display
    club_rows = db.query(Club).filter(Club.game_id == season.game_id).all()
    club_name_map = {row.id: row.name for row in club_rows}
    club_short_name_map = {row.id: row.short_name for row in club_rows}

    schedule = []
    month_lookup: Dict[int, str] = {m[0]: m[1] for m in month_mappings()}
    for fixture in fixtures:
        is_home = fixture.home_club_id == club_uuid
        opponent = None
        opponent_name = None
        opponent_short_name = None
        if fixture.home_club_id and fixture.away_club_id:
            opponent = str(fixture.away_club_id if is_home else fixture.home_club_id)
            opp_uuid = fixture.away_club_id if is_home else fixture.home_club_id
            opponent_name = club_name_map.get(opp_uuid)
            opponent_short_name = club_short_name_map.get(opp_uuid)
        schedule.append(
            {
                "month_index": fixture.match_month_index,
                "month_name": month_lookup.get(fixture.match_month_index, ""),
                "opponent": opponent,
                "opponent_name": opponent_name,
                "opponent_short_name": opponent_short_name,
                "home": is_home,
                "is_bye": fixture.is_bye,
                "status": fixture.match.status if fixture.match else None,
                "home_goals": fixture.match.home_goals if fixture.match else None,
                "away_goals": fixture.match.away_goals if fixture.match else None,
                "weather": fixture.weather,
                "home_attendance": fixture.home_attendance,
                "away_attendance": fixture.away_attendance,
                "total_attendance": fixture.total_attendance,
            }
        )

    return schedule


@router.get("/{season_id}/fixtures/{fixture_id}", response_model=FixtureView)
def get_fixture_detail(
    season_id: str,
    fixture_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    season = db.query(Season).filter(Season.id == season_id).first()
    if not season:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Season not found")
    require_role(user, db, str(season.game_id), MembershipRole.club_viewer)
    fixture = db.query(Fixture).filter(Fixture.id == fixture_id, Fixture.season_id == season_id).first()
    if not fixture:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fixture not found")

    # Ensure FixtureView.status is populated from related Match
    fixture.status = fixture.match.status if fixture.match else MatchStatus.scheduled
    return fixture


@router.get("/{season_id}/standings", response_model=List[StandingRead])
def get_season_standings(
    season_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    season = db.query(Season).filter(Season.id == season_id).first()
    if not season:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Season not found")
    
    require_role(user, db, str(season.game_id), MembershipRole.club_viewer)

    if season.is_finalized:
        finalizer = SeasonFinalizer(db, season.id)
        return finalizer._get_stored_standings()

    calculator = StandingsCalculator(db, season.id)
    return calculator.calculate()


@router.get("/{season_id}/status", response_model=SeasonStatusRead)
def get_season_status_endpoint(
    season_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    season = db.query(Season).filter(Season.id == season_id).first()
    if not season:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Season not found")
    
    require_role(user, db, str(season.game_id), MembershipRole.club_viewer)
    
    finalizer = SeasonFinalizer(db, uuid.UUID(season_id))
    return finalizer.get_status()


@router.post("/{season_id}/finalize", response_model=List[StandingRead])
def finalize_season_endpoint(
    season_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    season = db.query(Season).filter(Season.id == season_id).first()
    if not season:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Season not found")
    
    require_role(user, db, str(season.game_id), MembershipRole.gm)
    
    finalizer = SeasonFinalizer(db, uuid.UUID(season_id))
    return finalizer.finalize()


@router.get("/{season_id}/prizes")
def get_season_prizes(
    season_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """
    シーズンの賞金情報を取得（6月以降にアクセス可能）
    """
    season = db.query(Season).filter(Season.id == season_id).first()
    if not season:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Season not found")
    
    require_role(user, db, str(season.game_id), MembershipRole.club_viewer)
    
    # Check if season is past June (month_index >= 11)
    current_turn = (
        db.query(Turn)
        .filter(Turn.season_id == season_id, Turn.turn_state != TurnState.acked)
        .order_by(Turn.month_index)
        .first()
    )
    
    # If no active turn or current_turn is past June (11+), allow access
    if current_turn and current_turn.month_index < 11:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Prize information is only available after June (month 11)"
        )
    
    from app.services.prize import get_season_prize_info
    return get_season_prize_info(db, uuid.UUID(season_id))
