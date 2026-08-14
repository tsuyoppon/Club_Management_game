from decimal import Decimal

import pytest

from app.config import constants
from app.services import attendance, fanbase, finance, match_results
from app.services.current_performance import calculate_current_rank_score


EXPECTED_SCORES = {
    2: [0.6125, 0.3875],
    3: [0.725, 0.5, 0.275],
    4: [0.8375, 0.6125, 0.3875, 0.1625],
    5: [0.95, 0.725, 0.5, 0.275, 0.05],
}


@pytest.mark.parametrize("club_count, expected", EXPECTED_SCORES.items())
def test_current_rank_scores_have_fixed_step_and_neutral_mean(club_count, expected):
    scores = [
        calculate_current_rank_score(rank, club_count)
        for rank in range(1, club_count + 1)
    ]

    assert scores == pytest.approx(expected)
    assert sum(scores) / len(scores) == pytest.approx(0.5)
    assert all(
        left - right == pytest.approx(0.225)
        for left, right in zip(scores, scores[1:])
    )


def test_current_rank_score_uses_neutral_for_missing_or_degenerate_standings():
    assert calculate_current_rank_score(None, 5) == 0.5
    assert calculate_current_rank_score(1, 1) == 0.5
    assert calculate_current_rank_score(None, 0) == 0.5


def test_current_rank_score_validates_rank_and_clips_future_large_leagues():
    with pytest.raises(ValueError):
        calculate_current_rank_score(0, 5)
    with pytest.raises(ValueError):
        calculate_current_rank_score(6, 5)

    assert calculate_current_rank_score(1, 10) == 1.0
    assert calculate_current_rank_score(10, 10) == 0.0


def test_attendance_and_fanbase_use_the_same_shared_rank_score():
    assert finance.calculate_current_rank_score is calculate_current_rank_score
    assert match_results.calculate_current_rank_score is calculate_current_rank_score

    first = calculate_current_rank_score(1, 2)
    second = calculate_current_rank_score(2, 2)
    assert float(constants.HOME_ATTENDANCE_BETA_1) * (
        first - second
    ) == pytest.approx(0.18)
    fanbase_growth_gap = fanbase.A3 * Decimal(str(first - second))
    assert float(fanbase_growth_gap) == pytest.approx(0.00225)


def test_attendance_reads_rank_coefficient_from_central_constants(monkeypatch):
    common = {
        "home_fb": 10_000,
        "away_fb": 10_000,
        "hist": 0.5,
        "promo": 0,
        "weather": "sunny",
        "event": False,
    }
    monkeypatch.setattr(constants, "HOME_ATTENDANCE_BETA_1", Decimal("0"))

    first, _ = _home_attendance(perf=1.0, **common)
    second, _ = _home_attendance(perf=0.0, **common)

    assert first == second


def _home_attendance(*, home_fb, away_fb, perf, hist, promo, weather, event):
    home, away, total = attendance.calculate_attendance(
        home_fb=home_fb,
        away_fb=away_fb,
        weather=weather,
        perf_val=perf,
        hist_perf_val=hist,
        next_promo_spend=Decimal(str(promo)),
        is_event=event,
    )
    assert total == home + away
    return home, away


def test_two_club_rank_effect_is_between_twenty_and_twenty_five_percent_of_old():
    common = {
        "home_fb": 10_579,
        "away_fb": 9_361,
        "hist": 1.0,
        "promo": 1_000_000,
        "weather": "sunny",
        "event": False,
    }
    old_first, old_away = _home_attendance(perf=1.0, **common)
    old_second, _ = _home_attendance(perf=0.0, **common)
    new_first, new_away = _home_attendance(
        perf=calculate_current_rank_score(1, 2), **common
    )
    new_second, _ = _home_attendance(
        perf=calculate_current_rank_score(2, 2), **common
    )

    effect_ratio = (new_first - new_second) / (old_first - old_second)
    assert 0.20 <= effect_ratio <= 0.25
    assert effect_ratio == pytest.approx(297 / 1322)
    assert new_away == old_away


@pytest.mark.parametrize(
    "home_fb, away_fb, rank, hist, promo, weather, event, expected",
    [
        (10_422, 9_528, 2, 1.0, 1_000_000, "sunny", False, 1_880),
        (10_579, 9_361, 1, 1.0, 1_000_000, "sunny", False, 2_197),
        (10_745, 9_194, 1, 1.0, 1_000_000, "sunny", False, 2_222),
        (10_917, 9_028, 1, 1.0, 1_000_000, "sunny", False, 2_248),
        (11_076, 8_917, 1, 1.0, 1_000_000, "sunny", True, 2_657),
        (8_745, 11_247, 1, 0.0, 0, "cloudy", False, 873),
        (8_783, 11_194, 1, 0.0, 0, "sunny", False, 1_047),
        (8_804, 11_181, 1, 0.0, 0, "rain", False, 608),
        (8_838, 11_131, 1, 0.0, 0, "cloudy", False, 880),
    ],
)
def test_room_counterfactual_home_attendance(
    home_fb, away_fb, rank, hist, promo, weather, event, expected
):
    home, _ = _home_attendance(
        home_fb=home_fb,
        away_fb=away_fb,
        perf=calculate_current_rank_score(rank, 2),
        hist=hist,
        promo=promo,
        weather=weather,
        event=event,
    )

    assert home == expected


def test_neutral_rank_keeps_opening_match_unchanged():
    home, _ = _home_attendance(
        home_fb=8_718,
        away_fb=11_306,
        perf=calculate_current_rank_score(None, 2),
        hist=0.0,
        promo=0,
        weather="sunny",
        event=True,
    )

    assert home == 1_147


@pytest.mark.parametrize(
    "fixtures, expected_old_effect, expected_new_effect",
    [
        (
            [
                (10_579, 9_361, 1.0, 1_000_000, "sunny", False),
                (10_745, 9_194, 1.0, 1_000_000, "sunny", False),
                (10_917, 9_028, 1.0, 1_000_000, "sunny", False),
                (11_076, 8_917, 1.0, 1_000_000, "sunny", True),
            ],
            1_388.5,
            312.0,
        ),
        (
            [
                (8_745, 11_247, 0.0, 0, "cloudy", False),
                (8_783, 11_194, 0.0, 0, "sunny", False),
                (8_804, 11_181, 0.0, 0, "rain", False),
                (8_838, 11_131, 0.0, 0, "cloudy", False),
            ],
            578.0,
            128.5,
        ),
    ],
)
def test_room_rank_effect_acceptance_values(
    fixtures, expected_old_effect, expected_new_effect
):
    old_effects = []
    new_effects = []
    for home_fb, away_fb, hist, promo, weather, event in fixtures:
        common = {
            "home_fb": home_fb,
            "away_fb": away_fb,
            "hist": hist,
            "promo": promo,
            "weather": weather,
            "event": event,
        }
        old_first, _ = _home_attendance(perf=1.0, **common)
        old_second, _ = _home_attendance(perf=0.0, **common)
        new_first, _ = _home_attendance(
            perf=calculate_current_rank_score(1, 2), **common
        )
        new_second, _ = _home_attendance(
            perf=calculate_current_rank_score(2, 2), **common
        )
        old_effects.append(old_first - old_second)
        new_effects.append(new_first - new_second)

    old_average = sum(old_effects) / len(old_effects)
    new_average = sum(new_effects) / len(new_effects)
    assert old_average == expected_old_effect
    assert new_average == expected_new_effect
    assert 0.20 <= new_average / old_average <= 0.25
