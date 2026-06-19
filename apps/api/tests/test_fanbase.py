import pytest
import math
from decimal import Decimal
from uuid import uuid4
from app.services import fanbase
from app.db.models import (
    ClubFanbaseState,
    ClubStaff,
    StaffRole,
    Game,
    Season,
    Club,
    GameStatus,
    SeasonStatus,
)


def _add_staff(db_session, club_id, role, count):
    row = ClubStaff(
        club_id=club_id,
        role=role,
        count=count,
        salary_per_person=Decimal("0"),
    )
    db_session.add(row)
    db_session.commit()
    return row

def test_fanbase_update_logic(db_session):
    club_id = uuid4()
    season_id = uuid4()

    game = Game(id=uuid4(), name="Fanbase Game", status=GameStatus.active)
    db_session.add(game)
    db_session.commit()

    season = Season(id=season_id, game_id=game.id, year_label="2025", status=SeasonStatus.running)
    db_session.add(season)
    club = Club(id=club_id, game_id=game.id, name="Club A")
    db_session.add(club)
    db_session.commit()
    
    # Mock state
    state = ClubFanbaseState(
        club_id=club_id,
        season_id=season_id,
        fb_count=60000,
        fb_rate=Decimal("0.06"),
        cumulative_promo=Decimal("0"),
        cumulative_ht=Decimal("0"),
        last_ht_spend=Decimal("0")
    )
    db_session.add(state)
    db_session.commit()
    
    # Update
    promo = Decimal("10000000")
    ht = Decimal("5000000")
    perf = 1.0 # Best
    hist = 0.5
    
    updated = fanbase.update_fanbase_for_turn(db_session, state, promo, ht, perf, hist)
    
    assert updated.cumulative_promo > 0
    assert updated.cumulative_ht > 0
    assert updated.fb_rate > Decimal("0.06") # Should grow
    assert updated.fb_count > 60000
    assert updated.followers_public is not None
    
    # Test Penalty
    # Increase HT spend drastically
    ht2 = Decimal("50000000") # +45M
    updated2 = fanbase.update_fanbase_for_turn(db_session, state, promo, ht2, perf, hist)
    
    # Check if penalty applied (hard to check exact value without calc, but should run)
    assert updated2.last_ht_spend == ht2


def test_fanbase_staff_cumulatives_affect_growth_with_hometown_longer_memory(db_session, monkeypatch):
    club_id = uuid4()
    season_id = uuid4()

    game = Game(id=uuid4(), name="Fanbase Staff Game", status=GameStatus.active)
    db_session.add(game)
    db_session.commit()

    season = Season(id=season_id, game_id=game.id, year_label="2025", status=SeasonStatus.running)
    club = Club(id=club_id, game_id=game.id, name="Club Staff")
    db_session.add_all([season, club])
    db_session.commit()

    _add_staff(db_session, club_id, StaffRole.promotion, 3)
    _add_staff(db_session, club_id, StaffRole.hometown, 3)

    state = ClubFanbaseState(
        club_id=club_id,
        season_id=season_id,
        fb_count=60000,
        fb_rate=Decimal("0.06"),
        cumulative_promo=Decimal("0"),
        cumulative_ht=Decimal("0"),
        cumulative_promotion_staff=Decimal("1"),
        cumulative_hometown_staff=Decimal("1"),
        last_ht_spend=Decimal("0"),
        fb_trend_streak=0,
    )
    db_session.add(state)
    db_session.commit()

    monkeypatch.setattr(fanbase.random, "gauss", lambda mean, sigma: mean)

    updated = fanbase.update_fanbase_for_turn(
        db_session,
        state,
        Decimal("0"),
        Decimal("0"),
        0.5,
        0.5,
    )

    assert float(updated.cumulative_promotion_staff) == pytest.approx(1.2)
    assert float(updated.cumulative_hometown_staff) == pytest.approx(1.08)
    baseline_next_rate = Decimal("0.06") * (
        Decimal("1")
        + fanbase.G0 * (Decimal("1") - Decimal("0.06") / fanbase.F_MAX)
    )
    assert updated.fb_rate > baseline_next_rate

    promotion_staff = db_session.query(ClubStaff).filter_by(
        club_id=club_id,
        role=StaffRole.promotion,
    ).first()
    hometown_staff = db_session.query(ClubStaff).filter_by(
        club_id=club_id,
        role=StaffRole.hometown,
    ).first()
    promotion_staff.count = 1
    hometown_staff.count = 1
    db_session.commit()

    updated2 = fanbase.update_fanbase_for_turn(
        db_session,
        updated,
        Decimal("0"),
        Decimal("0"),
        0.5,
        0.5,
    )

    assert float(updated2.cumulative_promotion_staff) == pytest.approx(1.18)
    assert float(updated2.cumulative_hometown_staff) == pytest.approx(1.0768)


