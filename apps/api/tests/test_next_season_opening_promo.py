from datetime import datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from app.db import models
from app.main import app
from app.routers.seasons import generate_fixtures_core
from app.schemas import DecisionPayload
from app.services import decision_expense, match_results
from app.services.decision_validation import (
    get_available_input_details,
    get_available_inputs,
    get_next_home_promo_target,
    validate_decision_payload,
)


def _season_with_july(db, club_count=2, year_label="2026"):
    game = models.Game(name="Opening Promo League", status=models.GameStatus.active)
    db.add(game)
    db.flush()
    clubs = []
    created_at = datetime(2026, 1, 1)
    for index in range(club_count):
        club = models.Club(
            game_id=game.id,
            name=f"Club {index + 1}",
            created_at=created_at + timedelta(seconds=index),
        )
        db.add(club)
        clubs.append(club)
    db.flush()
    season = models.Season(
        game_id=game.id,
        season_number=1,
        year_label=year_label,
        status=models.SeasonStatus.running,
    )
    db.add(season)
    db.flush()
    july = models.Turn(
        season_id=season.id,
        month_index=12,
        month_name="Jul",
        month_number=7,
        turn_state=models.TurnState.collecting,
    )
    db.add(july)
    db.flush()
    for club in clubs:
        db.add(models.TurnDecision(turn_id=july.id, club_id=club.id))
    db.commit()
    return game, clubs, season, july


def _opening_home_and_others(db, clubs, july):
    targets = {club.id: get_next_home_promo_target(db, july, club.id) for club in clubs}
    home_club = next(club for club in clubs if targets[club.id] is not None)
    other_clubs = [club for club in clubs if club.id != home_club.id]
    return home_club, other_clubs, targets[home_club.id]


def test_july_preview_matches_persisted_next_season_opening_fixture(db):
    game, clubs, _, july = _season_with_july(db)
    home_club, other_clubs, target = _opening_home_and_others(db, clubs, july)

    assert target.season_number == 2
    assert target.month_index == 1
    assert target.month_name == "Aug"
    assert target.opponent_club_id == other_clubs[0].id
    assert "next_home_promo" in get_available_inputs(db, july, home_club.id)
    assert "next_home_promo" not in get_available_inputs(db, july, other_clubs[0].id)

    details = get_available_input_details(db, july, home_club.id)
    promo_detail = next(detail for detail in details if detail["key"] == "next_home_promo")
    assert promo_detail["label"] == "翌シーズン開幕ホーム向けプロモ"
    assert promo_detail["target"]["opponent_name"] == other_clubs[0].name

    next_season = models.Season(
        game_id=game.id,
        season_number=2,
        year_label="2027",
        status=models.SeasonStatus.running,
    )
    db.add(next_season)
    db.commit()
    generate_fixtures_core(db, next_season)
    opening = (
        db.query(models.Fixture)
        .filter(models.Fixture.season_id == next_season.id, models.Fixture.match_month_index == 1)
        .one()
    )
    assert opening.home_club_id == home_club.id
    assert opening.away_club_id == target.opponent_club_id


def test_july_opening_promo_rejects_away_bye_and_non_numeric_season(db):
    _, clubs, season, july = _season_with_july(db, club_count=3)
    home_club, other_clubs, _ = _opening_home_and_others(db, clubs, july)

    assert validate_decision_payload(
        db, july, home_club.id, DecisionPayload(next_home_promo=Decimal("1000000"))
    ) == []
    for club in other_clubs:
        errors = validate_decision_payload(
            db, july, club.id, DecisionPayload(next_home_promo=Decimal("1000000"))
        )
        assert errors == ["翌シーズン開幕戦がホームゲームではないため、開幕戦向けプロモ費は入力できません"]

    season.year_label = "training-final"
    db.commit()
    assert get_next_home_promo_target(db, july, home_club.id) is None


def test_prior_july_promo_is_read_for_next_season_august_and_charged_once(db):
    game, clubs, first_season, july = _season_with_july(db)
    home_club, _, _ = _opening_home_and_others(db, clubs, july)
    decision = (
        db.query(models.TurnDecision)
        .filter_by(turn_id=july.id, club_id=home_club.id)
        .one()
    )
    decision.payload_json = {"next_home_promo": 1_000_000}
    db.commit()

    decision_expense.process_decision_expenses(db, home_club.id, july.id, decision.payload_json)
    decision_expense.process_decision_expenses(db, home_club.id, july.id, decision.payload_json)
    db.commit()
    ledgers = (
        db.query(models.ClubFinancialLedger)
        .filter_by(
            club_id=home_club.id,
            turn_id=july.id,
            kind="next_home_promo_expense",
        )
        .all()
    )
    assert len(ledgers) == 1
    assert ledgers[0].amount == Decimal("-1000000")

    second_season = models.Season(
        game_id=game.id,
        season_number=2,
        year_label="2027",
        status=models.SeasonStatus.running,
    )
    db.add(second_season)
    db.flush()
    august = models.Turn(
        season_id=second_season.id,
        month_index=1,
        month_name="Aug",
        month_number=8,
    )
    db.add(august)
    db.commit()

    assert match_results.get_next_home_promo_spend(
        db, second_season.id, august.month_index, home_club.id
    ) == Decimal("1000000")
    assert match_results.get_next_home_promo_spend(
        db, first_season.id, 1, home_club.id
    ) == Decimal("0")


