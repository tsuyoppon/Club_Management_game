from uuid import UUID
import random
from sqlalchemy.orm import Session
from sqlalchemy import select, desc
from app.db import models

# Assumed v1Spec Constants
SALES_EFFORT_EFFECTIVENESS = 0.1 # 10% of effort converts to probability
RETENTION_RATE_BASE = 0.8 # 80% retention base
NEW_SPONSOR_PROBABILITY = 0.05 # 5% chance per unit of effective effort

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
            unit_price=5000000, # v1 Spec
            sales_effort_history={}
        )
        db.add(state)
        db.flush()
    return state

def record_sales_effort(db: Session, club_id: UUID, season_id: UUID, month: int, effort: int):
    """
    Record sales effort for a specific month (Apr=9, May=10, Jun=11).
    """
    state = ensure_sponsor_state(db, club_id, season_id)
    
    # Update history
    history = dict(state.sales_effort_history) if state.sales_effort_history else {}
    history[str(month)] = effort
    state.sales_effort_history = history
    db.add(state)
    return state

def determine_next_sponsors(db: Session, club_id: UUID, season_id: UUID):
    """
    Determine N_next in July (Month 7 in calendar, Month 12 in index).
    Uses history from Apr(9), May(10), Jun(11).
    """
    state = ensure_sponsor_state(db, club_id, season_id)
    
    # Idempotency: If already determined, do not change
    if state.next_count is not None:
        return state
        
    # Calculate Effective Effort (Average of Apr-Jun)
    history = state.sales_effort_history or {}
    efforts = [int(history.get(str(m), 0)) for m in [9, 10, 11]]
    effective_effort = sum(efforts) / 3.0 if efforts else 0
    
    # Deterministic Seed
    seed = f"{season_id}-{club_id}-sponsor"
    rng = random.Random(seed)
    
    # 1. Retention (Existing Sponsors)
    # Prob = Base + Effort * Coeff
    retention_prob = RETENTION_RATE_BASE + (effective_effort * 0.001) # Example scaling
    retention_prob = min(1.0, retention_prob)
    
    retained_count = 0
    for _ in range(state.count):
        if rng.random() < retention_prob:
            retained_count += 1
            
    # 2. New Acquisition
    # Count = Poisson or Binomial?
    # Let's say max potential new sponsors = 5
    # Prob = Effort * Coeff
    new_prob = effective_effort * 0.01 # Example: 50 effort -> 0.5 prob
    new_prob = min(1.0, new_prob)
    
    new_count = 0
    for _ in range(5): # Max 5 new
        if rng.random() < new_prob:
            new_count += 1
            
    total_next = retained_count + new_count
    
    state.next_count = total_next
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