def test_followers_use_new_scale_and_positive_trend_bias(db_session, monkeypatch):
    club_id = uuid4()
    season_id = uuid4()

    game = Game(id=uuid4(), name="Follower Trend Game", status=GameStatus.active)
    db_session.add(game)
    db_session.commit()

    season = Season(id=season_id, game_id=game.id, year_label="2025", status=SeasonStatus.running)
    club = Club(id=club_id, game_id=game.id, name="Club B")
    db_session.add_all([season, club])
    db_session.commit()

    state = ClubFanbaseState(
        club_id=club_id,
        season_id=season_id,
        fb_count=60000,
        fb_rate=Decimal("0.06"),
        cumulative_promo=Decimal("0"),
        cumulative_ht=Decimal("0"),
        last_ht_spend=Decimal("0"),
        fb_trend_streak=0,
    )
    db_session.add(state)
    db_session.commit()

    gauss_args = {}

    def fake_gauss(mean, sigma):
        gauss_args["mean"] = mean
        gauss_args["sigma"] = sigma
        return mean

    monkeypatch.setattr(fanbase.random, "gauss", fake_gauss)

    updated = fanbase.update_fanbase_for_turn(
        db_session,
        state,
        Decimal("10000000"),
        Decimal("5000000"),
        1.0,
        0.5,
    )

    assert updated.fb_trend_streak == 1
    assert gauss_args["mean"] == pytest.approx(0.13)
    assert gauss_args["sigma"] == pytest.approx(0.08)
    expected = int(math.exp(math.log(float(fanbase.KAPPA_F * updated.fb_count)) + 0.13))
    assert updated.followers_public == expected


def test_followers_negative_trend_lowers_error_mean(db_session, monkeypatch):
    club_id = uuid4()
    season_id = uuid4()

    game = Game(id=uuid4(), name="Follower Decline Game", status=GameStatus.active)
    db_session.add(game)
    db_session.commit()

    season = Season(id=season_id, game_id=game.id, year_label="2025", status=SeasonStatus.running)
    club = Club(id=club_id, game_id=game.id, name="Club C")
    db_session.add_all([season, club])
    db_session.commit()

    state = ClubFanbaseState(
        club_id=club_id,
        season_id=season_id,
        fb_count=60000,
        fb_rate=Decimal("0.06"),
        cumulative_promo=Decimal("0"),
        cumulative_ht=Decimal("0"),
        last_ht_spend=Decimal("0"),
        fb_trend_streak=-2,
    )
    db_session.add(state)
    db_session.commit()

    gauss_args = {}

    def fake_gauss(mean, sigma):
        gauss_args["mean"] = mean
        gauss_args["sigma"] = sigma
        return mean

    monkeypatch.setattr(fanbase.random, "gauss", fake_gauss)

    updated = fanbase.update_fanbase_for_turn(
        db_session,
        state,
        Decimal("0"),
        Decimal("0"),
        0.0,
        0.0,
    )

    assert updated.fb_trend_streak == -3
    assert gauss_args["mean"] == pytest.approx(0.01)
    assert gauss_args["sigma"] == pytest.approx(0.08)
