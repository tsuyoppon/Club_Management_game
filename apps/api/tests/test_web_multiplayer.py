import io
import zipfile
from datetime import datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app
from app.db import models
from app.routers.web_multiplayer import (
    _budget_event_for_turn,
    _finance_label,
    _saved_payload_value,
    _statement_from_ledgers,
)
from app.routers.seasons import create_season_core
from app.services import staff as staff_service
from app.services.public_disclosure import _build_financial_summary


def _create_room(client: TestClient, host_mode: str | None = None):
    payload = {
        "display_name": "Host",
        "room_name": "Browser League",
        "club_names": ["Tokyo", "Osaka"],
    }
    if host_mode is not None:
        payload["host_mode"] = host_mode
    response = client.post(
        "/api/rooms",
        json=payload,
    )
    assert response.status_code == 201
    return response.json()


def _ready_two_player_room(host: TestClient, player: TestClient):
    room = _create_room(host)
    host_club, player_club = room["clubs"]

    assert host.post(f"/api/rooms/{room['id']}/clubs/{host_club['id']}/claim").status_code == 200
    assert host.patch(f"/api/rooms/{room['id']}/memberships/me/ready", json={"ready": True}).status_code == 200

    assert player.post(f"/api/rooms/{room['invite_code']}/join", json={"display_name": "Player"}).status_code == 200
    assert player.post(f"/api/rooms/{room['id']}/clubs/{player_club['id']}/claim").status_code == 200
    assert player.patch(f"/api/rooms/{room['id']}/memberships/me/ready", json={"ready": True}).status_code == 200
    return room, host_club, player_club


def test_room_create_defaults_to_player_host_mode():
    host = TestClient(app)
    room = _create_room(host)

    assert room["host_mode"] == "player"
    assert room["self"]["club_id"] is None


def test_dedicated_host_mode_enforces_role_boundaries_and_result_scope(db):
    host = TestClient(app)
    player_one = TestClient(app)
    player_two = TestClient(app)
    room = _create_room(host, host_mode="dedicated")
    first_club, second_club = room["clubs"]

    assert room["host_mode"] == "dedicated"
    assert room["self"]["club_id"] is None
    assert host.post(f"/api/rooms/{room['id']}/clubs/{first_club['id']}/claim").status_code == 403
    assert host.patch(
        f"/api/rooms/{room['id']}/memberships/me/ready",
        json={"ready": True},
    ).status_code == 403

    assert player_one.post(
        f"/api/rooms/{room['invite_code']}/join",
        json={"display_name": "Player One"},
    ).status_code == 200
    assert player_one.post(f"/api/rooms/{room['id']}/clubs/{first_club['id']}/claim").status_code == 200
    assert player_one.patch(
        f"/api/rooms/{room['id']}/memberships/me/ready",
        json={"ready": True},
    ).status_code == 200
    assert host.post(f"/api/rooms/{room['id']}/start", json={}).status_code == 400

    assert player_two.post(
        f"/api/rooms/{room['invite_code']}/join",
        json={"display_name": "Player Two"},
    ).status_code == 200
    assert player_two.post(f"/api/rooms/{room['id']}/clubs/{second_club['id']}/claim").status_code == 200
    assert player_two.patch(
        f"/api/rooms/{room['id']}/memberships/me/ready",
        json={"ready": True},
    ).status_code == 200

    started = host.post(f"/api/rooms/{room['id']}/start", json={"year_label": "2026"})
    assert started.status_code == 200
    host_play = host.get(f"/api/games/{room['game_id']}/play-state")
    assert host_play.status_code == 200
    assert host_play.json()["room"]["host_mode"] == "dedicated"
    assert host_play.json()["self"]["club_id"] is None
    assert host.get(
        f"/api/games/{room['game_id']}/clubs/{first_club['id']}/turn-console"
    ).status_code == 403
    assert player_one.get(
        f"/api/games/{room['game_id']}/clubs/{second_club['id']}/turn-console"
    ).status_code == 403

    payload = {
        "sales_expense": 1000000,
        "promo_expense": 1000000,
        "hometown_expense": 1000000,
    }
    _save_and_commit(player_one, room, first_club, payload)
    _save_and_commit(player_two, room, second_club, payload)
    assert host.post(
        f"/api/games/{room['game_id']}/host/turn-action",
        json={"action": "lock"},
    ).status_code == 200

    _prepare_completed_july(db, room)
    db.commit()
    completed = host.post(f"/api/games/{room['game_id']}/complete")
    assert completed.status_code == 200
    assert completed.json()["viewer_scope"] == "host_all"
    assert len(completed.json()["club_reviews"]) == 2

    player_summary = player_one.get(f"/api/games/{room['game_id']}/result-summary")
    assert player_summary.status_code == 200
    assert player_summary.json()["viewer_scope"] == f"club:{first_club['id']}"
    assert [row["club_id"] for row in player_summary.json()["club_reviews"]] == [first_club["id"]]


