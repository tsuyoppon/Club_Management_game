import math
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

import pytest

from app.config import constants
from app.db import models
from app.routers.seasons import create_season_core
from app.services import attendance, fanbase


def _new_fanbase_state(
    db,
    *,
    ruleset_version: int,
    fb_count: int = 10_000,
    promotion_staff: int = 1,
    cumulative_promotion_staff: Decimal = Decimal("1"),
):
    game = models.Game(
        name=f"Fanbase calibration {uuid4()}",
        status=models.GameStatus.active,
        fanbase_ruleset_version=ruleset_version,
    )
    db.add(game)
    db.flush()
    season = models.Season(
        game_id=game.id,
        season_number=1,
        year_label="2026",
        status=models.SeasonStatus.running,
    )
    club = models.Club(game_id=game.id, name=f"Calibration Club {uuid4()}")
    db.add_all([season, club])
    db.flush()
    db.add(
        models.ClubStaff(
            club_id=club.id,
            role=models.StaffRole.promotion,
            count=promotion_staff,
            salary_per_person=Decimal("0"),
        )
    )
    state = models.ClubFanbaseState(
        club_id=club.id,
        season_id=season.id,
        fb_count=fb_count,
        fb_rate=Decimal(fb_count) / Decimal(fanbase.POPULATION),
        cumulative_promo=Decimal("0"),
        cumulative_ht=Decimal("0"),
        cumulative_promotion_staff=cumulative_promotion_staff,
        cumulative_hometown_staff=Decimal("1"),
        last_ht_spend=Decimal("0"),
        fb_trend_streak=0,
    )
    db.add(state)
    db.commit()
    db.refresh(state)
    return state


def _run_months(db, state, ruleset_version, spends, months=48):
    counts = []
    promo_assets = []
    promo_terms = []
    for month in range(months):
        spend = Decimal(str(spends[month])) if month < len(spends) else Decimal("0")
        state = fanbase.update_fanbase_for_turn(
            db,
            state,
            spend,
            Decimal("0"),
            0.5,
            0.5,
            fanbase_ruleset_version=ruleset_version,
        )
        counts.append(state.fb_count)
        promo_assets.append(Decimal(state.cumulative_promo))
        promo_terms.append(
            fanbase.promotion_growth_term(
                Decimal(state.cumulative_promo),
                ruleset_version,
            )
        )
    return counts, promo_assets, promo_terms


def _counterfactual(db, ruleset_version, spends, *, fb_count=10_000):
    baseline = _new_fanbase_state(
        db,
        ruleset_version=ruleset_version,
        fb_count=fb_count,
    )
    promoted = _new_fanbase_state(
        db,
        ruleset_version=ruleset_version,
        fb_count=fb_count,
    )
    baseline_counts, _, _ = _run_months(db, baseline, ruleset_version, [], 48)
    promoted_counts, assets, terms = _run_months(
        db, promoted, ruleset_version, spends, 48
    )
    gaps = [
        promoted - control
        for promoted, control in zip(promoted_counts, baseline_counts)
    ]
    return gaps, promoted_counts, assets, terms


@pytest.fixture(autouse=True)
def _deterministic_followers(monkeypatch):
    monkeypatch.setattr(fanbase.random, "gauss", lambda mean, sigma: mean)


def test_ruleset_v1_preserves_legacy_effect_and_v2_hits_four_year_target(db):
    legacy_gaps, _, _, _ = _counterfactual(
        db,
        constants.FANBASE_RULESET_LEGACY,
        [1_000_000],
    )
    revised_gaps, _, _, _ = _counterfactual(
        db,
        constants.FANBASE_RULESET_PROMO_ROI,
        [1_000_000],
    )

    # Numeric(10, 6) persistence rounds monthly FB rates to whole-person
    # resolution, so the legacy continuous estimate of 5-6 becomes 7 here.
    assert 5 <= legacy_gaps[47] <= 8
    assert 250 <= revised_gaps[11] <= 300
    assert 330 <= revised_gaps[23] <= 350
    assert 350 <= revised_gaps[47] <= 400


def test_v2_reference_case_recovers_cost_in_calibration_window(db):
    gaps, _, _, _ = _counterfactual(
        db,
        constants.FANBASE_RULESET_PROMO_ROI,
        [1_000_000],
    )
    home_months = [
        year * 12 + month
        for year in range(4)
        for month in (0, 2, 4, 6, 8)
    ]
    incremental_gross_profit = (
        sum(gaps[month] for month in home_months)
        * Decimal("0.11")
        * (
            constants.TICKET_PRICE
            + constants.MERCHANDISE_SPEND_PER_PERSON
            * constants.MERCHANDISE_MARGIN
        )
    )

    assert Decimal("1000000") <= incremental_gross_profit <= Decimal("1600000")


