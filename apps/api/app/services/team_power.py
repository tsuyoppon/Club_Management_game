"""
PR9: チーム力計算サービス
v1Spec Section 8.4

チーム力（TP）の計算と公開処理を行う。
"""

import math
import random
from decimal import Decimal
from typing import Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import (
    Club,
    Season,
    ClubFinancialProfile,
    ClubReinforcementPlan,
    ClubAcademy,
    ClubStaff,
    StaffRole,
    Turn,
    TurnDecision,
)
from app.config.constants import (
    TP_ALPHA,
    TP_BETA,
    TEAM_POWER_B_REF,
    TEAM_POWER_A_REF,
    TEAM_POWER_DISCLOSURE_SIGMA,
    TEAM_POWER_REINFORCEMENT_DECAY,
    TEAM_POWER_REINFORCEMENT_LOOKBACK_SEASONS,
    TEAM_POWER_JUNE_REINFORCEMENT_INPUT_WEIGHT,
    TEAM_POWER_JULY_REINFORCEMENT_INPUT_WEIGHT,
    TEAM_POWER_TOPTEAM_BUDGET_PER_STAFF,
    TEAM_POWER_TOPTEAM_PENALTY_FACTOR,
)


def _reinforcement_budget_for_plan(plan: Optional[ClubReinforcementPlan]) -> Decimal:
    if not plan:
        return Decimal("0")
    return Decimal(plan.annual_budget or 0) + Decimal(plan.additional_budget or 0)


def _target_reinforcement_budget_for_plan(
    plan: Optional[ClubReinforcementPlan],
    month_index: Optional[int],
) -> Decimal:
    if not plan:
        return Decimal("0")

    budget = Decimal(plan.annual_budget or 0)
    if month_index is None or month_index >= 6:
        budget += Decimal(plan.additional_budget or 0)
    return budget


def calculate_current_reinforcement_budget_for_topteam_penalty(
    db: Session,
    club_id: UUID,
    season_id: UUID,
    month_index: Optional[int] = None,
) -> Decimal:
    """
    topteam人数ペナルティ判定用の対象シーズン強化費を円単位で返す。
    TP本体の加重平均とは分け、当該シーズンの予算だけを見る。
    """
    plan = (
        db.query(ClubReinforcementPlan)
        .filter(
            ClubReinforcementPlan.club_id == club_id,
            ClubReinforcementPlan.season_id == season_id,
        )
        .first()
    )
    return _target_reinforcement_budget_for_plan(plan, month_index)


def _topteam_staff_count(
    db: Session,
    club_id: UUID,
    use_next_staff: bool = False,
) -> int:
    staff = (
        db.query(ClubStaff)
        .filter(
            ClubStaff.club_id == club_id,
            ClubStaff.role == StaffRole.topteam,
        )
        .first()
    )
    if not staff:
        return 1
    if use_next_staff:
        if staff.next_count is not None:
            return staff.next_count
        if staff.hiring_target is not None:
            return staff.hiring_target
    return staff.count


def calculate_topteam_staff_tp_multiplier(
    db: Session,
    club_id: UUID,
    reinforcement_budget: Decimal,
    use_next_staff: bool = False,
) -> Decimal:
    """
    topteam人数不足によるTP倍率を返す。

    強化費1億円あたりtopteam 1人以上なら倍率1.0。
    不足分に比例してペナルティを掛ける。
    3億円:1人で penalty_rate=20% になるよう係数0.30を使う。
    """
    budget = Decimal(reinforcement_budget or 0)
    if budget <= 0:
        return Decimal("1")

    required_staff = budget / TEAM_POWER_TOPTEAM_BUDGET_PER_STAFF
    if required_staff <= 0:
        return Decimal("1")

    staff_count = Decimal(
        _topteam_staff_count(db, club_id, use_next_staff=use_next_staff)
    )
    coverage = staff_count / required_staff
    if coverage >= 1:
        return Decimal("1")

    shortage = Decimal("1") - coverage
    penalty_rate = TEAM_POWER_TOPTEAM_PENALTY_FACTOR * shortage
    return Decimal("1") - penalty_rate


