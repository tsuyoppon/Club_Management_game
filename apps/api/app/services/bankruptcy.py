"""
PR8: 債務超過判定・ペナルティ処理
v1Spec Section 1.1, 14.1

- 債務超過判定（balance < 0）
- 勝点剥奪（-10点）
- 追加強化費入力禁止
"""
from decimal import Decimal
from uuid import UUID
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from app.db.models import (
    Club, ClubBankruptcyState, ClubFinancialState, ClubPointPenalty, Turn, Season
)
from app.config.constants import DEBT_POINT_DEDUCTION


def _get_turn(db: Session, turn_id: UUID) -> Turn | None:
    return db.query(Turn).filter(Turn.id == turn_id).first()


def _get_penalty(
    db: Session,
    club_id: UUID,
    season_id: UUID,
    reason: str = "bankruptcy",
) -> ClubPointPenalty | None:
    return db.query(ClubPointPenalty).filter(
        ClubPointPenalty.club_id == club_id,
        ClubPointPenalty.season_id == season_id,
        ClubPointPenalty.reason == reason,
    ).first()


def get_bankruptcy_state(
    db: Session,
    club_id: UUID,
    season_id: UUID,
) -> ClubBankruptcyState | None:
    return db.query(ClubBankruptcyState).filter(
        ClubBankruptcyState.club_id == club_id,
        ClubBankruptcyState.season_id == season_id,
    ).first()


def check_bankruptcy(db: Session, club_id: UUID, turn_id: UUID) -> bool:
    """
    債務超過チェック
    balance < 0 の場合、債務超過と判定
    
    Args:
        db: DBセッション
        club_id: クラブID
        turn_id: 現在のターンID
    
    Returns:
        True if club is now bankrupt (newly or already)
    """
    turn = _get_turn(db, turn_id)
    if not turn:
        return False

    fin_state = db.query(ClubFinancialState).filter(
        ClubFinancialState.club_id == club_id
    ).first()
    
    if not fin_state:
        return False
    
    if fin_state.balance < Decimal("0"):
        mark_bankrupt(db, club_id, turn_id)
        return True
    
    return is_bankrupt(db, club_id, turn.season_id)


def mark_bankrupt(db: Session, club_id: UUID, turn_id: UUID) -> None:
    """
    債務超過状態を設定
    
    Args:
        db: DBセッション
        club_id: クラブID
        turn_id: 債務超過発生ターンID
    """
    turn = _get_turn(db, turn_id)
    if not turn:
        return

    state = get_bankruptcy_state(db, club_id, turn.season_id)
    if state:
        if not state.is_bankrupt:
            state.is_bankrupt = True
        if state.bankrupt_since_turn_id is None:
            state.bankrupt_since_turn_id = turn_id
        db.add(state)
    else:
        state = ClubBankruptcyState(
            club_id=club_id,
            season_id=turn.season_id,
            is_bankrupt=True,
            bankrupt_since_turn_id=turn_id,
        )
        db.add(state)

    db.flush()


def is_bankrupt(db: Session, club_id: UUID, season_id: Optional[UUID] = None) -> bool:
    """
    債務超過状態を確認
    
    Args:
        db: DBセッション
        club_id: クラブID
    
    Returns:
        True if club is bankrupt
    """
    query = db.query(ClubBankruptcyState).filter(
        ClubBankruptcyState.club_id == club_id,
        ClubBankruptcyState.is_bankrupt == True,  # noqa: E712
    )
    if season_id is not None:
        query = query.filter(ClubBankruptcyState.season_id == season_id)

    return query.first() is not None


def apply_point_penalty(
    db: Session, 
    club_id: UUID, 
    season_id: UUID, 
    turn_id: UUID
) -> int:
    """
    勝点剥奪を適用
    
    Args:
        db: DBセッション
        club_id: クラブID
        season_id: シーズンID
        turn_id: 適用ターンID
    
    Returns:
        剥奪された点数（負の値）、既に適用済みなら0
    """
    if not is_bankrupt(db, club_id, season_id):
        return 0
    
    if _get_penalty(db, club_id, season_id):
        return 0  # 既に適用済み
    
    # 勝点剥奪記録を作成
    penalty = ClubPointPenalty(
        club_id=club_id,
        season_id=season_id,
        turn_id=turn_id,
        points_deducted=DEBT_POINT_DEDUCTION,
        reason="bankruptcy"
    )
    db.add(penalty)
    
    db.flush()
    
    return DEBT_POINT_DEDUCTION


