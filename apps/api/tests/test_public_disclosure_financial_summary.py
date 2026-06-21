from decimal import Decimal

from app.db import models
from app.services import public_disclosure


def _add_game_with_clubs(db):
    game = models.Game(name="Disclosure Game")
    clubs = [
        models.Club(name="Tokyo", short_name="TOK", game=game),
        models.Club(name="Osaka", short_name="OSA", game=game),
    ]
    db.add(game)
    db.add_all(clubs)
    db.commit()
    db.refresh(game)
    for club in clubs:
        db.refresh(club)
    return game, clubs


def _add_season(db, game, season_number, year_label, finalized=False):
    season = models.Season(
        game_id=game.id,
        season_number=season_number,
        year_label=year_label,
        status=models.SeasonStatus.finished if finalized else models.SeasonStatus.running,
        is_finalized=finalized,
    )
    db.add(season)
    db.commit()
    db.refresh(season)
    return season


def _add_turn(db, season, month_index, month_name="Dec", month_number=12):
    turn = models.Turn(
        season_id=season.id,
        month_index=month_index,
        month_name=month_name,
        month_number=month_number,
        turn_state=models.TurnState.resolved,
    )
    db.add(turn)
    db.commit()
    db.refresh(turn)
    return turn


def _add_finance_row(db, club, season, turn, sponsor_revenue, ending_balance):
    db.add(
        models.ClubFinancialLedger(
            club_id=club.id,
            turn_id=turn.id,
            kind="sponsor_annual",
            amount=Decimal(sponsor_revenue),
        )
    )
    db.add(
        models.ClubFinancialSnapshot(
            club_id=club.id,
            season_id=season.id,
            turn_id=turn.id,
            month_index=turn.month_index,
            opening_balance=Decimal("0"),
            income_total=Decimal(sponsor_revenue),
            expense_total=Decimal("0"),
            closing_balance=Decimal(ending_balance),
        )
    )
    db.commit()


def test_season1_financial_summary_is_not_published_or_returned(client, db):
    game, clubs = _add_game_with_clubs(db)
    season1 = _add_season(db, game, 1, "2025")
    december = _add_turn(db, season1, 5)

    for index, club in enumerate(clubs, start=1):
        _add_finance_row(db, club, season1, december, sponsor_revenue=1000 * index, ending_balance=5000 * index)

    result = public_disclosure.publish_financial_summary(db, season1.id, december.id)
    db.commit()

    assert result == {}
    assert db.query(models.SeasonPublicDisclosure).filter_by(
        season_id=season1.id,
        disclosure_type="financial_summary",
    ).first() is None

    stale_disclosure = models.SeasonPublicDisclosure(
        season_id=season1.id,
        disclosure_type="financial_summary",
        disclosure_month=5,
        turn_id=december.id,
        disclosed_data={"clubs": [{"club_id": str(clubs[0].id), "fiscal_year": "2025 (途中)"}]},
    )
    db.add(stale_disclosure)
    db.commit()

    response = client.get(f"/api/seasons/{season1.id}/disclosures/financial_summary")
    list_response = client.get(f"/api/seasons/{season1.id}/disclosures")

    assert response.status_code == 404
    assert list_response.status_code == 200
    assert all(item["disclosure_type"] != "financial_summary" for item in list_response.json())


def test_season2_financial_summary_uses_previous_full_season_only(client, db):
    game, clubs = _add_game_with_clubs(db)
    season1 = _add_season(db, game, 1, "2025", finalized=True)
    season2 = _add_season(db, game, 2, "2026")
    season1_july = _add_turn(db, season1, 12, month_name="Jul", month_number=7)
    season2_december = _add_turn(db, season2, 5)

    for index, club in enumerate(clubs, start=1):
        _add_finance_row(
            db,
            club,
            season1,
            season1_july,
            sponsor_revenue=1000 * index,
            ending_balance=5000 * index,
        )
        _add_finance_row(
            db,
            club,
            season2,
            season2_december,
            sponsor_revenue=999000 * index,
            ending_balance=9999000 * index,
        )

    result = public_disclosure.publish_financial_summary(db, season2.id, season2_december.id)
    db.commit()

    clubs_by_name = {club["club_name"]: club for club in result["clubs"]}
    assert set(clubs_by_name) == {"Tokyo", "Osaka"}
    assert clubs_by_name["Tokyo"]["fiscal_year"] == "2025"
    assert clubs_by_name["Tokyo"]["Sponsor_revenue"] == 1000
    assert clubs_by_name["Tokyo"]["total_revenue"] == 1000
    assert clubs_by_name["Tokyo"]["ending_balance"] == 5000
    assert clubs_by_name["Osaka"]["fiscal_year"] == "2025"
    assert clubs_by_name["Osaka"]["Sponsor_revenue"] == 2000
    assert clubs_by_name["Osaka"]["total_revenue"] == 2000
    assert clubs_by_name["Osaka"]["ending_balance"] == 10000

    disclosure = db.query(models.SeasonPublicDisclosure).filter_by(
        season_id=season2.id,
        disclosure_type="financial_summary",
    ).one()
    assert disclosure.disclosed_data == result

    response = client.get(f"/api/seasons/{season2.id}/disclosures/financial_summary")

    assert response.status_code == 200
    assert response.json()["disclosed_data"] == result
