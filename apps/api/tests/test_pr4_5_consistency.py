import pytest
from uuid import uuid4
from app.db.models import Match, Club, MatchStatus, Season, Game, GameStatus, Fixture, Turn, TurnState
from app.services.match_results import process_matches_for_turn
from app.services.standings import StandingsCalculator
from app.routers.seasons import season_schedule

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

def create_fixture(db, season_id, home, away, month_index=1):
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
        status=MatchStatus.scheduled
    )
    db.add(m)
    db.commit()
    return f, m

def test_resolve_turn_idempotency(db):
    game = create_game(db)
    season_id = uuid4()
    season = Season(id=season_id, game_id=game.id, year_label="2025", status="running")
    db.add(season)
    db.commit()
    
    c1 = create_club(db, "A", game.id)
    c2 = create_club(db, "B", game.id)
    
    f, m = create_fixture(db, season_id, c1, c2, month_index=1)
    
    turn_id = uuid4()
    
    # First run
    process_matches_for_turn(db, season_id, turn_id, month_index=1)
    db.commit()
    db.refresh(m)
    
    assert m.status == MatchStatus.played
    assert m.home_goals is not None
    assert m.away_goals is not None
    
    first_home_goals = m.home_goals
    first_away_goals = m.away_goals
    
    # Second run
    process_matches_for_turn(db, season_id, turn_id, month_index=1)
    db.refresh(m)
    
    assert m.status == MatchStatus.played
    assert m.home_goals == first_home_goals
    assert m.away_goals == first_away_goals

def test_schedule_standings_consistency(db):
    game = create_game(db)
    season_id = uuid4()
    season = Season(id=season_id, game_id=game.id, year_label="2025", status="running")
    db.add(season)
    db.commit()
    
    c1 = create_club(db, "A", game.id)
    c2 = create_club(db, "B", game.id)
    
    f, m = create_fixture(db, season_id, c1, c2, month_index=1)
    
    # Before resolve
    # Check Schedule (simulating router logic)
    fixtures = db.query(Fixture).filter(Fixture.season_id == season_id).all()
    assert len(fixtures) == 1
    assert fixtures[0].match.status == MatchStatus.scheduled
    assert fixtures[0].match.home_goals is None
    
    # Check Standings
    calc = StandingsCalculator(db, season_id)
    res = calc.calculate()
    # Should be empty or all zeros if clubs are initialized (StandingsCalculator initializes on fly based on matches)
    # Since no matches played, it might return empty list or list of clubs with 0 stats if we pre-populated.
    # The current implementation iterates matches to build stats. So it should be empty.
    assert len(res) == 0 
    
    # Resolve
    turn_id = uuid4()
    process_matches_for_turn(db, season_id, turn_id, month_index=1)
    db.commit()
    db.refresh(m)
    
    # After resolve
    assert m.status == MatchStatus.played
    
    # Check Standings
    res = calc.calculate()
    assert len(res) == 2
    assert res[0]['played'] == 1
    assert res[1]['played'] == 1
    
    # Verify consistency
    # Find the match in standings data? No, standings aggregates.
    # But we can verify that the points/goals match the match result.
    
    home_stats = next(r for r in res if r['club_id'] == c1.id)
    away_stats = next(r for r in res if r['club_id'] == c2.id)
    
    assert home_stats['gf'] == m.home_goals
    assert away_stats['gf'] == m.away_goals

def test_standings_ignores_scheduled(db):
    game = create_game(db)
    season_id = uuid4()
    season = Season(id=season_id, game_id=game.id, year_label="2025", status="running")
    db.add(season)
    db.commit()
    
    c1 = create_club(db, "A", game.id)
    c2 = create_club(db, "B", game.id)
    c3 = create_club(db, "C", game.id)
    c4 = create_club(db, "D", game.id)
    
    # Match 1: Played
    f1, m1 = create_fixture(db, season_id, c1, c2, month_index=1)
    m1.status = MatchStatus.played
    m1.home_goals = 2
    m1.away_goals = 1
    db.add(m1)
    
    # Match 2: Scheduled
    f2, m2 = create_fixture(db, season_id, c3, c4, month_index=2)
    # Defaults to scheduled and None goals
    
    db.commit()
    
    calc = StandingsCalculator(db, season_id)
    res = calc.calculate()
    
    # Should only contain c1 and c2
    assert len(res) == 2
    club_ids = [r['club_id'] for r in res]
    assert c1.id in club_ids
    assert c2.id in club_ids
    assert c3.id not in club_ids
    assert c4.id not in club_ids
