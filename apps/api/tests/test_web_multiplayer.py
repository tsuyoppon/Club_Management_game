from fastapi.testclient import TestClient

from app.main import app


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
