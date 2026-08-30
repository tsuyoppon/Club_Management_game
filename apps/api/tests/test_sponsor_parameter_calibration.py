from decimal import Decimal

import pytest

from app.config.constants import (
    LEADS_L0,
    SALES_EFFORT_REFERENCE_MONTHLY_SALARY,
    SALES_EFFORT_STAFF_TO_SPEND_EFFICIENCY,
    SPONSOR_CONVERSION_HISTORY_WEIGHTS,
    SPONSOR_EFFORT_HISTORY_WEIGHTS,
    SPONSOR_RETENTION_DILUTION_EXPONENT,
    SPONSOR_RETENTION_REFERENCE_COUNT,
    STAFF_SALARY_ANNUAL,
)
from app.db import models
from app.services.sales_effort import calculate_monthly_effort
from app.services.sponsor import (
    _calculate_churn_rate,
    _calculate_effective_sponsor_efforts,
    determine_next_sponsors,
    process_pipeline_progress,
)


def test_base_new_sponsor_leads_are_four():
    assert LEADS_L0 == Decimal("4.0")


def test_zero_retention_effort_has_forty_percent_neutral_churn():
    assert _calculate_churn_rate(c_ret=0.0, perf=0.5, fan_growth=0.0) == pytest.approx(0.40)


def test_normal_retention_effort_restores_churn_to_target_range():
    churn = _calculate_churn_rate(c_ret=2.2, perf=0.6, fan_growth=0.1)
    assert 0.15 <= churn <= 0.20


def test_reference_salary_matches_staff_payroll_model():
    assert SALES_EFFORT_REFERENCE_MONTHLY_SALARY == STAFF_SALARY_ANNUAL / Decimal("12")


def test_cross_season_sponsor_effort_parameters():
    assert SPONSOR_EFFORT_HISTORY_WEIGHTS == (
        Decimal("0.55"), Decimal("0.25"), Decimal("0.13"), Decimal("0.07")
    )
    assert SPONSOR_CONVERSION_HISTORY_WEIGHTS == (
        Decimal("0.70"), Decimal("0.20"), Decimal("0.07"), Decimal("0.03")
    )
    assert SPONSOR_RETENTION_REFERENCE_COUNT == Decimal("10")
    assert SPONSOR_RETENTION_DILUTION_EXPONENT == Decimal("0.7")


@pytest.mark.parametrize(
    ("staff_effort_index", "spend_effort_index"),
    [(0, 0), (1, 1)],
)
def test_staff_is_three_times_as_effective_as_equal_monthly_spend(
    staff_effort_index,
    spend_effort_index,
):
    staff_effort = calculate_monthly_effort(
        sales_staff=1,
        sales_spend=Decimal("0"),
        rho_new=Decimal("0.5"),
    )
    spend_effort = calculate_monthly_effort(
        sales_staff=0,
        sales_spend=SALES_EFFORT_REFERENCE_MONTHLY_SALARY,
        rho_new=Decimal("0.5"),
    )

    ratio = staff_effort[staff_effort_index] / spend_effort[spend_effort_index]
    assert float(ratio) == pytest.approx(float(SALES_EFFORT_STAFF_TO_SPEND_EFFICIENCY))


def _add_sponsor_season(
    db,
    game,
    club,
    season_number,
    *,
    sponsor_count,
    retention_effort,
    new_effort,
    finalized,
):
    season = models.Season(
        game_id=game.id,
        season_number=season_number,
        year_label=str(2023 + season_number),
        status=(
            models.SeasonStatus.finished if finalized else models.SeasonStatus.running
        ),
        is_finalized=finalized,
    )
    db.add(season)
    db.flush()
    state = models.ClubSponsorState(
        club_id=club.id,
        season_id=season.id,
        count=sponsor_count,
        cumulative_effort_ret=Decimal(str(retention_effort)),
        cumulative_effort_new=Decimal(str(new_effort)),
    )
    db.add(state)
    db.flush()
    return season, state


