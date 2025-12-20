from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.dependencies import get_current_user, get_db, require_role
from app.db.models import Club, ClubFanbaseState, MembershipRole
from app.schemas import FanbaseStateRead, FanIndicatorRead

router = APIRouter(prefix="/clubs", tags=["fanbase"])

@router.get("/{club_id}/fanbase", response_model=FanbaseStateRead)
def get_fanbase_state(
    club_id: str,
    season_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    club = db.query(Club).filter(Club.id == club_id).first()
    if not club:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Club not found")
    
    require_role(user, db, str(club.game_id), MembershipRole.club_owner, club_id)
    
    state = db.query(ClubFanbaseState).filter(
        ClubFanbaseState.club_id == club_id,
        ClubFanbaseState.season_id == season_id
    ).first()
    
    if not state:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fanbase state not found")
        
    return state

@router.get("/{club_id}/fan_indicator", response_model=FanIndicatorRead)
def get_fan_indicator(
    club_id: str,
    season_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    club = db.query(Club).filter(Club.id == club_id).first()
    if not club:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Club not found")
        
    require_role(user, db, str(club.game_id), MembershipRole.club_viewer)
    
    state = db.query(ClubFanbaseState).filter(
        ClubFanbaseState.club_id == club_id,
        ClubFanbaseState.season_id == season_id
    ).first()
    
    followers = state.followers_public if state and state.followers_public else 0
    
    return FanIndicatorRead(club_id=club.id, followers=followers)
