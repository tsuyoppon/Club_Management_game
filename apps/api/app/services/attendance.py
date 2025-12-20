import math
from decimal import Decimal
from app.services.weather import get_weather_effect

# Coefficients
BETA_0 = -1.986
BETA_W = 1.0
BETA_1 = 0.8
BETA_2 = 0.4
BETA_3 = 0.6
BETA_4 = 0.3
BETA_5 = 0.5

FB_REF = 60000
S_PROMO = 10000000

R_AWAY_0 = 0.018
KAPPA_W = 0.20
Q_MAX = 0.20

CAPACITY = 20000

def sigmoid(x):
    return 1 / (1 + math.exp(-x))

def calculate_attendance(
    home_fb: int,
    away_fb: int,
    weather: str,
    perf_val: float, # 0.0-1.0 (normalized rank)
    hist_perf_val: float, # 0.0-1.0
    next_promo_spend: Decimal, # Promo spend for THIS match (input in previous month)
    is_event: bool = False
) -> tuple[int, int, int]:
    # 1. Home Attendance Rate
    g_w = get_weather_effect(weather)
    
    # z = beta_0 + beta_W*g_W + beta_1*Perf + beta_2*HistPerf + beta_3*ln(1+Promo/S_promo) + beta_4*ln(FB_opp/FB_ref) + beta_5*g_event
    
    promo_val = float(next_promo_spend)
    term_promo = BETA_3 * math.log(1 + promo_val / S_PROMO)
    
    fb_opp_ratio = away_fb / FB_REF
    if fb_opp_ratio < 0.001: fb_opp_ratio = 0.001
    term_opp = BETA_4 * math.log(fb_opp_ratio)
    
    g_event = 0.4 if is_event else 0.0
    term_event = BETA_5 * g_event
    
    z = BETA_0 + BETA_W * g_w + BETA_1 * perf_val + BETA_2 * hist_perf_val + term_promo + term_opp + term_event
    
    r_home = sigmoid(z)
    
    home_attendance_raw = int(home_fb * r_home)
    if home_attendance_raw > CAPACITY:
        home_attendance_raw = CAPACITY
        
    # 2. Away Attendance
    # A_away = min(FB_opp * r_away_0 * exp(kappa_W * g_W), q_max * Cap)
    weather_adj = math.exp(KAPPA_W * g_w)
    away_attendance_raw = int(away_fb * R_AWAY_0 * weather_adj)
    
    away_cap = int(Q_MAX * CAPACITY)
    if away_attendance_raw > away_cap:
        away_attendance_raw = away_cap
        
    # 3. Cap Constraint
    total_raw = home_attendance_raw + away_attendance_raw
    
    if total_raw <= CAPACITY:
        return home_attendance_raw, away_attendance_raw, total_raw
    else:
        # Scale down
        ratio = CAPACITY / total_raw
        home_final = int(home_attendance_raw * ratio)
        away_final = int(away_attendance_raw * ratio)
        
        # Adjust rounding error
        if home_final + away_final < CAPACITY:
            home_final += (CAPACITY - (home_final + away_final))
            
        return home_final, away_final, CAPACITY
