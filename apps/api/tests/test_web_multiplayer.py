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


def test_browser_room_start_and_turn_console():
    host = TestClient(app)
    player = TestClient(app)

    room = _create_room(host)
    host_club, player_club = room["clubs"]

    host_claim = host.post(f"/api/rooms/{room['id']}/clubs/{host_club['id']}/claim")
    assert host_claim.status_code == 200
    host_ready = host.patch(f"/api/rooms/{room['id']}/memberships/me/ready", json={"ready": True})
    assert host_ready.status_code == 200

    joined = player.post(
        f"/api/rooms/{room['invite_code']}/join",
        json={"display_name": "Player"},
    )
    assert joined.status_code == 200
    player_claim = player.post(f"/api/rooms/{room['id']}/clubs/{player_club['id']}/claim")
    assert player_claim.status_code == 200
    player_ready = player.patch(f"/api/rooms/{room['id']}/memberships/me/ready", json={"ready": True})
    assert player_ready.status_code == 200

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
    room = _create_room(host)
    host_club, player_club = room["clubs"]

    host.post(f"/api/rooms/{room['id']}/clubs/{host_club['id']}/claim")
    host.patch(f"/api/rooms/{room['id']}/memberships/me/ready", json={"ready": True})
    player.post(f"/api/rooms/{room['invite_code']}/join", json={"display_name": "Player"})
    player.post(f"/api/rooms/{room['id']}/clubs/{player_club['id']}/claim")
    player.patch(f"/api/rooms/{room['id']}/memberships/me/ready", json={"ready": True})
    assert host.post(f"/api/rooms/{room['id']}/start", json={}).status_code == 200

    forbidden_console = player.get(f"/api/games/{room['game_id']}/clubs/{host_club['id']}/turn-console")
    assert forbidden_console.status_code == 403

    forbidden_host_action = player.post(
        f"/api/games/{room['game_id']}/host/turn-action",
        json={"action": "lock"},
    )
    assert forbidden_host_action.status_code == 403
