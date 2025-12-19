from uuid import UUID
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.db import models

def ensure_staff_state(db: Session, club_id: UUID):
    # Ensure all roles exist
    roles = [models.StaffRole.director, models.StaffRole.coach, models.StaffRole.scout]
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
                salary_per_person=1000000 # Default placeholder
            )
            db.add(staff)
    db.flush()

def process_staff_cost(db: Session, club_id: UUID, turn_id: UUID, month_index: int):
    """
    Calculate monthly staff cost.
    Also handle hiring/firing updates in August.
    """
    ensure_staff_state(db, club_id)
    
    # 1. Update counts if it's August (Month 1)
    if month_index == 1:
        staffs = db.execute(select(models.ClubStaff).where(models.ClubStaff.club_id == club_id)).scalars().all()
        for staff in staffs:
            if staff.next_count is not None:
                # If firing (next < current), we might need to record severance pay?
                # But severance pay is recorded "upon firing".
                # v1 Spec: "Firing: Only possible in May". "Severance pay recorded as one-time cost".
                # So severance should be recorded in May when the decision is made?
                # Or in August when it becomes effective?
                # Prompt says: "Severance pay recorded as a one-time cost upon firing."
                # And "Firing: Only possible in May".
                # So likely recorded in May.
                # Here in August, we just update the count.
                staff.count = staff.next_count
                staff.next_count = None
                db.add(staff)
        db.flush()

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
    else:
        # Hiring or No Change
        # If a severance ledger exists (e.g. user fired then cancelled), remove it.
        existing = db.execute(select(models.ClubFinancialLedger).where(
            models.ClubFinancialLedger.club_id == club_id,
            models.ClubFinancialLedger.turn_id == turn_id,
            models.ClubFinancialLedger.kind == ledger_kind
        )).scalar_one_or_none()
        
        if existing:
            db.delete(existing)
    
    staff.next_count = new_count
    db.add(staff)
    # We need to return info to create ledger if needed
    return staff