def apply_topteam_staff_tp_penalty(
    db: Session,
    club_id: UUID,
    tp: float,
    reinforcement_budget: Decimal,
    use_next_staff: bool = False,
) -> float:
    multiplier = calculate_topteam_staff_tp_multiplier(
        db,
        club_id,
        reinforcement_budget,
        use_next_staff=use_next_staff,
    )
    return tp * float(multiplier)


def _next_season_reinforcement_input_weight(month_index: int) -> Decimal:
    if month_index == 11:
        return TEAM_POWER_JUNE_REINFORCEMENT_INPUT_WEIGHT
    if month_index == 12:
        return TEAM_POWER_JULY_REINFORCEMENT_INPUT_WEIGHT
    return Decimal("1")


def _weighted_next_season_reinforcement_input_budget(
    db: Session,
    club_id: UUID,
    season_id: UUID,
) -> Decimal:
    """
    TP計算用の来期強化費入力を返す。

    実際の支出・予算額は6月/7月入力の単純合算を維持しつつ、
    早期に財務リスクを取る6月入力分だけをTP上は控えめに加重する。
    """
    rows = (
        db.query(TurnDecision.payload_json, Turn.month_index)
        .join(Turn, TurnDecision.turn_id == Turn.id)
        .filter(
            TurnDecision.club_id == club_id,
            Turn.season_id == season_id,
            Turn.month_index.in_([11, 12]),
        )
        .all()
    )

    total = Decimal("0")
    for payload, month_index in rows:
        if not payload:
            continue
        value = payload.get("reinforcement_budget")
        if value is None:
            continue
        total += Decimal(str(value or 0)) * _next_season_reinforcement_input_weight(
            month_index
        )
    return total


def calculate_weighted_reinforcement_budget(
    db: Session,
    club_id: UUID,
    season_id: UUID,
    month_index: Optional[int] = None,
    current_budget_override: Optional[Decimal] = None,
) -> Decimal:
    """
    TP計算用の強化費を円単位で返す。

    対象シーズンを最新シーズンとして含め、直近最大10シーズンの
    年間強化費を指数減衰加重平均する。

    対象シーズンの追加強化費は1月以降（month_index >= 6）だけ含める。
    current_budget_override が指定された場合は、翌シーズン向け入力などを
    対象シーズン相当の最新予算として扱い、現シーズン以前を過去実績として含める。
    """
    current_season = db.query(Season).filter(Season.id == season_id).first()
    if not current_season:
        return Decimal("0")

    weighted_budget = Decimal("0")
    weight_total = Decimal("0")
    decay = TEAM_POWER_REINFORCEMENT_DECAY
    max_count = TEAM_POWER_REINFORCEMENT_LOOKBACK_SEASONS

    if current_budget_override is not None:
        weighted_budget += Decimal(current_budget_override)
        weight_total += Decimal("1")
        remaining_count = max(max_count - 1, 0)
        historical_seasons = (
            db.query(Season)
            .filter(
                Season.game_id == current_season.game_id,
                Season.season_number <= current_season.season_number,
            )
            .order_by(Season.season_number.desc())
            .limit(remaining_count)
            .all()
        )
        start_index = 1
    else:
        historical_seasons = (
            db.query(Season)
            .filter(
                Season.game_id == current_season.game_id,
                Season.season_number <= current_season.season_number,
            )
            .order_by(Season.season_number.desc())
            .limit(max_count)
            .all()
        )
        start_index = 0

    for offset, season in enumerate(historical_seasons):
        index = start_index + offset
        weight = decay**index
        plan = (
            db.query(ClubReinforcementPlan)
            .filter(
                ClubReinforcementPlan.club_id == club_id,
                ClubReinforcementPlan.season_id == season.id,
            )
            .first()
        )
        if current_budget_override is None and season.id == current_season.id:
            budget = _target_reinforcement_budget_for_plan(plan, month_index)
        else:
            budget = _reinforcement_budget_for_plan(plan)
        weighted_budget += weight * budget
        weight_total += weight

    if weight_total == 0:
        return Decimal("0")
    return weighted_budget / weight_total