def test_standard_decision_api_keeps_available_inputs_and_adds_target_details(db):
    game, clubs, season, july = _season_with_july(db)
    home_club, other_clubs, target = _opening_home_and_others(db, clubs, july)
    home_user = models.User(email="home@example.com", display_name="Home")
    away_user = models.User(email="away@example.com", display_name="Away")
    db.add_all([home_user, away_user])
    db.flush()
    db.add_all(
        [
            models.Membership(
                game_id=game.id,
                user_id=home_user.id,
                role=models.MembershipRole.club_owner,
                club_id=home_club.id,
            ),
            models.Membership(
                game_id=game.id,
                user_id=away_user.id,
                role=models.MembershipRole.club_owner,
                club_id=other_clubs[0].id,
            ),
        ]
    )
    db.commit()

    client = TestClient(app)
    current = client.get(
        f"/api/turns/seasons/{season.id}/decisions/{home_club.id}/current",
        headers={"X-User-Email": home_user.email},
    )
    assert current.status_code == 200
    payload = current.json()
    assert "next_home_promo" in payload["available_inputs"]
    detail = next(item for item in payload["available_input_details"] if item["key"] == "next_home_promo")
    assert detail["target"]["season_number"] == 2
    assert detail["target"]["opponent_club_id"] == str(target.opponent_club_id)

    accepted = client.post(
        f"/api/turns/{july.id}/decisions/{home_club.id}/commit",
        headers={"X-User-Email": home_user.email},
        json={"payload": {"next_home_promo": 1_000_000}},
    )
    assert accepted.status_code == 200
    rejected = client.post(
        f"/api/turns/{july.id}/decisions/{other_clubs[0].id}/commit",
        headers={"X-User-Email": away_user.email},
        json={"payload": {"next_home_promo": 1_000_000}},
    )
    assert rejected.status_code == 400


def test_web_turn_console_shows_only_home_club_opening_promo_target(db):
    host = TestClient(app)
    player = TestClient(app)
    room = host.post(
        "/api/rooms",
        json={
            "display_name": "Host",
            "room_name": "Opening Promo Room",
            "club_names": ["Tokyo", "Osaka"],
        },
    ).json()
    host_club, player_club = room["clubs"]
    assert host.post(f"/api/rooms/{room['id']}/clubs/{host_club['id']}/claim").status_code == 200
    assert host.patch(f"/api/rooms/{room['id']}/memberships/me/ready", json={"ready": True}).status_code == 200
    assert player.post(f"/api/rooms/{room['invite_code']}/join", json={"display_name": "Player"}).status_code == 200
    assert player.post(f"/api/rooms/{room['id']}/clubs/{player_club['id']}/claim").status_code == 200
    assert player.patch(f"/api/rooms/{room['id']}/memberships/me/ready", json={"ready": True}).status_code == 200
    assert host.post(f"/api/rooms/{room['id']}/start", json={"year_label": "2026"}).status_code == 200

    season = db.query(models.Season).filter(models.Season.game_id == room["game_id"]).one()
    turns = db.query(models.Turn).filter(models.Turn.season_id == season.id).all()
    july = next(turn for turn in turns if turn.month_index == 12)
    for turn in turns:
        turn.turn_state = models.TurnState.acked if turn.month_index < 12 else models.TurnState.collecting
    db.commit()

    club_rows = db.query(models.Club).filter(models.Club.game_id == room["game_id"]).all()
    home_club, other_clubs, target = _opening_home_and_others(db, club_rows, july)
    clients = {host_club["id"]: host, player_club["id"]: player}
    home_client = clients[str(home_club.id)]
    away_client = clients[str(other_clubs[0].id)]

    console = home_client.get(f"/api/games/{room['game_id']}/clubs/{home_club.id}/turn-console")
    assert console.status_code == 200
    promo = next(item for item in console.json()["available_inputs"] if item["key"] == "next_home_promo")
    assert promo["label"] == f"翌シーズン開幕ホーム向けプロモ（vs {target.opponent_name}）"
    assert promo["target"]["opponent_name"] == target.opponent_name

    away_console = away_client.get(
        f"/api/games/{room['game_id']}/clubs/{other_clubs[0].id}/turn-console"
    )
    assert away_console.status_code == 200
    assert "next_home_promo" not in {
        item["key"] for item in away_console.json()["available_inputs"]
    }
    assert home_client.put(
        f"/api/games/{room['game_id']}/clubs/{home_club.id}/turn-draft",
        json={"payload": {"next_home_promo": 1_000_000}},
    ).status_code == 200
    assert away_client.put(
        f"/api/games/{room['game_id']}/clubs/{other_clubs[0].id}/turn-draft",
        json={"payload": {"next_home_promo": 1_000_000}},
    ).status_code == 400
