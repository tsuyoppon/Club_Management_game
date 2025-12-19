from datetime import datetime
from typing import Dict, Any, List, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_
from fastapi import HTTPException, status

from app.db import models
from app.services.standings import StandingsCalculator

class SeasonFinalizer:
    def __init__(self, db: Session, season_id: UUID):
        self.db = db
        self.season_id = season_id

    def get_status(self) -> Dict[str, Any]:
        season = self.db.query(models.Season).filter(models.Season.id == self.season_id).first()
        if not season:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Season not found")

        # Count fixtures (excluding byes)
        total_fixtures = self.db.query(models.Fixture).filter(
            models.Fixture.season_id == self.season_id,
            models.Fixture.is_bye == False
        ).count()

        # Count played matches
        played_matches = self.db.query(models.Match).join(models.Fixture).filter(
            models.Fixture.season_id == self.season_id,
            models.Match.status == models.MatchStatus.played
        ).count()

        # Count matches that exist (to detect missing matches)
        existing_matches = self.db.query(models.Match).join(models.Fixture).filter(
            models.Fixture.season_id == self.season_id
        ).count()

        missing_matches = total_fixtures - existing_matches
        unplayed_matches = total_fixtures - played_matches

        is_completed = (unplayed_matches == 0) and (missing_matches == 0)

        return {
            "season_id": str(self.season_id),
            "is_finalized": season.is_finalized,
            "finalized_at": season.finalized_at,
            "is_completed": is_completed,
            "total_fixtures": total_fixtures,
            "played_matches": played_matches,
            "missing_matches": missing_matches,
            "unplayed_matches": unplayed_matches
        }

    def finalize(self) -> List[Dict[str, Any]]:
        season = self.db.query(models.Season).filter(models.Season.id == self.season_id).with_for_update().first()
        if not season:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Season not found")

        if season.is_finalized:
            # Idempotent: return stored standings
            return self._get_stored_standings()

        status_info = self.get_status()
        if not status_info["is_completed"]:
            detail = "Season is not completed."
            if status_info["missing_matches"] > 0:
                detail += f" Missing {status_info['missing_matches']} matches (integrity error)."
            elif status_info["unplayed_matches"] > 0:
                detail += f" {status_info['unplayed_matches']} matches are unplayed."
            
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)

        # Calculate standings
        calculator = StandingsCalculator(self.db, self.season_id)
        standings = calculator.calculate()

        # Save to DB
        for row in standings:
            final_standing = models.SeasonFinalStanding(
                season_id=self.season_id,
                club_id=row["club_id"],
                rank=row["rank"],
                points=row["points"],
                gd=row["gd"],
                gf=row["gf"],
                ga=row["ga"],
                won=row["won"],
                drawn=row["drawn"],
                lost=row["lost"],
                played=row["played"]
            )
            self.db.add(final_standing)

        season.is_finalized = True
        season.finalized_at = datetime.utcnow()
        self.db.add(season)
        self.db.commit()

        return standings

    def _get_stored_standings(self) -> List[Dict[str, Any]]:
        stored = self.db.query(models.SeasonFinalStanding).filter(
            models.SeasonFinalStanding.season_id == self.season_id
        ).order_by(models.SeasonFinalStanding.rank).all()

        return [
            {
                "club_id": s.club_id,
                "club_name": s.club.name,
                "rank": s.rank,
                "points": s.points,
                "gd": s.gd,
                "gf": s.gf,
                "ga": s.ga,
                "won": s.won,
                "drawn": s.drawn,
                "lost": s.lost,
                "played": s.played
            }
            for s in stored
        ]
