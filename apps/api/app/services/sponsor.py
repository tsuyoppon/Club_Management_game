from uuid import UUID
import random
import math
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import select, desc, func, or_
from app.db import models
from app.config.constants import (
    SPONSOR_PRICE_PER_COMPANY,
    CHURN_C0, CHURN_C1, CHURN_C2, CHURN_C3, CHURN_MIN, CHURN_MAX,
    LEADS_L0, LEADS_L1, LEADS_L2, LEADS_L3, LEADS_L4,
    CONV_A0, CONV_A1, CONV_A2, CONV_A3,
    PIPELINE_PROB_EXISTING, PIPELINE_PROB_NEW,
)

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
            unit_price=SPONSOR_PRICE_PER_COMPANY,
            sales_effort_history={},
            cumulative_effort_ret=Decimal("0"),
            cumulative_effort_new=Decimal("0"),
            pipeline_confirmed_exist=0,
            pipeline_confirmed_new=0,
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
        
    # 2. Get Followers (from fanbase state; July-updated value)
    fanbase_state = db.execute(select(models.ClubFanbaseState).where(
        models.ClubFanbaseState.club_id == club_id,
        models.ClubFanbaseState.season_id == season_id
    )).scalar_one_or_none()
    
    followers_value = None
    if fanbase_state:
        followers_value = fanbase_state.followers_public
        if followers_value is None:
            followers_value = fanbase_state.fb_count
    
    followers = float(followers_value) if followers_value is not None else 10000.0
    
    # 3. Fan Growth (delta vs previous season fanbase)
    fan_growth = 0.0
    if fanbase_state:
        current_followers = followers_value if followers_value is not None else 0
        current_season = db.execute(select(models.Season).where(
            models.Season.id == season_id
        )).scalar_one_or_none()
        
        if current_season:
            prev_season = db.execute(select(models.Season).where(
                models.Season.game_id == current_season.game_id,
                models.Season.created_at < current_season.created_at
            ).order_by(desc(models.Season.created_at)).limit(1)).scalar_one_or_none()
            
            if prev_season:
                prev_state = db.execute(select(models.ClubFanbaseState).where(
                    models.ClubFanbaseState.club_id == club_id,
                    models.ClubFanbaseState.season_id == prev_season.id
                )).scalar_one_or_none()
                
                if prev_state:
                    prev_followers = prev_state.followers_public
                    if prev_followers is None:
                        prev_followers = prev_state.fb_count
                    if prev_followers and prev_followers > 0:
                        fan_growth = (current_followers - prev_followers) / float(prev_followers)
    
    return perf, followers, fan_growth

