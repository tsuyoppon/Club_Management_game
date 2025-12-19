from collections import defaultdict
from datetime import datetime
from typing import Dict, List
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
from app.schemas import FixtureGenerateRequest, SeasonCreate, SeasonRead
from app.services.fixtures import generate_round_robin

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
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    season = db.query(Season).filter(Season.id == season_id).first()
    if not season:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Season not found")
    require_role(user, db, season.game_id, MembershipRole.gm)

    fixtures = db.query(Fixture).filter(Fixture.season_id == season_id).order_by(Fixture.match_month_index).all()
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
            }
        )
    return grouped


@router.get("/{season_id}/clubs/{club_id}/schedule")
def club_schedule(
    season_id: str,
    club_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    season = db.query(Season).filter(Season.id == season_id).first()
    if not season:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Season not found")
    require_role(user, db, season.game_id, MembershipRole.club_viewer, club_id)

    club_uuid = uuid.UUID(str(club_id))
    fixtures = (
        db.query(Fixture)
        .filter(
            Fixture.season_id == season_id,
            ((Fixture.home_club_id == club_uuid) | (Fixture.away_club_id == club_uuid) | (Fixture.bye_club_id == club_uuid)),
        )
        .order_by(Fixture.match_month_index)
        .all()
    )

    schedule = []
    month_lookup: Dict[int, str] = {m[0]: m[1] for m in month_mappings()}
    for fixture in fixtures:
        is_home = fixture.home_club_id == club_uuid
        opponent = None
        if fixture.home_club_id and fixture.away_club_id:
            opponent = str(fixture.away_club_id if is_home else fixture.home_club_id)
        schedule.append(
            {
                "month_index": fixture.match_month_index,
                "month_name": month_lookup.get(fixture.match_month_index, ""),
                "opponent": opponent,
                "home": is_home,
                "is_bye": fixture.is_bye,
                "status": fixture.match.status if fixture.match else None,
                "home_goals": fixture.match.home_goals if fixture.match else None,
                "away_goals": fixture.match.away_goals if fixture.match else None,
            }
        )

    return schedule

