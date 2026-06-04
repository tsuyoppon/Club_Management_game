from decimal import Decimal

from app.db import models
from app.services import bankruptcy


def _season(db, game_id, season_number, label):
    season = models.Season(
        game_id=game_id,
        season_number=season_number,
        year_label=label,
        status=models.SeasonStatus.running,
    )
    db.add(season)
    db.flush()
    return season


def _turn(db, season_id, month_index, month_name):
    turn = models.Turn(
        season_id=season_id,
        month_index=month_index,
        month_name=month_name,
        month_number=8 if month_index == 1 else 12,
    )
    db.add(turn)
    db.flush()
    return turn


def test_bankruptcy_state_and_penalty_are_scoped_by_season(db):
    game = models.Game(name="Bankruptcy Season Scope")
    db.add(game)
    db.flush()
    club = models.Club(game_id=game.id, name="Scoped Club")
    db.add(club)
    db.flush()
    fin_state = models.ClubFinancialState(club_id=club.id, balance=Decimal("-1"))
    db.add(fin_state)

    season1 = _season(db, game.id, 1, "2026")
    turn1 = _turn(db, season1.id, 5, "Dec")

    assert bankruptcy.check_bankruptcy(db, club.id, turn1.id) is True
    assert bankruptcy.apply_point_penalty(db, club.id, season1.id, turn1.id) == -6
    fin_state.point_penalty_applied = True
    fin_state.balance = Decimal("100")
    db.add(fin_state)
    db.flush()

    season2 = _season(db, game.id, 2, "2027")
    turn2 = _turn(db, season2.id, 5, "Dec")

    assert bankruptcy.get_bankruptcy_status(db, club.id, season1.id)["is_bankrupt"] is True
    assert bankruptcy.get_bankruptcy_status(db, club.id, season2.id)["is_bankrupt"] is False
    assert bankruptcy.can_add_reinforcement(db, club.id, season2.id) is True
    assert bankruptcy.apply_point_penalty(db, club.id, season2.id, turn2.id) == 0

    fin_state.balance = Decimal("-1")
    db.add(fin_state)
    db.flush()

    assert bankruptcy.check_bankruptcy(db, club.id, turn2.id) is True
    assert bankruptcy.apply_point_penalty(db, club.id, season2.id, turn2.id) == -6

    penalties = db.query(models.ClubPointPenalty).filter(
        models.ClubPointPenalty.club_id == club.id,
        models.ClubPointPenalty.reason == "bankruptcy",
    ).all()
    assert {(penalty.season_id, penalty.points_deducted) for penalty in penalties} == {
        (season1.id, -6),
        (season2.id, -6),
    }
