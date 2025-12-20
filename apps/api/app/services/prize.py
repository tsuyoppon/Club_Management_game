"""
賞金サービス（v1Spec Section 7.1）
6月ターン終了で表示＆入金
"""
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db import models
from app.config.constants import PRIZE_AMOUNTS


def get_prize_amount_for_rank(rank: int) -> int:
    """順位に応じた賞金額を取得"""
    return PRIZE_AMOUNTS.get(rank, 0)


def process_prize_revenue(
    db: Session, 
    club_id: UUID, 
    season_id: UUID, 
    turn_id: UUID, 
    month_index: int
):
    """
    6月（month_index=11）に賞金を計上
    """
    if month_index != 11:  # 6月
        return
    
    kind = "prize_revenue"
    
    # Idempotency
    existing = db.execute(
        select(models.ClubFinancialLedger).where(
            models.ClubFinancialLedger.club_id == club_id,
            models.ClubFinancialLedger.turn_id == turn_id,
            models.ClubFinancialLedger.kind == kind
        )
    ).scalar_one_or_none()
    
    if existing:
        return
    
    # Get final standings (up to May = month_index 10)
    from app.services.standings import StandingsCalculator
    calc = StandingsCalculator(db, season_id)
    standings = calc.calculate(up_to_month=10)  # 5月まで
    
    rank = None
    for s in standings:
        if str(s["club_id"]) == str(club_id):
            rank = s["rank"]
            break
    
    if rank is None:
        return
    
    amount = get_prize_amount_for_rank(rank)
    if amount > 0:
        db.add(models.ClubFinancialLedger(
            club_id=club_id,
            turn_id=turn_id,
            kind=kind,
            amount=amount,
            meta={"rank": rank, "description": f"Prize for Rank {rank}"}
        ))
        db.flush()


def get_season_prize_info(db: Session, season_id: UUID) -> list:
    """
    シーズンの賞金情報を取得（APIレスポンス用）
    """
    from app.services.standings import StandingsCalculator
    calc = StandingsCalculator(db, season_id)
    standings = calc.calculate(up_to_month=10)
    
    result = []
    for s in standings:
        rank = s["rank"]
        result.append({
            "club_id": s["club_id"],
            "club_name": s["club_name"],
            "rank": rank,
            "prize_amount": int(get_prize_amount_for_rank(rank))
        })
    
    return result
