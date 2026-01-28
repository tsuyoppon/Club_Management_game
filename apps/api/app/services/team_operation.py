from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.db import models


TEAM_OPERATION_RATE = Decimal("0.10")


def process_team_operation_cost(db: Session, club_id: UUID, turn_id: UUID):
    """
    チーム運営費: 当月の強化費の10%
    """
    existing = db.execute(
        select(models.ClubFinancialLedger).where(
            models.ClubFinancialLedger.club_id == club_id,
            models.ClubFinancialLedger.turn_id == turn_id,
            models.ClubFinancialLedger.kind == "team_operation_cost",
        )
    ).scalar_one_or_none()
    if existing:
        return

    reinforcement_total = db.execute(
        select(func.coalesce(func.sum(models.ClubFinancialLedger.amount), 0)).where(
            models.ClubFinancialLedger.club_id == club_id,
            models.ClubFinancialLedger.turn_id == turn_id,
            models.ClubFinancialLedger.kind == "reinforcement_cost",
        )
    ).scalar_one()
    reinforcement_total = Decimal(reinforcement_total)

    if reinforcement_total == 0:
        return

    team_operation_cost = (reinforcement_total * TEAM_OPERATION_RATE).quantize(Decimal("0.01"))
    if team_operation_cost == 0:
        return

    db.add(
        models.ClubFinancialLedger(
            club_id=club_id,
            turn_id=turn_id,
            kind="team_operation_cost",
            amount=team_operation_cost,
            meta={
                "description": "Team Operation Cost (10% of reinforcement cost)",
                "reinforcement_total": float(reinforcement_total),
                "rate": float(TEAM_OPERATION_RATE),
            },
        )
    )
    db.flush()
