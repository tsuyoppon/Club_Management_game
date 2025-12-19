from uuid import UUID
import random
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.db import models

def process_ticket_revenue(db: Session, club_id: UUID, season_id: UUID, turn_id: UUID, month_index: int):
    """
    Calculate ticket revenue for home matches in this month.
    """
    # 1. Find Home Matches
    # Fixture.match_month_index == month_index
    fixtures = db.execute(select(models.Fixture).where(
        models.Fixture.season_id == season_id,
        models.Fixture.match_month_index == month_index,
        models.Fixture.home_club_id == club_id
    )).scalars().all()
    
    if not fixtures:
        return
        
    # 2. Get Profile
    profile = db.execute(select(models.ClubFinancialProfile).where(
        models.ClubFinancialProfile.club_id == club_id
    )).scalar_one()
    
    base_attendance = profile.base_attendance
    ticket_price = profile.ticket_price
    
    for fixture in fixtures:
        # Idempotency Key
        ledger_kind = f"ticket_rev_{fixture.id}"
        
        existing = db.execute(select(models.ClubFinancialLedger).where(
            models.ClubFinancialLedger.club_id == club_id,
            models.ClubFinancialLedger.turn_id == turn_id,
            models.ClubFinancialLedger.kind == ledger_kind
        )).scalar_one_or_none()
        
        if existing:
            continue
            
        # Calculate Attendance
        # Random fluctuation 0.9 - 1.1
        # Seed based on fixture
        seed = f"{fixture.id}-attendance"
        rng = random.Random(seed)
        fluctuation = rng.uniform(0.9, 1.1)
        
        attendance = int(base_attendance * fluctuation)
        revenue = attendance * ticket_price
        
        ledger = models.ClubFinancialLedger(
            club_id=club_id,
            turn_id=turn_id,
            kind=ledger_kind,
            amount=revenue,
            meta={
                "description": "Ticket Revenue", 
                "attendance": attendance, 
                "price": float(ticket_price),
                "fixture_id": str(fixture.id)
            }
        )
        db.add(ledger)
