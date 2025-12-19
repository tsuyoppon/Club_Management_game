from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import select, desc
from app.db import models

def ensure_sponsor_state(db: Session, club_id: UUID, season_id: UUID):
    state = db.execute(select(models.ClubSponsorState).where(
        models.ClubSponsorState.club_id == club_id,
        models.ClubSponsorState.season_id == season_id
    )).scalar_one_or_none()
    
    if not state:
        # Try to inherit from previous season
        current_season = db.execute(select(models.Season).where(models.Season.id == season_id)).scalar_one()
        
        prev_season = db.execute(select(models.Season).where(
            models.Season.game_id == current_season.game_id,
            models.Season.created_at < current_season.created_at
        ).order_by(desc(models.Season.created_at)).limit(1)).scalar_one_or_none()
        
        initial_count = 0
        if prev_season:
            prev_state = db.execute(select(models.ClubSponsorState).where(
                models.ClubSponsorState.club_id == club_id,
                models.ClubSponsorState.season_id == prev_season.id
            )).scalar_one_or_none()
            
            if prev_state:
                # Use next_count if determined, otherwise fallback to current count
                initial_count = prev_state.next_count if prev_state.next_count is not None else prev_state.count

        state = models.ClubSponsorState(
            club_id=club_id,
            season_id=season_id,
            count=initial_count,
            unit_price=5000000 # v1 Spec
        )
        db.add(state)
        db.flush()
    return state

def determine_next_sponsors(db: Session, club_id: UUID, season_id: UUID):
    """
    Determine N_next in July (Month 7 in calendar, Month 12 in index).
    """
    state = ensure_sponsor_state(db, club_id, season_id)
    
    # Idempotency: If already determined, do not change
    if state.next_count is not None:
        return state
        
    # Logic: For v1, we assume stable sponsors (next = current)
    # This can be replaced with complex logic later
    state.next_count = state.count
    db.add(state)
    return state

def process_sponsor_revenue(db: Session, club_id: UUID, season_id: UUID, turn_id: UUID):
    """
    In August (Month 8), record revenue based on `count` * `unit_price`.
    """
    state = ensure_sponsor_state(db, club_id, season_id)
    
    if state.is_revenue_recorded:
        return # Idempotent
        
    revenue = state.count * state.unit_price
    
    # Create Ledger
    ledger = models.ClubFinancialLedger(
        club_id=club_id,
        turn_id=turn_id,
        kind="sponsor_annual",
        amount=revenue,
        meta={"description": "Annual Sponsor Revenue", "count": state.count, "unit_price": float(state.unit_price)}
    )
    db.add(ledger)
    
    state.is_revenue_recorded = True
    db.add(state)
