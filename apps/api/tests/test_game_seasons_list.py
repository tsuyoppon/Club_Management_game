from fastapi.testclient import TestClient

from app.main import app


def _headers(email: str):
    return {"X-User-Email": email}


def test_list_game_seasons_returns_summary():
    client = TestClient(app)
    gm_headers = _headers("gm-seasons@example.com")
    viewer_headers = _headers("viewer-seasons@example.com")

    game_resp = client.post("/api/games", json={"name": "Season Game"}, headers=gm_headers)
    assert game_resp.status_code == 200
    game_id = game_resp.json()["id"]

    club_resp = client.post(f"/api/games/{game_id}/clubs", json={"name": "Season Club"}, headers=gm_headers)
    assert club_resp.status_code == 200
    club_id = club_resp.json()["id"]

    client.post(
        f"/api/games/{game_id}/memberships",
        json={"email": "viewer-seasons@example.com", "role": "club_viewer", "club_id": club_id},
        headers=gm_headers,
    )

    season_2024 = client.post(
        f"/api/seasons/games/{game_id}", json={"year_label": "2024"}, headers=gm_headers
    )
    assert season_2024.status_code == 200
    season_2025 = client.post(
        f"/api/seasons/games/{game_id}", json={"year_label": "2025"}, headers=gm_headers
    )
    assert season_2025.status_code == 200

    response = client.get(f"/api/games/{game_id}/seasons", headers=viewer_headers)
    assert response.status_code == 200
    data = response.json()
    assert [item["season_number"] for item in data] == [2, 1]
    for item in data:
        assert item["id"]
        assert item["year_label"]
        assert item["status"]
        assert item["created_at"]


def test_list_game_seasons_requires_membership():
    client = TestClient(app)
    gm_headers = _headers("gm-no-access@example.com")
    other_headers = _headers("outsider@example.com")

    game_resp = client.post("/api/games", json={"name": "Access Game"}, headers=gm_headers)
    assert game_resp.status_code == 200
    game_id = game_resp.json()["id"]

    response = client.get(f"/api/games/{game_id}/seasons", headers=other_headers)
    assert response.status_code == 403
