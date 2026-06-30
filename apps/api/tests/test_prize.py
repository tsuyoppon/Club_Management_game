from app.services.prize import get_prize_amount_for_rank


def test_prize_amounts_for_rank():
    assert get_prize_amount_for_rank(1) == 20_000_000
    assert get_prize_amount_for_rank(2) == 10_000_000
    assert get_prize_amount_for_rank(3) == 5_000_000
    assert get_prize_amount_for_rank(4) == 0
    assert get_prize_amount_for_rank(5) == 0
