from decimal import Decimal
from uuid import uuid4

from app.config import constants
from app.db import models
from app.services.ticket import process_ticket_revenue


def test_financial_profile_default_uses_central_ticket_price():
    assert models.ClubFinancialProfile.ticket_price.default.arg == constants.TICKET_PRICE


def test_ticket_revenue_uses_and_synchronizes_central_ticket_price(db, monkeypatch):
    configured_price = Decimal("2750")
    monkeypatch.setattr(constants, "TICKET_PRICE", configured_price)

    game = models.Game(id=uuid4(), name="Ticket configuration test")
    home = models.Club(id=uuid4(), game_id=game.id, name="Home")
    away = models.Club(id=uuid4(), game_id=game.id, name="Away")
    season = models.Season(
        id=uuid4(),
        game_id=game.id,
        season_number=1,
        year_label="2026",
        status=models.SeasonStatus.running,
    )
    turn = models.Turn(
        id=uuid4(),
        season_id=season.id,
        month_index=1,
        month_name="Aug",
        month_number=8,
        turn_state=models.TurnState.locked,
    )
    profile = models.ClubFinancialProfile(
        club_id=home.id,
        ticket_price=Decimal("2000"),
    )
    fixture = models.Fixture(
        id=uuid4(),
        season_id=season.id,
        match_month_index=1,
        match_month_name="Aug",
        home_club_id=home.id,
        away_club_id=away.id,
        home_attendance=1_000,
        away_attendance=100,
        total_attendance=1_100,
    )
    db.add_all([game, home, away, season, turn, profile, fixture])
    db.commit()

    process_ticket_revenue(db, home.id, season.id, turn.id, turn.month_index)
    db.flush()

    ledger = (
        db.query(models.ClubFinancialLedger)
        .filter(
            models.ClubFinancialLedger.club_id == home.id,
            models.ClubFinancialLedger.turn_id == turn.id,
        )
        .one()
    )
    assert ledger.amount == Decimal("3025000")
    assert ledger.meta["price"] == 2750.0
    assert profile.ticket_price == configured_price
