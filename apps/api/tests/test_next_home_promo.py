from decimal import Decimal

import pytest

from app.config import constants
from app.services import attendance


@pytest.mark.parametrize(
    "spend, expected",
    [
        (0, 0.0),
        (500_000, 0.1769593735),
        (1_000_000, 0.3147754722),
        (2_000_000, 0.5056964471),
        (5_000_000, 0.7343320011),
        (10_000_000, 0.7946096424),
    ],
)
def test_next_home_promo_effect_matches_bounded_saturation_curve(spend, expected):
    effect = attendance.calculate_next_home_promo_effect(Decimal(spend))

    assert effect == pytest.approx(expected)


def test_next_home_promo_effect_is_monotonic_with_diminishing_increments():
    effects = [
        attendance.calculate_next_home_promo_effect(Decimal(spend))
        for spend in range(0, 6_000_000, 1_000_000)
    ]
    increments = [right - left for left, right in zip(effects, effects[1:])]

    assert effects == sorted(effects)
    assert all(left > right > 0 for left, right in zip(increments, increments[1:]))


def test_next_home_promo_effect_is_bounded_and_rejects_negative_spend():
    max_effect = float(constants.NEXT_HOME_PROMO_MAX_LOGIT_EFFECT)
    very_large = attendance.calculate_next_home_promo_effect(Decimal("1000000000"))

    assert very_large == pytest.approx(max_effect)
    assert very_large <= max_effect
    with pytest.raises(ValueError):
        attendance.calculate_next_home_promo_effect(Decimal("-1"))


def test_next_home_promo_changes_only_home_attendance_before_capacity_scaling():
    common = {
        "home_fb": 10_000,
        "away_fb": 10_000,
        "weather": "sunny",
        "perf_val": 0.5,
        "hist_perf_val": 0.5,
        "is_event": False,
    }

    without_promo = attendance.calculate_attendance(
        next_promo_spend=Decimal("0"), **common
    )
    with_promo = attendance.calculate_attendance(
        next_promo_spend=Decimal("1000000"), **common
    )

    assert with_promo[0] > without_promo[0]
    assert with_promo[1] == without_promo[1]
    assert with_promo[2] - without_promo[2] == with_promo[0] - without_promo[0]
