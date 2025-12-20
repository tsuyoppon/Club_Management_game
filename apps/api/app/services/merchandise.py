"""
物販サービス（v1Spec Section 7.1, 7.2）
ホームゲーム月に物販収入・費用を計上
"""
from uuid import UUID
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db import models
from app.config.constants import MERCHANDISE_SPEND_PER_PERSON, MERCHANDISE_MARGIN


def process_merchandise(
    db: Session, 
    club_id: UUID, 
    season_id: UUID, 
    turn_id: UUID, 
    month_index: int
):
    """
    ホームゲーム月に物販収入・費用を計上
    Attendance から算出
    """
    # 1. Find Home Fixtures
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
        revenue_kind = f"merchandise_rev_{fixture.id}"
        cost_kind = f"merchandise_cost_{fixture.id}"
        
        # Idempotency
        existing = db.execute(
            select(models.ClubFinancialLedger).where(
                models.ClubFinancialLedger.club_id == club_id,
                models.ClubFinancialLedger.turn_id == turn_id,
                models.ClubFinancialLedger.kind == revenue_kind
            )
        ).scalar_one_or_none()
        
        if existing:
            continue
        
        # Calculate from attendance
        home_att = fixture.home_attendance or 0
        away_att = fixture.away_attendance or 0
        total_attendance = home_att + away_att
        
        if total_attendance == 0:
            continue
        
        gross_revenue = Decimal(total_attendance) * MERCHANDISE_SPEND_PER_PERSON
        cost = gross_revenue * (Decimal("1") - MERCHANDISE_MARGIN)
        
        # Revenue Ledger
        db.add(models.ClubFinancialLedger(
            club_id=club_id,
            turn_id=turn_id,
            kind=revenue_kind,
            amount=gross_revenue,
            meta={"fixture_id": str(fixture.id), "description": "Merchandise Revenue"}
        ))
        
        # Cost Ledger (negative)
        db.add(models.ClubFinancialLedger(
            club_id=club_id,
            turn_id=turn_id,
            kind=cost_kind,
            amount=-cost,
            meta={"fixture_id": str(fixture.id), "description": "Merchandise Cost"}
        ))
    
    db.flush()
