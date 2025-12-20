"""
配分金サービス（v1Spec Section 7.1）
8月一括入金
"""
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db import models
from app.config.constants import DISTRIBUTION_AMOUNT


def process_distribution_revenue(
    db: Session, 
    club_id: UUID, 
    season_id: UUID, 
    turn_id: UUID, 
    month_index: int
):
    """
    8月（month_index=1）に配分金を一括計上
    """
    if month_index != 1:  # 8月のみ
        return
    
    ledger_kind = "distribution_revenue"
    
    # Idempotency check
    existing = db.execute(
        select(models.ClubFinancialLedger).where(
            models.ClubFinancialLedger.club_id == club_id,
            models.ClubFinancialLedger.turn_id == turn_id,
            models.ClubFinancialLedger.kind == ledger_kind
        )
    ).scalar_one_or_none()
    
    if existing:
        return
    
    db.add(models.ClubFinancialLedger(
        club_id=club_id,
        turn_id=turn_id,
        kind=ledger_kind,
        amount=DISTRIBUTION_AMOUNT,
        meta={"description": "Distribution Revenue (August)"}
    ))
    db.flush()