def test_effective_effort_blends_three_prior_seasons_and_dilutes_retention(db):
    game = models.Game(name="Sponsor Memory Game")
    db.add(game)
    db.flush()
    club = models.Club(game_id=game.id, name="Sponsor Memory Club")
    db.add(club)
    db.flush()

    _add_sponsor_season(
        db, game, club, 1, sponsor_count=10,
        retention_effort=1, new_effort=1, finalized=True,
    )
    _add_sponsor_season(
        db, game, club, 2, sponsor_count=20,
        retention_effort=2, new_effort=2, finalized=True,
    )
    _add_sponsor_season(
        db, game, club, 3, sponsor_count=5,
        retention_effort=3, new_effort=3, finalized=True,
    )
    current_season, current_state = _add_sponsor_season(
        db, game, club, 4, sponsor_count=10,
        retention_effort=4, new_effort=4, finalized=False,
    )

    effective_retention, effective_new_leads, effective_new_conversion = (
        _calculate_effective_sponsor_efforts(
            db, current_state, current_season.id, club.id
        )
    )

    expected_retention = (
        0.55 * 4
        + 0.25 * (3 * (10 / 5) ** 0.7)
        + 0.13 * (2 * (10 / 20) ** 0.7)
        + 0.07 * 1
    )
    assert effective_retention == pytest.approx(expected_retention)
    assert effective_new_leads == pytest.approx(
        0.55 * 4 + 0.25 * 3 + 0.13 * 2 + 0.07 * 1
    )
    assert effective_new_conversion == pytest.approx(
        0.70 * 4 + 0.20 * 3 + 0.07 * 2 + 0.03 * 1
    )
    assert current_state.cumulative_effort_ret == Decimal("4")
    assert current_state.cumulative_effort_new == Decimal("4")


def test_effective_effort_renormalizes_available_history_and_ignores_unfinalized(db):
    game = models.Game(name="Sponsor Partial History Game")
    db.add(game)
    db.flush()
    club = models.Club(game_id=game.id, name="Sponsor Partial History Club")
    db.add(club)
    db.flush()

    _add_sponsor_season(
        db, game, club, 1, sponsor_count=10,
        retention_effort=1, new_effort=1, finalized=True,
    )
    _add_sponsor_season(
        db, game, club, 2, sponsor_count=10,
        retention_effort=100, new_effort=100, finalized=False,
    )
    current_season, current_state = _add_sponsor_season(
        db, game, club, 3, sponsor_count=10,
        retention_effort=3, new_effort=3, finalized=False,
    )

    effective_retention, effective_new_leads, effective_new_conversion = (
        _calculate_effective_sponsor_efforts(
            db, current_state, current_season.id, club.id
        )
    )

    assert effective_retention == pytest.approx((0.55 * 3 + 0.13 * 1) / 0.68)
    assert effective_new_leads == pytest.approx((0.55 * 3 + 0.13 * 1) / 0.68)
    assert effective_new_conversion == pytest.approx((0.70 * 3 + 0.07 * 1) / 0.77)


def test_finalized_next_count_is_not_recalculated(db, monkeypatch):
    game = models.Game(name="Sponsor Existing Final Game")
    db.add(game)
    db.flush()
    club = models.Club(game_id=game.id, name="Sponsor Existing Final Club")
    db.add(club)
    db.flush()
    season, state = _add_sponsor_season(
        db, game, club, 1, sponsor_count=10,
        retention_effort=1, new_effort=1, finalized=False,
    )
    state.next_count = 12
    state.next_exist_count = 8
    state.next_new_count = 4
    db.flush()

    def fail_if_recalculated(*_args, **_kwargs):
        raise AssertionError("already-finalized sponsor counts must not be recalculated")

    monkeypatch.setattr(
        "app.services.sponsor._calculate_forecast_next_counts",
        fail_if_recalculated,
    )

    result = determine_next_sponsors(db, club.id, season.id)

    assert result.next_count == 12
    assert result.next_exist_count == 8
    assert result.next_new_count == 4


def test_april_pipeline_uses_history_and_keeps_confirmed_floor(db):
    game = models.Game(name="Sponsor Pipeline Memory Game")
    db.add(game)
    db.flush()
    club = models.Club(game_id=game.id, name="Sponsor Pipeline Memory Club")
    db.add(club)
    db.flush()

    _, previous_state = _add_sponsor_season(
        db, game, club, 1, sponsor_count=10,
        retention_effort=100, new_effort=0, finalized=True,
    )
    current_season, current_state = _add_sponsor_season(
        db, game, club, 2, sponsor_count=10,
        retention_effort=0, new_effort=0, finalized=False,
    )

    process_pipeline_progress(db, club.id, current_season.id, month_index=9)

    # The prior season's relationship capital clips churn to its 5% floor.
    assert current_state.next_exist_count == 10

    # Later forecasts may fall, but already-confirmed sponsors remain a floor.
    previous_state.cumulative_effort_ret = Decimal("0")
    current_state.pipeline_confirmed_exist = 9
    db.flush()
    process_pipeline_progress(db, club.id, current_season.id, month_index=10)

    assert current_state.next_exist_count == 9
    assert current_state.pipeline_confirmed_exist >= 9
