import math
import random
import logging
from datetime import datetime
from uuid import UUID
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, or_
from app.db import models
from app.services import weather as weather_service
from app.services import attendance as attendance_service
from app.services import standings as standings_service
from app.services import historical_performance

logger = logging.getLogger(__name__)

# v1Spec Constants
# ---------------------------------------------------------
# 1. Win/Draw Probability Model
# p_draw = D0 * exp(-C * |Delta|)
D0 = 0.30
C = 0.08
# p_{H|no_draw} = 1 / (1 + exp(-K * Delta))
K = 0.15

# 2. Team Power (TP) Generation
# TP = ALPHA * ln(1 + B / B_REF) + BETA * ln(1 + A / A_REF)
ALPHA = 10.0
BETA = 1.0
# Reference values (Unit: Million JPY)
# B_REF: Reference Annual Budget (e.g. 500 Million)
B_REF = 500.0
# A_REF: Reference Academy Cumulative (e.g. 100 Million)
A_REF = 100.0

# 3. Effective Rating (ER)
# ER = TP + HOME_ADVANTAGE + StreakAdj
HOME_ADVANTAGE = 3.0  # v1Spec: +3
STREAK_FACTOR = 0.5   # +0.5 per win
STREAK_CAP = 2.0      # Max +/- 2

# 4. Score Model
# Goal Difference Adjustment
LAMBDA = 0.08

# Score Candidates & Weights
# Home Win (W)
SCORE_W = [
    ((1, 0), 0.22), ((2, 0), 0.16), ((2, 1), 0.22), ((3, 0), 0.10),
    ((3, 1), 0.14), ((3, 2), 0.06), ((4, 0), 0.04), ((4, 1), 0.06)
]
# Draw (D)
SCORE_D = [
    ((0, 0), 0.22), ((1, 1), 0.58), ((2, 2), 0.17), ((3, 3), 0.03)
]
# Away Win (A) -> Reverse of W
SCORE_A = [((a, h), w) for (h, a), w in SCORE_W]

# ---------------------------------------------------------

def calculate_tp(db: Session, club_id: UUID, season_id: UUID) -> float:
    """
    Calculate Team Power (TP) based on Reinforcement and Academy.
    TP_i = alpha * ln(1 + B_i / B_ref) + beta * ln(1 + A_cum_i / A_ref)
    """
    # 1. Reinforcement (B_i)
    reinforcement = db.execute(select(models.ClubReinforcementPlan).where(
        models.ClubReinforcementPlan.club_id == club_id,
        models.ClubReinforcementPlan.season_id == season_id
    )).scalar_one_or_none()
    
    # Convert to Million JPY
    r_budget_raw = float(reinforcement.annual_budget + reinforcement.additional_budget) if reinforcement else 0.0
    b_i = r_budget_raw / 1_000_000.0
    
    # 2. Academy (A_cum_i)
    academy = db.execute(select(models.ClubAcademy).where(
        models.ClubAcademy.club_id == club_id,
        models.ClubAcademy.season_id == season_id
    )).scalar_one_or_none()
    
    # Convert to Million JPY
    a_invest_raw = float(academy.cumulative_investment) if academy else 0.0
    a_cum_i = a_invest_raw / 1_000_000.0
    
    # Calculation
    term_b = ALPHA * math.log(1 + b_i / B_REF)
    term_a = BETA * math.log(1 + a_cum_i / A_REF)
    
    return term_b + term_a

def get_streak(db: Session, club_id: UUID, season_id: UUID, current_turn_month: int) -> int:
    """
    Calculate current winning streak in the current season before this turn.
    Positive for win streak, negative for loss streak.
    """
    # Get played matches for this club in this season, ordered by date desc
    matches = db.execute(select(models.Match).join(models.Fixture).where(
        models.Fixture.season_id == season_id,
        models.Fixture.match_month_index < current_turn_month,
        models.Match.status == models.MatchStatus.played,
        or_(models.Fixture.home_club_id == club_id, models.Fixture.away_club_id == club_id)
    ).order_by(models.Fixture.match_month_index.desc())).scalars().all()
    
    streak = 0
    if not matches:
        return 0

    # Determine if we are counting wins or losses based on the most recent match
    last_match = matches[0]
    is_home = last_match.fixture.home_club_id == club_id
    
    # Check result of last match
    last_result = 0 # 1: Win, -1: Loss, 0: Draw
    if is_home:
        if last_match.home_goals > last_match.away_goals: last_result = 1
        elif last_match.home_goals < last_match.away_goals: last_result = -1
    else:
        if last_match.away_goals > last_match.home_goals: last_result = 1
        elif last_match.away_goals < last_match.home_goals: last_result = -1
        
    if last_result == 0:
        return 0
        
    # Count streak
    for match in matches:
        is_home = match.fixture.home_club_id == club_id
        current_result = 0
        if is_home:
            if match.home_goals > match.away_goals: current_result = 1
            elif match.home_goals < match.away_goals: current_result = -1
        else:
            if match.away_goals > match.home_goals: current_result = 1
            elif match.away_goals < match.home_goals: current_result = -1
            
        if current_result == last_result:
            streak += current_result # Adds 1 or -1
        else:
            break
            
    return streak

