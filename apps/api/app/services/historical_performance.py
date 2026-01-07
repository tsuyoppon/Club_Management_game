from typing import List
from uuid import UUID

from sqlalchemy.orm import Session

from app.db import models


def get_hist_perf_value(db: Session, season_id: UUID, club_id: UUID) -> float:
    season = db.query(models.Season).filter(models.Season.id == season_id).first()
    if not season:
        return 0.5

    previous_seasons: List[models.Season] = db.query(models.Season).filter(
        models.Season.game_id == season.game_id,
        models.Season.is_finalized == True,
        models.Season.id != season_id,
    ).all()

    if not previous_seasons:
        return 0.5

    values: List[float] = []
    for prev_season in previous_seasons:
        standings = db.query(models.SeasonFinalStanding).filter(
            models.SeasonFinalStanding.season_id == prev_season.id
        ).all()
        if not standings:
            continue

        num_clubs = len(standings)
        standing = next((s for s in standings if s.club_id == club_id), None)
        if not standing:
            continue

        if num_clubs <= 1:
            values.append(0.5)
        else:
            values.append(1.0 - (standing.rank - 1) / (num_clubs - 1))

    if not values:
        return 0.5

    return float(sum(values) / len(values))
