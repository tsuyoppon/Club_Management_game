from uuid import UUID
import random
import math
from sqlalchemy.orm import Session
from sqlalchemy import select, desc, func, or_
from app.db import models

# v1Spec Constants
# ---------------------------------------------------------
# 10.5 Existing Sponsors (Churn)
# Churn = clip(c0 - c1*ln(1+C) - c2*(Perf-0.5) - c3*FanGrowth, c_min, c_max)
CHURN_C0 = 0.22
CHURN_C1 = 0.05
CHURN_C2 = 0.06
CHURN_C3 = 0.04
CHURN_MIN = 0.05
CHURN_MAX = 0.45

# 10.6 New Sponsors
# Leads L = round(L0 + l1*ln(1+C) + l2*ln(1+N) + l3*(Perf-0.5) + l4*ln(1+Followers))
LEADS_L0 = 8.0
LEADS_L1 = 4.0
LEADS_L2 = 1.2
LEADS_L3 = 2.0
LEADS_L4 = 0.8

# Conversion p = sigmoid(a0 + a1*ln(1+C) + a2*(Perf-0.5) + a3*ln(1+Followers))
CONV_A0 = -2.0
CONV_A1 = 0.55
CONV_A2 = 0.45
CONV_A3 = 0.10
# ---------------------------------------------------------

def ensure_sponsor_state(db: Session, club_id: UUID, season_id: UUID):
    state = db.execute(select(models.ClubSponsorState).where(
        models.ClubSponsorState.club_id == club_id,
        models.ClubSponsorState.season_id == season_id
    )).scalar_one_or_none()
    
    if not state:
        # Try to inherit from previous season
        current_season = db.execute(select(models.Season).where(models.Season.id == season_id)).scalar_one()
        
        prev_season = db.execute(select(models.Season).where(
            models.Season.game_id == current_season.game_id,
            models.Season.created_at < current_season.created_at
        ).order_by(desc(models.Season.created_at)).limit(1)).scalar_one_or_none()
        
        initial_count = 0
        if prev_season:
            prev_state = db.execute(select(models.ClubSponsorState).where(
                models.ClubSponsorState.club_id == club_id,
                models.ClubSponsorState.season_id == prev_season.id
            )).scalar_one_or_none()
            
            if prev_state:
                # Use next_count if determined, otherwise fallback to current count
                initial_count = prev_state.next_count if prev_state.next_count is not None else prev_state.count

        state = models.ClubSponsorState(
            club_id=club_id,
            season_id=season_id,
            count=initial_count,
            unit_price=5000000, # v1 Spec
            sales_effort_history={}
        )
        db.add(state)
        db.flush()
    return state

def record_sales_effort(db: Session, club_id: UUID, season_id: UUID, month: int, effort: int):
    """
    Record sales effort for a specific month (Apr=9, May=10, Jun=11).
    """
    state = ensure_sponsor_state(db, club_id, season_id)
    
    # Update history
    history = dict(state.sales_effort_history) if state.sales_effort_history else {}
    history[str(month)] = effort
    state.sales_effort_history = history
    db.add(state)
    return state

def get_performance_metrics(db: Session, club_id: UUID, season_id: UUID):
    """
    Calculate Perf (Win Rate) and Followers (Base Attendance).
    Perf = (Wins + 0.5 * Draws) / Total Matches
    """
    # 1. Calculate Perf
    matches = db.execute(select(models.Match).join(models.Fixture).where(
        models.Fixture.season_id == season_id,
        models.Match.status == models.MatchStatus.played,
        or_(models.Fixture.home_club_id == club_id, models.Fixture.away_club_id == club_id)
    )).scalars().all()
    
    wins = 0
    draws = 0
    total = 0
    
    for match in matches:
        total += 1
        is_home = match.fixture.home_club_id == club_id
        
        if match.home_goals == match.away_goals:
            draws += 1
        elif is_home and match.home_goals > match.away_goals:
            wins += 1
        elif not is_home and match.away_goals > match.home_goals:
            wins += 1
            
    perf = 0.5 # Default if no matches
    if total > 0:
        perf = (wins + 0.5 * draws) / total
        
    # 2. Get Followers (Base Attendance)
    profile = db.execute(select(models.ClubFinancialProfile).where(
        models.ClubFinancialProfile.club_id == club_id
    )).scalar_one_or_none()
    
    followers = float(profile.base_attendance) if profile else 10000.0
    
    # 3. Fan Growth (Assume 0 for now as we don't track history yet)
    fan_growth = 0.0
    
    return perf, followers, fan_growth