def _continuous_gap(spends, months=48):
    def simulate(monthly_spends):
        fb_rate = Decimal("0.01")
        cumulative_promo = Decimal("0")
        for month in range(months):
            spend = (
                Decimal(str(monthly_spends[month]))
                if month < len(monthly_spends)
                else Decimal("0")
            )
            cumulative_promo = (
                Decimal("0.9") * cumulative_promo + Decimal("0.1") * spend
            )
            growth = fanbase.G0 + fanbase.promotion_growth_term(
                cumulative_promo,
                constants.FANBASE_RULESET_PROMO_ROI,
            )
            fb_rate *= Decimal("1") + growth * (
                Decimal("1") - fb_rate / fanbase.F_MAX
            )
        return fb_rate * Decimal(fanbase.POPULATION)

    return simulate(spends) - simulate([])


def test_repeated_spend_stays_within_two_percent_of_twelve_single_investments():
    single_gap = _continuous_gap([1_000_000])
    repeated_gap = _continuous_gap([1_000_000] * 12)

    ratio = repeated_gap / (Decimal("12") * single_gap)
    assert Decimal("0.98") <= ratio <= Decimal("1.02")


def test_two_million_has_strictly_diminishing_returns(db):
    one_million, _, _, _ = _counterfactual(
        db, constants.FANBASE_RULESET_PROMO_ROI, [1_000_000]
    )
    two_million, _, _, _ = _counterfactual(
        db, constants.FANBASE_RULESET_PROMO_ROI, [2_000_000]
    )

    assert two_million[47] < 2 * one_million[47]


def test_ruleset_v2_effect_declines_in_relative_terms_near_fanbase_cap(db):
    small, _, _, _ = _counterfactual(
        db, constants.FANBASE_RULESET_PROMO_ROI, [1_000_000], fb_count=10_000
    )
    medium, _, _, _ = _counterfactual(
        db, constants.FANBASE_RULESET_PROMO_ROI, [1_000_000], fb_count=100_000
    )
    near_cap, near_cap_counts, _, _ = _counterfactual(
        db, constants.FANBASE_RULESET_PROMO_ROI, [1_000_000], fb_count=240_000
    )

    assert Decimal(medium[47]) / Decimal(100_000) < Decimal(small[47]) / Decimal(
        10_000
    )
    assert Decimal(near_cap[47]) / Decimal(240_000) < Decimal("0.002")
    assert max(near_cap_counts) <= int(fanbase.F_MAX * fanbase.POPULATION)


def test_promo_asset_and_growth_term_decay_monotonically_after_spend(db):
    state = _new_fanbase_state(
        db,
        ruleset_version=constants.FANBASE_RULESET_PROMO_ROI,
    )
    _, assets, terms = _run_months(
        db,
        state,
        constants.FANBASE_RULESET_PROMO_ROI,
        [1_000_000],
        months=12,
    )

    for previous, current in zip(assets, assets[1:]):
        assert current == (previous * Decimal("0.9")).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
    assert all(current < previous for previous, current in zip(terms, terms[1:]))


def test_promotion_staff_ewma_updates_before_v2_spend(db):
    state = _new_fanbase_state(
        db,
        ruleset_version=constants.FANBASE_RULESET_PROMO_ROI,
        promotion_staff=3,
    )
    state = fanbase.update_fanbase_for_turn(
        db,
        state,
        Decimal("1000000"),
        Decimal("0"),
        0.5,
        0.5,
        fanbase_ruleset_version=constants.FANBASE_RULESET_PROMO_ROI,
    )

    assert state.cumulative_promotion_staff == Decimal("1.2000")
    expected_multiplier = Decimal("1") + Decimal("0.4") * Decimal(str(math.log1p(0.1)))
    assert fanbase.promotion_staff_spend_multiplier(
        state.cumulative_promotion_staff,
        constants.FANBASE_RULESET_PROMO_ROI,
    ) == pytest.approx(expected_multiplier)
    assert state.cumulative_promo == pytest.approx(Decimal("100000") * expected_multiplier)


def test_promotion_staff_ewma_moves_toward_active_headcount_and_can_decline(db):
    state = _new_fanbase_state(
        db,
        ruleset_version=constants.FANBASE_RULESET_PROMO_ROI,
        promotion_staff=3,
    )
    counts, _, _ = _run_months(
        db,
        state,
        constants.FANBASE_RULESET_PROMO_ROI,
        [],
        months=24,
    )
    assert counts
    assert Decimal(state.cumulative_promotion_staff) > Decimal("2.8")
    assert Decimal(state.cumulative_promotion_staff) < Decimal("3")

    staff = db.query(models.ClubStaff).filter_by(
        club_id=state.club_id,
        role=models.StaffRole.promotion,
    ).one()
    staff.count = 1
    db.commit()
    previous = Decimal(state.cumulative_promotion_staff)
    _run_months(
        db,
        state,
        constants.FANBASE_RULESET_PROMO_ROI,
        [],
        months=1,
    )
    assert Decimal(state.cumulative_promotion_staff) == (
        Decimal("0.9") * previous + Decimal("0.1")
    ).quantize(
        Decimal("0.0001"),
        rounding=ROUND_HALF_UP,
    )