def calculate_er(tp: float, is_home: bool, streak: int) -> float:
    """
    Calculate Effective Rating (ER).
    ER = TP + HomeAdv + StreakAdj
    StreakAdj = +/- min(2, 0.5 * |streak|)
    """
    er = tp
    if is_home:
        er += HOME_ADVANTAGE
    
    # Streak adjustment
    # streak is positive for wins, negative for losses
    adj = streak * STREAK_FACTOR
    
    # Clip to +/- STREAK_CAP
    if adj > STREAK_CAP:
        adj = STREAK_CAP
    elif adj < -STREAK_CAP:
        adj = -STREAK_CAP
        
    er += adj
    
    return er

def calculate_win_probs(er_h: float, er_a: float):
    """
    Calculate probabilities for Home Win, Draw, Away Win.
    """
    delta = er_h - er_a
    abs_delta = abs(delta)
    
    # P_draw
    p_draw = D0 * math.exp(-C * abs_delta)
    
    # P_H_no_draw (Conditional probability of Home win given no draw)
    # 1 / (1 + exp(-k * delta))
    # Note: If delta is large positive, exp(-k*delta) is small, P -> 1. Correct.
    try:
        p_h_no_draw = 1.0 / (1.0 + math.exp(-K * delta))
    except OverflowError:
        p_h_no_draw = 0.0 if delta < 0 else 1.0
        
    p_home = (1.0 - p_draw) * p_h_no_draw
    p_away = (1.0 - p_draw) * (1.0 - p_h_no_draw)
    
    return p_home, p_draw, p_away

def determine_outcome(p_home: float, p_draw: float, seed: str) -> str:
    """
    Determine result: 'H', 'D', 'A'
    """
    rng = random.Random(seed)
    r = rng.random()
    
    if r < p_home:
        return 'H'
    elif r < p_home + p_draw:
        return 'D'
    else:
        return 'A'

def determine_score(outcome: str, er_home: float, er_away: float, seed: str) -> tuple[int, int]:
    """
    Determine the exact score based on the outcome and ER difference.
    """
    delta = er_home - er_away
    abs_delta_term = min(abs(delta) / 12.0, 1.0)
    
    if outcome == 'H': # Home Win
        base_candidates = SCORE_W
    elif outcome == 'A': # Away Win
        base_candidates = SCORE_A
    else: # Draw
        base_candidates = SCORE_D
        
    # Calculate adjusted weights
    weighted_candidates = []
    total_weight = 0.0
    
    for (score, weight) in base_candidates:
        h_score, a_score = score
        goal_diff = abs(h_score - a_score)
        
        # Adjustment
        # weight_adj = weight * exp(LAMBDA * (goal_diff - 1) * min(|Delta|/12, 1))
        adjustment_exponent = LAMBDA * (goal_diff - 1) * abs_delta_term
        weight_adj = weight * math.exp(adjustment_exponent)
        
        weighted_candidates.append((score, weight_adj))
        total_weight += weight_adj
        
    # Select based on seed
    rng = random.Random(seed + "-score")
    r = rng.random()
    target_weight = r * total_weight
    
    current_cum_weight = 0.0
    selected_score = base_candidates[0][0] # Default
    
    for (score, w) in weighted_candidates:
        current_cum_weight += w
        if current_cum_weight >= target_weight:
            selected_score = score
            break
            
    return selected_score

