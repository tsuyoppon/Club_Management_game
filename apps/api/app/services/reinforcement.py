from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import select
from decimal import Decimal
from app.db import models

def ensure_reinforcement_plan(db: Session, club_id: UUID, season_id: UUID):
    plan = db.execute(select(models.ClubReinforcementPlan).where(
        models.ClubReinforcementPlan.club_id == club_id,
        models.ClubReinforcementPlan.season_id == season_id
    )).scalar_one_or_none()
    
    if not plan:
        plan = models.ClubReinforcementPlan(
            club_id=club_id,
            season_id=season_id,
            annual_budget=0,
            additional_budget=0,
            next_season_budget=0
        )
        db.add(plan)
        db.flush()
    return plan


def calculate_next_season_budget(db: Session, club_id: UUID, season_id: UUID) -> Decimal:
    """Sum offseason reinforcement inputs (June/July) for the given season/club."""
    rows = db.execute(
        select(models.TurnDecision.payload_json, models.Turn.month_index)
        .join(models.Turn, models.TurnDecision.turn_id == models.Turn.id)
        .where(
            models.TurnDecision.club_id == club_id,
            models.Turn.season_id == season_id,
            models.Turn.month_index.in_([11, 12]),
        )
    ).all()

    total = Decimal(0)
    for payload, _month_index in rows:
        if not payload:
            continue
        value = payload.get("reinforcement_budget")
        if value is None:
            continue
        total += Decimal(str(value or 0))
    return total


def update_next_season_reinforcement_plan(db: Session, club_id: UUID, season_id: UUID) -> Decimal:
    """Persist offseason reinforcement sum on current plan and next season plan if it exists."""
    total = calculate_next_season_budget(db, club_id, season_id)

    current_plan = ensure_reinforcement_plan(db, club_id, season_id)
    current_plan.next_season_budget = total

    season = db.execute(select(models.Season).where(models.Season.id == season_id)).scalar_one_or_none()
    if season and season.year_label and season.year_label.isdigit():
        next_label = str(int(season.year_label) + 1)
        next_season = db.execute(
            select(models.Season).where(
                models.Season.game_id == season.game_id,
                models.Season.year_label == next_label,
            )
        ).scalar_one_or_none()
        if next_season:
            next_plan = ensure_reinforcement_plan(db, club_id, next_season.id)
            next_plan.annual_budget = total

    db.flush()
    return total

def process_reinforcement_cost(db: Session, club_id: UUID, season_id: UUID, turn_id: UUID, month_index: int):
    """
    Calculate and record monthly reinforcement cost.
    """
    plan = ensure_reinforcement_plan(db, club_id, season_id)
    
    # Check idempotency
    existing = db.execute(select(models.ClubFinancialLedger).where(
        models.ClubFinancialLedger.club_id == club_id,
        models.ClubFinancialLedger.turn_id == turn_id,
        models.ClubFinancialLedger.kind == "reinforcement_cost"
    )).scalar_one_or_none()
    
    if existing:
        return
        
    # Calculation Logic
    # 1. Base Annual Budget: Paid over 12 months (Aug-Jul)
    # 2. Additional Budget: Paid over remaining months from when it's applied.
    #    But v1 says "Additional budget can be added once mid-season".
    #    And "re-distributed over remaining months".
    #    Let's assume if `is_additional_applied` is True, we include it.
    #    But we need to know WHEN it was applied to calculate correctly?
    #    Or we just calculate: (Total Remaining Budget) / (Remaining Months).
    #    But we don't track "Total Remaining Budget" explicitly in DB.
    #    
    #    Simpler approach for v1:
    #    - Base monthly = Annual / 12
    #    - Additional monthly = Additional / (12 - ApplicationMonthIndex + 1)?
    #    - If additional is NOT applied yet, cost is Base monthly.
    #    - If additional IS applied, cost is Base + Additional_Monthly.
    #    
    #    Wait, if we add budget in Dec (Month 5), we have Dec, Jan...Jul (8 months).
    #    So Additional / 8.
    #    We need to know the month index when it was applied.
    #    Let's assume for now we just calculate simply:
    #    If `additional_budget` > 0, we assume it's applied.
    #    But we need to know the start month.
    #    Let's assume additional budget is always applied in Dec (Month 5) for v1 as per prompt "assumed December".
    #    Or better, we can store `additional_applied_month` in the plan.
    #    But I didn't add that column.
    #    Let's stick to: Annual / 12.
    #    And if `additional_budget` > 0, we assume it starts from Dec (Month 5).
    #    If current month < 5, cost = Annual / 12.
    #    If current month >= 5, cost = Annual / 12 + Additional / (12 - 5 + 1).
    
    base_monthly = plan.annual_budget / 12
    additional_monthly = 0
    
    # 追加強化費は1月〜7月（month_index 6〜12）の7ヶ月に分割計上
    # 12月（month_index 5）に入力されるが、費用は翌月から
    ADDITIONAL_START_MONTH = 6  # 1月 (month_index 6)
    ADDITIONAL_END_MONTH = 12   # 7月 (month_index 12)
    ADDITIONAL_MONTHS = 7       # 1月〜7月の7ヶ月
    
    if plan.additional_budget > 0 and ADDITIONAL_START_MONTH <= month_index <= ADDITIONAL_END_MONTH:
        additional_monthly = plan.additional_budget / ADDITIONAL_MONTHS
        
    total_cost = base_monthly + additional_monthly
    
    if total_cost > 0:
        ledger = models.ClubFinancialLedger(
            club_id=club_id,
            turn_id=turn_id,
            kind="reinforcement_cost",
            amount=-total_cost, # Expense
            meta={"description": "Monthly Reinforcement Cost", "base": float(base_monthly), "additional": float(additional_monthly)}
        )
        db.add(ledger)
