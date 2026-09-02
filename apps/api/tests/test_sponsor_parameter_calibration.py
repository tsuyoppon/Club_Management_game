import math
import random
from decimal import Decimal

import pytest

from app.config.constants import (
    CONV_A0,
    CONV_A1,
    CONV_A2,
    CONV_A3,
    CONV_FOLLOWER_RELATIVE_BOOST,
    LEADS_FOLLOWER_RELATIVE_BOOST,
    LEADS_L0,
    LEADS_L1,
    LEADS_L2,
    LEADS_L3,
    LEADS_L4,
    PIPELINE_PROB_EXISTING,
    PIPELINE_PROB_NEW,
    SALES_EFFORT_LAMBDA_NEW,
    SALES_EFFORT_LAMBDA_RET,
    SALES_EFFORT_REFERENCE_MONTHLY_SALARY,
    SALES_EFFORT_STAFF_TO_SPEND_EFFICIENCY,
    SPONSOR_CONVERSION_HISTORY_WEIGHTS,
    SPONSOR_EFFORT_HISTORY_WEIGHTS,
    SPONSOR_FOLLOWER_REFERENCE_COUNT,
    SPONSOR_RETENTION_DILUTION_EXPONENT,
    SPONSOR_RETENTION_REFERENCE_COUNT,
    STAFF_SALARY_ANNUAL,
)
from app.db import models
from app.services.sales_effort import calculate_monthly_effort
from app.services.sponsor import (
    _calculate_churn_rate,
    _calculate_effective_sponsor_efforts,
    _calculate_follower_effects,
    _retention_effort_per_sponsor,
    _weighted_effort,
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


def test_sponsor_follower_popularity_parameters():
    assert SPONSOR_FOLLOWER_REFERENCE_COUNT == Decimal("3000")
    assert LEADS_FOLLOWER_RELATIVE_BOOST == Decimal("2.0")
    assert CONV_FOLLOWER_RELATIVE_BOOST == Decimal("0.30")


def test_follower_effects_preserve_reference_balance_and_amplify_doubling():
    reference = float(SPONSOR_FOLLOWER_REFERENCE_COUNT)
    reference_leads, reference_conversion = _calculate_follower_effects(reference)
    doubled_leads, doubled_conversion = _calculate_follower_effects(2 * reference)

    assert reference_leads == pytest.approx(float(LEADS_L4) * math.log1p(reference))
    assert reference_conversion == pytest.approx(
        float(CONV_A3) * math.log1p(reference)
    )

    doubled_log_difference = math.log1p(2 * reference) - math.log1p(reference)
    assert doubled_leads - reference_leads == pytest.approx(
        (float(LEADS_L4) + float(LEADS_FOLLOWER_RELATIVE_BOOST))
        * doubled_log_difference
    )
    assert doubled_conversion - reference_conversion == pytest.approx(
        (float(CONV_A3) + float(CONV_FOLLOWER_RELATIVE_BOOST))
        * doubled_log_difference
    )


def test_follower_effects_clamp_negative_counts_to_zero():
    zero_effects = _calculate_follower_effects(0)
    negative_effects = _calculate_follower_effects(-100)

    assert negative_effects == pytest.approx(zero_effects)
    assert all(math.isfinite(value) for value in zero_effects)


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


_CALIBRATION_MONTHS = (9, 10, 11, 12)
_CALIBRATION_PIPELINE_MONTHS = (9, 10, 11)
_CALIBRATION_SEASONS = 5


def _calibration_cumulative_efforts() -> tuple[dict[int, float], dict[int, float]]:
    monthly_retention, monthly_new = calculate_monthly_effort(
        sales_staff=1,
        sales_spend=Decimal("0"),
        rho_new=Decimal("0.5"),
    )
    retention_lambda = float(SALES_EFFORT_LAMBDA_RET)
    new_lambda = float(SALES_EFFORT_LAMBDA_NEW)
    retention = {
        month: float(monthly_retention) * (1 - (1 - retention_lambda) ** month)
        for month in _CALIBRATION_MONTHS
    }
    new = {
        month: float(monthly_new) * (1 - (1 - new_lambda) ** month)
        for month in _CALIBRATION_MONTHS
    }
    return retention, new


def _calibration_effective_efforts(
    month: int,
    sponsor_count: int,
    prior_sponsor_counts: list[int],
    cumulative_retention: dict[int, float],
    cumulative_new: dict[int, float],
) -> tuple[float, float, float]:
    retention_by_age = {
        0: _retention_effort_per_sponsor(
            cumulative_retention[month], sponsor_count
        )
    }
    new_by_age = {0: cumulative_new[month]}
    for age, previous_count in enumerate(
        reversed(prior_sponsor_counts[-3:]), start=1
    ):
        retention_by_age[age] = _retention_effort_per_sponsor(
            cumulative_retention[12], previous_count
        )
        new_by_age[age] = cumulative_new[12]

    return (
        _weighted_effort(retention_by_age, SPONSOR_EFFORT_HISTORY_WEIGHTS),
        _weighted_effort(new_by_age, SPONSOR_EFFORT_HISTORY_WEIGHTS),
        _weighted_effort(new_by_age, SPONSOR_CONVERSION_HISTORY_WEIGHTS),
    )


def _calibration_forecast(
    sponsor_count: int,
    followers: int,
    retention_effort: float,
    new_leads_effort: float,
    new_conversion_effort: float,
    forecast_draws: list[float],
) -> tuple[int, int]:
    churn = _calculate_churn_rate(
        c_ret=retention_effort, perf=0.5, fan_growth=0.0
    )
    existing = round(sponsor_count * (1 - churn))
    follower_lead_term, follower_conversion_term = _calculate_follower_effects(
        followers
    )
    leads = max(
        0,
        round(
            float(LEADS_L0)
            + float(LEADS_L1) * math.log1p(new_leads_effort)
            + float(LEADS_L2) * math.log1p(sponsor_count)
            + float(LEADS_L3) * (0.5 - 0.5)
            + follower_lead_term
        ),
    )
    logit = (
        float(CONV_A0)
        + float(CONV_A1) * math.log1p(new_conversion_effort)
        + float(CONV_A2) * (0.5 - 0.5)
        + follower_conversion_term
    )
    conversion_probability = 1 / (1 + math.exp(-logit))
    new = sum(draw < conversion_probability for draw in forecast_draws[:leads])
    return existing, new


def _simulate_five_season_sponsor_count(
    followers: int,
    yearly_noise: list[
        tuple[list[float], dict[int, list[float]], dict[int, list[float]]]
    ],
) -> int:
    cumulative_retention, cumulative_new = _calibration_cumulative_efforts()
    sponsor_count = 10
    prior_sponsor_counts: list[int] = []

    for forecast_draws, pipeline_existing_draws, pipeline_new_draws in yearly_noise:
        confirmed_existing = 0
        confirmed_new = 0

        for month in _CALIBRATION_MONTHS:
            effective_retention, effective_new_leads, effective_new_conversion = (
                _calibration_effective_efforts(
                    month,
                    sponsor_count,
                    prior_sponsor_counts,
                    cumulative_retention,
                    cumulative_new,
                )
            )
            forecast_existing, forecast_new = _calibration_forecast(
                sponsor_count,
                followers,
                effective_retention,
                effective_new_leads,
                effective_new_conversion,
                forecast_draws,
            )

            if month in _CALIBRATION_PIPELINE_MONTHS:
                target_existing = max(forecast_existing, confirmed_existing)
                target_new = max(forecast_new, confirmed_new)
                confirmed_existing += sum(
                    draw < PIPELINE_PROB_EXISTING[month]
                    for draw in pipeline_existing_draws[month][
                        : target_existing - confirmed_existing
                    ]
                )
                confirmed_new += sum(
                    draw < PIPELINE_PROB_NEW[month]
                    for draw in pipeline_new_draws[month][: target_new - confirmed_new]
                )
                continue

            next_existing = max(forecast_existing, confirmed_existing)
            next_new = max(forecast_new, confirmed_new)
            prior_sponsor_counts.append(sponsor_count)
            sponsor_count = next_existing + next_new

    return sponsor_count


def _paired_calibration_average(
    lower_followers: int,
    higher_followers: int,
    *,
    samples: int = 3000,
) -> tuple[float, float]:
    rng = random.Random(20260902)
    lower_total = 0
    higher_total = 0

    for _ in range(samples):
        yearly_noise = []
        for _season in range(_CALIBRATION_SEASONS):
            yearly_noise.append(
                (
                    [rng.random() for _ in range(80)],
                    {
                        month: [rng.random() for _ in range(80)]
                        for month in _CALIBRATION_PIPELINE_MONTHS
                    },
                    {
                        month: [rng.random() for _ in range(80)]
                        for month in _CALIBRATION_PIPELINE_MONTHS
                    },
                )
            )
        lower_total += _simulate_five_season_sponsor_count(
            lower_followers, yearly_noise
        )
        higher_total += _simulate_five_season_sponsor_count(
            higher_followers, yearly_noise
        )

    return lower_total / samples, higher_total / samples


def test_follower_doubling_produces_target_five_season_sponsor_uplift():
    calibrated_results = {}
    for lower_followers in (1500, 3000, 6000, 30000):
        lower_average, higher_average = _paired_calibration_average(
            lower_followers, 2 * lower_followers
        )
        uplift = higher_average / lower_average - 1
        calibrated_results[lower_followers] = (
            lower_average,
            higher_average,
            uplift,
        )
        assert 0.20 <= uplift <= 0.50

    reference_lower, reference_higher, reference_uplift = calibrated_results[3000]
    assert reference_lower == pytest.approx(12.0, abs=0.6)
    assert reference_higher == pytest.approx(15.6, abs=0.7)
    assert 0.25 <= reference_uplift <= 0.35


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
