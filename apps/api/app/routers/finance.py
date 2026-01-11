from typing import List, Optional
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
    ClubFinancialLedgerRead,
    ClubTaxInfoRead,
)
from app.services import finance as finance_service
from sqlalchemy import select

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


@router.get("/ledger", response_model=List[ClubFinancialLedgerRead])
def get_finance_ledger(
    club_id: UUID,
    season_id: UUID,
    month_index: Optional[int] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return ledger entries for a club in a season, optionally filtered by month."""
    club = get_club_or_404(db, club_id)
    require_role(user, db, club.game_id, MembershipRole.club_viewer, club_id=club_id)

    stmt = (
        select(
            models.ClubFinancialLedger.turn_id,
            models.Turn.month_index,
            models.ClubFinancialLedger.kind,
            models.ClubFinancialLedger.amount,
            models.ClubFinancialLedger.meta,
        )
        .join(models.Turn, models.Turn.id == models.ClubFinancialLedger.turn_id)
        .where(
            models.ClubFinancialLedger.club_id == club_id,
            models.Turn.season_id == season_id,
        )
        .order_by(models.Turn.month_index)
    )

    if month_index is not None:
        stmt = stmt.where(models.Turn.month_index == month_index)

    rows = db.execute(stmt).all()
    # Map to list of dicts for Pydantic
    return [
        {
            "turn_id": r.turn_id,
            "month_index": r.month_index,
            "kind": r.kind,
            "amount": float(r.amount),
            "meta": r.meta,
        }
        for r in rows
    ]


@router.get("/tax-info", response_model=ClubTaxInfoRead)
def get_tax_info(
    club_id: UUID,
    season_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    club = get_club_or_404(db, club_id)
    require_role(user, db, club.game_id, MembershipRole.club_viewer, club_id=club_id)

    try:
        return finance_service.get_tax_info(db, club_id, season_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