def calculate_past_weighted_reinforcement_budget(
    db: Session,
    club_id: UUID,
    season_id: UUID,
) -> Decimal:
    """
    旧仕様互換: 対象シーズンを含めず、過去シーズンだけを加重平均する。
    新規TP計算では calculate_weighted_reinforcement_budget を使う。
    """
    current_season = db.query(Season).filter(Season.id == season_id).first()
    if not current_season:
        return Decimal("0")

    previous_seasons = (
        db.query(Season)
        .filter(
            Season.game_id == current_season.game_id,
            Season.season_number < current_season.season_number,
        )
        .order_by(Season.season_number.desc())
        .limit(TEAM_POWER_REINFORCEMENT_LOOKBACK_SEASONS)
        .all()
    )

    weighted_budget = Decimal("0")
    weight_total = Decimal("0")
    decay = TEAM_POWER_REINFORCEMENT_DECAY

    for index, season in enumerate(previous_seasons):
        weight = decay**index
        plan = (
            db.query(ClubReinforcementPlan)
            .filter(
                ClubReinforcementPlan.club_id == club_id,
                ClubReinforcementPlan.season_id == season.id,
            )
            .first()
        )
        weighted_budget += weight * _reinforcement_budget_for_plan(plan)
        weight_total += weight

    if weight_total == 0:
        return Decimal("0")
    return weighted_budget / weight_total


def calculate_team_power(
    db: Session,
    club_id: UUID,
    season_id: UUID,
    month_index: Optional[int] = None,
) -> Decimal:
    """
    チーム力指標を計算

    v1Spec Section 8.4:
    TP = α * ln(1 + B/B_ref) + β * ln(1 + A_cum/A_ref)

    - B: 当該シーズンを含む直近最大10シーズンの年間強化費の指数減衰加重平均
    - A_cum: アカデミー累積投資
    - α = 10, β = 1
    """
    reinforcement_budget = calculate_weighted_reinforcement_budget(
        db, club_id, season_id, month_index=month_index
    )

    # アカデミー累積投資: シーズン固有の累積値を参照
    academy = (
        db.query(ClubAcademy)
        .filter(
            ClubAcademy.club_id == club_id,
            ClubAcademy.season_id == season_id,
        )
        .first()
    )
    academy_cumulative = (
        Decimal(academy.cumulative_investment or 0) if academy else Decimal("0")
    )

    # チーム力計算（参照係数は円ベースで保持しているため金額そのままを参照）
    b_ratio = (
        float(reinforcement_budget) / float(TEAM_POWER_B_REF) if TEAM_POWER_B_REF else 0
    )
    a_ratio = (
        float(academy_cumulative) / float(TEAM_POWER_A_REF) if TEAM_POWER_A_REF else 0
    )

    tp = TP_ALPHA * math.log(1 + b_ratio) + TP_BETA * math.log(1 + a_ratio)
    penalty_budget = calculate_current_reinforcement_budget_for_topteam_penalty(
        db, club_id, season_id, month_index=month_index
    )
    tp = apply_topteam_staff_tp_penalty(db, club_id, tp, penalty_budget)

    return Decimal(str(round(tp, 2)))


def calculate_team_power_for_july_disclosure(
    db: Session,
    club_id: UUID,
    season_id: UUID,
) -> Decimal:
    """
    7月公開用のチーム力を計算

    - B: 次シーズン向け強化費（6月・7月入力の合算）
    - A_cum: 当該シーズンのアカデミー累積投資
    """
    plan = (
        db.query(ClubReinforcementPlan)
        .filter(
            ClubReinforcementPlan.club_id == club_id,
            ClubReinforcementPlan.season_id == season_id,
        )
        .first()
    )
    next_season_budget = Decimal(plan.next_season_budget or 0) if plan else Decimal("0")
    tp_next_season_budget = _weighted_next_season_reinforcement_input_budget(
        db, club_id, season_id
    )
    if tp_next_season_budget == 0:
        tp_next_season_budget = next_season_budget
    reinforcement_budget = calculate_weighted_reinforcement_budget(
        db,
        club_id,
        season_id,
        current_budget_override=tp_next_season_budget,
    )

    academy = (
        db.query(ClubAcademy)
        .filter(
            ClubAcademy.club_id == club_id,
            ClubAcademy.season_id == season_id,
        )
        .first()
    )
    academy_cumulative = (
        Decimal(academy.cumulative_investment or 0) if academy else Decimal("0")
    )

    b_ratio = (
        float(reinforcement_budget) / float(TEAM_POWER_B_REF) if TEAM_POWER_B_REF else 0
    )
    a_ratio = (
        float(academy_cumulative) / float(TEAM_POWER_A_REF) if TEAM_POWER_A_REF else 0
    )

    tp = TP_ALPHA * math.log(1 + b_ratio) + TP_BETA * math.log(1 + a_ratio)
    tp = apply_topteam_staff_tp_penalty(
        db,
        club_id,
        tp,
        next_season_budget,
        use_next_staff=True,
    )

    return Decimal(str(round(tp, 2)))


