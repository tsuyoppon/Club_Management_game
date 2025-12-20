"""
PR7: スポンサー営業モデル API
v1Spec Section 10 準拠
"""
from uuid import UUID
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db.session import get_db
from app.db import models
from app.services import sponsor, sales_effort
from app.schemas import (
    SalesAllocationUpdate, SalesAllocationRead,
    PipelineStatusRead, NextSponsorInfoRead,
)

router = APIRouter(prefix="/sponsors", tags=["sponsors"])


@router.get("/seasons/{season_id}/clubs/{club_id}/allocation", response_model=SalesAllocationRead)
def get_sales_allocation(
    season_id: UUID,
    club_id: UUID,
    quarter: int = Query(..., ge=1, le=4, description="Quarter (1-4)"),
    db: Session = Depends(get_db)
):
    """
    指定四半期の営業リソース配分を取得
    """
    allocation = sales_effort.ensure_sales_allocation(db, club_id, season_id, quarter)
    return SalesAllocationRead(
        club_id=allocation.club_id,
        season_id=allocation.season_id,
        quarter=allocation.quarter,
        rho_new=float(allocation.rho_new)
    )


@router.put("/seasons/{season_id}/clubs/{club_id}/allocation", response_model=SalesAllocationRead)
def set_sales_allocation(
    season_id: UUID,
    club_id: UUID,
    quarter: int = Query(..., ge=1, le=4, description="Quarter (1-4)"),
    payload: SalesAllocationUpdate = None,
    db: Session = Depends(get_db)
):
    """
    四半期の営業リソース配分を設定（四半期開始月のみ変更可能）
    
    Args:
        rho_new: 新規営業配分率 (0.0〜1.0)
            - 0.0 = 全リソースを既存顧客維持に
            - 1.0 = 全リソースを新規獲得に
            - 0.5 = 均等配分（デフォルト）
    """
    # Validate season exists
    season = db.execute(select(models.Season).where(models.Season.id == season_id)).scalar_one_or_none()
    if not season:
        raise HTTPException(status_code=404, detail="Season not found")
    
    # Validate club exists
    club = db.execute(select(models.Club).where(models.Club.id == club_id)).scalar_one_or_none()
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")
    
    allocation = sales_effort.set_sales_allocation(
        db, club_id, season_id, quarter, Decimal(str(payload.rho_new))
    )
    db.commit()
    
    return SalesAllocationRead(
        club_id=allocation.club_id,
        season_id=allocation.season_id,
        quarter=allocation.quarter,
        rho_new=float(allocation.rho_new)
    )


@router.get("/seasons/{season_id}/clubs/{club_id}/allocations", response_model=list[SalesAllocationRead])
def get_all_allocations(
    season_id: UUID,
    club_id: UUID,
    db: Session = Depends(get_db)
):
    """
    シーズン全四半期の営業配分を取得
    """
    allocations = []
    for q in range(1, 5):
        alloc = sales_effort.ensure_sales_allocation(db, club_id, season_id, q)
        allocations.append(SalesAllocationRead(
            club_id=alloc.club_id,
            season_id=alloc.season_id,
            quarter=alloc.quarter,
            rho_new=float(alloc.rho_new)
        ))
    return allocations


@router.get("/seasons/{season_id}/clubs/{club_id}/pipeline", response_model=PipelineStatusRead)
def get_pipeline_status(
    season_id: UUID,
    club_id: UUID,
    db: Session = Depends(get_db)
):
    """
    スポンサーパイプライン状況を取得
    
    4〜7月に表示される内定進捗状況を返す。
    """
    status = sponsor.get_pipeline_status(db, club_id, season_id)
    return PipelineStatusRead(**status)


@router.get("/seasons/{season_id}/clubs/{club_id}/next-sponsor", response_model=NextSponsorInfoRead)
def get_next_sponsor_info(
    season_id: UUID,
    club_id: UUID,
    db: Session = Depends(get_db)
):
    """
    次年度スポンサー情報を取得（7月UI表示用）
    
    7月に確定した次年度スポンサー数と予想収入を返す。
    """
    info = sponsor.get_next_sponsor_info(db, club_id, season_id)
    return NextSponsorInfoRead(**info)


@router.get("/seasons/{season_id}/clubs/{club_id}/effort")
def get_cumulative_effort(
    season_id: UUID,
    club_id: UUID,
    db: Session = Depends(get_db)
):
    """
    累積営業努力（EWMA）を取得
    """
    state = sponsor.ensure_sponsor_state(db, club_id, season_id)
    return {
        "club_id": str(club_id),
        "season_id": str(season_id),
        "cumulative_effort_ret": float(state.cumulative_effort_ret),
        "cumulative_effort_new": float(state.cumulative_effort_new),
        "current_sponsors": state.count,
    }
