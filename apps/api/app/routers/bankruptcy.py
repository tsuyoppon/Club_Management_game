"""
PR8: 債務超過関連API
v1Spec Section 1.1, 14.1
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List, Optional

from app.db.session import get_db
from app.db.models import Game, Club, Season, ClubPointPenalty
from app.schemas import (
    BankruptcyStatusRead, 
    PointPenaltyRead, 
    BankruptClubSummary,
    LastPlacePenaltyUpdate,
    LastPlacePenaltyRead
)
from app.services import bankruptcy as bankruptcy_service

router = APIRouter(prefix="/api", tags=["bankruptcy"])


@router.get("/clubs/{club_id}/finance/bankruptcy-status", response_model=BankruptcyStatusRead)
def get_bankruptcy_status(
    club_id: UUID, 
    season_id: UUID = Query(..., description="シーズンID（勝点剥奪合計計算用）"),
    db: Session = Depends(get_db)
):
    """
    債務超過状態を取得
    
    Args:
        club_id: クラブID
        season_id: シーズンID（勝点剥奪合計計算用）
    """
    club = db.query(Club).filter(Club.id == club_id).first()
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")
    
    season = db.query(Season).filter(Season.id == season_id).first()
    if not season:
        raise HTTPException(status_code=404, detail="Season not found")
    
    status = bankruptcy_service.get_bankruptcy_status(db, club_id, season_id)
    return status


@router.get("/seasons/{season_id}/bankrupt-clubs", response_model=List[BankruptClubSummary])
def get_bankrupt_clubs(
    season_id: UUID, 
    db: Session = Depends(get_db)
):
    """
    シーズン内の債務超過クラブ一覧を取得
    """
    season = db.query(Season).filter(Season.id == season_id).first()
    if not season:
        raise HTTPException(status_code=404, detail="Season not found")
    
    return bankruptcy_service.get_bankrupt_clubs_for_season(db, season_id)


@router.get("/clubs/{club_id}/penalties", response_model=List[PointPenaltyRead])
def get_point_penalties(
    club_id: UUID, 
    season_id: Optional[UUID] = Query(None, description="シーズンID（指定時はそのシーズンのみ）"),
    db: Session = Depends(get_db)
):
    """
    勝点剥奪履歴を取得
    
    Args:
        club_id: クラブID
        season_id: シーズンID（指定時はそのシーズンのみ）
    """
    club = db.query(Club).filter(Club.id == club_id).first()
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")
    
    penalties = bankruptcy_service.get_penalties_for_club(db, club_id, season_id)
    return penalties


@router.put("/games/{game_id}/settings/last-place-penalty", response_model=LastPlacePenaltyRead)
def update_last_place_penalty(
    game_id: UUID,
    update: LastPlacePenaltyUpdate,
    db: Session = Depends(get_db)
):
    """
    最下位ペナルティ設定を更新
    """
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    
    game.last_place_penalty_enabled = update.enabled
    db.commit()
    db.refresh(game)
    
    return {
        "game_id": game.id,
        "last_place_penalty_enabled": game.last_place_penalty_enabled
    }


@router.get("/games/{game_id}/settings/last-place-penalty", response_model=LastPlacePenaltyRead)
def get_last_place_penalty(
    game_id: UUID,
    db: Session = Depends(get_db)
):
    """
    最下位ペナルティ設定を取得
    """
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    
    return {
        "game_id": game.id,
        "last_place_penalty_enabled": game.last_place_penalty_enabled
    }
