import pytest
from uuid import UUID
from app.db import models
from app.db.models import StaffRole

def test_pr3_1_compliance_reinforcement(client, db, auth_headers):
    # 1. Setup
    resp = client.post("/api/games", json={"name": "PR3.1 Reinf"}, headers=auth_headers)
    game_id = resp.json()["id"]
    resp = client.post(f"/api/games/{game_id}/clubs", json={"name": "Club R"}, headers=auth_headers)
    club_id = resp.json()["id"]
    resp = client.post(f"/api/seasons/games/{game_id}", json={"year_label": "2024"}, headers=auth_headers)
    season_id = resp.json()["id"]
    client.post(f"/api/seasons/{season_id}/fixtures/generate", json={}, headers=auth_headers)
    
    # Set Annual Budget = 12M (1M/month)
    client.put(f"/api/finance/clubs/{club_id}/reinforcement", json={"annual_budget": 12000000}, headers=auth_headers)
    
    # 2. Advance to Nov (Month 4) - Before Additional
    # Turns: Aug(1), Sep(2), Oct(3), Nov(4)
    # We need to resolve turns 1, 2, 3, 4.
    
    turns = client.get(f"/api/turns/seasons/{season_id}/current", headers=auth_headers).json()
    # Just loop until we reach Nov
    # Actually, we can just get the turn by month index if we want, but API only exposes "current".
    # So we have to advance.
    
    # Helper to advance turn
    def advance_turn():
        t = client.get(f"/api/turns/seasons/{season_id}/current", headers=auth_headers).json()
        tid = t["id"]
        client.post(f"/api/turns/{tid}/open", headers=auth_headers)
        client.post(f"/api/turns/{tid}/lock", headers=auth_headers)
        client.post(f"/api/turns/{tid}/resolve", headers=auth_headers)
        client.post(f"/api/turns/{tid}/ack", json={"club_id": club_id, "ack": True}, headers=auth_headers)
        client.post(f"/api/turns/{tid}/advance", headers=auth_headers)
        return t
        
    # Aug (1)
    t1 = advance_turn()
    # Sep (2)
    t2 = advance_turn()
    # Oct (3)
    t3 = advance_turn()
    # Nov (4)
    t4 = advance_turn()
    
    # Check Nov Cost
    # Ledger for Turn 4
    ledgers = db.query(models.ClubFinancialLedger).filter(
        models.ClubFinancialLedger.turn_id == t4["id"],
        models.ClubFinancialLedger.kind == "reinforcement_cost"
    ).all()
    assert len(ledgers) == 1
    assert float(ledgers[0].amount) == -1000000.0
    
    # 3. Dec (Month 5) - Add Additional Budget
    # Current turn should be Dec
    t5_curr = client.get(f"/api/turns/seasons/{season_id}/current", headers=auth_headers).json()
    assert t5_curr["month_index"] == 5
    
    # Add 8M additional
    # Remaining months: Dec..Jul = 8 months.
    # Additional Monthly = 8M / 8 = 1M.
    # Total Monthly = 1M (Base) + 1M (Add) = 2M.
    client.put(f"/api/finance/clubs/{club_id}/reinforcement", json={"additional_budget": 8000000}, headers=auth_headers)
    
    # Resolve Dec
    t5 = advance_turn()
    
    # Check Dec Cost
    ledgers = db.query(models.ClubFinancialLedger).filter(
        models.ClubFinancialLedger.turn_id == t5["id"],
        models.ClubFinancialLedger.kind == "reinforcement_cost"
    ).all()
    assert len(ledgers) == 1
    assert float(ledgers[0].amount) == -2000000.0
    
    # 4. Jan (Month 6) - Should also be 2M
    t6 = advance_turn()
    ledgers = db.query(models.ClubFinancialLedger).filter(
        models.ClubFinancialLedger.turn_id == t6["id"],
        models.ClubFinancialLedger.kind == "reinforcement_cost"
    ).all()
    assert len(ledgers) == 1
    assert float(ledgers[0].amount) == -2000000.0

