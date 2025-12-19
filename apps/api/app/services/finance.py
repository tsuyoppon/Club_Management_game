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
    
from app.services import sponsor, reinforcement, staff, academy, ticket

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
            
        # --- PR3 Structural Elements ---
        # A. Sponsor Revenue (August)
        if turn.month_index == 1: # August
            sponsor.process_sponsor_revenue(db, club.id, season_id, turn_id)
            
        # A2. Sponsor Determination (July)
        if turn.month_index == 12: # July
            sponsor.determine_next_sponsors(db, club.id, season_id)
            
        # B. Reinforcement Cost (Monthly)
        reinforcement.process_reinforcement_cost(db, club.id, season_id, turn_id, turn.month_index)
        
        # C. Staff Cost (Monthly)
        # PR4: Pass season_id for hiring resolution in August
        staff.process_staff_cost(db, club.id, turn_id, turn.month_index, season_id)
        
        # --- PR4 Dynamics ---
        # D. Academy Cost (Monthly)
        academy.process_monthly_cost(db, club.id, season_id, turn_id)
        
        # E. Academy Transfer Fee (July)
        if turn.month_index == 12: # July
            academy.process_transfer_fee(db, club.id, season_id, turn_id)
            
        # F. Ticket Revenue (Monthly)
        ticket.process_ticket_revenue(db, club.id, season_id, turn_id, turn.month_index)
        # -------------------------------
            
        # 3. Calculate items (Legacy PR2 + New PR3 Aggregation)
        # We need to sum up ALL ledgers for this turn to create the snapshot.
        # Since we just added PR3 ledgers, we should query them or accumulate them.
        # But `apply_finance_for_turn` is creating ledgers AND snapshot in one go.
        # The PR2 code created ledgers and then summed them up.
        # Let's keep PR2 logic for "Base Monthly" but maybe we should deprecate it if PR3 replaces it?
        # The prompt says "Integrate into resolve_turn".
        # PR2 had `sponsor_base_monthly` and `monthly_cost`.
        # PR3 adds specific structural costs.
        # We should keep PR2 as "Basic/Misc" costs for now, or maybe `monthly_cost` represents "Other fixed costs".
        
        # Income
        income_sponsor = profile.sponsor_base_monthly
        
        # Expenses
        expense_fixed = profile.monthly_cost
        
        # 4. Create Ledgers (PR2)
        # Sponsor Income (Monthly Base)
        ledger_sponsor = models.ClubFinancialLedger(
            club_id=club.id,
            turn_id=turn_id,
            kind="sponsor",
            amount=income_sponsor,
            meta={"description": "Monthly Sponsor Income (Base)"}
        )
        db.add(ledger_sponsor)
        
        # Fixed Cost (Monthly Base)
        ledger_cost = models.ClubFinancialLedger(
            club_id=club.id,
            turn_id=turn_id,
            kind="cost",
            amount=-expense_fixed,
            meta={"description": "Monthly Fixed Cost (Base)"}
        )
        db.add(ledger_cost)
        
        # Flush to ensure all ledgers (PR2 + PR3) are in session
        db.flush()
        
        # 5. Update State & Create Snapshot
        # Sum all ledgers for this turn
        ledgers = db.execute(select(models.ClubFinancialLedger).where(
            models.ClubFinancialLedger.club_id == club.id,
            models.ClubFinancialLedger.turn_id == turn_id
        )).scalars().all()
        
        turn_income = sum(l.amount for l in ledgers if l.amount > 0)
        turn_expense = sum(l.amount for l in ledgers if l.amount < 0)
        
        opening_balance = state.balance
        net_change = turn_income + turn_expense
        closing_balance = opening_balance + net_change
        
        snapshot = models.ClubFinancialSnapshot(
            club_id=club.id,
            season_id=season_id,
            turn_id=turn_id,
            month_index=turn.month_index,
            opening_balance=opening_balance,
            income_total=turn_income,
            expense_total=turn_expense,
            closing_balance=closing_balance
        )
        db.add(snapshot)
        
        # Update State
        state.balance = closing_balance
        state.last_applied_turn_id = turn_id
        db.add(state)
        
    db.commit()
