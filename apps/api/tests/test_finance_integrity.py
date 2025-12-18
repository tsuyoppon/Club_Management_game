import pytest
from sqlalchemy import select, func
from app.db import models
from app.services import finance

def test_finance_integrity(client, db, auth_headers):
    # 1. Setup Game, Club, Season
    resp = client.post("/api/games", json={"name": "Integrity Game"}, headers=auth_headers)
    game_id = resp.json()["id"]
    
    resp = client.post(f"/api/games/{game_id}/clubs", json={"name": "Integrity Club"}, headers=auth_headers)
    club_id = resp.json()["id"]
    
    resp = client.post(f"/api/seasons/games/{game_id}", json={"year_label": "2024"}, headers=auth_headers)
    season_id = resp.json()["id"]
    
    # Generate Fixtures
    client.post(f"/api/seasons/{season_id}/fixtures/generate", json={}, headers=auth_headers)
    
    # Setup Finance Profile
    client.put(
        f"/api/clubs/{club_id}/finance/profile",
        json={"sponsor_base_monthly": 1000, "monthly_cost": 200},
        headers=auth_headers
    )
    
    # 2. Process 2 Turns
    # Turn 1
    resp = client.get(f"/api/turns/seasons/{season_id}/current", headers=auth_headers)
    turn1_id = resp.json()["id"]
    
    client.post(f"/api/turns/{turn1_id}/open", headers=auth_headers)
    client.post(f"/api/turns/{turn1_id}/lock", headers=auth_headers)
    client.post(f"/api/turns/{turn1_id}/resolve", headers=auth_headers)
    
    # Ack Turn
    client.post(f"/api/turns/{turn1_id}/ack", json={"club_id": club_id, "ack": True}, headers=auth_headers)
    
    # Advance to Turn 2
    resp = client.post(f"/api/turns/{turn1_id}/advance", headers=auth_headers)
    assert resp.status_code == 200
    
    resp = client.get(f"/api/turns/seasons/{season_id}/current", headers=auth_headers)
    turn2_id = resp.json()["id"]
    assert turn1_id != turn2_id
    
    client.post(f"/api/turns/{turn2_id}/open", headers=auth_headers)
    client.post(f"/api/turns/{turn2_id}/lock", headers=auth_headers)
    client.post(f"/api/turns/{turn2_id}/resolve", headers=auth_headers)
    
    # Ack Turn 2
    client.post(f"/api/turns/{turn2_id}/ack", json={"club_id": club_id, "ack": True}, headers=auth_headers)
    
    # 3. Verify Integrity
    # Get all ledgers
    ledgers = db.execute(
        select(models.ClubFinancialLedger)
        .where(models.ClubFinancialLedger.club_id == club_id)
        .order_by(models.ClubFinancialLedger.created_at)
    ).scalars().all()
    
    # Get all snapshots
    snapshots = db.execute(
        select(models.ClubFinancialSnapshot)
        .where(models.ClubFinancialSnapshot.club_id == club_id)
        .order_by(models.ClubFinancialSnapshot.month_index)
    ).scalars().all()
    
    # Assertions
    # We expect 2 snapshots (one for each resolved turn)
    assert len(snapshots) == 2
    
    # Calculate expected balance from ledgers
    # Initial balance is 0
    calculated_balance = 0
    for ledger in ledgers:
        calculated_balance += ledger.amount
        
    # Check last snapshot balance
    last_snapshot = snapshots[-1]
    
    assert last_snapshot.closing_balance == calculated_balance
    
    # Also check that snapshot opening/closing logic holds
    for snap in snapshots:
        assert snap.closing_balance == snap.opening_balance + snap.income_total + snap.expense_total