def determine_next_sponsors(db: Session, club_id: UUID, season_id: UUID):
    """
    Determine N_next in July (Month 7 in calendar, Month 12 in index).
    Uses history from Apr(9), May(10), Jun(11).
    """
    state = ensure_sponsor_state(db, club_id, season_id)
    
    # Idempotency: If already determined, do not change
    if state.next_count is not None:
        return state
        
    # Calculate Effective Effort (Average of Apr-Jun)
    history = state.sales_effort_history or {}
    efforts = [int(history.get(str(m), 0)) for m in [9, 10, 11]]
    effective_effort = sum(efforts) / 3.0 if efforts else 0.0
    
    # Get Metrics
    perf, followers, fan_growth = get_performance_metrics(db, club_id, season_id)
    
    # Deterministic Seed
    seed = f"{season_id}-{club_id}-sponsor"
    rng = random.Random(seed)
    
    # -----------------------------------------------------
    # 1. Existing Sponsors (Churn)
    # Churn = clip(c0 - c1*ln(1+C) - c2*(Perf-0.5) - c3*FanGrowth, c_min, c_max)
    # -----------------------------------------------------
    term_c = CHURN_C1 * math.log(1 + effective_effort)
    term_p = CHURN_C2 * (perf - 0.5)
    term_f = CHURN_C3 * fan_growth
    
    churn_raw = CHURN_C0 - term_c - term_p - term_f
    churn = max(CHURN_MIN, min(CHURN_MAX, churn_raw))
    
    # N_exist_next = round(N_this * (1 - Churn))
    # Note: Using probabilistic round or simple round? Spec says "round".
    # But usually retention is individual. 
    # "N_exist_next = round(...)" implies a deterministic calculation on the count.
    # However, to be safe and consistent with "Churn rate", let's use simple rounding.
    n_exist_next = round(state.count * (1.0 - churn))
    
    # -----------------------------------------------------
    # 2. New Sponsors
    # -----------------------------------------------------
    # Leads L
    # L = round(L0 + l1*ln(1+C) + l2*ln(1+N) + l3*(Perf-0.5) + l4*ln(1+Followers))
    term_l_c = LEADS_L1 * math.log(1 + effective_effort)
    term_l_n = LEADS_L2 * math.log(1 + state.count)
    term_l_p = LEADS_L3 * (perf - 0.5)
    term_l_f = LEADS_L4 * math.log(1 + followers)
    
    leads_raw = LEADS_L0 + term_l_c + term_l_n + term_l_p + term_l_f
    leads = max(0, round(leads_raw))
    
    # Conversion Rate p
    # p = sigmoid(a0 + a1*ln(1+C) + a2*(Perf-0.5) + a3*ln(1+Followers))
    term_p_c = CONV_A1 * math.log(1 + effective_effort)
    term_p_p = CONV_A2 * (perf - 0.5)
    term_p_f = CONV_A3 * math.log(1 + followers)
    
    logit = CONV_A0 + term_p_c + term_p_p + term_p_f
    # Sigmoid
    try:
        prob = 1.0 / (1.0 + math.exp(-logit))
    except OverflowError:
        prob = 0.0 if logit < 0 else 1.0
        
    # New Count ~ Binomial(L, p)
    n_new_next = 0
    for _ in range(leads):
        if rng.random() < prob:
            n_new_next += 1
            
    total_next = n_exist_next + n_new_next
    
    state.next_count = total_next
    db.add(state)
    return state

def process_sponsor_revenue(db: Session, club_id: UUID, season_id: UUID, turn_id: UUID):
    """
    In August (Month 8), record revenue based on `count` * `unit_price`.
    """
    state = ensure_sponsor_state(db, club_id, season_id)
    
    if state.is_revenue_recorded:
        return # Idempotent
        
    revenue = state.count * state.unit_price
    
    # Create Ledger
    ledger = models.ClubFinancialLedger(
        club_id=club_id,
        turn_id=turn_id,
        kind="sponsor_annual",
        amount=revenue,
        meta={"description": "Annual Sponsor Revenue", "count": state.count, "unit_price": float(state.unit_price)}
    )
    db.add(ledger)
    
    state.is_revenue_recorded = True
    db.add(state)
