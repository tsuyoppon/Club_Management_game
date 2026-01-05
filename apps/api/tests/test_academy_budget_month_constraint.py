from app.db import models


def _process_turn(client, auth_headers, turn_id, club_id):
    client.post(f"/api/turns/{turn_id}/open", headers=auth_headers)
    client.post(f"/api/turns/{turn_id}/lock", headers=auth_headers)
    client.post(f"/api/turns/{turn_id}/resolve", headers=auth_headers)
    client.post(
        f"/api/turns/{turn_id}/ack",
        json={"club_id": club_id, "ack": True},
        headers=auth_headers,
    )
    client.post(f"/api/turns/{turn_id}/advance", headers=auth_headers)


def _setup_game_season(client, auth_headers):
    resp = client.post("/api/games", json={"name": "Academy Budget Game"}, headers=auth_headers)
    game_id = resp.json()["id"]

    resp = client.post(f"/api/games/{game_id}/clubs", json={"name": "Academy Club"}, headers=auth_headers)
    club_id = resp.json()["id"]

    resp = client.post(f"/api/seasons/games/{game_id}", json={"year_label": "2024"}, headers=auth_headers)
    season_id = resp.json()["id"]

    return game_id, club_id, season_id


def test_academy_budget_rejected_outside_may(client, auth_headers):
    _, club_id, season_id = _setup_game_season(client, auth_headers)

    resp = client.get(f"/api/turns/seasons/{season_id}/current", headers=auth_headers)
    assert resp.json()["month_index"] == 1

    resp = client.post(
        f"/api/clubs/{club_id}/management/academy/budget",
        params={"season_id": season_id},
        json={"annual_budget": 12000000},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "academy_budget is only allowed in May (month_index=10)"


def test_academy_budget_allowed_in_may(client, db, auth_headers):
    _, club_id, season_id = _setup_game_season(client, auth_headers)

    client.post(f"/api/seasons/{season_id}/fixtures/generate", json={}, headers=auth_headers)

    for _ in range(9):
        resp = client.get(f"/api/turns/seasons/{season_id}/current", headers=auth_headers)
        turn_id = resp.json()["id"]
        _process_turn(client, auth_headers, turn_id, club_id)

    resp = client.get(f"/api/turns/seasons/{season_id}/current", headers=auth_headers)
    assert resp.json()["month_index"] == 10

    resp = client.post(
        f"/api/clubs/{club_id}/management/academy/budget",
        params={"season_id": season_id},
        json={"annual_budget": 12000000},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    state = db.query(models.ClubAcademy).filter(
        models.ClubAcademy.club_id == club_id,
        models.ClubAcademy.season_id == season_id,
    ).one()
    assert {"next_budget": 12000000} in (state.transfer_fee_history or [])
