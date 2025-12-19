import pytest
from app.services.match_results import (
    calculate_tp,
    calculate_er,
    calculate_win_probs,
    determine_outcome,
    determine_score,
    SCORE_W,
    SCORE_D,
    SCORE_A,
)
from app.db.models import Match, Club, Fixture, MatchStatus


def test_calculate_er():
    # Home team: TP=15, HomeAdv=3.0, Streak=1 -> 15 + 3 + 0.5 = 18.5
    assert calculate_er(15, True, 1) == 18.5
    # Away team: TP=15, HomeAdv=0, Streak=0 -> 15
    assert calculate_er(15, False, 0) == 15
    # Away team with streak: TP=15, HomeAdv=0, Streak=2 -> 15 + 1.0 = 16.0
    assert calculate_er(15, False, 2) == 16.0
    # Streak Cap check: Streak=10 -> 0.5*10=5 -> Cap 2.0
    assert calculate_er(15, False, 10) == 17.0

def test_calculate_win_probs():
    # Equal ER
    p_home, p_draw, p_away = calculate_win_probs(20, 20)
    # Delta ER = 0
    # P_draw = 0.3 * exp(0) = 0.3
    # P_H_no_draw = sigmoid(0) = 0.5
    # P_home = (1 - 0.3) * 0.5 = 0.35
    # P_away = (1 - 0.3) * (1 - 0.5) = 0.35
    assert p_draw == 0.3
    assert p_home == 0.35
    assert p_away == 0.35
    assert abs((p_home + p_draw + p_away) - 1.0) < 1e-9

    # Home much stronger (Delta ER = 10)
    # P_draw = 0.3 * exp(-0.8) approx 0.3 * 0.449 = 0.134
    # P_H_no_draw = sigmoid(1.5) approx 0.817
    # P_home = (1 - 0.134) * 0.817 = 0.707
    # P_away = (1 - 0.134) * (1 - 0.817) = 0.158
    p_home_s, p_draw_s, p_away_s = calculate_win_probs(30, 20)
    assert p_home_s > p_away_s
    assert p_draw_s < 0.3

def test_determine_outcome():
    # Mock random to test deterministic paths if needed, 
    # but for now just check structure
    p_home, p_draw, p_away = 0.5, 0.3, 0.2
    seed = "test_seed"
    outcome = determine_outcome(p_home, p_draw, seed)
    assert outcome in ["H", "D", "A"]

def test_determine_score():
    # Test signature and return type
    # Outcome "H", ER_H=20, ER_A=10 (Delta=10), Seed="test"
    score = determine_score("H", 20.0, 10.0, "test_seed")
    assert isinstance(score, tuple)
    assert len(score) == 2
    assert score[0] > score[1] # Home win usually implies H > A
    
    # Outcome "A"
    score_a = determine_score("A", 10.0, 20.0, "test_seed")
    assert score_a[1] > score_a[0]
    
    # Outcome "D"
    score_d = determine_score("D", 15.0, 15.0, "test_seed")
    assert score_d[0] == score_d[1]


def test_score_candidates_respected():
    # Ensure determine_score never emits a score outside the allowed candidate sets
    candidates_w = [s for s, w in SCORE_W]
    candidates_a = [s for s, w in SCORE_A]
    candidates_d = [s for s, w in SCORE_D]
    
    for i in range(50):
        h, a = determine_score("H", 20.0, 10.0, f"seed_h_{i}")
        assert (h, a) in candidates_w

        h, a = determine_score("A", 10.0, 20.0, f"seed_a_{i}")
        assert (h, a) in candidates_a

        h, a = determine_score("D", 15.0, 15.0, f"seed_d_{i}")
        assert (h, a) in candidates_d


def test_large_delta_produces_larger_goal_diff():
    # With a larger |Delta| we should see, on average, larger goal differences
    # Increase sample size to reduce noise, as the effect size is small (~0.06 goals)
    diffs_small = []
    diffs_large = []
    n_samples = 2000

    for i in range(n_samples):
        h, a = determine_score("H", 15.0, 15.0, f"seed_small_{i}")
        diffs_small.append(h - a)

        h, a = determine_score("H", 25.0, 10.0, f"seed_large_{i}")
        diffs_large.append(h - a)

    assert (sum(diffs_large) / len(diffs_large)) > (sum(diffs_small) / len(diffs_small))