def determine_next_sponsors(db: Session, club_id: UUID, season_id: UUID):
    """
    Determine N_next in July (Month 7 in calendar, Month 12 in index).
    Uses cumulative effort C^ret(t=12) and C^new(t=12).
    v1Spec Section 10.5-10.6準拠
    """
    state = ensure_sponsor_state(db, club_id, season_id)
    
    # Idempotency: If already determined, do not change
    if state.next_count is not None:
        return state
    
    # Get Metrics
    perf, followers, fan_growth = get_performance_metrics(db, club_id, season_id)
    
    # Use cumulative effort from EWMA (PR7)
    c_ret = float(state.cumulative_effort_ret)
    c_new = float(state.cumulative_effort_new)
    
    # Deterministic Seed
    seed = f"{season_id}-{club_id}-sponsor"
    rng = random.Random(seed)
    
    # -----------------------------------------------------
    # 1. Existing Sponsors (Churn) - Section 10.5
    # Churn = clip(c0 - c1*ln(1+C^ret(7月)) - c2*(Perf-0.5) - c3*FanGrowth, c_min, c_max)
    # -----------------------------------------------------
    term_c = float(CHURN_C1) * math.log(1 + c_ret)
    term_p = float(CHURN_C2) * (perf - 0.5)
    term_f = float(CHURN_C3) * fan_growth
    
    churn_raw = float(CHURN_C0) - term_c - term_p - term_f
    churn = max(float(CHURN_MIN), min(float(CHURN_MAX), churn_raw))
    
    # N_exist_next = round(N_this * (1 - Churn))
    n_exist_next = round(state.count * (1.0 - churn))
    
    # -----------------------------------------------------
    # 2. New Sponsors - Section 10.6
    # -----------------------------------------------------
    # Leads L = round(L0 + l1*ln(1+C^new) + l2*ln(1+N) + l3*(Perf-0.5) + l4*ln(1+Followers))
    term_l_c = float(LEADS_L1) * math.log(1 + c_new)
    term_l_n = float(LEADS_L2) * math.log(1 + state.count)
    term_l_p = float(LEADS_L3) * (perf - 0.5)
    term_l_f = float(LEADS_L4) * math.log(1 + followers)
    
    leads_raw = float(LEADS_L0) + term_l_c + term_l_n + term_l_p + term_l_f
    leads = max(0, round(leads_raw))
    
    # Conversion Rate p = sigmoid(a0 + a1*ln(1+C^new) + a2*(Perf-0.5) + a3*ln(1+Followers))
    term_p_c = float(CONV_A1) * math.log(1 + c_new)
    term_p_p = float(CONV_A2) * (perf - 0.5)
    term_p_f = float(CONV_A3) * math.log(1 + followers)
    
    logit = float(CONV_A0) + term_p_c + term_p_p + term_p_f
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
    
    # Store detailed breakdown (PR7)
    state.next_exist_count = n_exist_next
    state.next_new_count = n_new_next
    state.next_count = total_next
    
    # Finalize pipeline in July (confirm all remaining)
    state.pipeline_confirmed_exist = n_exist_next
    state.pipeline_confirmed_new = n_new_next
    
    db.add(state)
    return state


def process_pipeline_progress(db: Session, club_id: UUID, season_id: UUID, month_index: int):
    """
    Process sponsor pipeline progress for months 9-11 (Apr-Jun).
    v1Spec Section 10.7 - 内定進捗（4〜7月、上限保証・速度自然）
    
    月 m ∈ {4,5,6}: Δ(m) ~ Binomial(R(m), q_m), R(m) = N_next - C(m-1)
    7月: Δ(7) = R(7) → C(7) = N_next （強制確定）
    """
    state = ensure_sponsor_state(db, club_id, season_id)
    
    # Only process in Apr(9), May(10), Jun(11)
    if month_index not in [9, 10, 11]:
        return state
    
    # Need to have calculated N_exist_next and N_new_next first
    # This is typically done at start of Apr or by a prior calculation
    if state.next_exist_count is None or state.next_new_count is None:
        # Calculate tentative values based on current state
        _calculate_tentative_next_counts(db, state, season_id, club_id)
    
    # Deterministic seed per month
    seed = f"{season_id}-{club_id}-pipeline-{month_index}"
    rng = random.Random(seed)
    
    # Get probabilities for this month
    q_exist = PIPELINE_PROB_EXISTING.get(month_index, 0.3)
    q_new = PIPELINE_PROB_NEW.get(month_index, 0.2)
    
    # Remaining to confirm
    r_exist = state.next_exist_count - state.pipeline_confirmed_exist
    r_new = state.next_new_count - state.pipeline_confirmed_new
    
    # Binomial draw for confirmed this month
    delta_exist = sum(1 for _ in range(r_exist) if rng.random() < q_exist)
    delta_new = sum(1 for _ in range(r_new) if rng.random() < q_new)
    
    state.pipeline_confirmed_exist += delta_exist
    state.pipeline_confirmed_new += delta_new
    
    db.add(state)
    db.flush()
    
    return {
        "month_index": month_index,
        "delta_exist": delta_exist,
        "delta_new": delta_new,
        "confirmed_exist": state.pipeline_confirmed_exist,
        "confirmed_new": state.pipeline_confirmed_new,
        "total_confirmed": state.pipeline_confirmed_exist + state.pipeline_confirmed_new,
    }


