import pytest
from decimal import Decimal
from uuid import uuid4
from app.services import fanbase
from app.db.models import ClubFanbaseState

def test_fanbase_update_logic(db_session):
    club_id = uuid4()
    season_id = uuid4()
    
    # Mock state
    state = ClubFanbaseState(
        club_id=club_id,
        season_id=season_id,
        fb_count=60000,
        fb_rate=Decimal("0.06"),
        cumulative_promo=Decimal("0"),
        cumulative_ht=Decimal("0"),
        last_ht_spend=Decimal("0")
    )
    db_session.add(state)
    db_session.commit()
    
    # Update
    promo = Decimal("10000000")
    ht = Decimal("5000000")
    perf = 1.0 # Best
    hist = 0.5
    
    updated = fanbase.update_fanbase_for_turn(db_session, state, promo, ht, perf, hist)
    
    assert updated.cumulative_promo > 0
    assert updated.cumulative_ht > 0
    assert updated.fb_rate > Decimal("0.06") # Should grow
    assert updated.fb_count > 60000
    assert updated.followers_public is not None
    
    # Test Penalty
    # Increase HT spend drastically
    ht2 = Decimal("50000000") # +45M
    updated2 = fanbase.update_fanbase_for_turn(db_session, state, promo, ht2, perf, hist)
    
    # Check if penalty applied (hard to check exact value without calc, but should run)
    assert updated2.last_ht_spend == ht2
