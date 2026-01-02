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

from app.db.models import Club, Season, ClubFinancialProfile, ClubReinforcementPlan, ClubAcademy
from app.config.constants import (
    TP_ALPHA,
    TP_BETA,
    TEAM_POWER_B_REF,
    TEAM_POWER_A_REF,
    TEAM_POWER_DISCLOSURE_SIGMA,
)


def calculate_team_power(
    db: Session,
    club_id: UUID,
    season_id: UUID,
) -> Decimal:
    """
    チーム力指標を計算
    
    v1Spec Section 8.4:
    TP = α * ln(1 + B/B_ref) + β * ln(1 + A_cum/A_ref)
    
    - B: 当年の強化費（年額）
    - A_cum: アカデミー累積投資
    - α = 10, β = 1
    """
    # 強化費（当年）: シーズン固有の強化計画を参照
    plan = db.query(ClubReinforcementPlan).filter(
        ClubReinforcementPlan.club_id == club_id,
        ClubReinforcementPlan.season_id == season_id,
    ).first()
    reinforcement_budget = Decimal("0")
    if plan:
        reinforcement_budget = Decimal(plan.annual_budget or 0) + Decimal(plan.additional_budget or 0)

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
    noise = random.gauss(0, TEAM_POWER_DISCLOSURE_SIGMA)
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