def _save_and_commit(client: TestClient, room: dict, club: dict, payload: dict):
    saved = client.put(
        f"/api/games/{room['game_id']}/clubs/{club['id']}/turn-draft",
        json={"payload": payload},
    )
    assert saved.status_code == 200
    committed = client.post(f"/api/games/{room['game_id']}/clubs/{club['id']}/turn-commit")
    assert committed.status_code == 200


def _prepare_completed_july(db, room: dict):
    season = db.query(models.Season).filter(models.Season.game_id == room["game_id"]).one()
    turns = (
        db.query(models.Turn)
        .filter(models.Turn.season_id == season.id)
        .order_by(models.Turn.month_index)
        .all()
    )
    july = next(turn for turn in turns if turn.month_index == 12)
    for turn in turns[:-1]:
        turn.turn_state = models.TurnState.acked
    july.turn_state = models.TurnState.resolved
    july.resolved_at = datetime.utcnow()

    fixtures = db.query(models.Fixture).filter(models.Fixture.season_id == season.id).all()
    for index, fixture in enumerate(fixtures):
        if fixture.is_bye:
            continue
        fixture.home_attendance = 12000 + index * 100
        fixture.total_attendance = fixture.home_attendance
        fixture.match.status = models.MatchStatus.played
        fixture.match.home_goals = index % 3
        fixture.match.away_goals = (index + 1) % 2
        fixture.match.played_at = datetime.utcnow()

    members = (
        db.query(models.GameRoomMember)
        .filter(models.GameRoomMember.room_id == room["id"], models.GameRoomMember.club_id.isnot(None))
        .all()
    )
    for index, member in enumerate(members, start=1):
        decision = db.query(models.TurnDecision).filter_by(turn_id=july.id, club_id=member.club_id).one()
        decision.decision_state = models.DecisionState.locked
        decision.committed_by_user_id = member.user_id
        decision.committed_at = datetime.utcnow()
        decision.payload_json = {
            "sales_expense": index * 1000000,
            "promo_expense": index * 200000,
            "staff_plan": {"sales": index + 1},
            "private_note_for_test": f"club-{member.club_id}",
        }
        db.add(models.TurnAck(
            turn_id=july.id,
            club_id=member.club_id,
            user_id=member.user_id,
            ack=True,
            acked_at=datetime.utcnow(),
        ))

        fanbase = db.query(models.ClubFanbaseState).filter_by(
            club_id=member.club_id,
            season_id=season.id,
        ).first()
        if not fanbase:
            fanbase = models.ClubFanbaseState(club_id=member.club_id, season_id=season.id)
            db.add(fanbase)
        fanbase.fb_count = 10000 + index * 1000
        fanbase.followers_public = 5000 + index * 500

        sponsor = db.query(models.ClubSponsorState).filter_by(
            club_id=member.club_id,
            season_id=season.id,
        ).first()
        if not sponsor:
            sponsor = models.ClubSponsorState(club_id=member.club_id, season_id=season.id)
            db.add(sponsor)
        sponsor.count = 3 + index
        sponsor.next_count = 4 + index

        snapshot = db.query(models.ClubFinancialSnapshot).filter_by(
            club_id=member.club_id,
            turn_id=july.id,
        ).first()
        if not snapshot:
            db.add(models.ClubFinancialSnapshot(
                club_id=member.club_id,
                season_id=season.id,
                turn_id=july.id,
                month_index=12,
                opening_balance=10000000,
                income_total=index * 5000000,
                expense_total=index * -2000000,
                closing_balance=10000000 + index * 3000000,
            ))
    db.commit()
    return season, july, members


def test_finance_label_dynamic_fixture_kinds_are_localized():
    assert _finance_label("merchandise_rev_fixture-1") == "物販収入"
    assert _finance_label("merchandise_cost_fixture-1") == "物販原価"
    assert _finance_label("match_operation_cost_fixture-1") == "試合関連経費"


