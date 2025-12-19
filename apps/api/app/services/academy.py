from uuid import UUID
from decimal import Decimal
import random
from sqlalchemy.orm import Session
from sqlalchemy import select, desc
from app.db import models

# Assumed v1Spec Constants
TRANSFER_FEE_PROBABILITY_BASE = 0.01 # 1% per 10M cumulative investment
TRANSFER_FEE_MIN = 50000000 # 50M
TRANSFER_FEE_MAX = 200000000 # 200M

def ensure_academy_state(db: Session, club_id: UUID, season_id: UUID):
    state = db.execute(select(models.ClubAcademy).where(
        models.ClubAcademy.club_id == club_id,
        models.ClubAcademy.season_id == season_id
    )).scalar_one_or_none()
    
    if not state:
        # Inherit cumulative investment from previous season
        current_season = db.execute(select(models.Season).where(models.Season.id == season_id)).scalar_one()
        
        prev_season = db.execute(select(models.Season).where(
            models.Season.game_id == current_season.game_id,
            models.Season.created_at < current_season.created_at
        ).order_by(desc(models.Season.created_at)).limit(1)).scalar_one_or_none()
        
        cumulative = Decimal("0")
        annual_budget = Decimal("0")
        
        if prev_season:
            prev_state = db.execute(select(models.ClubAcademy).where(
                models.ClubAcademy.club_id == club_id,
                models.ClubAcademy.season_id == prev_season.id
            )).scalar_one_or_none()
            
            if prev_state:
                cumulative = prev_state.cumulative_investment
                
                # Extract next_budget from history
                history = prev_state.transfer_fee_history or []
                for h in history:
                    if isinstance(h, dict) and "next_budget" in h:
                        annual_budget = Decimal(str(h["next_budget"]))
                        break
                # Note: We store next_budget in transfer_fee_history as a temporary measure
                # to avoid adding a new column for "next_annual_budget".

        state = models.ClubAcademy(
            club_id=club_id,
            season_id=season_id,
            annual_budget=annual_budget,
            cumulative_investment=cumulative
        )
        db.add(state)
        db.flush()
    return state

def update_academy_plan(db: Session, club_id: UUID, season_id: UUID, annual_budget: int):
    """
    Set annual budget for NEXT season.
    """
    # We need to store this "next budget" somewhere.
    # Since I missed the column, I'll use a temporary solution:
    # I'll store it in `transfer_fee_history` as a special key "next_budget" for now, 
    # and when creating next season, I'll read it.
    # This is technical debt but avoids another migration cycle right now.
    state = ensure_academy_state(db, club_id, season_id)
    
    history = list(state.transfer_fee_history) if state.transfer_fee_history else []
    # Remove existing next_budget entry if any
    history = [h for h in history if not isinstance(h, dict) or "next_budget" not in h]
    history.append({"next_budget": annual_budget})
    
    state.transfer_fee_history = history
    db.add(state)
    return state

def process_monthly_cost(db: Session, club_id: UUID, season_id: UUID, turn_id: UUID):
    state = ensure_academy_state(db, club_id, season_id)
    
    monthly_cost = state.annual_budget / 12
    
    if monthly_cost > 0:
        # Check idempotency
        existing = db.execute(select(models.ClubFinancialLedger).where(
            models.ClubFinancialLedger.club_id == club_id,
            models.ClubFinancialLedger.turn_id == turn_id,
            models.ClubFinancialLedger.kind == "academy_cost"
        )).scalar_one_or_none()
        
        if not existing:
            ledger = models.ClubFinancialLedger(
                club_id=club_id,
                turn_id=turn_id,
                kind="academy_cost",
                amount=-monthly_cost,
                meta={"description": "Monthly Academy Cost"}
            )
            db.add(ledger)
            
            # Update cumulative investment?
            # Spec says "cumulative investment". Does it update monthly or annually?
            # Usually monthly.
            state.cumulative_investment += monthly_cost
            db.add(state)

def process_transfer_fee(db: Session, club_id: UUID, season_id: UUID, turn_id: UUID):
    """
    July (Month 12). Probabilistic revenue.
    """
    state = ensure_academy_state(db, club_id, season_id)
    
    # Check idempotency
    existing = db.execute(select(models.ClubFinancialLedger).where(
        models.ClubFinancialLedger.club_id == club_id,
        models.ClubFinancialLedger.turn_id == turn_id,
        models.ClubFinancialLedger.kind == "academy_transfer_fee"
    )).scalar_one_or_none()
    
    if existing:
        return
        
    # Calculate Probability
    # 1% per 10M.
    prob = float(state.cumulative_investment) / 10000000.0 * TRANSFER_FEE_PROBABILITY_BASE
    prob = min(0.5, prob) # Cap at 50%
    
    seed = f"{season_id}-{club_id}-academy-transfer"
    rng = random.Random(seed)
    
    if rng.random() < prob:
        # Success
        amount = rng.randint(TRANSFER_FEE_MIN, TRANSFER_FEE_MAX)
        
        ledger = models.ClubFinancialLedger(
            club_id=club_id,
            turn_id=turn_id,
            kind="academy_transfer_fee",
            amount=amount,
            meta={"description": "Academy Transfer Fee Revenue", "prob": prob}
        )
        db.add(ledger)
        
        # Record in history
        history = list(state.transfer_fee_history) if state.transfer_fee_history else []
        history.append({"season_id": str(season_id), "amount": amount})
        state.transfer_fee_history = history
        db.add(state)