def process_matches_for_turn(db: Session, season_id: UUID, turn_id: UUID, month_index: int):
    """
    Process all matches for the given month.
    Idempotent: Checks if match is already played.
    """
    # 1. Get Fixtures for this month
    fixtures = db.execute(select(models.Fixture).where(
        models.Fixture.season_id == season_id,
        models.Fixture.match_month_index == month_index
    )).scalars().all()
    
    hist_perf_cache = {}

    for fixture in fixtures:
        if fixture.is_bye:
            continue
            
        # Ensure Match record exists (it should, but good to be safe or create if missing?)
        # Models say Match is 1-to-1 with Fixture.
        match = fixture.match
        if not match:
            # Should have been created with fixture? 
            # If not, create it.
            logger.warning(f"Fixture {fixture.id} has no match record. Creating fallback match.")
            match = models.Match(fixture_id=fixture.id, status=models.MatchStatus.scheduled)
            db.add(match)
            db.flush()
            
        if match.status == models.MatchStatus.played:
            continue # Already processed
            
        # --- PR5: Weather & Attendance ---
        # 1. Determine Weather
        weather = weather_service.determine_weather()
        fixture.weather = weather
        
        # 2. Get Fanbase States
        fb_home = db.query(models.ClubFanbaseState).filter_by(club_id=fixture.home_club_id, season_id=season_id).first()
        fb_away = db.query(models.ClubFanbaseState).filter_by(club_id=fixture.away_club_id, season_id=season_id).first()
        
        home_fb_count = fb_home.fb_count if fb_home else 60000
        away_fb_count = fb_away.fb_count if fb_away else 60000
        
        # 3. Get Performance (Rank)
        perf_val = 0.5
        if fixture.home_club_id not in hist_perf_cache:
            hist_perf_cache[fixture.home_club_id] = (
                historical_performance.get_hist_perf_value(
                    db, season_id, fixture.home_club_id
                )
            )
        hist_perf_val = hist_perf_cache[fixture.home_club_id]
        
        if month_index > 1:
            # Calculate standings up to previous month
            calc = standings_service.StandingsCalculator(db, season_id)
            standings = calc.calculate(up_to_month=month_index-1)
            
            # Find home club rank
            num_clubs = len(standings)
            if num_clubs > 1:
                for s in standings:
                    if s["club_id"] == fixture.home_club_id:
                        rank = s["rank"]
                        # Normalize: 1st -> 1.0, Last -> 0.0
                        perf_val = 1.0 - (rank - 1) / (num_clubs - 1)
                        break
        
        # 4. Get Promo Spend (Next Home Promo)
        # Input in previous month (month_index - 1)
        next_promo_spend = Decimal(0)
        if month_index > 1:
            prev_turn = db.query(models.Turn).filter_by(season_id=season_id, month_index=month_index-1).first()
            if prev_turn:
                decision = db.query(models.TurnDecision).filter_by(turn_id=prev_turn.id, club_id=fixture.home_club_id).first()
                if decision and decision.payload_json:
                    val = decision.payload_json.get("next_home_promo")
                    if val is not None:
                        next_promo_spend = Decimal(val)

        # 5. Calculate Attendance
        # Event: Aug (1) or May (10)
        is_event = (month_index == 1 or month_index == 10)
        
        h_att, a_att, t_att = attendance_service.calculate_attendance(
            home_fb=home_fb_count,
            away_fb=away_fb_count,
            weather=weather,
            perf_val=perf_val,
            hist_perf_val=hist_perf_val,
            next_promo_spend=next_promo_spend,
            is_event=is_event
        )
        
        fixture.home_attendance = h_att
        fixture.away_attendance = a_att
        fixture.total_attendance = t_att
        
        db.add(fixture)
        # -------------------------------
            
        # 2. Calculate TP
        tp_home = calculate_tp(db, fixture.home_club_id, season_id)
        tp_away = calculate_tp(db, fixture.away_club_id, season_id)
        
        # 3. Get Streaks
        streak_home = get_streak(db, fixture.home_club_id, season_id, month_index)
        streak_away = get_streak(db, fixture.away_club_id, season_id, month_index)
        
        # 4. Calculate ER
        er_home = calculate_er(tp_home, True, streak_home)
        er_away = calculate_er(tp_away, False, streak_away)
        
        # 5. Calculate Probs
        p_h, p_d, p_a = calculate_win_probs(er_home, er_away)
        
        # 6. Determine Outcome
        seed = f"{fixture.id}-{turn_id}-result"
        outcome = determine_outcome(p_h, p_d, seed)
        
        # 7. Determine Score
        h_goals, a_goals = determine_score(outcome, er_home, er_away, seed)
        
        # 8. Update Match
        match.home_goals = h_goals
        match.away_goals = a_goals
        match.status = models.MatchStatus.played
        match.played_at = datetime.utcnow()
        
        db.add(match)