def _calculate_tentative_next_counts(db: Session, state: models.ClubSponsorState, season_id: UUID, club_id: UUID):
    """
    Calculate tentative N_exist_next and N_new_next based on current cumulative effort.
    Called at start of Apr (month 9) if not already calculated.
    """
    perf, followers, fan_growth = get_performance_metrics(db, club_id, season_id)
    
    c_ret = float(state.cumulative_effort_ret)
    c_new = float(state.cumulative_effort_new)
    
    seed = f"{season_id}-{club_id}-tentative"
    rng = random.Random(seed)
    
    # Churn calculation
    term_c = float(CHURN_C1) * math.log(1 + c_ret)
    term_p = float(CHURN_C2) * (perf - 0.5)
    term_f = float(CHURN_C3) * fan_growth
    churn_raw = float(CHURN_C0) - term_c - term_p - term_f
    churn = max(float(CHURN_MIN), min(float(CHURN_MAX), churn_raw))
    n_exist_next = round(state.count * (1.0 - churn))
    
    # Leads calculation
    term_l_c = float(LEADS_L1) * math.log(1 + c_new)
    term_l_n = float(LEADS_L2) * math.log(1 + state.count)
    term_l_p = float(LEADS_L3) * (perf - 0.5)
    term_l_f = float(LEADS_L4) * math.log(1 + followers)
    leads_raw = float(LEADS_L0) + term_l_c + term_l_n + term_l_p + term_l_f
    leads = max(0, round(leads_raw))
    
    # Conversion calculation
    term_p_c = float(CONV_A1) * math.log(1 + c_new)
    term_p_p = float(CONV_A2) * (perf - 0.5)
    term_p_f = float(CONV_A3) * math.log(1 + followers)
    logit = float(CONV_A0) + term_p_c + term_p_p + term_p_f
    try:
        prob = 1.0 / (1.0 + math.exp(-logit))
    except OverflowError:
        prob = 0.0 if logit < 0 else 1.0
    
    n_new_next = sum(1 for _ in range(leads) if rng.random() < prob)
    
    state.next_exist_count = n_exist_next
    state.next_new_count = n_new_next
    state.pipeline_confirmed_exist = 0
    state.pipeline_confirmed_new = 0
    db.add(state)
    db.flush()


def get_pipeline_status(db: Session, club_id: UUID, season_id: UUID) -> dict:
    """
    Get current pipeline status for UI display.
    """
    state = ensure_sponsor_state(db, club_id, season_id)
    
    return {
        "current_sponsors": state.count,
        "next_exist_target": state.next_exist_count,
        "next_new_target": state.next_new_count,
        "confirmed_exist": state.pipeline_confirmed_exist,
        "confirmed_new": state.pipeline_confirmed_new,
        "total_confirmed": state.pipeline_confirmed_exist + state.pipeline_confirmed_new,
        "next_total": state.next_count,
        "cumulative_effort_ret": float(state.cumulative_effort_ret),
        "cumulative_effort_new": float(state.cumulative_effort_new),
    }


def get_next_sponsor_info(db: Session, club_id: UUID, season_id: UUID) -> dict:
    """
    Get next season sponsor information for July UI display.
    """
    state = ensure_sponsor_state(db, club_id, season_id)
    
    next_total = state.next_count or 0
    unit_price = float(state.unit_price)
    expected_revenue = next_total * unit_price
    
    return {
        "next_sponsors_total": next_total,
        "next_sponsors_exist": state.next_exist_count or 0,
        "next_sponsors_new": state.next_new_count or 0,
        "unit_price": unit_price,
        "expected_revenue": expected_revenue,
        "is_finalized": state.next_count is not None,
    }

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