def test_three_staff_improves_v2_spend_but_zero_spend_remains_zero(db):
    one_staff = _new_fanbase_state(
        db,
        ruleset_version=constants.FANBASE_RULESET_PROMO_ROI,
        promotion_staff=1,
    )
    three_staff = _new_fanbase_state(
        db,
        ruleset_version=constants.FANBASE_RULESET_PROMO_ROI,
        promotion_staff=3,
    )
    zero_spend_staff = _new_fanbase_state(
        db,
        ruleset_version=constants.FANBASE_RULESET_PROMO_ROI,
        promotion_staff=3,
    )
    one_counts, one_assets, _ = _run_months(
        db, one_staff, constants.FANBASE_RULESET_PROMO_ROI, [1_000_000], 48
    )
    three_counts, three_assets, _ = _run_months(
        db, three_staff, constants.FANBASE_RULESET_PROMO_ROI, [1_000_000], 48
    )
    _, zero_spend_assets, _ = _run_months(
        db,
        zero_spend_staff,
        constants.FANBASE_RULESET_PROMO_ROI,
        [],
        1,
    )

    assert three_assets[0] > one_assets[0]
    assert three_counts[47] > one_counts[47]
    assert zero_spend_assets[0] == 0
    assert fanbase.promotion_staff_spend_multiplier(
        Decimal("3"), constants.FANBASE_RULESET_LEGACY
    ) == Decimal("1")


def test_unsupported_ruleset_fails_closed(db):
    state = _new_fanbase_state(db, ruleset_version=constants.FANBASE_RULESET_LEGACY)
    with pytest.raises(ValueError, match="Unsupported fanbase ruleset"):
        fanbase.update_fanbase_for_turn(
            db,
            state,
            Decimal("0"),
            Decimal("0"),
            0.5,
            0.5,
            fanbase_ruleset_version=999,
        )


def test_new_game_creation_paths_use_current_ruleset(client, db, auth_headers):
    standard = client.post(
        "/api/games",
        json={"name": "Ruleset API Game"},
        headers=auth_headers,
    )
    assert standard.status_code == 200
    standard_game = db.get(models.Game, standard.json()["id"])
    assert (
        standard_game.fanbase_ruleset_version
        == constants.CURRENT_FANBASE_RULESET_VERSION
    )

    browser = client.post(
        "/api/rooms",
        json={
            "display_name": "Ruleset Host",
            "room_name": "Ruleset Browser Game",
            "club_names": ["One FC", "Two FC"],
        },
    )
    assert browser.status_code == 201
    browser_game = db.get(models.Game, browser.json()["game_id"])
    assert (
        browser_game.fanbase_ruleset_version
        == constants.CURRENT_FANBASE_RULESET_VERSION
    )


def test_ruleset_and_staff_ewma_persist_across_seasons(db):
    game = models.Game(
        name="Fanbase ruleset continuity",
        fanbase_ruleset_version=constants.FANBASE_RULESET_PROMO_ROI,
    )
    db.add(game)
    db.flush()
    club = models.Club(game_id=game.id, name="Continuity FC")
    first_season = models.Season(
        game_id=game.id,
        season_number=1,
        year_label="2026",
        status=models.SeasonStatus.finished,
    )
    db.add_all([club, first_season])
    db.flush()
    db.add(
        models.ClubFanbaseState(
            club_id=club.id,
            season_id=first_season.id,
            fb_count=10_382,
            fb_rate=Decimal("0.010382"),
            cumulative_promo=Decimal("706.97"),
            cumulative_ht=Decimal("0"),
            cumulative_promotion_staff=Decimal("2.7500"),
            cumulative_hometown_staff=Decimal("1"),
            last_ht_spend=Decimal("0"),
            fb_trend_streak=1,
        )
    )
    db.commit()

    next_season = create_season_core(db, game, "2027")
    copied = db.query(models.ClubFanbaseState).filter_by(
        club_id=club.id,
        season_id=next_season.id,
    ).one()

    assert game.fanbase_ruleset_version == constants.FANBASE_RULESET_PROMO_ROI
    assert copied.fb_count == 10_382
    assert copied.cumulative_promo == Decimal("706.97")
    assert copied.cumulative_promotion_staff == Decimal("2.7500")


def test_capacity_still_caps_attendance_after_fanbase_growth():
    before = attendance.calculate_attendance(
        home_fb=240_000,
        away_fb=100_000,
        weather="sunny",
        perf_val=0.5,
        hist_perf_val=0.5,
        next_promo_spend=Decimal("0"),
    )
    after = attendance.calculate_attendance(
        home_fb=240_400,
        away_fb=100_000,
        weather="sunny",
        perf_val=0.5,
        hist_perf_val=0.5,
        next_promo_spend=Decimal("0"),
    )

    assert before[2] == constants.STADIUM_CAPACITY
    assert after[2] == constants.STADIUM_CAPACITY
