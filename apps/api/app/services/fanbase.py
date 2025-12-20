import math
import random
from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Session
from app.db.models import ClubFanbaseState

# Coefficients
LAMBDA_EWMA = Decimal("0.10")
PHI_PENALTY = Decimal("0.00002")

G0 = Decimal("-0.0005")
A1 = Decimal("0.006")
A2 = Decimal("0.006")
A3 = Decimal("0.010")
A4 = Decimal("0.006")

S_PROMO = Decimal("10000000")
S_HT = Decimal("10000000")

F_MAX = Decimal("0.25")
POPULATION = 1000000

KAPPA_F = Decimal("1.0")
SIGMA_F = 0.15

def ensure_fanbase_state(db: Session, club_id: str, season_id: str) -> ClubFanbaseState:
    state = db.query(ClubFanbaseState).filter_by(club_id=club_id, season_id=season_id).first()
    if not state:
        state = ClubFanbaseState(
            club_id=club_id,
            season_id=season_id,
            fb_count=60000,
            fb_rate=Decimal("0.06"),
            cumulative_promo=Decimal("0"),
            cumulative_ht=Decimal("0"),
            last_ht_spend=Decimal("0"),
            followers_public=None
        )
        db.add(state)
        db.commit()
        db.refresh(state)
    return state

def update_fanbase_for_turn(
    db: Session, 
    state: ClubFanbaseState, 
    promo_spend: Decimal, 
    ht_spend: Decimal,
    perf_val: float, # 0.0 to 1.0 (normalized rank, 1.0 is best)
    hist_perf_val: float # 0.0 to 1.0
) -> ClubFanbaseState:
    # 1. Update Cumulative Promo
    # C_promo(t) = (1-lambda)C(t-1) + lambda * Spend
    state.cumulative_promo = (1 - LAMBDA_EWMA) * state.cumulative_promo + LAMBDA_EWMA * promo_spend
    
    # 2. Update Cumulative HT
    # C_ht(t) = (1-lambda)C(t-1) + lambda * Spend - phi * |Delta Spend|
    delta_ht = ht_spend - state.last_ht_spend
    penalty = PHI_PENALTY * abs(delta_ht)
    
    state.cumulative_ht = (1 - LAMBDA_EWMA) * state.cumulative_ht + LAMBDA_EWMA * ht_spend - penalty
    if state.cumulative_ht < 0:
        state.cumulative_ht = Decimal("0")
        
    state.last_ht_spend = ht_spend
    
    # 3. Calculate Growth Rate g(t)
    # g(t) = g0 + a1*ln(1 + C_promo/S_promo) + a2*ln(1 + C_ht/S_ht) + a3*(Perf-0.5) + a4*(HistPerf-0.5)
    
    # Avoid log(0) or negative
    c_promo_float = float(state.cumulative_promo)
    c_ht_float = float(state.cumulative_ht)
    s_promo_float = float(S_PROMO)
    s_ht_float = float(S_HT)
    
    term_promo = A1 * Decimal(math.log(1 + c_promo_float / s_promo_float))
    term_ht = A2 * Decimal(math.log(1 + c_ht_float / s_ht_float))
    term_perf = A3 * Decimal(perf_val - 0.5)
    term_hist = A4 * Decimal(hist_perf_val - 0.5)
    
    g_t = G0 + term_promo + term_ht + term_perf + term_hist
    
    # 4. Effective Growth Rate (Cap constraint)
    # g_eff = g(t) * (1 - f(t)/f_max)
    f_t = state.fb_rate
    g_eff = g_t * (1 - f_t / F_MAX)
    
    # 5. Update FB Rate
    # f(t+1) = clip(f(t)*(1+g_eff), 0, f_max)
    f_next = f_t * (1 + g_eff)
    if f_next < 0:
        f_next = Decimal("0")
    if f_next > F_MAX:
        f_next = F_MAX
        
    state.fb_rate = f_next
    
    # Update FB Count
    state.fb_count = int(f_next * POPULATION)
    
    # 6. Update Public Followers
    # ln(Followers) = ln(kappa * FB) + epsilon
    # epsilon ~ N(0, sigma^2)
    
    fb_val = state.fb_count
    if fb_val < 1:
        fb_val = 1
        
    mu = math.log(float(KAPPA_F * fb_val))
    epsilon = random.gauss(0, SIGMA_F)
    log_followers = mu + epsilon
    followers = int(math.exp(log_followers))
    
    state.followers_public = followers
    
    db.add(state)
    db.commit()
    db.refresh(state)
    return state
