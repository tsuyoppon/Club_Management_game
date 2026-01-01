"""
入力バリデーションサービス（v1Spec Section 5）
"""
from uuid import UUID
from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db import models
from app.schemas import DecisionPayload
from app.config.constants import QUARTER_START_MONTHS, SEASON_MONTHS


def validate_decision_payload(
    db: Session,
    turn: models.Turn,
    club_id: UUID,
    payload: DecisionPayload
) -> List[str]:
    """
    入力バリデーション
    Returns: List of error messages (empty if valid)
    """
    errors = []
    
    # 1. 翌月ホーム向けプロモ費: 「翌月にホーム戦がある月」のみ入力可
    if payload.next_home_promo is not None and payload.next_home_promo > 0:
        next_month = turn.month_index + 1
        # 翌月がシーズン内（month_index 1-10）かつホーム戦があるか
        if next_month <= 10:  # シーズン内
            has_next_home = _has_home_fixture_in_month(db, turn.season_id, club_id, next_month)
            if not has_next_home:
                errors.append("翌月にホーム戦がないため、翌月ホーム向けプロモ費は入力できません")
        else:
            errors.append("翌月は試合月ではないため、翌月ホーム向けプロモ費は入力できません")
    
    # 2. 追加強化費: 12月（month_index=5）のみ入力可
    if payload.additional_reinforcement is not None and payload.additional_reinforcement > 0:
        if turn.month_index != 5:  # 12月 = month_index 5
            errors.append("追加強化費は12月のみ入力可能です")
        # 債務超過チェック
        if _is_in_debt(db, club_id):
            errors.append("債務超過中のため追加強化費は入力できません")

    # 2.5 翌シーズン強化費: 6月・7月（month_index=11,12）のみ入力可
    if payload.reinforcement_budget is not None and payload.reinforcement_budget > 0:
        if turn.month_index not in [11, 12]:
            errors.append("翌シーズン強化費は6月と7月のみ入力可能です")
    
    # 3. 営業リソース配分: 四半期開始月のみ変更可能
    if payload.sales_allocation_new is not None:
        if turn.month_index not in QUARTER_START_MONTHS:
            errors.append("営業リソース配分は四半期開始月（8月,11月,2月,5月）のみ変更可能です")
    
    return errors


def _has_home_fixture_in_month(db: Session, season_id: UUID, club_id: UUID, month_index: int) -> bool:
    """指定月にホーム戦があるかチェック"""
    fixture = db.execute(
        select(models.Fixture).where(
            models.Fixture.season_id == season_id,
            models.Fixture.home_club_id == club_id,
            models.Fixture.match_month_index == month_index
        )
    ).scalar_one_or_none()
    return fixture is not None


def _is_in_debt(db: Session, club_id: UUID) -> bool:
    """
    債務超過状態かチェック
    現金残高がマイナスの場合はTrue
    """
    state = db.execute(
        select(models.ClubFinancialState).where(
            models.ClubFinancialState.club_id == club_id
        )
    ).scalar_one_or_none()
    
    if state and state.balance < 0:
        return True
    return False


def parse_decision_payload(payload_dict: dict) -> DecisionPayload:
    """
    dictからDecisionPayloadを生成
    後方互換性のため、不明なキーは無視する
    """
    if not payload_dict:
        return DecisionPayload()
    
    try:
        return DecisionPayload(**payload_dict)
    except Exception:
        # 後方互換性：既存のpayload形式でもエラーにしない
        return DecisionPayload(
            promo_expense=payload_dict.get("promo_expense"),
            hometown_expense=payload_dict.get("hometown_expense"),
            next_home_promo=payload_dict.get("next_home_promo"),
        )