def get_point_penalty_for_club(db: Session, club_id: UUID, season_id: UUID) -> int:
    """
    クラブのシーズン内勝点剥奪合計を取得
    
    Args:
        db: DBセッション
        club_id: クラブID
        season_id: シーズンID
    
    Returns:
        剥奪勝点合計（負の値）
    """
    penalties = db.query(ClubPointPenalty).filter(
        ClubPointPenalty.club_id == club_id,
        ClubPointPenalty.season_id == season_id
    ).all()
    
    return sum(p.points_deducted for p in penalties)


def can_add_reinforcement(db: Session, club_id: UUID, season_id: UUID) -> bool:
    """
    追加強化費を入力可能かチェック
    債務超過クラブは追加強化費禁止
    
    Args:
        db: DBセッション
        club_id: クラブID
    
    Returns:
        True if club can add reinforcement
    """
    return not is_bankrupt(db, club_id, season_id)


def get_bankruptcy_status(db: Session, club_id: UUID, season_id: UUID) -> Dict[str, Any]:
    """
    債務超過状態の詳細を取得
    
    Args:
        db: DBセッション
        club_id: クラブID
        season_id: シーズンID
    
    Returns:
        債務超過状態の詳細辞書
    """
    state = get_bankruptcy_state(db, club_id, season_id)
    
    # 債務超過発生月を取得
    bankrupt_month = None
    if state and state.bankrupt_since_turn_id:
        turn = db.query(Turn).filter(Turn.id == state.bankrupt_since_turn_id).first()
        if turn:
            bankrupt_month = turn.month_name
    
    total_penalty = get_point_penalty_for_club(db, club_id, season_id)
    point_penalty_applied = _get_penalty(db, club_id, season_id) is not None
    is_season_bankrupt = bool(state and state.is_bankrupt)
    
    return {
        "club_id": str(club_id),
        "is_bankrupt": is_season_bankrupt,
        "bankrupt_since_turn_id": str(state.bankrupt_since_turn_id) if state and state.bankrupt_since_turn_id else None,
        "bankrupt_since_month": bankrupt_month,
        "point_penalty_applied": point_penalty_applied,
        "total_penalty_points": total_penalty,
        "can_add_reinforcement": not is_season_bankrupt
    }


def get_bankrupt_clubs_for_season(db: Session, season_id: UUID) -> List[Dict[str, Any]]:
    """
    シーズン内の債務超過クラブ一覧を取得
    
    Args:
        db: DBセッション
        season_id: シーズンID
    
    Returns:
        債務超過クラブのサマリーリスト
    """
    season = db.query(Season).filter(Season.id == season_id).first()
    if not season:
        return []
    
    # シーズンに参加している全クラブを取得
    clubs = db.query(Club).filter(Club.game_id == season.game_id).all()
    
    result = []
    for club in clubs:
        state = get_bankruptcy_state(db, club.id, season_id)
        if not state or not state.is_bankrupt:
            continue

        bankrupt_month = None
        if state.bankrupt_since_turn_id:
            turn = db.query(Turn).filter(Turn.id == state.bankrupt_since_turn_id).first()
            if turn:
                bankrupt_month = turn.month_name

        penalty = get_point_penalty_for_club(db, club.id, season_id)

        result.append({
            "club_id": str(club.id),
            "club_name": club.name,
            "is_bankrupt": True,
            "bankrupt_since_month": bankrupt_month,
            "penalty_points": penalty
        })
    
    return result


def get_penalties_for_club(db: Session, club_id: UUID, season_id: Optional[UUID] = None) -> List[ClubPointPenalty]:
    """
    クラブの勝点剥奪履歴を取得
    
    Args:
        db: DBセッション
        club_id: クラブID
        season_id: シーズンID（指定時はそのシーズンのみ）
    
    Returns:
        勝点剥奪履歴リスト
    """
    query = db.query(ClubPointPenalty).filter(ClubPointPenalty.club_id == club_id)
    if season_id:
        query = query.filter(ClubPointPenalty.season_id == season_id)
    
    return query.order_by(ClubPointPenalty.created_at.desc()).all()