def test_pr3_1_compliance_staff(client, db, auth_headers):
    # 1. Setup
    resp = client.post("/api/games", json={"name": "PR3.1 Staff"}, headers=auth_headers)
    game_id = resp.json()["id"]
    resp = client.post(f"/api/games/{game_id}/clubs", json={"name": "Club S"}, headers=auth_headers)
    club_id = resp.json()["id"]
    resp = client.post(f"/api/seasons/games/{game_id}", json={"year_label": "2024"}, headers=auth_headers)
    season_id = resp.json()["id"]
    client.post(f"/api/seasons/{season_id}/fixtures/generate", json={}, headers=auth_headers)
    
    # Helper to advance turn
    def advance_turn():
        t = client.get(f"/api/turns/seasons/{season_id}/current", headers=auth_headers).json()
        tid = t["id"]
        client.post(f"/api/turns/{tid}/open", headers=auth_headers)
        client.post(f"/api/turns/{tid}/lock", headers=auth_headers)
        client.post(f"/api/turns/{tid}/resolve", headers=auth_headers)
        client.post(f"/api/turns/{tid}/ack", json={"club_id": club_id, "ack": True}, headers=auth_headers)
        client.post(f"/api/turns/{tid}/advance", headers=auth_headers)
        return t

    # Advance to May (Month 10)
    # Aug(1)..Apr(9) -> 9 turns
    for _ in range(9):
        advance_turn()
        
    # Current is May (10)
    t10_curr = client.get(f"/api/turns/seasons/{season_id}/current", headers=auth_headers).json()
    assert t10_curr["month_index"] == 10
    
    # 2. Fire Staff
    # Default: 1 Coach. Fire to 0? No, min 1.
    # So we need to Hire first? Or assume we started with > 1?
    # We can't change staff except in May. So we are stuck with default 1.
    # Wait, we can Hire in May, but it reflects in August.
    # If we want to test Firing, we need to have > 1 staff.
    # But we can only change in May.
    # So:
    # Year 1 May: Hire Coach -> 2.
    # Year 2 May: Fire Coach -> 1.
    
    # Let's Hire now (Year 1 May)
    client.post(
        f"/api/finance/clubs/{club_id}/staff",
        json={"role": StaffRole.coach, "new_count": 2},
        headers=auth_headers
    )
    
    # Resolve May
    t10 = advance_turn()
    
    # Check: No severance (Hiring)
    ledgers = db.query(models.ClubFinancialLedger).filter(
        models.ClubFinancialLedger.turn_id == t10["id"],
        models.ClubFinancialLedger.kind.like("staff_severance%")
    ).all()
    assert len(ledgers) == 0
    
    # Advance Jun(11), Jul(12)
    advance_turn()
    advance_turn()

    # Manually close Season 1 to avoid ambiguity in update_staff
    s1 = db.query(models.Season).filter(models.Season.id == season_id).first()
    s1.status = models.SeasonStatus.finished
    db.commit()

    # Season Finished. Create Season 2.
    resp = client.post(f"/api/seasons/games/{game_id}", json={"year_label": "2025"}, headers=auth_headers)
    season2_id = resp.json()["id"]
    client.post(f"/api/seasons/{season2_id}/fixtures/generate", json={}, headers=auth_headers)
    
    # Helper for Season 2
    def advance_turn_s2():
        t = client.get(f"/api/turns/seasons/{season2_id}/current", headers=auth_headers).json()
        tid = t["id"]
        client.post(f"/api/turns/{tid}/open", headers=auth_headers)
        client.post(f"/api/turns/{tid}/lock", headers=auth_headers)
        client.post(f"/api/turns/{tid}/resolve", headers=auth_headers)
        client.post(f"/api/turns/{tid}/ack", json={"club_id": club_id, "ack": True}, headers=auth_headers)
        client.post(f"/api/turns/{tid}/advance", headers=auth_headers)
        return t
        
    # Aug (1) of Season 2
    # Staff count should be 2 now.
    t1_s2 = advance_turn_s2()
    
    # Check Staff Cost
    # 2 Coaches + 1 Director + 1 Scout = 4 Staff.
    # Cost = 4 * 1M = 4M.
    ledgers = db.query(models.ClubFinancialLedger).filter(
        models.ClubFinancialLedger.turn_id == t1_s2["id"],
        models.ClubFinancialLedger.kind == "staff_cost"
    ).all()
    assert len(ledgers) == 1
    assert float(ledgers[0].amount) == -4000000.0
    
    # Advance to May (10) of Season 2
    # Current is Aug (1).
    # We need to reach May (10).
    # t1_s2 call advanced 1 -> 2.
    # So current is 2.
    # 2 -> 10 is 8 steps.
    for _ in range(8): # Sep..May
        advance_turn_s2()
        
    # Verify we are in May
    t_curr = client.get(f"/api/turns/seasons/{season2_id}/current", headers=auth_headers).json()
    assert t_curr["month_index"] == 10

    # Fire Coach (2 -> 1)
    resp = client.post(
        f"/api/finance/clubs/{club_id}/staff",
        json={"role": StaffRole.coach, "new_count": 1},
        headers=auth_headers
    )
    assert resp.status_code == 200
    
    # Idempotency Check: Call again with same value
    resp = client.post(
        f"/api/finance/clubs/{club_id}/staff",
        json={"role": StaffRole.coach, "new_count": 1},
        headers=auth_headers
    )
    assert resp.status_code == 200

    # Resolve May
    t10_s2 = advance_turn_s2()
    
    # Check Severance
    # Diff = 1. Salary = 12M. Factor = 0.75. Severance = 9M.
    ledgers = db.query(models.ClubFinancialLedger).filter(
        models.ClubFinancialLedger.turn_id == t10_s2["id"],
        models.ClubFinancialLedger.kind == "staff_severance_coach"
    ).all()
    assert len(ledgers) == 1
    assert float(ledgers[0].amount) == -9000000.0

