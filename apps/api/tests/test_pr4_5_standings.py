import pytest
from uuid import uuid4
from app.db.models import Match, Club, MatchStatus, Season, Game, GameStatus, Fixture
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

def create_match(db, season_id, home, away, h_score, a_score):
    f = Fixture(
        id=uuid4(),
        season_id=season_id,
        match_month_index=1,
        match_month_name="Aug",
        home_club_id=home.id,
        away_club_id=away.id
    )
    db.add(f)
    db.commit()
    
    m = Match(
        id=uuid4(),
        fixture_id=f.id,
        home_goals=h_score,
        away_goals=a_score,
        status=MatchStatus.played
    )
    db.add(m)
    db.commit()
    return m

def test_standings_basic(db):
    game = create_game(db)
    season_id = uuid4()
    # Need to create Season object for FK
    season = Season(id=season_id, game_id=game.id, year_label="2025", status="running")
    db.add(season)
    db.commit()
    
    c1 = create_club(db, "A", game.id)
    c2 = create_club(db, "B", game.id)
    c3 = create_club(db, "C", game.id)

    # A beats B 2-0
    create_match(db, season_id, c1, c2, 2, 0)
    # A beats C 1-0
    create_match(db, season_id, c1, c3, 1, 0)
    # B beats C 3-0
    create_match(db, season_id, c2, c3, 3, 0)

    # Expected:
    # A: 2W, 6pts
    # B: 1W 1L, 3pts
    # C: 2L, 0pts

    calc = StandingsCalculator(db, season_id)
    res = calc.calculate()

    assert len(res) == 3
    assert res[0]['club_id'] == c1.id
    assert res[0]['points'] == 6
    assert res[0]['rank'] == 1
    
    assert res[1]['club_id'] == c2.id
    assert res[1]['points'] == 3
    assert res[1]['rank'] == 2
    
    assert res[2]['club_id'] == c3.id
    assert res[2]['points'] == 0
    assert res[2]['rank'] == 3

def test_standings_gd_gf(db):
    game = create_game(db)
    season_id = uuid4()
    season = Season(id=season_id, game_id=game.id, year_label="2025", status="running")
    db.add(season)
    db.commit()
    
    c1 = create_club(db, "A", game.id)
    c2 = create_club(db, "B", game.id)
    c3 = create_club(db, "C", game.id)

    # A vs B: Draw 1-1
    create_match(db, season_id, c1, c2, 1, 1)
    
    # A beats C 3-0
    create_match(db, season_id, c1, c3, 3, 0)
    # B beats C 2-0
    create_match(db, season_id, c2, c3, 2, 0)

    # A: 4pts, GD +3, GF 4
    # B: 4pts, GD +2, GF 3
    # C: 0pts

    calc = StandingsCalculator(db, season_id)
    res = calc.calculate()

    assert res[0]['club_id'] == c1.id
    assert res[0]['gd'] == 3
    assert res[1]['club_id'] == c2.id
    assert res[1]['gd'] == 2

def test_standings_h2h_tie_fallback(db):
    # Perfect 3-way tie where H2H is also tied
    game = create_game(db)
    season_id = uuid4()
    season = Season(id=season_id, game_id=game.id, year_label="2025", status="running")
    db.add(season)
    db.commit()
    
    c1 = create_club(db, "A", game.id)
    c2 = create_club(db, "B", game.id)
    c3 = create_club(db, "C", game.id)
    
    # A vs B: 1-0
    create_match(db, season_id, c1, c2, 1, 0)
    # A vs C: 0-1
    create_match(db, season_id, c1, c3, 0, 1)
    # B vs C: 1-0
    create_match(db, season_id, c2, c3, 1, 0)
    
    # Global:
    # A: 3pts. GF 1, GA 1. GD 0.
    # B: 3pts. GF 1, GA 1. GD 0.
    # C: 3pts. GF 1, GA 1. GD 0.
    
    # H2H Mini-League is same as Global here because everyone played everyone.
    # So H2H stats are also identical.
    # Fallback to Name: A, B, C.
    
    calc = StandingsCalculator(db, season_id)
    res = calc.calculate()
    
    assert res[0]['club_name'] == "A"
    assert res[1]['club_name'] == "B"
    assert res[2]['club_name'] == "C"

def test_standings_h2h_resolution(db):
    # Scenario where Global is tied, but H2H breaks it.
    # A and B tied globally.
    # A beat B.
    
    game = create_game(db)
    season_id = uuid4()
    season = Season(id=season_id, game_id=game.id, year_label="2025", status="running")
    db.add(season)
    db.commit()
    
    c1 = create_club(db, "A", game.id)
    c2 = create_club(db, "B", game.id)
    c3 = create_club(db, "C", game.id)
    c4 = create_club(db, "D", game.id)
    
    # A vs B: 1-0
    create_match(db, season_id, c1, c2, 1, 0)
    
    # To balance stats:
    # A needs to lose/draw something to drop points/GD.
    # B needs to win something to gain points/GD.
    
    # A vs C: 0-0
    # B vs D: 0-0
    
    # A: 4pts. GF 1, GA 0. GD +1.
    # B: 1pt. GF 0, GA 1. GD -1.
    # Not tied.
    
    # Let's try:
    # A vs B: 1-0
    # A vs C: 0-1
    # B vs D: 1-0
    
    # A: 3pts. GF 1, GA 1. GD 0.
    # B: 3pts. GF 1, GA 1. GD 0.
    
    # C and D are dummy opponents.
    # C vs D? Not needed if we just look at A and B.
    # But wait, C and D stats don't matter for A vs B comparison, 
    # but they matter for A and B's global stats.
    
    # A vs C (0-1) -> A loses.
    # B vs D (1-0) -> B wins.
    
    # A total: 1W 1L. 3pts. GF 1, GA 1. GD 0.
    # B total: 1W 1L. 3pts. GF 1, GA 1. GD 0.
    
    # Perfect tie globally.
    # H2H: A vs B (1-0). A wins.
    # A should be ranked higher.
    
    # We need to ensure C and D exist so FKs work.
    
    create_match(db, season_id, c1, c3, 0, 1)
    create_match(db, season_id, c2, c4, 1, 0)
    
    calc = StandingsCalculator(db, season_id)
    res = calc.calculate()
    
    # Filter only A and B
    res_ab = [x for x in res if x['club_id'] in (c1.id, c2.id)]
    
    assert res_ab[0]['club_name'] == "A"
    assert res_ab[1]['club_name'] == "B"
