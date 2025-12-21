from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db import models
from app.db.models import MembershipRole, User, StaffRole
from app.dependencies import get_current_user, get_db, require_role
from app.schemas import (
    AcademyBudgetUpdate,
    SponsorEffortUpdate,
    StaffHistoryEntry,
    StaffPlanUpdate,
    StaffEntryRead,
)
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


@router.get("/staff", response_model=List[StaffEntryRead])
def get_staff(
    club_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """現在のスタッフ配置を取得"""
    club = get_club_or_404(db, club_id)
    require_role(user, db, club.game_id, MembershipRole.club_viewer, club_id=club_id)

    # Ensure baseline rows exist to keep responses consistent
    staff.ensure_staff_state(db, club_id)
    db.commit()

    rows = db.query(models.ClubStaff).filter(models.ClubStaff.club_id == club_id).order_by(models.ClubStaff.role).all()
    return [
        StaffEntryRead(
            role=row.role.value,
            count=row.count,
            salary_per_person=float(row.salary_per_person),
            next_count=row.next_count,
            hiring_target=row.hiring_target,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


@router.get("/staff/history", response_model=List[StaffHistoryEntry])
def get_staff_history(
    club_id: UUID,
    season_id: Optional[UUID] = None,
    from_month: Optional[int] = None,
    to_month: Optional[int] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """月次スタッフコスト台帳から人員推移を参照"""
    club = get_club_or_404(db, club_id)
    require_role(user, db, club.game_id, MembershipRole.club_viewer, club_id=club_id)

    if season_id:
        season = db.query(models.Season).filter(models.Season.id == season_id).first()
        if not season:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Season not found")
        if season.game_id != club.game_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Season does not belong to club's game")

    query = (
        db.query(models.ClubFinancialLedger, models.Turn)
        .join(models.Turn, models.Turn.id == models.ClubFinancialLedger.turn_id)
        .filter(
            models.ClubFinancialLedger.club_id == club_id,
            models.ClubFinancialLedger.kind == "staff_cost",
        )
    )

    if season_id:
        query = query.filter(models.Turn.season_id == season_id)
    if from_month is not None:
        query = query.filter(models.Turn.month_index >= from_month)
    if to_month is not None:
        query = query.filter(models.Turn.month_index <= to_month)

    ledgers = query.order_by(models.Turn.season_id, models.Turn.month_index).all()

    results: List[StaffHistoryEntry] = []
    for ledger, turn in ledgers:
        details = (ledger.meta or {}).get("details", {})
        results.append(
            StaffHistoryEntry(
                turn_id=ledger.turn_id,
                season_id=turn.season_id,
                month_index=turn.month_index,
                month_name=turn.month_name,
                total_cost=float(abs(ledger.amount)),
                staff=details,
                created_at=ledger.created_at,
            )
        )
    return results

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
