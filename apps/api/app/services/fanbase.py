import math
import random
from decimal import Decimal
from sqlalchemy.orm import Session
from app.config.constants import (
    FANBASE_RULESET_LEGACY,
    FANBASE_RULESET_PROMO_ROI,
    FB_A1_LEGACY,
    FB_A1_PROMO_ROI,
    FB_PROMOTION_STAFF_SPEND_EFFICIENCY,
    FB_S_PROMO_GROWTH_LEGACY,
    FB_S_PROMO_GROWTH_PROMO_ROI,
    INITIAL_FANBASE_COUNT,
    INITIAL_FB_RATE,
)
from app.db.models import ClubFanbaseState, ClubStaff, StaffRole

# Coefficients
LAMBDA_EWMA = Decimal("0.10")
PROMOTION_STAFF_EWMA_LAMBDA = Decimal("0.10")
HOMETOWN_STAFF_EWMA_LAMBDA = Decimal("0.04")
PHI_PENALTY = Decimal("0.00002")

G0 = Decimal("-0.0005")
A2 = Decimal("0.006")
A3 = Decimal("0.010")
A4 = Decimal("0.006")
A_PROMOTION_STAFF = Decimal("0.0015")
A_HOMETOWN_STAFF = Decimal("0.0012")

S_HT = Decimal("10000000")
S_PROMOTION_STAFF = Decimal("2")
S_HOMETOWN_STAFF = Decimal("2")

F_MAX = Decimal("0.25")
POPULATION = 1000000

KAPPA_F = Decimal("0.3")
SIGMA_F = 0.08
FOLLOWER_ERROR_MEAN = 0.10
FOLLOWER_TREND_MEAN_STEP = 0.03
FOLLOWER_TREND_MEAN_CAP = 0.12


def ensure_fanbase_state(db: Session, club_id: str, season_id: str) -> ClubFanbaseState:
    state = db.query(ClubFanbaseState).filter_by(club_id=club_id, season_id=season_id).first()
    if not state:
        state = ClubFanbaseState(
            club_id=club_id,
            season_id=season_id,
            fb_count=INITIAL_FANBASE_COUNT,
            fb_rate=INITIAL_FB_RATE,
            cumulative_promo=Decimal("0"),
            cumulative_ht=Decimal("0"),
            cumulative_promotion_staff=Decimal("1"),
            cumulative_hometown_staff=Decimal("1"),
            last_ht_spend=Decimal("0"),
            fb_trend_streak=0,
            followers_public=None
        )
        db.add(state)
        db.commit()
        db.refresh(state)
    return state


def _staff_count(db: Session, club_id, role: StaffRole) -> Decimal:
    staff = db.query(ClubStaff).filter(
        ClubStaff.club_id == club_id,
        ClubStaff.role == role,
    ).first()
    if not staff:
        return Decimal("1")
    return Decimal(staff.count or 1)


def _promo_growth_parameters(fanbase_ruleset_version: int) -> tuple[Decimal, Decimal]:
    """Return (growth coefficient, spend scale) for a fixed game ruleset."""
    if fanbase_ruleset_version == FANBASE_RULESET_LEGACY:
        return FB_A1_LEGACY, FB_S_PROMO_GROWTH_LEGACY
    if fanbase_ruleset_version == FANBASE_RULESET_PROMO_ROI:
        return FB_A1_PROMO_ROI, FB_S_PROMO_GROWTH_PROMO_ROI
    raise ValueError(f"Unsupported fanbase ruleset version: {fanbase_ruleset_version}")


def promotion_staff_spend_multiplier(
    cumulative_promotion_staff: Decimal,
    fanbase_ruleset_version: int,
) -> Decimal:
    """Return the spend multiplier after the current turn's staff EWMA update."""
    _promo_growth_parameters(fanbase_ruleset_version)
    if fanbase_ruleset_version == FANBASE_RULESET_LEGACY:
        return Decimal("1")

    staff_excess = max(Decimal("0"), Decimal(cumulative_promotion_staff) - Decimal("1"))
    if staff_excess == 0:
        return Decimal("1")
    log_term = Decimal(str(math.log1p(float(staff_excess / S_PROMOTION_STAFF))))
    return Decimal("1") + FB_PROMOTION_STAFF_SPEND_EFFICIENCY * log_term


def promotion_growth_term(
    cumulative_promo: Decimal,
    fanbase_ruleset_version: int,
) -> Decimal:
    """Return the monthly growth contribution from the promo asset."""
    promo_coefficient, promo_scale = _promo_growth_parameters(fanbase_ruleset_version)
    ratio = float(Decimal(cumulative_promo) / promo_scale)
    if fanbase_ruleset_version == FANBASE_RULESET_LEGACY:
        # Preserve the original float-to-Decimal conversion exactly for games
        # that began before ruleset versioning was introduced.
        return promo_coefficient * Decimal(math.log(1 + ratio))
    return promo_coefficient * Decimal(str(math.log1p(ratio)))


