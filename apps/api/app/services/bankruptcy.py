"""
PR8: 債務超過判定・ペナルティ処理
v1Spec Section 1.1, 14.1

- 債務超過判定（balance < 0）
- 勝点剥奪（-6点）
- 追加強化費入力禁止
"""
from decimal import Decimal
from uuid import UUID
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from app.db.models import (
    Club, ClubFinancialState, ClubPointPenalty, Turn, Season
)
from app.config.constants import DEBT_POINT_DEDUCTION


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
    fin_state = db.query(ClubFinancialState).filter(
        ClubFinancialState.club_id == club_id
    ).first()
    
    if not fin_state:
        return False
    
    if fin_state.balance < Decimal("0"):
        if not fin_state.is_bankrupt:
            # 新規に債務超過になった
            mark_bankrupt(db, club_id, turn_id)
        return True
    
    return fin_state.is_bankrupt


def mark_bankrupt(db: Session, club_id: UUID, turn_id: UUID) -> None:
    """
    債務超過状態を設定
    
    Args:
        db: DBセッション
        club_id: クラブID
        turn_id: 債務超過発生ターンID
    """
    fin_state = db.query(ClubFinancialState).filter(
        ClubFinancialState.club_id == club_id
    ).first()
    
    if fin_state and not fin_state.is_bankrupt:
        fin_state.is_bankrupt = True
        fin_state.bankrupt_since_turn_id = turn_id
        db.flush()


def is_bankrupt(db: Session, club_id: UUID) -> bool:
    """
    債務超過状態を確認
    
    Args:
        db: DBセッション
        club_id: クラブID
    
    Returns:
        True if club is bankrupt
    """
    fin_state = db.query(ClubFinancialState).filter(
        ClubFinancialState.club_id == club_id
    ).first()
    
    return fin_state.is_bankrupt if fin_state else False


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
    fin_state = db.query(ClubFinancialState).filter(
        ClubFinancialState.club_id == club_id
    ).first()
    
    if not fin_state or not fin_state.is_bankrupt:
        return 0
    
    if fin_state.point_penalty_applied:
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
    
    # 適用済みフラグを立てる
    fin_state.point_penalty_applied = True
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


def can_add_reinforcement(db: Session, club_id: UUID) -> bool:
    """
    追加強化費を入力可能かチェック
    債務超過クラブは追加強化費禁止
    
    Args:
        db: DBセッション
        club_id: クラブID
    
    Returns:
        True if club can add reinforcement
    """
    return not is_bankrupt(db, club_id)


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
    fin_state = db.query(ClubFinancialState).filter(
        ClubFinancialState.club_id == club_id
    ).first()
    
    if not fin_state:
        return {
            "club_id": str(club_id),
            "is_bankrupt": False,
            "bankrupt_since_turn_id": None,
            "bankrupt_since_month": None,
            "point_penalty_applied": False,
            "total_penalty_points": 0,
            "can_add_reinforcement": True
        }
    
    # 債務超過発生月を取得
    bankrupt_month = None
    if fin_state.bankrupt_since_turn_id:
        turn = db.query(Turn).filter(Turn.id == fin_state.bankrupt_since_turn_id).first()
        if turn:
            bankrupt_month = turn.month_name
    
    total_penalty = get_point_penalty_for_club(db, club_id, season_id)
    
    return {
        "club_id": str(club_id),
        "is_bankrupt": fin_state.is_bankrupt,
        "bankrupt_since_turn_id": str(fin_state.bankrupt_since_turn_id) if fin_state.bankrupt_since_turn_id else None,
        "bankrupt_since_month": bankrupt_month,
        "point_penalty_applied": fin_state.point_penalty_applied,
        "total_penalty_points": total_penalty,
        "can_add_reinforcement": not fin_state.is_bankrupt
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
        fin_state = db.query(ClubFinancialState).filter(
            ClubFinancialState.club_id == club.id
        ).first()
        
        if fin_state and fin_state.is_bankrupt:
            bankrupt_month = None
            if fin_state.bankrupt_since_turn_id:
                turn = db.query(Turn).filter(Turn.id == fin_state.bankrupt_since_turn_id).first()
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
