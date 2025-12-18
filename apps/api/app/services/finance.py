from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.db import models
from app.schemas import ClubFinancialProfileUpdate

def ensure_finance_initialized_for_club(db: Session, club_id: UUID):
    """
    Ensure that a club has a financial profile and state.
    If not, create them with default values.
    """
    # Check profile
    profile = db.execute(select(models.ClubFinancialProfile).where(models.ClubFinancialProfile.club_id == club_id)).scalar_one_or_none()
    if not profile:
        profile = models.ClubFinancialProfile(club_id=club_id)
        db.add(profile)
    
    # Check state
    state = db.execute(select(models.ClubFinancialState).where(models.ClubFinancialState.club_id == club_id)).scalar_one_or_none()
    if not state:
        state = models.ClubFinancialState(club_id=club_id)
        db.add(state)
    
    db.flush()
    return profile, state

def update_financial_profile(db: Session, club_id: UUID, update_data: ClubFinancialProfileUpdate):
    profile, _ = ensure_finance_initialized_for_club(db, club_id)
    
    if update_data.sponsor_base_monthly is not None:
        profile.sponsor_base_monthly = update_data.sponsor_base_monthly
    if update_data.sponsor_per_point is not None:
        profile.sponsor_per_point = update_data.sponsor_per_point
    if update_data.monthly_cost is not None:
        profile.monthly_cost = update_data.monthly_cost
    
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile

def get_financial_state(db: Session, club_id: UUID):
    _, state = ensure_finance_initialized_for_club(db, club_id)
    return state

def get_financial_snapshots(db: Session, club_id: UUID, season_id: UUID):
    stmt = select(models.ClubFinancialSnapshot).where(
        models.ClubFinancialSnapshot.club_id == club_id,
        models.ClubFinancialSnapshot.season_id == season_id
    ).order_by(models.ClubFinancialSnapshot.month_index)
    return db.execute(stmt).scalars().all()

def apply_finance_for_turn(db: Session, season_id: UUID, turn_id: UUID):
    """
    Calculate and apply finances for all clubs in the given turn.
    Idempotent: if snapshot exists for (club_id, turn_id), skip.
    """
    # Get turn info to know the month (if needed) or just process all clubs
    turn = db.execute(select(models.Turn).where(models.Turn.id == turn_id)).scalar_one_or_none()
    if not turn:
        raise ValueError(f"Turn {turn_id} not found")
    
    # Get all clubs in the game (assuming turn belongs to a season -> game)
    # We need to find the game_id from season_id
    season = db.execute(select(models.Season).where(models.Season.id == season_id)).scalar_one_or_none()
    if not season:
        raise ValueError(f"Season {season_id} not found")
    
    clubs = db.execute(select(models.Club).where(models.Club.game_id == season.game_id)).scalars().all()
    
    for club in clubs:
        # 1. Ensure initialized
        profile, state = ensure_finance_initialized_for_club(db, club.id)
        
        # 2. Check idempotency
        existing_snapshot = db.execute(select(models.ClubFinancialSnapshot).where(
            models.ClubFinancialSnapshot.club_id == club.id,
            models.ClubFinancialSnapshot.turn_id == turn_id
        )).scalar_one_or_none()
        
        if existing_snapshot:
            continue # Already processed
            
        # 3. Calculate items
        # Income
        income_sponsor = profile.sponsor_base_monthly
        # TODO: Add performance based income here later
        
        # Expenses
        expense_fixed = profile.monthly_cost
        
        # 4. Create Ledgers
        # Sponsor Income
        ledger_sponsor = models.ClubFinancialLedger(
            club_id=club.id,
            turn_id=turn_id,
            kind="sponsor",
            amount=income_sponsor,
            meta={"description": "Monthly Sponsor Income"}
        )
        db.add(ledger_sponsor)
        
        # Fixed Cost
        ledger_cost = models.ClubFinancialLedger(
            club_id=club.id,
            turn_id=turn_id,
            kind="cost",
            amount=-expense_fixed, # Expense is negative in ledger amount? 
            # Spec says: "amount NUMERIC(14,2) NOT NULL # 収入は+、支出は-"
            meta={"description": "Monthly Fixed Cost"}
        )
        db.add(ledger_cost)
        
        # 5. Update State & Create Snapshot
        opening_balance = state.balance
        income_total = income_sponsor
        expense_total = -expense_fixed # expense_total in snapshot usually positive? 
        # Spec says: "closing_balance = opening + income_total + expense_total"
        # So expense_total should be negative if we add it. 
        # Or if expense_total is positive magnitude, then formula is opening + income - expense.
        # Let's follow "amount is negative for expense" rule for ledger.
        # For snapshot, let's keep consistency. 
        # "expense_total NUMERIC(14,2)" -> usually implies magnitude, but let's stick to signed sum for simplicity in formula.
        # Wait, "expense_total" usually means "Total Expenses", which is a positive number representing cost.
        # But "closing_balance = opening + income_total + expense_total" implies expense_total is negative.
        # Let's assume expense_total is negative.
        
        net_change = income_sponsor - expense_fixed
        closing_balance = opening_balance + net_change
        
        snapshot = models.ClubFinancialSnapshot(
            club_id=club.id,
            season_id=season_id,
            turn_id=turn_id,
            month_index=turn.month_index,
            opening_balance=opening_balance,
            income_total=income_sponsor,
            expense_total=-expense_fixed,
            closing_balance=closing_balance
        )
        db.add(snapshot)
        
        # Update State
        state.balance = closing_balance
        state.last_applied_turn_id = turn_id
        db.add(state)
        
    db.commit()
