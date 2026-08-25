"""
入力バリデーションサービス（v1Spec Section 5）
"""
from dataclasses import asdict, dataclass
from uuid import UUID
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db import models
from app.schemas import DecisionPayload
from app.config.constants import QUARTER_START_MONTHS
from app.services.bankruptcy import can_add_reinforcement
from app.services.fixtures import generate_game_round_robin


DECISION_INPUT_LABELS = {
    "sales_expense": "営業費",
    "promo_expense": "プロモーション費",
    "hometown_expense": "ホームタウン活動費",
    "next_home_promo": "翌月ホーム向けプロモ",
    "additional_reinforcement": "追加強化費",
    "reinforcement_budget": "翌シーズン強化費",
    "sales_allocation_new": "新規スポンサー営業配分",
}


@dataclass(frozen=True)
class NextHomePromoTarget:
    season_number: int
    month_index: int
    month_name: str
    home_club_id: UUID
    opponent_club_id: UUID
    opponent_name: str

    def to_dict(self) -> dict:
        return asdict(self)


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
    
    # 1. 翌月ホーム向けプロモ費: 同一シーズン翌月、または7月から来季開幕戦
    if payload.next_home_promo is not None and payload.next_home_promo > 0:
        if get_next_home_promo_target(db, turn, club_id) is None:
            if turn.month_index == 12:
                errors.append("翌シーズン開幕戦がホームゲームではないため、開幕戦向けプロモ費は入力できません")
            elif turn.month_index in (10, 11):
                errors.append("翌月は試合月ではないため、翌月ホーム向けプロモ費は入力できません")
            else:
                errors.append("翌月にホーム戦がないため、翌月ホーム向けプロモ費は入力できません")
    
    # 2. 追加強化費: 12月（month_index=5）のみ入力可
    if payload.additional_reinforcement is not None and payload.additional_reinforcement > 0:
        if turn.month_index != 5:  # 12月 = month_index 5
            errors.append("追加強化費は12月のみ入力可能です")
        # 債務超過チェック
        if not can_add_reinforcement(db, club_id, turn.season_id):
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


def get_available_inputs(db: Session, turn: models.Turn, club_id: UUID) -> List[str]:
    """指定ターンで入力可能な項目リストを返す（バリデーション条件に基づく）。"""
    available: List[str] = [
        "sales_expense",
        "promo_expense",
        "hometown_expense",
    ]

    # 営業リソース配分: 四半期開始月のみ
    if turn.month_index in QUARTER_START_MONTHS:
        available.append("sales_allocation_new")

    # 翌月ホームプロモ: 同一シーズン翌月、または7月から来季開幕戦
    if get_next_home_promo_target(db, turn, club_id) is not None:
        available.append("next_home_promo")

    # 追加強化費: 12月のみ、かつ債務超過クラブは不可
    if turn.month_index == 5 and can_add_reinforcement(db, club_id, turn.season_id):
        available.append("additional_reinforcement")

    # 翌シーズン強化費: 6月・7月のみ
    if turn.month_index in [11, 12]:
        available.append("reinforcement_budget")

    return available


def get_available_actions(db: Session, turn: models.Turn, club_id: UUID) -> List[str]:
    """入力ではないが、この月に実行できるアクションのリストを返す。"""
    actions: List[str] = []
    # 5月 (month_index 10): スタッフ採用/解雇が可能
    if turn.month_index == 10:
        actions.append("staff_hiring_firing_available")
    return actions


def get_available_input_details(db: Session, turn: models.Turn, club_id: UUID) -> List[dict]:
    """Return backward-compatible input keys with optional target metadata."""
    available = get_available_inputs(db, turn, club_id)
    promo_target = get_next_home_promo_target(db, turn, club_id) if "next_home_promo" in available else None
    details: List[dict] = []
    for key in available:
        detail = {"key": key, "label": DECISION_INPUT_LABELS.get(key, key)}
        if key == "next_home_promo" and promo_target is not None:
            detail["target"] = promo_target.to_dict()
            if turn.month_index == 12:
                detail["label"] = "翌シーズン開幕ホーム向けプロモ"
        details.append(detail)
    return details


def get_next_home_promo_target(
    db: Session,
    turn: models.Turn,
    club_id: UUID,
) -> Optional[NextHomePromoTarget]:
    """Resolve the home fixture targeted by a next-home promotion input."""
    club_uuid = UUID(str(club_id))
    season = turn.season or db.query(models.Season).filter(models.Season.id == turn.season_id).first()
    if season is None:
        return None

    if turn.month_index <= 9:
        fixture = db.execute(
            select(models.Fixture).where(
                models.Fixture.season_id == season.id,
                models.Fixture.home_club_id == club_uuid,
                models.Fixture.match_month_index == turn.month_index + 1,
            )
        ).scalar_one_or_none()
        if fixture is None or fixture.away_club_id is None:
            return None
        opponent = db.query(models.Club).filter(models.Club.id == fixture.away_club_id).first()
        if opponent is None:
            return None
        return NextHomePromoTarget(
            season_number=season.season_number,
            month_index=fixture.match_month_index,
            month_name=fixture.match_month_name,
            home_club_id=club_uuid,
            opponent_club_id=opponent.id,
            opponent_name=opponent.name,
        )

    if turn.month_index != 12 or not season.year_label or not season.year_label.isdigit():
        return None

    opening = next(
        (
            spec
            for spec in generate_game_round_robin(db, season.game_id, match_months=10)
            if spec.match_month_index == 1 and spec.home_club_id == club_uuid and not spec.is_bye
        ),
        None,
    )
    if opening is None or opening.away_club_id is None:
        return None
    opponent = db.query(models.Club).filter(models.Club.id == opening.away_club_id).first()
    if opponent is None:
        return None
    return NextHomePromoTarget(
        season_number=season.season_number + 1,
        month_index=1,
        month_name="Aug",
        home_club_id=club_uuid,
        opponent_club_id=opponent.id,
        opponent_name=opponent.name,
    )


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