def test_pr3_1_compliance_sponsor(client, db, auth_headers):
    # 1. Setup
    resp = client.post("/api/games", json={"name": "PR3.1 Sponsor"}, headers=auth_headers)
    game_id = resp.json()["id"]
    resp = client.post(f"/api/games/{game_id}/clubs", json={"name": "Club Sp"}, headers=auth_headers)
    club_id = resp.json()["id"]
    resp = client.post(f"/api/seasons/games/{game_id}", json={"year_label": "2024"}, headers=auth_headers)
    season_id = resp.json()["id"]
    client.post(f"/api/seasons/{season_id}/fixtures/generate", json={}, headers=auth_headers)
    
    # Set Sponsor Count = 10
    client.put(f"/api/finance/clubs/{club_id}/sponsors?count=10", headers=auth_headers)
    
    # Helper to advance turn
    def advance_turn():
        t = client.get(f"/api/turns/seasons/{season_id}/current", headers=auth_headers).json()
        tid = t["id"]
        client.post(f"/api/turns/{tid}/open", headers=auth_headers)
        client.post(f"/api/turns/{tid}/lock", headers=auth_headers)
        client.post(f"/api/turns/{tid}/resolve", headers=auth_headers)
        client.post(f"/api/turns/{tid}/ack", json={"club_id": club_id, "ack": True}, headers=auth_headers)
        client.post(f"/api/turns/{tid}/advance", headers=auth_headers)
        return t
        
    # Advance to July (Month 12)
    # Aug(1)..Jun(11) -> 11 turns
    for _ in range(11):
        advance_turn()
        
    # Resolve July
    # This should trigger determine_next_sponsors
    t12 = advance_turn()
    
    # Check DB for next_count
    state = db.query(models.ClubSponsorState).filter(
        models.ClubSponsorState.club_id == club_id,
        models.ClubSponsorState.season_id == season_id
    ).one()
    assert state.next_count == 10 # Should be same as count
    
    # Manually hack next_count to 20 to verify it carries over
    state.next_count = 20
    db.add(state)
    db.commit()
    
    # Create Season 2
    resp = client.post(f"/api/seasons/games/{game_id}", json={"year_label": "2025"}, headers=auth_headers)
    season2_id = resp.json()["id"]
    client.post(f"/api/seasons/{season2_id}/fixtures/generate", json={}, headers=auth_headers)
    
    # Resolve Aug (Month 1) of Season 2
    t1_s2_curr = client.get(f"/api/turns/seasons/{season2_id}/current", headers=auth_headers).json()
    tid = t1_s2_curr["id"]
    client.post(f"/api/turns/{tid}/open", headers=auth_headers)
    client.post(f"/api/turns/{tid}/lock", headers=auth_headers)
    client.post(f"/api/turns/{tid}/resolve", headers=auth_headers)
    
    # Check Revenue
    # Should be 20 * 5M = 100M
    ledgers = db.query(models.ClubFinancialLedger).filter(
        models.ClubFinancialLedger.turn_id == tid,
        models.ClubFinancialLedger.kind == "sponsor_annual"
    ).all()
    assert len(ledgers) == 1
    assert float(ledgers[0].amount) == 100000000.0
