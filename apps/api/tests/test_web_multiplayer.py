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
from app.services.public_disclosure import _build_financial_summary


def _create_room(client: TestClient):
    response = client.post(
        "/api/rooms",
        json={
            "display_name": "Host",
            "room_name": "Browser League",
            "club_names": ["Tokyo", "Osaka"],
        },
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


def _save_and_commit(client: TestClient, room: dict, club: dict, payload: dict):
    saved = client.put(
        f"/api/games/{room['game_id']}/clubs/{club['id']}/turn-draft",
        json={"payload": payload},
    )
    assert saved.status_code == 200
    committed = client.post(f"/api/games/{room['game_id']}/clubs/{club['id']}/turn-commit")
    assert committed.status_code == 200


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


def test_browser_room_start_and_turn_console():
    host = TestClient(app)
    player = TestClient(app)

    room, _, player_club = _ready_two_player_room(host, player)

    start = host.post(f"/api/rooms/{room['id']}/start", json={"year_label": "2026"})
    assert start.status_code == 200

    play_state = player.get(f"/api/games/{room['game_id']}/play-state")
    assert play_state.status_code == 200
    assert play_state.json()["turn"]["state"] == "collecting"
    assert play_state.json()["self"]["club_id"] == player_club["id"]

    turn_console = player.get(f"/api/games/{room['game_id']}/clubs/{player_club['id']}/turn-console")
    assert turn_console.status_code == 200
    available = {item["key"] for item in turn_console.json()["available_inputs"]}
    assert {"sales_expense", "promo_expense", "hometown_expense"}.issubset(available)

    saved = player.put(
        f"/api/games/{room['game_id']}/clubs/{player_club['id']}/turn-draft",
        json={"payload": {"sales_expense": 1000000}},
    )
    assert saved.status_code == 200
    committed = player.post(f"/api/games/{room['game_id']}/clubs/{player_club['id']}/turn-commit")
    assert committed.status_code == 200


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
