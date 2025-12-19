from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db import models
from app.db.models import MembershipRole, User, StaffRole
from app.dependencies import get_current_user, get_db, require_role
from app.schemas import SponsorEffortUpdate, StaffPlanUpdate, AcademyBudgetUpdate
from app.services import sponsor, staff, academy

router = APIRouter(prefix="/clubs/{club_id}/management", tags=["management"])

def get_club_or_404(db: Session, club_id: UUID) -> models.Club:
    club = db.query(models.Club).filter(models.Club.id == club_id).first()
    if not club:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Club not found")
    return club

def get_turn_or_404(db: Session, turn_id: UUID) -> models.Turn:
    turn = db.query(models.Turn).filter(models.Turn.id == turn_id).first()
    if not turn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Turn not found")
    return turn

@router.post("/sponsor/effort")
def set_sponsor_effort(
    club_id: UUID,
    season_id: UUID,
    turn_id: UUID,
    payload: SponsorEffortUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    club = get_club_or_404(db, club_id)
    require_role(user, db, club.game_id, MembershipRole.club_owner, club_id=club_id)
    
    sponsor.record_sales_effort(db, club_id, season_id, turn_id, payload.effort)
    db.commit()
    return {"status": "ok", "effort": payload.effort}

@router.post("/staff/plan")
def set_staff_plan(
    club_id: UUID,
    turn_id: UUID,
    payload: StaffPlanUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    club = get_club_or_404(db, club_id)
    require_role(user, db, club.game_id, MembershipRole.club_owner, club_id=club_id)
    
    turn = get_turn_or_404(db, turn_id)
    
    try:
        role_enum = StaffRole(payload.role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid role: {payload.role}")
    
    try:
        staff.update_staff_plan(db, club_id, role_enum, payload.count, turn.month_index, turn_id)
        db.commit()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    return {"status": "ok", "role": payload.role, "count": payload.count}

@router.post("/academy/budget")
def set_academy_budget(
    club_id: UUID,
    season_id: UUID,
    payload: AcademyBudgetUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    club = get_club_or_404(db, club_id)
    require_role(user, db, club.game_id, MembershipRole.club_owner, club_id=club_id)
    
    academy.update_academy_plan(db, club_id, season_id, payload.annual_budget)
    db.commit()
    return {"status": "ok", "annual_budget": payload.annual_budget}
