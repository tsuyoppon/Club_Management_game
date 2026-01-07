import pytest

from app.db import models
from app.services.historical_performance import get_hist_perf_value


def _create_game_with_clubs(db, club_count):
    game = models.Game(name="Test Game")
    db.add(game)
    db.flush()

    clubs = []
    for idx in range(club_count):
        club = models.Club(game_id=game.id, name=f"Club {idx + 1}")
        clubs.append(club)
    db.add_all(clubs)
    db.flush()
    return game, clubs


def _create_season(db, game_id, season_number, year_label, finalized):
    season = models.Season(
        game_id=game_id,
        season_number=season_number,
        year_label=year_label,
        status=models.SeasonStatus.finished if finalized else models.SeasonStatus.running,
        is_finalized=finalized,
    )
    db.add(season)
    db.flush()
    return season


def _add_final_standings(db, season_id, clubs, ranks):
    for club, rank in zip(clubs, ranks):
        db.add(
            models.SeasonFinalStanding(
                season_id=season_id,
                club_id=club.id,
                rank=rank,
                points=0,
                gd=0,
                gf=0,
                ga=0,
                won=0,
                drawn=0,
                lost=0,
                played=0,
            )
        )
    db.flush()


def test_hist_perf_defaults_when_no_previous_season(db):
    game, clubs = _create_game_with_clubs(db, 2)
    current_season = _create_season(db, game.id, 2, "2025", finalized=False)

    hist_perf = get_hist_perf_value(db, current_season.id, clubs[0].id)

    assert hist_perf == pytest.approx(0.5)


def test_hist_perf_from_single_previous_season(db):
    game, clubs = _create_game_with_clubs(db, 3)
    prev_season = _create_season(db, game.id, 1, "2024", finalized=True)
    _add_final_standings(db, prev_season.id, clubs, [1, 2, 3])

    current_season = _create_season(db, game.id, 2, "2025", finalized=False)

    top_hist_perf = get_hist_perf_value(db, current_season.id, clubs[0].id)
    bottom_hist_perf = get_hist_perf_value(db, current_season.id, clubs[2].id)

    assert top_hist_perf == pytest.approx(1.0)
    assert bottom_hist_perf == pytest.approx(0.0)


def test_hist_perf_averages_multiple_seasons(db):
    game, clubs = _create_game_with_clubs(db, 3)
    prev_season_1 = _create_season(db, game.id, 1, "2023", finalized=True)
    prev_season_2 = _create_season(db, game.id, 2, "2024", finalized=True)
    _add_final_standings(db, prev_season_1.id, clubs, [1, 2, 3])
    _add_final_standings(db, prev_season_2.id, clubs, [3, 2, 1])

    current_season = _create_season(db, game.id, 3, "2025", finalized=False)

    hist_perf = get_hist_perf_value(db, current_season.id, clubs[0].id)

    assert hist_perf == pytest.approx(0.5)
