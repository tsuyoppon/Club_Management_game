import math
from decimal import Decimal

from app.config import constants
from app.services.weather import get_weather_effect


def sigmoid(x):
    return 1 / (1 + math.exp(-x))


def calculate_attendance(
    home_fb: int,
    away_fb: int,
    weather: str,
    perf_val: float, # 0.0-1.0 (fixed-step current-rank score)
    hist_perf_val: float, # 0.0-1.0
    next_promo_spend: Decimal, # Promo spend for THIS match (input in previous month)
    is_event: bool = False
) -> tuple[int, int, int]:
    # 1. Home Attendance Rate
    g_w = get_weather_effect(weather)
    
    # z = beta_0 + beta_W*g_W + beta_1*Perf + beta_2*HistPerf + beta_3*ln(1+Promo/S_promo) + beta_4*ln(FB_opp/FB_ref) + beta_5*g_event
    
    promo_val = float(next_promo_spend)
    term_promo = float(constants.HOME_ATTENDANCE_BETA_3) * math.log(
        1 + promo_val / float(constants.S_PROMO)
    )
    
    fb_opp_ratio = away_fb / constants.FB_REF
    if fb_opp_ratio < 0.001: fb_opp_ratio = 0.001
    term_opp = float(constants.HOME_ATTENDANCE_BETA_4) * math.log(fb_opp_ratio)
    
    g_event = float(constants.G_EVENT) if is_event else 0.0
    term_event = float(constants.HOME_ATTENDANCE_BETA_5) * g_event
    
    z = (
        float(constants.HOME_ATTENDANCE_BETA_0)
        + float(constants.HOME_ATTENDANCE_BETA_W) * g_w
        + float(constants.HOME_ATTENDANCE_BETA_1) * perf_val
        + float(constants.HOME_ATTENDANCE_BETA_2) * hist_perf_val
        + term_promo
        + term_opp
        + term_event
    )
    
    r_home = sigmoid(z)
    
    home_attendance_raw = int(home_fb * r_home)
    if home_attendance_raw > constants.STADIUM_CAPACITY:
        home_attendance_raw = constants.STADIUM_CAPACITY
        
    # 2. Away Attendance
    # A_away = min(FB_opp * r_away_0 * exp(kappa_W * g_W), q_max * Cap)
    weather_adj = math.exp(float(constants.AWAY_WEATHER_KAPPA) * g_w)
    away_attendance_raw = int(
        away_fb * float(constants.AWAY_BASE_RATE) * weather_adj
    )
    
    away_cap = int(
        float(constants.AWAY_MAX_RATIO) * constants.STADIUM_CAPACITY
    )
    if away_attendance_raw > away_cap:
        away_attendance_raw = away_cap
        
    # 3. Cap Constraint
    total_raw = home_attendance_raw + away_attendance_raw
    
    if total_raw <= constants.STADIUM_CAPACITY:
        return home_attendance_raw, away_attendance_raw, total_raw
    else:
        # Scale down
        ratio = constants.STADIUM_CAPACITY / total_raw
        home_final = int(home_attendance_raw * ratio)
        away_final = int(away_attendance_raw * ratio)
        
        # Adjust rounding error
        if home_final + away_final < constants.STADIUM_CAPACITY:
            home_final += (
                constants.STADIUM_CAPACITY - (home_final + away_final)
            )
            
        return home_final, away_final, constants.STADIUM_CAPACITY
