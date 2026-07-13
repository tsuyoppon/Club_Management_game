from decimal import Decimal

from app.config.constants import MATCH_OPERATION_FIXED_COST
from app.db.models import ClubFinancialProfile


def test_operating_cost_defaults_are_one_million_yen():
    assert MATCH_OPERATION_FIXED_COST == Decimal("1000000")
    assert ClubFinancialProfile.monthly_cost.default.arg == 1_000_000