def test_finance_statement_groups_same_display_item():
    statement = _statement_from_ledgers([
        models.ClubFinancialLedger(kind="ticket_rev_fixture-1", amount=1000),
        models.ClubFinancialLedger(kind="ticket_rev_fixture-2", amount=2500),
        models.ClubFinancialLedger(kind="match_operation_cost_fixture-1", amount=-300),
        models.ClubFinancialLedger(kind="match_operation_cost_fixture-2", amount=-700),
    ])

    assert statement["income"] == [{"kind": "income:ticket_rev", "label": "入場料収入", "amount": 3500.0}]
    assert statement["expenses"] == [{"kind": "expense:match_operation_cost", "label": "試合関連経費", "amount": -1000.0}]


def test_annual_finance_ledger_returns_only_season_end_totals(client, db):
    room = _create_room(client)
    club = room["clubs"][0]
    assert client.post(f"/api/rooms/{room['id']}/clubs/{club['id']}/claim").status_code == 200

    seasons = []
    for season_number, final_month in [(1, 12), (2, 11), (3, 12)]:
        season = models.Season(
            game_id=room["game_id"],
            season_number=season_number,
            year_label=str(2024 + season_number),
            status=models.SeasonStatus.running,
        )
        db.add(season)
        db.flush()
        turn = models.Turn(
            season_id=season.id,
            month_index=final_month,
            month_name="Jul" if final_month == 12 else "Jun",
            month_number=7 if final_month == 12 else 6,
            turn_state=models.TurnState.resolved,
        )
        db.add(turn)
        db.flush()
        db.add_all([
            models.ClubFinancialLedger(club_id=club["id"], turn_id=turn.id, kind="sponsor_annual", amount=season_number * 1000),
            models.ClubFinancialLedger(club_id=club["id"], turn_id=turn.id, kind="admin_cost", amount=season_number * -100),
            models.ClubFinancialSnapshot(
                club_id=club["id"],
                season_id=season.id,
                turn_id=turn.id,
                month_index=final_month,
                opening_balance=10000,
                income_total=season_number * 1000,
                expense_total=season_number * -100,
                closing_balance=10000 + season_number * 900,
            ),
        ])
        seasons.append(season)
    db.commit()

    response = client.get(f"/api/games/{room['game_id']}/clubs/{club['id']}/annual-finance-ledger")

    assert response.status_code == 200
    payload = response.json()
    assert [season["season_number"] for season in payload["seasons"]] == [1, 3]
    assert [season["closing_balance"] for season in payload["seasons"]] == [10900.0, 12700.0]
    assert {entry["season_id"] for entry in payload["ledger"]} == {str(seasons[0].id), str(seasons[2].id)}
    assert sum(entry["amount"] for entry in payload["ledger"] if entry["season_id"] == str(seasons[0].id)) == 900.0


def test_financial_disclosure_summary_exposes_display_items():
    summary = _build_financial_summary(
        {
            "sponsor_annual": 1000,
            "sponsor": 200,
            "ticket_rev_home-1": 300,
            "distribution_revenue": 400,
            "prize_revenue": 500,
            "merchandise_rev_home-1": 600,
            "academy_transfer_fee": 700,
            "reinforcement_cost": -80,
            "match_operation_cost_home-1": -90,
            "team_operation_cost": -100,
            "academy_cost": -110,
            "merchandise_cost_home-1": -120,
            "staff_cost": -130,
            "admin_cost": -140,
            "tax": -150,
        },
        ending_balance=12345,
    )

    assert summary["Sponsor_revenue"] == 1200
    assert summary["ticket_revenue"] == 300
    assert summary["distribution_revenue"] == 400
    assert summary["prize_revenue"] == 500
    assert summary["merchandise_revenue"] == 600
    assert summary["academy_transfer_fee"] == 700
    assert summary["total_revenue"] == 3700
    assert summary["reinforcement_cost"] == 80
    assert summary["match_operation_cost"] == 90
    assert summary["team_operation_cost"] == 100
    assert summary["academy_cost"] == 110
    assert summary["merchandise_cost"] == 120
    assert summary["staff_cost"] == 130
    assert summary["total_expense"] == 920
    assert summary["total expense"] == 920
    assert summary["net_income"] == 2780
    assert summary["ending_balance"] == 12345


def test_budget_event_metadata_by_month():
    assert _budget_event_for_turn(SimpleNamespace(month_index=5), 1200) == {
        "key": "additional_reinforcement",
        "title": "12月イベント",
        "input_label": "追加強化費",
        "saved_amount": 1200,
    }
    assert _budget_event_for_turn(SimpleNamespace(month_index=11), None)["title"] == "6月イベント"
    assert _budget_event_for_turn(SimpleNamespace(month_index=12), None)["title"] == "7月イベント"
    assert _budget_event_for_turn(SimpleNamespace(month_index=10), None) is None


