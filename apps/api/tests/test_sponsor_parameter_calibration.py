from decimal import Decimal

import pytest

from app.config.constants import (
    LEADS_L0,
    SALES_EFFORT_REFERENCE_MONTHLY_SALARY,
    SALES_EFFORT_STAFF_TO_SPEND_EFFICIENCY,
    STAFF_SALARY_ANNUAL,
)
from app.services.sales_effort import calculate_monthly_effort
from app.services.sponsor import _calculate_churn_rate


def test_base_new_sponsor_leads_are_four():
    assert LEADS_L0 == Decimal("4.0")


def test_zero_retention_effort_has_forty_percent_neutral_churn():
    assert _calculate_churn_rate(c_ret=0.0, perf=0.5, fan_growth=0.0) == pytest.approx(0.40)


def test_normal_retention_effort_restores_churn_to_target_range():
    churn = _calculate_churn_rate(c_ret=2.2, perf=0.6, fan_growth=0.1)
    assert 0.15 <= churn <= 0.20


def test_reference_salary_matches_staff_payroll_model():
    assert SALES_EFFORT_REFERENCE_MONTHLY_SALARY == STAFF_SALARY_ANNUAL / Decimal("12")


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
