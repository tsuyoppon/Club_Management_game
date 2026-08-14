"""
v1Spec 係数一覧（実装用まとめ）
このファイルに係数を集約し、プレイテストでの調整を容易にする。
"""

from decimal import Decimal

# =============================================================================
# Initial scenario defaults
# =============================================================================

INITIAL_CASH_BALANCE = Decimal("100000000")  # 1億円
INITIAL_SPONSOR_COUNT = 10
INITIAL_FANBASE_COUNT = 10000
INITIAL_REINFORCEMENT_BUDGET = Decimal("30000000")  # 3000万円
INITIAL_ACADEMY_ANNUAL_BUDGET = Decimal("0")
INITIAL_ACADEMY_CUMULATIVE_INVESTMENT = Decimal("50000000")  # 5000万円

# =============================================================================
# Section 7: 会計（収入・費用）
# =============================================================================

# 配分金（8月一括入金）
DISTRIBUTION_AMOUNT = Decimal("20000000")  # 2000万円

# 物販
MERCHANDISE_SPEND_PER_PERSON = Decimal("800")  # 1人あたり物販購入額
MERCHANDISE_MARGIN = Decimal("0.40")  # 粗利率40%（原価60%）

# 試合運営費（固定）
MATCH_OPERATION_FIXED_COST = Decimal("1000000")  # 100万円/試合

# 賞金（順位別、6月入金）
PRIZE_AMOUNTS = {
    1: Decimal("20000000"),  # 1位: 2000万円
    2: Decimal("10000000"),  # 2位: 1000万円
    3: Decimal("5000000"),  # 3位: 500万円
}

# 退職金係数（年収×0.75）
SEVERANCE_COEFFICIENT = Decimal("0.75")

# =============================================================================
# Section 9: 入場者数モデル（チケット収入）- PR5で実装済み、参照用
# =============================================================================

# 固定（初期シナリオ共通）
POPULATION = 1000000
STADIUM_CAPACITY = 20000
INITIAL_FB_RATE = Decimal("0.01")  # f(0) = 0.01 -> FB(0) = 10,000
FB_MAX_RATE = Decimal("0.25")  # f_max
TICKET_PRICE = Decimal("2000")  # チケット単価

# 天候確率
WEATHER_PROBABILITIES = {
    "sunny": 0.55,
    "cloudy": 0.30,
    "rain": 0.15,
}

# 天候効果 g_W
WEATHER_EFFECTS = {
    "sunny": 0.0,
    "cloudy": -0.2,
    "rain": -0.6,
}

# アウェイ来場
AWAY_BASE_RATE = Decimal("0.018")  # r_away_0
AWAY_WEATHER_KAPPA = Decimal("0.20")  # κ_W
AWAY_MAX_RATIO = Decimal("0.20")  # q_max

# ホーム来場率ロジスティック回帰係数
HOME_ATTENDANCE_BETA_0 = Decimal("-1.986")
HOME_ATTENDANCE_BETA_W = Decimal("1.0")  # 天候
HOME_ATTENDANCE_BETA_1 = Decimal("0.8")  # 今期順位
HOME_ATTENDANCE_BETA_2 = Decimal("0.4")  # 過去平均成績
HOME_ATTENDANCE_BETA_4 = Decimal("0.3")  # 相手FB効果
HOME_ATTENDANCE_BETA_5 = Decimal("0.5")  # イベント効果

# 翌月ホーム向けプロモ
# 低〜中額帯では十分な効果を持たせつつ、高額帯では効果を滑らかに頭打ちにする。
# PromoTerm = MAX_EFFECT * (1 - exp(-Spend / SATURATION_SCALE))
NEXT_HOME_PROMO_MAX_LOGIT_EFFECT = Decimal("0.8")
NEXT_HOME_PROMO_SATURATION_SCALE = Decimal("2000000")

# 今期順位スコア
# リーグ中央を0.5とし、2〜5クラブのいずれでも1順位差を0.225に固定する。
# 入場モデルの係数0.8との積は0.18で、2クラブ制の旧1位/2位差0.8の22.5%。
CURRENT_RANK_SCORE_NEUTRAL = Decimal("0.5")
CURRENT_RANK_SCORE_STEP = Decimal("0.225")

FB_REF = 60000
G_EVENT = Decimal("0.4")  # 開幕/最終戦

# =============================================================================
# Section 9.6: FB成長 - PR5で実装済み、参照用
# =============================================================================

FB_EWMA_LAMBDA = Decimal("0.10")
FB_HT_PENALTY_PHI = Decimal("0.00002")
FB_S_PROMO_GROWTH = Decimal("10000000")  # 調整済み（PR5テスト通過値）
FB_S_HT_GROWTH = Decimal("10000000")  # 調整済み
FB_G0 = Decimal("-0.0005")  # 調整済み
FB_A1 = Decimal("0.006")
FB_A2 = Decimal("0.006")
FB_A3 = Decimal("0.010")
FB_A4 = Decimal("0.006")

# 公開ファン指標
FAN_INDICATOR_KAPPA = Decimal("0.3")
FAN_INDICATOR_SIGMA = 0.08
FAN_INDICATOR_ERROR_MEAN = Decimal("0.10")
FAN_INDICATOR_TREND_MEAN_STEP = Decimal("0.03")
FAN_INDICATOR_TREND_MEAN_CAP = Decimal("0.12")

# =============================================================================
# Section 10: スポンサー数モデル
# =============================================================================