def test_saved_payload_value_prefers_draft_over_decision():
    draft = SimpleNamespace(payload_json={"reinforcement_budget": 3000})
    decision = SimpleNamespace(payload_json={"reinforcement_budget": 1000})

    assert _saved_payload_value(draft, decision, "reinforcement_budget") == 3000.0
    assert _saved_payload_value(None, decision, "reinforcement_budget") == 1000.0
    assert _saved_payload_value(None, decision, "additional_reinforcement") is None


def test_browser_room_start_and_turn_console(db):
    host = TestClient(app)
    player = TestClient(app)

    room, _, player_club = _ready_two_player_room(host, player)

    start = host.post(f"/api/rooms/{room['id']}/start", json={"year_label": "2026"})
    assert start.status_code == 200

    play_state = player.get(f"/api/games/{room['game_id']}/play-state")
    assert play_state.status_code == 200
    assert play_state.json()["turn"]["state"] == "collecting"
    assert play_state.json()["self"]["club_id"] == player_club["id"]

    sponsor_state = (
        db.query(models.ClubSponsorState)
        .filter(models.ClubSponsorState.club_id == player_club["id"])
        .one()
    )
    sponsor_state.pipeline_confirmed_new = 3
    sponsor_state.pipeline_confirmed_exist = 5
    db.commit()

    turn_console = player.get(f"/api/games/{room['game_id']}/clubs/{player_club['id']}/turn-console")
    assert turn_console.status_code == 200
    assert turn_console.json()["sponsor"] == {
        "count": sponsor_state.count,
        "confirmed_next": 8,
        "confirmed_next_new": 3,
        "confirmed_next_existing": 5,
    }
    available = {item["key"] for item in turn_console.json()["available_inputs"]}
    assert {"sales_expense", "promo_expense", "hometown_expense"}.issubset(available)

    saved = player.put(
        f"/api/games/{room['game_id']}/clubs/{player_club['id']}/turn-draft",
        json={"payload": {"sales_expense": 1000000}},
    )
    assert saved.status_code == 200
    committed = player.post(f"/api/games/{room['game_id']}/clubs/{player_club['id']}/turn-commit")
    assert committed.status_code == 200


