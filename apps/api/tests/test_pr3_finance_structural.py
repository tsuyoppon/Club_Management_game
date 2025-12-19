import pytest
from app.db import models
from app.db.models import StaffRole

def test_pr3_structural_finance(client, db, auth_headers):
    # 1. Setup Game, Club, Season
    resp = client.post("/api/games", json={"name": "PR3 Game"}, headers=auth_headers)
    game_id = resp.json()["id"]
    
    resp = client.post(f"/api/games/{game_id}/clubs", json={"name": "PR3 Club"}, headers=auth_headers)
    club_id = resp.json()["id"]
    
    resp = client.post(f"/api/seasons/games/{game_id}", json={"year_label": "2024"}, headers=auth_headers)
    season_id = resp.json()["id"]
    
    # Generate Fixtures (creates turns)
    client.post(f"/api/seasons/{season_id}/fixtures/generate", json={}, headers=auth_headers)
    
    # 2. Setup Structural Elements
    # A. Sponsors (Set count=10 -> 50M revenue expected in Aug)
    client.put(f"/api/finance/clubs/{club_id}/sponsors?count=10", headers=auth_headers)
    
    # B. Reinforcement (Annual=12M -> 1M/month)
    client.put(f"/api/finance/clubs/{club_id}/reinforcement", json={"annual_budget": 12000000}, headers=auth_headers)
    
    # C. Staff (Default 1 each, let's keep default)
    # Default: 3 roles * 1 person * 1M = 3M/month?
    # Need to check default salary in service. I set it to 1,000,000.
    # So 3M/month.
    
    # 3. Process Turn 1 (August - Month 1)
    resp = client.get(f"/api/turns/seasons/{season_id}/current", headers=auth_headers)
    turn1_id = resp.json()["id"]
    
    client.post(f"/api/turns/{turn1_id}/open", headers=auth_headers)
    client.post(f"/api/turns/{turn1_id}/lock", headers=auth_headers)
    client.post(f"/api/turns/{turn1_id}/resolve", headers=auth_headers)
    
    # Verify Ledger for Turn 1
    # Expected:
    # - Sponsor Revenue: 10 * 5M = 50M (Positive)
    # - Reinforcement: -1M (Negative)
    # - Staff: -3M (Negative)
    # - Base Sponsor/Cost (PR2): 0 (Default)
    
    state = client.get(f"/api/clubs/{club_id}/finance/state", headers=auth_headers).json()
    # Balance = 50M - 1M - 3M = 46M
    assert state["balance"] == 46000000
    
    # 4. Process Turn 2 (September - Month 2)
    client.post(f"/api/turns/{turn1_id}/ack", json={"club_id": club_id, "ack": True}, headers=auth_headers)
    client.post(f"/api/turns/{turn1_id}/advance", headers=auth_headers)
    
    resp = client.get(f"/api/turns/seasons/{season_id}/current", headers=auth_headers)
    turn2_id = resp.json()["id"]
    
    client.post(f"/api/turns/{turn2_id}/open", headers=auth_headers)
    client.post(f"/api/turns/{turn2_id}/lock", headers=auth_headers)
    client.post(f"/api/turns/{turn2_id}/resolve", headers=auth_headers)
    
    # Verify Ledger for Turn 2
    # Expected:
    # - Sponsor Revenue: 0 (Only in Aug)
    # - Reinforcement: -1M
    # - Staff: -3M
    # Total Change: -4M
    # Balance = 46M - 4M = 42M
    
    state = client.get(f"/api/clubs/{club_id}/finance/state", headers=auth_headers).json()
    assert state["balance"] == 42000000
    
    # 5. Test Staff Change Constraint (Try in Sep -> Fail)
    resp = client.post(
        f"/api/finance/clubs/{club_id}/staff",
        json={"role": StaffRole.coach, "new_count": 2},
        headers=auth_headers
    )
    assert resp.status_code == 400 # Only May
    
    # 6. Test Additional Reinforcement (Mid-season)
    # Add 8M additional.
    # If applied in Sep (Month 2), remaining months = 12 - 2 + 1 = 11?
    # Wait, my logic in service assumed "Dec (Month 5)" start for additional.
    # So adding it now shouldn't affect Sep cost if logic holds.
    client.put(f"/api/finance/clubs/{club_id}/reinforcement", json={"additional_budget": 8000000}, headers=auth_headers)
    
    # Re-resolve Turn 2 (Idempotency check)
    client.post(f"/api/turns/{turn2_id}/resolve", headers=auth_headers)
    state = client.get(f"/api/clubs/{club_id}/finance/state", headers=auth_headers).json()
    assert state["balance"] == 42000000 # Unchanged