SPONSOR_PRICE_PER_COMPANY = Decimal("5000000")  # 500万円/社

# 営業努力係数
SALES_EFFORT_WS_RET = Decimal("1.4")
# 月給40万円を基準に、同額のスタッフ投資が営業費の約3倍の努力を生むよう校正。
# w_m = w_s * 1,000,000 / (400,000 * 3)
SALES_EFFORT_WM_RET = Decimal("1.1666666667")
SALES_EFFORT_WS_NEW = Decimal("1.6")
SALES_EFFORT_WM_NEW = Decimal("1.3333333333")
SALES_EFFORT_REFERENCE_MONTHLY_SALARY = Decimal("400000")
SALES_EFFORT_STAFF_TO_SPEND_EFFICIENCY = Decimal("3")

# EWMA λ（累積営業努力）
SALES_EFFORT_LAMBDA_RET = Decimal("0.12")
SALES_EFFORT_LAMBDA_NEW = Decimal("0.05")

# Churn（既存スポンサー脱落率）
# 維持努力ゼロ・成績/ファン成長が中立なら脱落率40%。
# 通常水準の維持努力（C_ret≒2）では従来に近い15〜20%まで改善する。
CHURN_C0 = Decimal("0.40")
CHURN_C1 = Decimal("0.20")
CHURN_C2 = Decimal("0.06")
CHURN_C3 = Decimal("0.04")
CHURN_MIN = Decimal("0.05")
CHURN_MAX = Decimal("0.45")

# Leads（見込み顧客）
LEADS_L0 = Decimal("4.0")
LEADS_L1 = Decimal("4.0")
LEADS_L2 = Decimal("1.2")
LEADS_L3 = Decimal("2.0")
LEADS_L4 = Decimal("0.8")

# Conversion（成約率）
CONV_A0 = Decimal("-2.0")
CONV_A1 = Decimal("0.55")
CONV_A2 = Decimal("0.45")
CONV_A3 = Decimal("0.10")

# 内定進捗確率（仕様は4〜6月、実装の month_index では9〜11に対応）
PIPELINE_PROB_EXISTING = {9: 0.40, 10: 0.35, 11: 0.30}
PIPELINE_PROB_NEW = {9: 0.15, 10: 0.25, 11: 0.35}

# =============================================================================
# Section 8: 試合勝敗 - PR4.5で実装済み、参照用
# =============================================================================

HOME_ADV_BASE = Decimal("1.0")
HOME_ADV_RATE = Decimal("0.3")
HOME_ADV_MIN = Decimal("1.0")
HOME_ADV_MAX = Decimal("4.0")
MATCH_K = Decimal("0.15")
MATCH_D0 = Decimal("0.30")
MATCH_C = Decimal("0.08")

# TP（チーム力）
TP_ALPHA = 10
TP_BETA = 1
ACADEMY_DECAY_RHO = Decimal("0.5")
TEAM_POWER_REINFORCEMENT_LOOKBACK_SEASONS = 10
TEAM_POWER_REINFORCEMENT_DECAY = Decimal("0.6")
# 早期（6月）に来期強化費を確定した投資をTPへやや強く反映する係数。
TEAM_POWER_JUNE_REINFORCEMENT_INPUT_WEIGHT = Decimal("1.10")
TEAM_POWER_JULY_REINFORCEMENT_INPUT_WEIGHT = Decimal("1.00")
TEAM_POWER_TOPTEAM_BUDGET_PER_STAFF = Decimal("100000000")
TEAM_POWER_TOPTEAM_PENALTY_FACTOR = Decimal("0.30")

# =============================================================================
# Section 14: ペナルティ
# =============================================================================

DEBT_POINT_DEDUCTION = -10  # 勝点剥奪

# =============================================================================
# Section 4: 情報公開（PR9）
# =============================================================================

# チーム力計算の基準値
TEAM_POWER_B_REF = Decimal("100000000")  # 強化費基準値（1億円）
TEAM_POWER_A_REF = Decimal("50000000")  # アカデミー基準値（5000万円）
TEAM_POWER_DISCLOSURE_SIGMA = 1.5  # 7月公開時の不確実性（標準偏差）

# 公開イベントの月インデックス
DISCLOSURE_MONTH_DECEMBER = 5  # 12月 = month_index 5
DISCLOSURE_MONTH_MAY = 10  # 5月 = month_index 10
DISCLOSURE_MONTH_JUNE = 11  # 6月 = month_index 11
DISCLOSURE_MONTH_JULY = 12  # 7月 = month_index 12

# =============================================================================
# Section 11: 人件費
# =============================================================================

STAFF_SALARY_ANNUAL = Decimal("4800000")  # 480万円/年

# =============================================================================
# ターン・月マッピング（参照用）
# =============================================================================

# month_index: 1=8月, 2=9月, ..., 10=5月, 11=6月, 12=7月
MONTH_INDEX_TO_CALENDAR = {
    1: 8,
    2: 9,
    3: 10,
    4: 11,
    5: 12,
    6: 1,
    7: 2,
    8: 3,
    9: 4,
    10: 5,
    11: 6,
    12: 7,
}

# 四半期開始月（営業リソース配分変更可能）
QUARTER_START_MONTHS = [1, 4, 7, 10]  # 8月, 11月, 2月, 5月

# シーズン月（試合がある月）
SEASON_MONTHS = list(range(1, 11))  # month_index 1-10 (8月〜5月)
