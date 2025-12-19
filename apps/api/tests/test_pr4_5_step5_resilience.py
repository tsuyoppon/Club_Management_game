import pytest
from uuid import uuid4
from app.db import models
from app.services.season_finalize import SeasonFinalizer
from app.services.standings import StandingsCalculator

def test_finalized_standings_consistency(db):
    # 1. Setup Season and Clubs
    game = models.Game(name="Test Game", id=uuid4())
    db.add(game)
    season = models.Season(game_id=game.id, year_label="2024", id=uuid4(), status=models.SeasonStatus.running)
    db.add(season)
    
    club1 = models.Club(name="Club A", game_id=game.id, id=uuid4())
    club2 = models.Club(name="Club B", game_id=game.id, id=uuid4())
    db.add_all([club1, club2])
    db.commit()

    # 2. Create Fixture and Match (Played)
    fixture = models.Fixture(season_id=season.id, home_club_id=club1.id, away_club_id=club2.id, match_month_index=1, match_month_name="January", id=uuid4())
    db.add(fixture)
    match = models.Match(fixture_id=fixture.id, status=models.MatchStatus.played, home_goals=2, away_goals=1, id=uuid4())
    db.add(match)
    db.commit()

    # 3. Finalize Season
    finalizer = SeasonFinalizer(db, season.id)
    finalizer.finalize()
    
    # 4. Verify Standings (Should come from SeasonFinalStanding)
    calc = StandingsCalculator(db, season.id)
    standings_finalized = calc.calculate()
    
    assert len(standings_finalized) == 2
    assert standings_finalized[0]["club_name"] == "Club A"
    assert standings_finalized[0]["points"] == 3
    
    # 5. Tamper with Match Data (Simulate "Live" change after finalization)
    # If we were using live calculation, this would change the standings.
    # Since we are finalized, it should NOT change.
    match.home_goals = 0
    match.away_goals = 5 # Club B wins now
    db.add(match)
    db.commit()
    
    standings_after_tamper = calc.calculate()
    
    # Should still reflect original result (Club A wins)
    assert standings_after_tamper[0]["club_name"] == "Club A"
    assert standings_after_tamper[0]["points"] == 3
    assert standings_after_tamper[0]["gf"] == 2 # Original GF
    
    # 6. Unfinalize (Manually) to prove live calculation works
    season.is_finalized = False
    db.add(season)
    db.commit()
    
    standings_live = calc.calculate()
    # Now it should reflect the tamper (Club B wins)
    assert standings_live[0]["club_name"] == "Club B"
    assert standings_live[0]["points"] == 3
    assert standings_live[0]["gf"] == 5


def test_anomaly_detection_missing_match(db):
    # 1. Setup Season
    game = models.Game(name="Test Game 2", id=uuid4())
    db.add(game)
    season = models.Season(game_id=game.id, year_label="2025", id=uuid4(), status=models.SeasonStatus.running)
    db.add(season)
    db.commit()

    # 2. Create Fixture WITHOUT Match
    club_home = models.Club(name="Club Home", game_id=game.id, id=uuid4())
    club_away = models.Club(name="Club Away", game_id=game.id, id=uuid4())
    db.add_all([club_home, club_away])
    db.commit()

    fixture = models.Fixture(season_id=season.id, home_club_id=club_home.id, away_club_id=club_away.id, match_month_index=1, match_month_name="January", id=uuid4())
    db.add(fixture)
    db.commit()

    # 3. Check Status
    finalizer = SeasonFinalizer(db, season.id)
    status_info = finalizer.get_status()
    
    assert status_info["missing_matches"] == 1
    assert len(status_info["warnings"]) > 0
    assert "Integrity Error" in status_info["warnings"][0]
    
    # 4. Attempt Finalize (Should Fail)
    import pytest
    from fastapi import HTTPException
    
    with pytest.raises(HTTPException) as excinfo:
        finalizer.finalize()
    
    assert excinfo.value.status_code == 409
    assert "Missing 1 matches" in excinfo.value.detail