def _calculate_team_power_from_reinforcement_budget(
    db: Session,
    club_id: UUID,
    season_id: UUID,
    reinforcement_budget: Decimal,
    topteam_penalty_budget: Optional[Decimal] = None,
    use_next_staff: bool = False,
) -> Decimal:
    academy = (
        db.query(ClubAcademy)
        .filter(
            ClubAcademy.club_id == club_id,
            ClubAcademy.season_id == season_id,
        )
        .first()
    )
    academy_cumulative = (
        Decimal(academy.cumulative_investment or 0) if academy else Decimal("0")
    )

    b_ratio = (
        float(reinforcement_budget) / float(TEAM_POWER_B_REF) if TEAM_POWER_B_REF else 0
    )
    a_ratio = (
        float(academy_cumulative) / float(TEAM_POWER_A_REF) if TEAM_POWER_A_REF else 0
    )

    tp = TP_ALPHA * math.log(1 + b_ratio) + TP_BETA * math.log(1 + a_ratio)
    tp = apply_topteam_staff_tp_penalty(
        db,
        club_id,
        tp,
        (
            topteam_penalty_budget
            if topteam_penalty_budget is not None
            else reinforcement_budget
        ),
        use_next_staff=use_next_staff,
    )
    return Decimal(str(round(tp, 2)))


def _reinforcement_budget_input_for_month(
    db: Session,
    club_id: UUID,
    season_id: UUID,
    month_index: int,
) -> Decimal:
    row = (
        db.query(TurnDecision.payload_json)
        .join(Turn, TurnDecision.turn_id == Turn.id)
        .filter(
            TurnDecision.club_id == club_id,
            Turn.season_id == season_id,
            Turn.month_index == month_index,
        )
        .first()
    )
    payload = row[0] if row else None
    if not payload:
        return Decimal("0")
    return Decimal(str(payload.get("reinforcement_budget", 0) or 0))


def calculate_team_power_for_monthly_reinforcement_input(
    db: Session,
    club_id: UUID,
    season_id: UUID,
    month_index: int,
) -> Decimal:
    """
    指定月に入力された翌シーズン強化費だけを使って公開用TPを計算する。
    6月resolve後の暫定公開で使用する。
    """
    input_budget = _reinforcement_budget_input_for_month(
        db, club_id, season_id, month_index
    )
    tp_input_budget = input_budget * _next_season_reinforcement_input_weight(
        month_index
    )
    reinforcement_budget = calculate_weighted_reinforcement_budget(
        db,
        club_id,
        season_id,
        current_budget_override=tp_input_budget,
    )
    return _calculate_team_power_from_reinforcement_budget(
        db,
        club_id,
        season_id,
        reinforcement_budget,
        topteam_penalty_budget=input_budget,
        use_next_staff=True,
    )


def calculate_team_power_monthly_input_with_uncertainty(
    db: Session,
    club_id: UUID,
    season_id: UUID,
    month_index: int,
) -> Tuple[Decimal, Decimal]:
    """
    指定月入力ベースの公開用TPに、7月公開と同じ不確実性を付与する。
    """
    actual_tp = calculate_team_power_for_monthly_reinforcement_input(
        db, club_id, season_id, month_index
    )
    noise = random.gauss(0, float(TEAM_POWER_DISCLOSURE_SIGMA))
    disclosed_tp = actual_tp + Decimal(str(round(noise, 2)))
    return (disclosed_tp, actual_tp)