def update_fanbase_for_turn(
    db: Session,
    state: ClubFanbaseState,
    promo_spend: Decimal,
    ht_spend: Decimal,
    perf_val: float, # 0.0 to 1.0 (fixed-step current-rank score)
    hist_perf_val: float, # 0.0 to 1.0
    *,
    fanbase_ruleset_version: int,
) -> ClubFanbaseState:
    _promo_growth_parameters(fanbase_ruleset_version)

    # 1. Update cumulative staff effects before applying this month's spend.
    # C_staff(t) = (1-lambda)C_staff(t-1) + lambda * active_staff(t)
    promotion_staff = _staff_count(db, state.club_id, StaffRole.promotion)
    hometown_staff = _staff_count(db, state.club_id, StaffRole.hometown)
    state.cumulative_promotion_staff = (
        (Decimal("1") - PROMOTION_STAFF_EWMA_LAMBDA)
        * Decimal(state.cumulative_promotion_staff or 1)
        + PROMOTION_STAFF_EWMA_LAMBDA * promotion_staff
    )
    state.cumulative_hometown_staff = (
        (Decimal("1") - HOMETOWN_STAFF_EWMA_LAMBDA)
        * Decimal(state.cumulative_hometown_staff or 1)
        + HOMETOWN_STAFF_EWMA_LAMBDA * hometown_staff
    )

    # 2. Update Cumulative Promo.  Ruleset v2 stores an EWMA of effective
    # spend; v1 deliberately preserves the raw-spend EWMA.
    promo_multiplier = promotion_staff_spend_multiplier(
        Decimal(state.cumulative_promotion_staff),
        fanbase_ruleset_version,
    )
    effective_promo_spend = promo_spend * promo_multiplier
    state.cumulative_promo = (
        (Decimal("1") - LAMBDA_EWMA) * Decimal(state.cumulative_promo)
        + LAMBDA_EWMA * effective_promo_spend
    )

    # 3. Update Cumulative HT
    # C_ht(t) = (1-lambda)C(t-1) + lambda * Spend - phi * |Delta Spend|
    delta_ht = ht_spend - state.last_ht_spend
    penalty = PHI_PENALTY * abs(delta_ht)

    state.cumulative_ht = (1 - LAMBDA_EWMA) * state.cumulative_ht + LAMBDA_EWMA * ht_spend - penalty
    if state.cumulative_ht < 0:
        state.cumulative_ht = Decimal("0")

    state.last_ht_spend = ht_spend

    # 4. Calculate Growth Rate g(t)
    # Staff terms use effective excess over the baseline 1-person structure.

    # Avoid log(0) or negative
    c_ht_float = float(state.cumulative_ht)
    s_ht_float = float(S_HT)
    promotion_staff_excess = max(0.0, float(state.cumulative_promotion_staff) - 1.0)
    hometown_staff_excess = max(0.0, float(state.cumulative_hometown_staff) - 1.0)

    term_promo = promotion_growth_term(
        Decimal(state.cumulative_promo),
        fanbase_ruleset_version,
    )
    term_ht = A2 * Decimal(math.log(1 + c_ht_float / s_ht_float))
    term_perf = A3 * Decimal(perf_val - 0.5)
    term_hist = A4 * Decimal(hist_perf_val - 0.5)
    term_promotion_staff = A_PROMOTION_STAFF * Decimal(
        math.log(1 + promotion_staff_excess / float(S_PROMOTION_STAFF))
    )
    term_hometown_staff = A_HOMETOWN_STAFF * Decimal(
        math.log(1 + hometown_staff_excess / float(S_HOMETOWN_STAFF))
    )

    g_t = (
        G0
        + term_promo
        + term_ht
        + term_promotion_staff
        + term_hometown_staff
        + term_perf
        + term_hist
    )
    
    # 5. Effective Growth Rate (Cap constraint)
    # g_eff = g(t) * (1 - f(t)/f_max)
    f_t = state.fb_rate
    prev_fb_count = state.fb_count
    g_eff = g_t * (1 - f_t / F_MAX)
    
    # 6. Update FB Rate
    # f(t+1) = clip(f(t)*(1+g_eff), 0, f_max)
    f_next = f_t * (1 + g_eff)
    if f_next < 0:
        f_next = Decimal("0")
    if f_next > F_MAX:
        f_next = F_MAX
        
    state.fb_rate = f_next
    
    # Update FB Count
    state.fb_count = int(f_next * POPULATION)
    if state.fb_count > prev_fb_count:
        state.fb_trend_streak = max((state.fb_trend_streak or 0) + 1, 1)
    elif state.fb_count < prev_fb_count:
        state.fb_trend_streak = min((state.fb_trend_streak or 0) - 1, -1)
    else:
        state.fb_trend_streak = 0
    
    # 7. Update Public Followers
    # ln(Followers) = ln(kappa * FB) + epsilon
    # epsilon ~ N(mu_epsilon, sigma^2)
    # mu_epsilon = base_mean + trend adjustment.
    
    fb_val = state.fb_count
    if fb_val < 1:
        fb_val = 1
        
    mu = math.log(float(KAPPA_F * fb_val))
    trend_adjustment = max(
        -FOLLOWER_TREND_MEAN_CAP,
        min(FOLLOWER_TREND_MEAN_CAP, (state.fb_trend_streak or 0) * FOLLOWER_TREND_MEAN_STEP),
    )
    epsilon_mean = FOLLOWER_ERROR_MEAN + trend_adjustment
    epsilon = random.gauss(epsilon_mean, SIGMA_F)
    log_followers = mu + epsilon
    followers = int(math.exp(log_followers))
    
    state.followers_public = followers
    
    db.add(state)
    db.commit()
    db.refresh(state)
    return state
