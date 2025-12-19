import pytest
from uuid import uuid4
from app.db.models import Match, Club, MatchStatus, Season, Game, GameStatus, Fixture, SeasonFinalStanding
from app.services.season_finalize import SeasonFinalizer
from app.services.standings import StandingsCalculator

def create_game(db):
    g = Game(id=uuid4(), name="Test Game", status=GameStatus.active)
    db.add(g)
    db.commit()
    return g

def create_club(db, name, game_id):
    c = Club(id=uuid4(), name=name, game_id=game_id)
    db.add(c)
    db.commit()
    return c

def create_fixture(db, season_id, home, away, month_index=1, played=False):
    f = Fixture(
        id=uuid4(),
        season_id=season_id,
        match_month_index=month_index,
        match_month_name="Aug",
        home_club_id=home.id,
        away_club_id=away.id
    )
    db.add(f)
    db.commit()
    
    m = Match(
        id=uuid4(),
        fixture_id=f.id,
        status=MatchStatus.played if played else MatchStatus.scheduled,
        home_goals=1 if played else None,
        away_goals=0 if played else None
    )
    db.add(m)
    db.commit()
    return f, m

def test_season_status_incomplete(db):
    game = create_game(db)
    season_id = uuid4()
    season = Season(id=season_id, game_id=game.id, year_label="2025", status="running")
    db.add(season)
    db.commit()
    
    c1 = create_club(db, "A", game.id)
    c2 = create_club(db, "B", game.id)
    
    # 1 played, 1 scheduled
    create_fixture(db, season_id, c1, c2, month_index=1, played=True)
    create_fixture(db, season_id, c2, c1, month_index=2, played=False)
    
    finalizer = SeasonFinalizer(db, season_id)
    status = finalizer.get_status()
    
    assert status["is_completed"] is False
    assert status["total_fixtures"] == 2
    assert status["played_matches"] == 1
    assert status["unplayed_matches"] == 1
    assert status["missing_matches"] == 0

def test_finalize_requires_completion(db):
    game = create_game(db)
    season_id = uuid4()
    season = Season(id=season_id, game_id=game.id, year_label="2025", status="running")
    db.add(season)
    db.commit()
    
    c1 = create_club(db, "A", game.id)
    c2 = create_club(db, "B", game.id)
    
    create_fixture(db, season_id, c1, c2, month_index=1, played=False)
    
    finalizer = SeasonFinalizer(db, season_id)
    
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as excinfo:
        finalizer.finalize()
    
    assert excinfo.value.status_code == 409
    assert "Season is not completed" in excinfo.value.detail

def test_finalize_idempotent(db):
    game = create_game(db)
    season_id = uuid4()
    season = Season(id=season_id, game_id=game.id, year_label="2025", status="running")
    db.add(season)
    db.commit()
    
    c1 = create_club(db, "A", game.id)
    c2 = create_club(db, "B", game.id)
    
    create_fixture(db, season_id, c1, c2, month_index=1, played=True)
    
    finalizer = SeasonFinalizer(db, season_id)
    
    # First finalize
    res1 = finalizer.finalize()
    assert len(res1) == 2
    
    db.refresh(season)
    assert season.is_finalized is True
    assert season.finalized_at is not None
    
    # Check DB
    stored = db.query(SeasonFinalStanding).filter(SeasonFinalStanding.season_id == season_id).all()
    assert len(stored) == 2
    
    # Second finalize
    res2 = finalizer.finalize()
    assert res1 == res2
    
    # Check DB count didn't increase
    stored_again = db.query(SeasonFinalStanding).filter(SeasonFinalStanding.season_id == season_id).all()
    assert len(stored_again) == 2

def test_missing_match_detected(db):
    game = create_game(db)
    season_id = uuid4()
    season = Season(id=season_id, game_id=game.id, year_label="2025", status="running")
    db.add(season)
    db.commit()
    
    c1 = create_club(db, "A", game.id)
    c2 = create_club(db, "B", game.id)
    
    # Create fixture WITHOUT match
    f = Fixture(
        id=uuid4(),
        season_id=season_id,
        match_month_index=1,
        match_month_name="Aug",
        home_club_id=c1.id,
        away_club_id=c2.id
    )
    db.add(f)
    db.commit()
    
    finalizer = SeasonFinalizer(db, season_id)
    status = finalizer.get_status()
    
    assert status["is_completed"] is False
    assert status["missing_matches"] == 1
    
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as excinfo:
        finalizer.finalize()
    
    assert excinfo.value.status_code == 409
    assert "integrity error" in excinfo.value.detail

def test_final_standings_matches_calculated(db):
    game = create_game(db)
    season_id = uuid4()
    season = Season(id=season_id, game_id=game.id, year_label="2025", status="running")
    db.add(season)
    db.commit()
    
    c1 = create_club(db, "A", game.id)
    c2 = create_club(db, "B", game.id)
    
    create_fixture(db, season_id, c1, c2, month_index=1, played=True)
    
    finalizer = SeasonFinalizer(db, season_id)
    finalized_res = finalizer.finalize()
    
    calc = StandingsCalculator(db, season_id)
    calc_res = calc.calculate()
    
    # Compare
    # Note: calc_res might have different object identities but content should be same
    # Also finalize returns dicts similar to calculate
    
    assert len(finalized_res) == len(calc_res)
    for f_row, c_row in zip(finalized_res, calc_res):
        assert f_row['club_id'] == c_row['club_id']
        assert f_row['points'] == c_row['points']
        assert f_row['rank'] == c_row['rank']
