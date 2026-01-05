from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db, require_role
from app.db.models import Club, MembershipRole, Season, SeasonFinalStanding, User
from app.schemas import ClubFinalStandingRead

router = APIRouter(prefix="/clubs", tags=["clubs"])


@router.get("/{club_id}/final-standings", response_model=List[ClubFinalStandingRead])
def get_club_final_standings(
    club_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    club = db.query(Club).filter(Club.id == club_id).first()
    if not club:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Club not found")

    require_role(user, db, str(club.game_id), MembershipRole.club_viewer)

    rows = (
        db.query(SeasonFinalStanding, Season)
        .join(Season, Season.id == SeasonFinalStanding.season_id)
        .filter(
            SeasonFinalStanding.club_id == club_id,
            Season.is_finalized == True,
        )
        .order_by(Season.season_number)
        .all()
    )

    results: List[ClubFinalStandingRead] = []
    for standing, season in rows:
        results.append(
            ClubFinalStandingRead(
                season_id=season.id,
                season_number=season.season_number,
                year_label=season.year_label,
                finalized_at=season.finalized_at,
                club_id=standing.club_id,
                club_name=club.name,
                rank=standing.rank,
                points=standing.points,
                played=standing.played,
                won=standing.won,
                drawn=standing.drawn,
                lost=standing.lost,
                gf=standing.gf,
                ga=standing.ga,
                gd=standing.gd,
            )
        )

    return results
