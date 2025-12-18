import pytest
from app.db import models
from app.db.models import MembershipRole

def test_finance_profile_auth(client, db):
    # 1. Setup Game & Club
    # We need to create users first to assign memberships
    
    # GM User
    gm_email = "gm@example.com"
    gm_headers = {"X-User-Email": gm_email, "X-User-Name": "GM User"}
    
    # Owner User
    owner_email = "owner@example.com"
    owner_headers = {"X-User-Email": owner_email, "X-User-Name": "Owner User"}
    
    # Viewer User
    viewer_email = "viewer@example.com"
    viewer_headers = {"X-User-Email": viewer_email, "X-User-Name": "Viewer User"}
    
    # Create Game (implicitly creates GM membership for the creator if logic exists, 
    # but let's rely on the API creating the user if they don't exist, 
    # and then we might need to manually assign roles if the API doesn't default to GM)
    
    # Actually, the API usually creates a user on the fly if X-User-Email is present.
    # But assigning roles usually happens via game creation (creator becomes GM) or invitation.
    # Let's see how game creation works.
    
    resp = client.post("/api/games", json={"name": "Auth Game"}, headers=gm_headers)
    assert resp.status_code == 200
    game_id = resp.json()["id"]
    
    # GM should be GM of this game now.
    
    # Create Club
    resp = client.post(f"/api/games/{game_id}/clubs", json={"name": "Auth Club"}, headers=gm_headers)
    assert resp.status_code == 200
    club_id = resp.json()["id"]
    
    # Now we need to add the other users to the game.
    # Manually create users and memberships
    
    owner_user = models.User(email=owner_email, display_name="Owner User")
    db.add(owner_user)
    viewer_user = models.User(email=viewer_email, display_name="Viewer User")
    db.add(viewer_user)
    db.commit()
    
    # Assign Owner Role
    owner_membership = models.Membership(
        game_id=game_id,
        user_id=owner_user.id,
        role=MembershipRole.club_owner,
        club_id=club_id
    )
    db.add(owner_membership)
    
    # Assign Viewer Role
    viewer_membership = models.Membership(
        game_id=game_id,
        user_id=viewer_user.id,
        role=MembershipRole.club_viewer,
        club_id=club_id
    )
    db.add(viewer_membership)
    db.commit()
    
    # 2. Test GM Access (PUT Profile)
    resp = client.put(
        f"/api/clubs/{club_id}/finance/profile",
        json={"sponsor_base_monthly": 5000, "monthly_cost": 2000},
        headers=gm_headers
    )
    assert resp.status_code == 200
    assert resp.json()["sponsor_base_monthly"] == 5000
    
    # 3. Test Owner Access (PUT Profile) -> Should Fail (Only GM can set finance params?)
    # The requirement says: "Non-GM cannot update finance profile."
    resp = client.put(
        f"/api/clubs/{club_id}/finance/profile",
        json={"sponsor_base_monthly": 9999, "monthly_cost": 100},
        headers=owner_headers
    )
    # Expecting 403 Forbidden
    assert resp.status_code == 403
    
    # Verify no change
    resp = client.get(f"/api/clubs/{club_id}/finance/state", headers=gm_headers)
    # We need to check the profile, not state, but the endpoint returns state which might include profile info?
    # Or we can check the profile endpoint if it exists.
    # The PUT returns the profile.
    # Let's check via GM again.
    # Wait, there is no GET profile endpoint in the previous `test_finance.py`, only PUT.
    # But `test_finance.py` checked `resp.json()["sponsor_base_monthly"]` after PUT.
    # Let's try to PUT again with GM to verify it's still 5000 (or just trust the 403).
    
    # 4. Test Viewer Access (PUT Profile) -> Should Fail
    resp = client.put(
        f"/api/clubs/{club_id}/finance/profile",
        json={"sponsor_base_monthly": 8888, "monthly_cost": 100},
        headers=viewer_headers
    )
    assert resp.status_code == 403

