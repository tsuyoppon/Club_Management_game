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

from app.db.models import Club, Season, ClubFinancialProfile, ClubReinforcementPlan, ClubAcademy, Turn, TurnDecision
from app.config.constants import (
    TP_ALPHA,
    TP_BETA,
    TEAM_POWER_B_REF,
    TEAM_POWER_A_REF,
    TEAM_POWER_DISCLOSURE_SIGMA,
    TEAM_POWER_REINFORCEMENT_DECAY,
    TEAM_POWER_REINFORCEMENT_LOOKBACK_SEASONS,
)


def _reinforcement_budget_for_plan(plan: Optional[ClubReinforcementPlan]) -> Decimal:
    if not plan:
        return Decimal("0")
    return Decimal(plan.annual_budget or 0) + Decimal(plan.additional_budget or 0)


def calculate_weighted_reinforcement_budget(
    db: Session,
    club_id: UUID,
    season_id: UUID,
) -> Decimal:
    """
    TP計算用の強化費を円単位で返す。

    通常は直近最大10シーズンの年間強化費を指数減衰加重平均する。
    過去シーズンがない初年度だけ、当年度強化費をフォールバックとして使う。
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

    if not previous_seasons:
        current_plan = db.query(ClubReinforcementPlan).filter(
            ClubReinforcementPlan.club_id == club_id,
            ClubReinforcementPlan.season_id == season_id,
        ).first()
        return _reinforcement_budget_for_plan(current_plan)

    weighted_budget = Decimal("0")
    weight_total = Decimal("0")
    decay = TEAM_POWER_REINFORCEMENT_DECAY

    for index, season in enumerate(previous_seasons):
        weight = decay ** index
        plan = db.query(ClubReinforcementPlan).filter(
            ClubReinforcementPlan.club_id == club_id,
            ClubReinforcementPlan.season_id == season.id,
        ).first()
        weighted_budget += weight * _reinforcement_budget_for_plan(plan)
        weight_total += weight

    if weight_total == 0:
        return Decimal("0")
    return weighted_budget / weight_total


def calculate_team_power(
    db: Session,
    club_id: UUID,
    season_id: UUID,
) -> Decimal:
    """
    チーム力指標を計算
    
    v1Spec Section 8.4:
    TP = α * ln(1 + B/B_ref) + β * ln(1 + A_cum/A_ref)
    
    - B: 直近最大10シーズンの年間強化費の指数減衰加重平均
    - A_cum: アカデミー累積投資
    - α = 10, β = 1
    """
    reinforcement_budget = calculate_weighted_reinforcement_budget(db, club_id, season_id)

    # アカデミー累積投資: シーズン固有の累積値を参照
    academy = db.query(ClubAcademy).filter(
        ClubAcademy.club_id == club_id,
        ClubAcademy.season_id == season_id,
    ).first()
    academy_cumulative = Decimal(academy.cumulative_investment or 0) if academy else Decimal("0")

    # チーム力計算（参照係数は円ベースで保持しているため金額そのままを参照）
    b_ratio = float(reinforcement_budget) / float(TEAM_POWER_B_REF) if TEAM_POWER_B_REF else 0
    a_ratio = float(academy_cumulative) / float(TEAM_POWER_A_REF) if TEAM_POWER_A_REF else 0

    tp = TP_ALPHA * math.log(1 + b_ratio) + TP_BETA * math.log(1 + a_ratio)

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
    plan = db.query(ClubReinforcementPlan).filter(
        ClubReinforcementPlan.club_id == club_id,
        ClubReinforcementPlan.season_id == season_id,
    ).first()
    reinforcement_budget = Decimal(plan.next_season_budget or 0) if plan else Decimal("0")

    academy = db.query(ClubAcademy).filter(
        ClubAcademy.club_id == club_id,
        ClubAcademy.season_id == season_id,
    ).first()
    academy_cumulative = Decimal(academy.cumulative_investment or 0) if academy else Decimal("0")

    b_ratio = float(reinforcement_budget) / float(TEAM_POWER_B_REF) if TEAM_POWER_B_REF else 0
    a_ratio = float(academy_cumulative) / float(TEAM_POWER_A_REF) if TEAM_POWER_A_REF else 0

    tp = TP_ALPHA * math.log(1 + b_ratio) + TP_BETA * math.log(1 + a_ratio)

    return Decimal(str(round(tp, 2)))


def _calculate_team_power_from_reinforcement_budget(
    db: Session,
    club_id: UUID,
    season_id: UUID,
    reinforcement_budget: Decimal,
) -> Decimal:
    academy = db.query(ClubAcademy).filter(
        ClubAcademy.club_id == club_id,
        ClubAcademy.season_id == season_id,
    ).first()
    academy_cumulative = Decimal(academy.cumulative_investment or 0) if academy else Decimal("0")

    b_ratio = float(reinforcement_budget) / float(TEAM_POWER_B_REF) if TEAM_POWER_B_REF else 0
    a_ratio = float(academy_cumulative) / float(TEAM_POWER_A_REF) if TEAM_POWER_A_REF else 0

    tp = TP_ALPHA * math.log(1 + b_ratio) + TP_BETA * math.log(1 + a_ratio)
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
    reinforcement_budget = _reinforcement_budget_input_for_month(db, club_id, season_id, month_index)
    return _calculate_team_power_from_reinforcement_budget(db, club_id, season_id, reinforcement_budget)


def calculate_team_power_monthly_input_with_uncertainty(
    db: Session,
    club_id: UUID,
    season_id: UUID,
    month_index: int,
) -> Tuple[Decimal, Decimal]:
    """
    指定月入力ベースの公開用TPに、7月公開と同じ不確実性を付与する。
    """
    actual_tp = calculate_team_power_for_monthly_reinforcement_input(db, club_id, season_id, month_index)
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
) -> Tuple[Decimal, Decimal]:
    """
    7月公開用：不確実性付きチーム力
    
    v1Spec Section 4.2:
    - 7月ターン終了時：次シーズンのチーム力指標を公開（不確実性付き）
    
    Returns:
        (disclosed_tp, actual_tp) - 公開値と実際値のタプル
    """
    actual_tp = calculate_team_power(db, club_id, season_id)
    
    # ノイズを付与
    noise = random.gauss(0, float(TEAM_POWER_DISCLOSURE_SIGMA))
    disclosed_tp = actual_tp + Decimal(str(round(noise, 2)))
    
    return (disclosed_tp, actual_tp)


def get_all_clubs_team_power(
    db: Session,
    season_id: UUID,
    with_uncertainty: bool = False,
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
                db, club.id, season_id
            )
            results.append({
                "club_id": str(club.id),
                "club_name": club.name,
                "team_power": float(disclosed_tp),
                "actual_team_power": float(actual_tp),  # 内部用（保存はしない）
            })
        else:
            tp = calculate_team_power(db, club.id, season_id)
            results.append({
                "club_id": str(club.id),
                "club_name": club.name,
                "team_power": float(tp),
            })
    
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
        results.append({
            "club_id": str(club.id),
            "club_name": club.name,
            "team_power": float(disclosed_tp),
            "actual_team_power": float(actual_tp),
        })

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
        results.append({
            "club_id": str(club.id),
            "club_name": club.name,
            "team_power": float(disclosed_tp),
            "actual_team_power": float(actual_tp),
        })

    results.sort(key=lambda x: x["team_power"], reverse=True)
    return results
