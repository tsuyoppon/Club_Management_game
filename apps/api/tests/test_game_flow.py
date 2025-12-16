import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.services.fixtures import generate_round_robin


def _headers(email: str):
    return {"X-User-Email": email}


def test_game_club_season_schedule_flow():
    client = TestClient(app)
    gm_headers = _headers("gm@example.com")

    game_resp = client.post("/api/games", json={"name": "Test Game"}, headers=gm_headers)
    assert game_resp.status_code == 200
    game_id = game_resp.json()["id"]

    club_ids = []
    for idx in range(3):
        club_resp = client.post(
            f"/api/games/{game_id}/clubs", json={"name": f"Club {idx}"}, headers=gm_headers
        )
        assert club_resp.status_code == 200
        club_ids.append(club_resp.json()["id"])

    season_resp = client.post(f"/api/seasons/games/{game_id}", json={"year_label": "2025"}, headers=gm_headers)
    assert season_resp.status_code == 200
    season_id = season_resp.json()["id"]

    fixtures_resp = client.post(f"/api/seasons/{season_id}/fixtures/generate", json={}, headers=gm_headers)
    assert fixtures_resp.status_code == 201

    schedule_resp = client.get(
        f"/api/seasons/{season_id}/clubs/{club_ids[0]}/schedule",
        headers=gm_headers,
    )
    assert schedule_resp.status_code == 200
    schedule = schedule_resp.json()
    assert len(schedule) == 10
    assert any(item["is_bye"] for item in schedule)


def test_fixture_fairness_counts():
    for club_count in [2, 3, 4, 5]:
        ids = [uuid.uuid4() for _ in range(club_count)]
        specs = generate_round_robin(ids, match_months=10)
        assert len({s.match_month_index for s in specs}) == 10

        home_counts = {cid: 0 for cid in ids}
        bye_counts = {cid: 0 for cid in ids}
        for spec in specs:
            if spec.is_bye and spec.bye_club_id:
                bye_counts[spec.bye_club_id] += 1
            elif spec.home_club_id is not None:
                home_counts[spec.home_club_id] += 1

        if club_count % 2 == 1:
            max_bye = max(bye_counts.values())
            min_bye = min(bye_counts.values())
            assert max_bye - min_bye <= 1
        max_home = max(home_counts.values())
        min_home = min(home_counts.values())
        assert max_home - min_home <= 1


def test_viewer_cannot_commit():
    client = TestClient(app)
    gm_headers = _headers("gm2@example.com")
    viewer_headers = _headers("viewer@example.com")

    game_resp = client.post("/api/games", json={"name": "Role Game"}, headers=gm_headers)
    game_id = game_resp.json()["id"]

    club_resp = client.post(f"/api/games/{game_id}/clubs", json={"name": "Viewer Club"}, headers=gm_headers)
    club_id = club_resp.json()["id"]

    season_resp = client.post(f"/api/seasons/games/{game_id}", json={"year_label": "2026"}, headers=gm_headers)
    season_id = season_resp.json()["id"]

    client.post(
        f"/api/games/{game_id}/memberships",
        json={"email": "viewer@example.com", "role": "club_viewer", "club_id": club_id},
        headers=gm_headers,
    )

    current_turn_resp = client.get(f"/api/turns/seasons/{season_id}/current", headers=viewer_headers)
    assert current_turn_resp.status_code == 200
    turn_id = current_turn_resp.json()["id"]

    commit_resp = client.post(
        f"/api/turns/{turn_id}/decisions/{club_id}/commit",
        json={"payload": {"foo": "bar"}},
        headers=viewer_headers,
    )
    assert commit_resp.status_code == 403

