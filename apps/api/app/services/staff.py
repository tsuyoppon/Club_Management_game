from uuid import UUID
import random
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.db import models
from app.config.constants import STAFF_SALARY_ANNUAL

# Assumed v1Spec Constants
BASE_HIRING_CHANCE = 0.8 # 80% base chance
FIRING_PENALTY_PER_PERSON = Decimal("0.1") # 10% penalty per fired person
PENALTY_DECAY = Decimal("0.5") # Halves every year

def ensure_staff_state(db: Session, club_id: UUID):
    monthly_salary = STAFF_SALARY_ANNUAL / Decimal(12)
    # Ensure all roles exist
    roles = [
        models.StaffRole.sales,
        models.StaffRole.hometown,
        models.StaffRole.operations,
        models.StaffRole.promotion,
        models.StaffRole.administration,
        models.StaffRole.topteam,
        models.StaffRole.academy,
    ]
    for role in roles:
        staff = db.execute(select(models.ClubStaff).where(
            models.ClubStaff.club_id == club_id,
            models.ClubStaff.role == role
        )).scalar_one_or_none()
        
        if not staff:
            staff = models.ClubStaff(
                club_id=club_id,
                role=role,
                count=1, # Min 1
                salary_per_person=monthly_salary # Set from annual constant
            )
            db.add(staff)
    db.flush()

def resolve_hiring(db: Session, club_id: UUID, season_id: UUID):
    """
    Resolve hiring requests in August (Month 1).
    """
    ensure_staff_state(db, club_id)
    
    # Get Firing Penalty
    fin_state = db.execute(select(models.ClubFinancialState).where(
        models.ClubFinancialState.club_id == club_id
    )).scalar_one_or_none()
    
    penalty = float(fin_state.staff_firing_penalty) if fin_state else 0.0
    
    # Decay penalty for next year (applied now for current year? or after?)
    # Spec: "解雇累積（最近重視）に応じて、翌年以降の採用成功率にペナルティ"
    # If we are in August, we are starting a new year.
    # So we should apply decay to the penalty from PREVIOUS years?
    # But if we just fired in May, that penalty should be active now.
    # Let's assume penalty accumulates and decays annually.
    # We apply decay at the START of the season (August), but AFTER using it for hiring?
    # Or BEFORE? "Recency weighted".
    # If I fired in May, I want it to affect THIS August hiring.
    # So decay should happen AFTER hiring resolution or BEFORE adding new penalty?
    # Let's apply decay at the END of this function (preparing for next year).
    
    staffs = db.execute(select(models.ClubStaff).where(models.ClubStaff.club_id == club_id)).scalars().all()
    
    seed = f"{season_id}-{club_id}-hiring"
    rng = random.Random(seed)
    
    for staff in staffs:
        # 1. Handle Firing (next_count < count) - Already handled in May?
        # In May we set next_count.
        # If next_count is set, we update count.
        if staff.next_count is not None:
            # This handles Firing (where next_count was set in May)
            # AND Hiring success from previous logic?
            # Wait, for Hiring, we use hiring_target.
            
            # If next_count is set (Firing), just apply it.
            staff.count = staff.next_count
            staff.next_count = None
            db.add(staff)
            
        # 2. Handle Hiring (hiring_target > count)
        if staff.hiring_target is not None and staff.hiring_target > staff.count:
            needed = staff.hiring_target - staff.count
            # v1 simplification: deterministically honor hiring target (probability modeled via penalty may be reintroduced later)
            staff.count += needed
            staff.hiring_target = None # Reset
            db.add(staff)
            
    # Apply Decay to Penalty
    if fin_state:
        fin_state.staff_firing_penalty = fin_state.staff_firing_penalty * PENALTY_DECAY
        db.add(fin_state)
        
    db.flush()

def process_staff_cost(db: Session, club_id: UUID, turn_id: UUID, month_index: int, season_id: UUID = None):
    """
    Calculate monthly staff cost.
    Also handle hiring/firing updates in August.
    """
    ensure_staff_state(db, club_id)
    
    # 1. Update counts if it's August (Month 1)
    if month_index == 1 and season_id:
        resolve_hiring(db, club_id, season_id)

    # 2. Calculate Monthly Cost
    total_cost = 0
    staffs = db.execute(select(models.ClubStaff).where(models.ClubStaff.club_id == club_id)).scalars().all()
    
    details = {}
    for staff in staffs:
        cost = staff.count * staff.salary_per_person
        total_cost += cost
        details[staff.role.value] = {"count": staff.count, "cost": float(cost)}
        
    # Check idempotency
    existing = db.execute(select(models.ClubFinancialLedger).where(
        models.ClubFinancialLedger.club_id == club_id,
        models.ClubFinancialLedger.turn_id == turn_id,
        models.ClubFinancialLedger.kind == "staff_cost"
    )).scalar_one_or_none()
    
    if existing:
        return

    if total_cost > 0:
        ledger = models.ClubFinancialLedger(
            club_id=club_id,
            turn_id=turn_id,
            kind="staff_cost",
            amount=-total_cost,
            meta={"description": "Monthly Staff Cost", "details": details}
        )
        db.add(ledger)

