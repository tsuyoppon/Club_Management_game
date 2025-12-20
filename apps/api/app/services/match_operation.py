"""
試合運営費サービス（v1Spec Section 7.2）
ホームゲーム月に計上
"""
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db import models
from app.config.constants import MATCH_OPERATION_FIXED_COST


def process_match_operation_cost(
    db: Session, 
    club_id: UUID, 
    season_id: UUID, 
    turn_id: UUID, 
    month_index: int
):
    """
    ホームゲーム開催時の運営費（固定費）
    """
    # Find Home Fixtures
    fixtures = db.execute(
        select(models.Fixture).where(
            models.Fixture.season_id == season_id,
            models.Fixture.home_club_id == club_id,
            models.Fixture.match_month_index == month_index
        )
    ).scalars().all()
    
    if not fixtures:
        return
    
    for fixture in fixtures:
        kind = f"match_operation_cost_{fixture.id}"
        
        # Idempotency
        existing = db.execute(
            select(models.ClubFinancialLedger).where(
                models.ClubFinancialLedger.club_id == club_id,
                models.ClubFinancialLedger.turn_id == turn_id,
                models.ClubFinancialLedger.kind == kind
            )
        ).scalar_one_or_none()
        
        if existing:
            continue
        
        db.add(models.ClubFinancialLedger(
            club_id=club_id,
            turn_id=turn_id,
            kind=kind,
            amount=-MATCH_OPERATION_FIXED_COST,
            meta={"fixture_id": str(fixture.id), "description": "Match Operation Cost"}
        ))
    
    db.flush()
