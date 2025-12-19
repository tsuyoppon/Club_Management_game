import pytest
from uuid import UUID
from app.db import models
from app.services import finance

def test_finance_flow(client, db, auth_headers):
    # 1. Setup Game, Club, Season, Turn
    # Create Game
    resp = client.post("/api/games", json={"name": "Finance Test Game"}, headers=auth_headers)
    assert resp.status_code == 200
    game_id = resp.json()["id"]
    
    # Create Club
    resp = client.post(f"/api/games/{game_id}/clubs", json={"name": "Rich Club"}, headers=auth_headers)
    assert resp.status_code == 200
    club_id = resp.json()["id"]
    
    # Create Season
    resp = client.post(f"/api/seasons/games/{game_id}", json={"year_label": "2024"}, headers=auth_headers)
    assert resp.status_code == 200
    season_id = resp.json()["id"]
    
    # Generate Fixtures (creates turns)
    resp = client.post(f"/api/seasons/{season_id}/fixtures/generate", json={}, headers=auth_headers)
    assert resp.status_code == 201
    
    # Get Current Turn
    resp = client.get(f"/api/turns/seasons/{season_id}/current", headers=auth_headers)
    assert resp.status_code == 200
    turn_id = resp.json()["id"]
    
    # 2. Setup Finance Profile
    # Default should be 0
    resp = client.get(f"/api/clubs/{club_id}/finance/state", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["balance"] == 0
    
    # Update Profile
    resp = client.put(
        f"/api/clubs/{club_id}/finance/profile",
        json={"sponsor_base_monthly": 1000, "monthly_cost": 200},
        headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["sponsor_base_monthly"] == 1000
    
    # 3. Resolve Turn (Trigger Finance)
    # Open
    client.post(f"/api/turns/{turn_id}/open", headers=auth_headers)
    # Lock
    client.post(f"/api/turns/{turn_id}/lock", headers=auth_headers)
    
    # Resolve
    resp = client.post(f"/api/turns/{turn_id}/resolve", headers=auth_headers)
    assert resp.status_code == 200
    
    # 4. Verify State & Snapshot
    resp = client.get(f"/api/clubs/{club_id}/finance/state", headers=auth_headers)
    assert resp.status_code == 200
    # Balance = 0 + 1000 (Base Sponsor) - 200 (Base Cost) - 3,000,000 (Default Staff Cost) = -2,999,200
    assert resp.json()["balance"] == -2999200.0
    assert resp.json()["last_applied_turn_id"] == turn_id
    
    resp = client.get(f"/api/clubs/{club_id}/finance/snapshots?season_id={season_id}", headers=auth_headers)
    assert resp.status_code == 200
    snapshots = resp.json()
    assert len(snapshots) == 1
    assert snapshots[0]["closing_balance"] == -2999200.0
    assert snapshots[0]["income_total"] == 1000
    assert snapshots[0]["expense_total"] == -3000200.0
    
    # 5. Idempotency Check
    # Call apply_finance_for_turn again manually
    finance.apply_finance_for_turn(db, UUID(season_id), UUID(turn_id))
    
    # Balance should still be -2999200.0
    state = finance.get_financial_state(db, UUID(club_id))
    assert state.balance == -2999200.0
