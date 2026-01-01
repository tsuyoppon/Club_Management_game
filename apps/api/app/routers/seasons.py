from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db, require_role
from app.db.models import (
    Club,
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
from app.services import reinforcement

router = APIRouter(prefix="/seasons", tags=["seasons"])


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

    existing_season = db.query(Season).filter(Season.game_id == game_id, Season.year_label == payload.year_label).first()
    if existing_season:
        return existing_season

    season = Season(game_id=game_id, year_label=payload.year_label, status=SeasonStatus.running)
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

    clubs = db.query(Club).filter(Club.game_id == game_id).all()
    for turn in turns:
        for club in clubs:
            decision = TurnDecision(turn_id=turn.id, club_id=club.id, decision_state=DecisionState.draft)
            db.add(decision)
    db.commit()

    # 前季オフシーズン入力を新シーズンの強化費初期値に反映
    prev_season = None
    try:
        prev_label = str(int(payload.year_label) - 1)
        prev_season = db.query(Season).filter(Season.game_id == game_id, Season.year_label == prev_label).first()
    except Exception:
        prev_season = None

    if prev_season:
        for club in clubs:
            prev_plan = reinforcement.ensure_reinforcement_plan(db, club.id, prev_season.id)
            plan = reinforcement.ensure_reinforcement_plan(db, club.id, season.id)
            plan.annual_budget = prev_plan.next_season_budget
        db.commit()

    db.refresh(season)
    return season


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

    existing = db.query(Fixture).filter(Fixture.season_id == season_id).all()
    if existing and not payload.force:
        return {"fixtures": len(existing)}

    if existing and payload.force:
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
            season_id=season_id,
            match_month_index=spec.match_month_index,
            match_month_name=month_lookup.get(spec.match_month_index, ""),
            home_club_id=spec.home_club_id,
            away_club_id=spec.away_club_id,
            is_bye=spec.is_bye,
            bye_club_id=spec.bye_club_id,
        )
        db.add(fixture)
        db.commit()
        db.refresh(fixture)
        if not spec.is_bye:
            match = Match(fixture_id=fixture.id, status=MatchStatus.scheduled)
            db.add(match)
            db.commit()

    return {"fixtures": len(specs)}


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
        
    # Ensure match status is populated in FixtureView
    # FixtureView has status field. Fixture model doesn't have status, Match does.
    # But FixtureView expects status.
    # I need to map it.
    # Pydantic ORM mode might not handle nested relationship attribute mapping automatically if names differ?
    # FixtureView: status: MatchStatus
    # Fixture model: match (relationship) -> status
    # I should probably update FixtureView or handle it manually.
    # But FixtureView is Pydantic.
    # If I return Fixture object, Pydantic tries to read .status
    # Fixture object does NOT have .status.
    # I need to attach it or use a wrapper.
    
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