def test_new_season_staff_console_applies_previous_season_plan_before_first_resolve(db):
    host = TestClient(app)
    player = TestClient(app)
    room, _, player_club = _ready_two_player_room(host, player)

    assert host.post(f"/api/rooms/{room['id']}/start", json={"year_label": "2026"}).status_code == 200

    first_season = (
        db.query(models.Season)
        .filter(models.Season.game_id == room["game_id"])
        .one()
    )
    first_season.status = models.SeasonStatus.finished

    sales = db.query(models.ClubStaff).filter_by(
        club_id=player_club["id"], role=models.StaffRole.sales
    ).one()
    sales.count = 4
    sales.next_count = 1

    promotion = db.query(models.ClubStaff).filter_by(
        club_id=player_club["id"], role=models.StaffRole.promotion
    ).one()
    promotion.count = 2
    promotion.hiring_target = 5

    financial_state = db.query(models.ClubFinancialState).filter_by(
        club_id=player_club["id"]
    ).one()
    financial_state.staff_firing_penalty = 0.4
    db.commit()

    game = db.query(models.Game).filter(models.Game.id == room["game_id"]).one()
    second_season = create_season_core(db, game, "2027")

    response = player.get(
        f"/api/games/{room['game_id']}/clubs/{player_club['id']}/turn-console"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["turn"]["season_id"] == str(second_season.id)
    assert payload["turn"]["month_index"] == 1
    assert payload["turn"]["state"] == "collecting"
    staff_by_role = {entry["role"]: entry for entry in payload["staff"]}
    assert staff_by_role["sales"] == {
        "role": "sales",
        "count": 1,
        "next_count": None,
        "hiring_target": None,
        "input_count": None,
    }
    assert staff_by_role["promotion"] == {
        "role": "promotion",
        "count": 5,
        "next_count": None,
        "hiring_target": None,
        "input_count": None,
    }
    assert float(financial_state.staff_firing_penalty) == 0.2

    first_turn = db.query(models.Turn).filter_by(
        season_id=second_season.id, month_index=1
    ).one()
    staff_service.process_staff_cost(
        db, player_club["id"], first_turn.id, first_turn.month_index, second_season.id
    )
    db.flush()
    assert float(financial_state.staff_firing_penalty) == 0.2


def test_staff_console_repairs_pending_plan_in_already_created_first_turn(db):
    host = TestClient(app)
    player = TestClient(app)
    room, _, player_club = _ready_two_player_room(host, player)

    assert host.post(f"/api/rooms/{room['id']}/start", json={"year_label": "2026"}).status_code == 200

    sales = db.query(models.ClubStaff).filter_by(
        club_id=player_club["id"], role=models.StaffRole.sales
    ).one()
    sales.count = 4
    sales.next_count = 1
    promotion = db.query(models.ClubStaff).filter_by(
        club_id=player_club["id"], role=models.StaffRole.promotion
    ).one()
    promotion.count = 2
    promotion.hiring_target = 5
    db.commit()

    response = player.get(
        f"/api/games/{room['game_id']}/clubs/{player_club['id']}/turn-console"
    )

    assert response.status_code == 200
    assert response.json()["turn"]["month_index"] == 1
    staff_by_role = {entry["role"]: entry for entry in response.json()["staff"]}
    assert staff_by_role["sales"]["count"] == 1
    assert staff_by_role["promotion"]["count"] == 5
    assert staff_by_role["sales"]["input_count"] is None
    assert staff_by_role["promotion"]["input_count"] is None


def test_match_history_returns_current_and_past_seasons(db):
    host = TestClient(app)
    player = TestClient(app)
    room, host_club, player_club = _ready_two_player_room(host, player)

    assert host.post(f"/api/rooms/{room['id']}/start", json={"year_label": "2026"}).status_code == 200

    current_season = (
        db.query(models.Season)
        .filter(models.Season.game_id == room["game_id"])
        .one()
    )
    current_season.season_number = 2
    db.flush()
    past_season = models.Season(
        game_id=room["game_id"],
        season_number=1,
        year_label="2025",
        status=models.SeasonStatus.finished,
        is_finalized=True,
    )
    db.add(past_season)
    db.flush()
    past_fixture = models.Fixture(
        season_id=past_season.id,
        match_month_index=1,
        match_month_name="Aug",
        home_club_id=host_club["id"],
        away_club_id=player_club["id"],
        weather="rain",
        total_attendance=4321,
    )
    db.add(past_fixture)
    db.flush()
    db.add(models.Match(
        fixture_id=past_fixture.id,
        status=models.MatchStatus.played,
        home_goals=3,
        away_goals=1,
    ))
    db.commit()

    response = player.get(
        f"/api/games/{room['game_id']}/clubs/{player_club['id']}/match-history"
    )

    assert response.status_code == 200
    payload = response.json()
    assert [season["season_number"] for season in payload["seasons"]] == [2, 1]
    assert len(payload["fixtures"][str(current_season.id)]) == 10
    past_matches = payload["fixtures"][str(past_season.id)]
    assert len(past_matches) == 1
    assert past_matches[0]["opponent"] == "Tokyo"
    assert past_matches[0]["home"] is False
    assert past_matches[0]["score"] == [3, 1]
    assert past_matches[0]["score_for_club"] == [1, 3]
    assert past_matches[0]["weather"] == "rain"
    assert past_matches[0]["total_attendance"] == 4321

    forbidden = player.get(
        f"/api/games/{room['game_id']}/clubs/{host_club['id']}/match-history"
    )
    assert forbidden.status_code == 403


def test_recent_rooms_restore_candidates_and_archive_visibility():
    host = TestClient(app)
    player = TestClient(app)
    room, host_club, player_club = _ready_two_player_room(host, player)

    host_recent = host.get("/api/rooms/recent")
    assert host_recent.status_code == 200
    host_room = host_recent.json()["rooms"][0]
    assert host_room["room_id"] == room["id"]
    assert host_room["game_id"] == room["game_id"]
    assert host_room["room_name"] == "Browser League"
    assert host_room["is_host"] is True
    assert host_room["host_mode"] == "player"
    assert host_room["club_id"] == host_club["id"]

    player_recent = player.get("/api/rooms/recent")
    assert player_recent.status_code == 200
    player_room = player_recent.json()["rooms"][0]
    assert player_room["is_host"] is False
    assert player_room["club_id"] == player_club["id"]

    forbidden_archive = player.post(f"/api/games/{room['game_id']}/archive")
    assert forbidden_archive.status_code == 403

    archived = host.post(f"/api/games/{room['game_id']}/archive")
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    assert archived.json()["room_status"] == "archived"

    assert host.get("/api/rooms/recent").json()["rooms"] == []
    host_archived = host.get("/api/rooms/recent?include_archived=true")
    assert host_archived.status_code == 200
    assert host_archived.json()["rooms"][0]["game_status"] == "archived"

    player_archived = player.get("/api/rooms/recent?include_archived=true")
    assert player_archived.status_code == 200
    assert player_archived.json()["rooms"] == []


def test_archived_game_requires_confirmation_before_delete(db_session):
    host = TestClient(app)
    player = TestClient(app)
    room, _, player_club = _ready_two_player_room(host, player)
    assert host.post(f"/api/rooms/{room['id']}/start", json={"year_label": "2026"}).status_code == 200

    saved = player.put(
        f"/api/games/{room['game_id']}/clubs/{player_club['id']}/turn-draft",
        json={"payload": {"sales_expense": 1000000}},
    )
    assert saved.status_code == 200

    active_delete = host.request("DELETE", f"/api/games/{room['game_id']}", json={"confirm": room["invite_code"]})
    assert active_delete.status_code == 409

    assert host.post(f"/api/games/{room['game_id']}/archive").status_code == 200
    archived_play_state = player.get(f"/api/games/{room['game_id']}/play-state")
    assert archived_play_state.status_code == 409

    preview = host.get(f"/api/games/{room['game_id']}/delete-preview")
    assert preview.status_code == 200
    counts = preview.json()["counts"]
    assert counts["clubs"] == 2
    assert counts["seasons"] == 1
    assert counts["turns"] == 12
    assert counts["drafts"] == 1

    bad_confirm = host.request("DELETE", f"/api/games/{room['game_id']}", json={"confirm": "wrong"})
    assert bad_confirm.status_code == 400

    deleted = host.request("DELETE", f"/api/games/{room['game_id']}", json={"confirm": room["invite_code"]})
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert deleted.json()["backup"]["verified"] is True
    assert deleted.json()["backup"]["counts"]["games"] == 1

    assert db_session.query(models.Game).filter(models.Game.id == room["game_id"]).first() is None
    assert db_session.query(models.Club).count() == 0
    assert db_session.query(models.Season).count() == 0
    assert db_session.query(models.WebTurnDraft).count() == 0


def test_host_can_uncommit_before_lock_for_corrections():
    host = TestClient(app)
    player = TestClient(app)
    room, _, player_club = _ready_two_player_room(host, player)

    assert host.post(f"/api/rooms/{room['id']}/start", json={"year_label": "2026"}).status_code == 200
    _save_and_commit(player, room, player_club, {"sales_expense": 1000000})

    committed_state = player.get(f"/api/games/{room['game_id']}/play-state")
    assert committed_state.status_code == 200
    assert next(club for club in committed_state.json()["clubs"] if club["id"] == player_club["id"])["committed"]

    reopened = host.post(f"/api/games/{room['game_id']}/host/clubs/{player_club['id']}/turn-uncommit")
    assert reopened.status_code == 200
    assert reopened.json()["state"] == "draft"

    play_state = player.get(f"/api/games/{room['game_id']}/play-state")
    assert play_state.status_code == 200
    assert not next(club for club in play_state.json()["clubs"] if club["id"] == player_club["id"])["committed"]

    turn_console = player.get(f"/api/games/{room['game_id']}/clubs/{player_club['id']}/turn-console")
    assert turn_console.status_code == 200
    assert turn_console.json()["decision"]["state"] == "draft"
    assert turn_console.json()["decision"]["payload"]["sales_expense"] == 1000000


def test_host_turn_actions_and_private_console_are_role_aware():
    host = TestClient(app)
    player = TestClient(app)
    room, host_club, _ = _ready_two_player_room(host, player)

    assert host.post(f"/api/rooms/{room['id']}/start", json={}).status_code == 200

    forbidden_console = player.get(f"/api/games/{room['game_id']}/clubs/{host_club['id']}/turn-console")
    assert forbidden_console.status_code == 403

    forbidden_host_action = player.post(
        f"/api/games/{room['game_id']}/host/turn-action",
        json={"action": "lock"},
    )
    assert forbidden_host_action.status_code == 403


def test_browser_multiplayer_full_turn_can_advance():
    host = TestClient(app)
    player = TestClient(app)
    room, host_club, player_club = _ready_two_player_room(host, player)

    assert host.post(f"/api/rooms/{room['id']}/start", json={"year_label": "2026"}).status_code == 200

    premature_lock = host.post(
        f"/api/games/{room['game_id']}/host/turn-action",
        json={"action": "lock"},
    )
    assert premature_lock.status_code == 400
    assert premature_lock.json()["detail"] == "Not all decisions committed"

    payload = {
        "sales_expense": 1000000,
        "promo_expense": 1000000,
        "hometown_expense": 1000000,
    }
    _save_and_commit(host, room, host_club, payload)
    _save_and_commit(player, room, player_club, payload)

    locked = host.post(f"/api/games/{room['game_id']}/host/turn-action", json={"action": "lock"})
    assert locked.status_code == 200
    assert locked.json()["state"] == "locked"

    resolved = host.post(f"/api/games/{room['game_id']}/host/turn-action", json={"action": "resolve"})
    assert resolved.status_code == 200
    assert resolved.json()["state"] == "resolved"

    blocked_advance = host.post(f"/api/games/{room['game_id']}/host/turn-action", json={"action": "advance"})
    assert blocked_advance.status_code == 400
    assert blocked_advance.json()["detail"] == "Not all clubs acknowledged"

    assert host.post(f"/api/games/{room['game_id']}/clubs/{host_club['id']}/turn-ack").status_code == 200
    assert player.post(f"/api/games/{room['game_id']}/clubs/{player_club['id']}/turn-ack").status_code == 200

    advanced = host.post(f"/api/games/{room['game_id']}/host/turn-action", json={"action": "advance"})
    assert advanced.status_code == 200

    play_state = player.get(f"/api/games/{room['game_id']}/play-state")
    assert play_state.status_code == 200
    assert play_state.json()["turn"]["month_index"] == 2
    assert play_state.json()["turn"]["state"] == "collecting"
    assert all(not club["committed"] and not club["acked"] for club in play_state.json()["clubs"])

    turn_console = player.get(f"/api/games/{room['game_id']}/clubs/{player_club['id']}/turn-console")
    assert turn_console.status_code == 200
    fixtures = turn_console.json()["fixtures"]
    assert len(fixtures) == 10
    assert [fixture["month_index"] for fixture in fixtures] == list(range(1, 11))
    played_fixture = fixtures[0]
    assert played_fixture["status"] == "played"
    assert played_fixture["score"] is not None
    if played_fixture["home"]:
        assert played_fixture["score_for_club"] == played_fixture["score"]
    else:
        assert played_fixture["score_for_club"] == list(reversed(played_fixture["score"]))
    assert played_fixture["weather"] in {"sunny", "cloudy", "rain"}
    assert played_fixture["total_attendance"] > 0

    finance_report = turn_console.json()["finance"]["report"]
    assert finance_report["period"]["season_number"] == 1
    assert finance_report["period"]["month_index"] == 1
    assert finance_report["period"]["month_name"] == "Aug"
    assert finance_report["monthly"]["income"]
    assert finance_report["monthly"]["expenses"]
    assert finance_report["monthly"]["net"] == (
        finance_report["monthly"]["income_total"] + finance_report["monthly"]["expense_total"]
    )
    assert finance_report["cumulative"]["net"] == finance_report["monthly"]["net"]
    assert finance_report["closing_balance"] is not None


def test_game_completion_summary_exports_reopen_and_advance(db):
    from pypdf import PdfReader

    host = TestClient(app)
    player = TestClient(app)
    room, host_club, player_club = _ready_two_player_room(host, player)
    assert host.post(f"/api/rooms/{room['id']}/start", json={"year_label": "2026"}).status_code == 200

    too_early = host.post(f"/api/games/{room['game_id']}/complete")
    assert too_early.status_code == 409
    assert "july_not_resolved" in too_early.json()["detail"]["blockers"]

    season, july, _ = _prepare_completed_july(db, room)
    assert player.post(f"/api/games/{room['game_id']}/complete").status_code == 403

    completed = host.post(f"/api/games/{room['game_id']}/complete")
    assert completed.status_code == 200
    host_summary = completed.json()
    assert host_summary["viewer_scope"] == "host_all"
    assert len(host_summary["overall_results"]) == 2
    assert len(host_summary["club_reviews"]) == 2
    assert {row["final_fanbase"] for row in host_summary["overall_results"]} == {11000, 12000}
    assert {row["final_followers"] for row in host_summary["overall_results"]} == {5500, 6000}
    assert {row["final_sponsor_count"] for row in host_summary["overall_results"]} == {4, 5}

    db.expire_all()
    game = db.query(models.Game).filter(models.Game.id == room["game_id"]).one()
    stored_season = db.query(models.Season).filter(models.Season.id == season.id).one()
    assert game.status == models.GameStatus.completed
    assert stored_season.status == models.SeasonStatus.finished
    assert stored_season.is_finalized is True
    assert db.query(models.Season).filter(models.Season.game_id == room["game_id"]).count() == 1
    assert db.query(models.GameCompletion).filter(models.GameCompletion.game_id == room["game_id"]).count() == 1

    repeated = host.post(f"/api/games/{room['game_id']}/complete")
    assert repeated.status_code == 200
    assert db.query(models.GameCompletion).filter(models.GameCompletion.game_id == room["game_id"]).count() == 1

    player_summary_response = player.get(f"/api/games/{room['game_id']}/result-summary")
    assert player_summary_response.status_code == 200
    player_summary = player_summary_response.json()
    assert player_summary["viewer_scope"] == f"club:{player_club['id']}"
    assert len(player_summary["overall_results"]) == 2
    assert [row["club_id"] for row in player_summary["club_reviews"]] == [player_club["id"]]
    assert all(row["club_id"] == player_club["id"] for row in player_summary["highlights"])

    blocked_draft = player.put(
        f"/api/games/{room['game_id']}/clubs/{player_club['id']}/turn-draft",
        json={"payload": {"sales_expense": 1}},
    )
    assert blocked_draft.status_code == 409

    csv_export = player.get(f"/api/games/{room['game_id']}/result-summary/exports/csv-zip")
    assert csv_export.status_code == 200
    assert csv_export.headers["cache-control"] == "private, no-store"
    with zipfile.ZipFile(io.BytesIO(csv_export.content)) as archive:
        assert set(archive.namelist()) == {
            "manifest.csv",
            "overall_results.csv",
            "season_standings.csv",
            "season_metrics.csv",
            "decisions.csv",
            "highlights.csv",
        }
        for name in archive.namelist():
            assert archive.read(name).startswith(b"\xef\xbb\xbf")
        decisions_csv = archive.read("decisions.csv").decode("utf-8-sig")
        assert player_club["id"] in decisions_csv
        assert host_club["id"] not in decisions_csv

    pdf_export = player.get(f"/api/games/{room['game_id']}/result-summary/exports/pdf")
    assert pdf_export.status_code == 200
    assert pdf_export.headers["content-type"] == "application/pdf"
    assert pdf_export.headers["cache-control"] == "private, no-store"
    reader = PdfReader(io.BytesIO(pdf_export.content))
    assert len(reader.pages) >= 3
    assert reader.metadata.title.endswith("結果サマリー")

    assert player.post(f"/api/games/{room['game_id']}/reopen").status_code == 403
    reopened = host.post(f"/api/games/{room['game_id']}/reopen")
    assert reopened.status_code == 200
    assert host.get(f"/api/games/{room['game_id']}/result-summary").status_code == 409
    assert host.get(f"/api/games/{room['game_id']}/result-summary/exports/pdf").status_code == 409

    db.expire_all()
    completion = db.query(models.GameCompletion).filter(models.GameCompletion.game_id == room["game_id"]).one()
    assert completion.reopened_at is not None
    assert db.query(models.Season).filter(models.Season.id == season.id).one().status == models.SeasonStatus.running
    assert db.query(models.Turn).filter(models.Turn.id == july.id).one().turn_state == models.TurnState.resolved

    advanced = host.post(
        f"/api/games/{room['game_id']}/host/turn-action",
        json={"action": "advance"},
    )
    assert advanced.status_code == 200
    assert db.query(models.Season).filter(models.Season.game_id == room["game_id"]).count() == 2


def test_archived_completed_results_are_host_only(db):
    host = TestClient(app)
    player = TestClient(app)
    room, _, _ = _ready_two_player_room(host, player)
    assert host.post(f"/api/rooms/{room['id']}/start", json={"year_label": "2026"}).status_code == 200
    _prepare_completed_july(db, room)
    assert host.post(f"/api/games/{room['game_id']}/complete").status_code == 200
    assert host.post(f"/api/games/{room['game_id']}/archive").status_code == 200

    assert player.get(f"/api/games/{room['game_id']}/result-summary").status_code == 403
    assert player.get(f"/api/games/{room['game_id']}/result-summary/exports/csv-zip").status_code == 403
    assert host.get(f"/api/games/{room['game_id']}/result-summary").status_code == 200
    assert host.post(f"/api/games/{room['game_id']}/reopen").status_code == 409


def test_csv_formula_injection_is_neutralized():
    from app.services.result_exports import _csv_bytes

    content = _csv_bytes(["value"], [["=1+1"], ["+SUM(A1:A2)"], ["-2+3"], ["@cmd"]])
    decoded = content.decode("utf-8-sig")
    assert "'=1+1" in decoded
    assert "'+SUM(A1:A2)" in decoded
    assert "'-2+3" in decoded
    assert "'@cmd" in decoded


def test_optional_result_ranking_uses_competition_ranks_and_excludes_missing():
    from app.services.result_summary import _rank_optional

    rows = [
        {"value": 12},
        {"value": None},
        {"value": 20},
        {"value": 20},
    ]
    _rank_optional(rows, "value", "rank")

    assert [row["rank"] for row in rows] == [3, None, 1, 1]