def calculate_team_power_july_with_uncertainty(
    db: Session,
    club_id: UUID,
    season_id: UUID,
) -> Tuple[Decimal, Decimal]:
    """
    7月公開用：不確実性付きチーム力（次シーズン向け強化費を使用）

    Returns:
        (disclosed_tp, actual_tp) - 公開値と実際値のタプル
    """
    actual_tp = calculate_team_power_for_july_disclosure(db, club_id, season_id)

    noise = random.gauss(0, float(TEAM_POWER_DISCLOSURE_SIGMA))
    disclosed_tp = actual_tp + Decimal(str(round(noise, 2)))

    return (disclosed_tp, actual_tp)


def calculate_team_power_with_uncertainty(
    db: Session,
    club_id: UUID,
    season_id: UUID,
    month_index: Optional[int] = None,
) -> Tuple[Decimal, Decimal]:
    """
    7月公開用：不確実性付きチーム力

    v1Spec Section 4.2:
    - 7月ターン終了時：次シーズンのチーム力指標を公開（不確実性付き）

    Returns:
        (disclosed_tp, actual_tp) - 公開値と実際値のタプル
    """
    actual_tp = calculate_team_power(db, club_id, season_id, month_index=month_index)

    # ノイズを付与
    noise = random.gauss(0, float(TEAM_POWER_DISCLOSURE_SIGMA))
    disclosed_tp = actual_tp + Decimal(str(round(noise, 2)))

    return (disclosed_tp, actual_tp)


def get_all_clubs_team_power(
    db: Session,
    season_id: UUID,
    with_uncertainty: bool = False,
    month_index: Optional[int] = None,
) -> list[dict]:
    """
    シーズン内の全クラブのチーム力を取得

    Args:
        db: データベースセッション
        season_id: シーズンID
        with_uncertainty: True=7月用（不確実性付き）、False=12月用（実際値）

    Returns:
        クラブごとのチーム力リスト
    """
    season = db.query(Season).filter(Season.id == season_id).first()
    if not season:
        return []

    clubs = db.query(Club).filter(Club.game_id == season.game_id).all()

    results = []
    for club in clubs:
        if with_uncertainty:
            disclosed_tp, actual_tp = calculate_team_power_with_uncertainty(
                db, club.id, season_id, month_index=month_index
            )
            results.append(
                {
                    "club_id": str(club.id),
                    "club_name": club.name,
                    "team_power": float(disclosed_tp),
                    "actual_team_power": float(actual_tp),  # 内部用（保存はしない）
                }
            )
        else:
            tp = calculate_team_power(db, club.id, season_id, month_index=month_index)
            results.append(
                {
                    "club_id": str(club.id),
                    "club_name": club.name,
                    "team_power": float(tp),
                }
            )

    # チーム力順でソート
    results.sort(key=lambda x: x["team_power"], reverse=True)

    return results


def get_all_clubs_team_power_for_july(
    db: Session,
    season_id: UUID,
) -> list[dict]:
    """
    7月公開用のチーム力を取得（次シーズン向け強化費 + 当該シーズンのアカデミー累積）
    """
    season = db.query(Season).filter(Season.id == season_id).first()
    if not season:
        return []

    clubs = db.query(Club).filter(Club.game_id == season.game_id).all()

    results = []
    for club in clubs:
        disclosed_tp, actual_tp = calculate_team_power_july_with_uncertainty(
            db, club.id, season_id
        )
        results.append(
            {
                "club_id": str(club.id),
                "club_name": club.name,
                "team_power": float(disclosed_tp),
                "actual_team_power": float(actual_tp),
            }
        )

    results.sort(key=lambda x: x["team_power"], reverse=True)

    return results


def get_all_clubs_team_power_for_monthly_input(
    db: Session,
    season_id: UUID,
    month_index: int,
) -> list[dict]:
    """
    指定月入力の翌シーズン強化費を使った公開用チーム力を取得する。
    """
    season = db.query(Season).filter(Season.id == season_id).first()
    if not season:
        return []

    clubs = db.query(Club).filter(Club.game_id == season.game_id).all()

    results = []
    for club in clubs:
        disclosed_tp, actual_tp = calculate_team_power_monthly_input_with_uncertainty(
            db, club.id, season_id, month_index
        )
        results.append(
            {
                "club_id": str(club.id),
                "club_name": club.name,
                "team_power": float(disclosed_tp),
                "actual_team_power": float(actual_tp),
            }
        )

    results.sort(key=lambda x: x["team_power"], reverse=True)
    return results