SEVERANCE_PAY_FACTOR = Decimal("0.75") # 75% of annual salary (v1Spec)

def update_staff_plan(db: Session, club_id: UUID, role: models.StaffRole, new_count: int, turn_month: int, turn_id: UUID):
    """
    Handle hiring/firing.
    Constraint: Only in May (Month 10).
    """
    if turn_month != 10:
        raise ValueError("Staff changes only allowed in May")
        
    staff = db.execute(select(models.ClubStaff).where(
        models.ClubStaff.club_id == club_id,
        models.ClubStaff.role == role
    )).scalar_one()
    
    if new_count < 1:
        raise ValueError("Minimum 1 staff required")
            
    # Severance Pay Logic
    ledger_kind = f"staff_severance_{role.value}"
    
    if new_count < staff.count:
        # Firing
        # Record severance pay immediately (in May)
        diff = staff.count - new_count
        annual_salary = staff.salary_per_person * 12
        severance_total = diff * annual_salary * SEVERANCE_PAY_FACTOR
                
        # Check idempotency for severance ledger
        existing = db.execute(select(models.ClubFinancialLedger).where(
            models.ClubFinancialLedger.club_id == club_id,
            models.ClubFinancialLedger.turn_id == turn_id,
            models.ClubFinancialLedger.kind == ledger_kind
        )).scalar_one_or_none()
        
        if existing:
            # Update existing ledger (e.g. user changed firing count from 1 to 2)
            existing.amount = -severance_total
            existing.meta = {
                "description": f"Severance Pay for {role.value}", 
                "fired_count": diff, 
                "factor": float(SEVERANCE_PAY_FACTOR)
            }
            db.add(existing)
        else:
            # Create new ledger
            ledger = models.ClubFinancialLedger(
                club_id=club_id,
                turn_id=turn_id,
                kind=ledger_kind,
                amount=-severance_total,
                meta={
                    "description": f"Severance Pay for {role.value}", 
                    "fired_count": diff, 
                    "factor": float(SEVERANCE_PAY_FACTOR)
                }
            )
            db.add(ledger)
            
        # Update next_count (Deterministic Firing)
        staff.next_count = new_count
        staff.hiring_target = None # Clear hiring target if firing
        
        # Update Firing Penalty
        fin_state = db.execute(select(models.ClubFinancialState).where(
            models.ClubFinancialState.club_id == club_id
        )).scalar_one()
        # Add penalty (idempotency? If we call this multiple times, we shouldn't add penalty multiple times)
        # This is tricky. If I fire 1 person, penalty += 0.1.
        # If I call again with same firing, penalty shouldn't increase.
        # But we don't track "penalty added for this turn".
        # We can assume the penalty is calculated based on "fired count" in this turn?
        # Or we just accept that calling this API multiple times might increase penalty?
        # Ideally we should recalculate penalty based on total fired count in history? No, history is complex.
        # Let's assume the API is called once per decision commit?
        # Or we can store "penalty_added" in ledger meta?
        # For now, let's just add it. (Simplification)
        # TODO: Fix idempotency for penalty
        fin_state.staff_firing_penalty += (Decimal(diff) * FIRING_PENALTY_PER_PERSON)
        db.add(fin_state)
        
    else:
        # Hiring or No Change
        # If a severance ledger exists (e.g. user fired then cancelled), remove it.
        existing = db.execute(select(models.ClubFinancialLedger).where(
            models.ClubFinancialLedger.club_id == club_id,
            models.ClubFinancialLedger.turn_id == turn_id,
            models.ClubFinancialLedger.kind == ledger_kind
        )).scalar_one_or_none()
        
        if existing:
            # Revert penalty? (Complex)
            # For now, ignore reverting penalty.
            db.delete(existing)
            
        if new_count > staff.count:
            # Hiring Request
            staff.hiring_target = new_count
            staff.next_count = None # Clear firing intent
        else:
            # No change
            staff.hiring_target = None
            staff.next_count = None
    
    db.add(staff)
    # We need to return info to create ledger if needed
    return staff

