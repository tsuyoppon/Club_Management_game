from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import models
from app.db.models import MembershipRole, User
from app.dependencies import get_current_user, get_db, require_role
from app.schemas import (
    ClubFinancialProfileRead,
    ClubFinancialProfileUpdate,
    ClubFinancialSnapshotRead,
    ClubFinancialStateRead,
)
from app.services import finance as finance_service

router = APIRouter(prefix="/clubs/{club_id}/finance", tags=["finance"])


def get_club_or_404(db: Session, club_id: UUID) -> models.Club:
    club = db.query(models.Club).filter(models.Club.id == club_id).first()
    if not club:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Club not found")
    return club


@router.put("/profile", response_model=ClubFinancialProfileRead)
def update_finance_profile(
    club_id: UUID,
    payload: ClubFinancialProfileUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    club = get_club_or_404(db, club_id)
    # Only GM can update finance profile
    require_role(user, db, club.game_id, MembershipRole.gm, club_id=club_id)
    
    profile = finance_service.update_financial_profile(db, club_id, payload)
    return profile


@router.get("/state", response_model=ClubFinancialStateRead)
def get_finance_state(
    club_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    club = get_club_or_404(db, club_id)
    # Club Owner, Viewer, or GM can view state
    require_role(user, db, club.game_id, MembershipRole.club_viewer, club_id=club_id)
    
    state = finance_service.get_financial_state(db, club_id)
    return state


@router.get("/snapshots", response_model=List[ClubFinancialSnapshotRead])
def get_finance_snapshots(
    club_id: UUID,
    season_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    club = get_club_or_404(db, club_id)
    # Club Owner, Viewer, or GM can view snapshots
    require_role(user, db, club.game_id, MembershipRole.club_viewer, club_id=club_id)
    
    snapshots = finance_service.get_financial_snapshots(db, club_id, season_id)
    return snapshots
