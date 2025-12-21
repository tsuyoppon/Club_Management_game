import uuid

import pytest

from app.db import models
from app.db.session import SessionLocal


@pytest.fixture
def seed_basic(db):
    game = models.Game(name="Smoke Game")
    db.add(game)
    db.commit()
    db.refresh(game)

    club = models.Club(name="Smoke Club", game_id=game.id)
    db.add(club)
    db.commit()
    db.refresh(club)

    gm_user = models.User(email="gm@example.com")
    owner_user = models.User(email="owner@example.com")
    db.add_all([gm_user, owner_user])
    db.commit()
    db.refresh(gm_user)
    db.refresh(owner_user)

    gm_membership = models.Membership(game_id=game.id, user_id=gm_user.id, role=models.MembershipRole.gm)
    owner_membership = models.Membership(
        game_id=game.id,
        user_id=owner_user.id,
        role=models.MembershipRole.club_owner,
        club_id=club.id,
    )
    db.add_all([gm_membership, owner_membership])
    db.commit()

    season = models.Season(game_id=game.id, year_label="2025", status=models.SeasonStatus.running)
    db.add(season)
    db.commit()
    db.refresh(season)

    turn = models.Turn(
        season_id=season.id,
        month_index=1,
        month_name="Aug",
        month_number=8,
        turn_state=models.TurnState.collecting,
    )
    db.add(turn)
    db.commit()
    db.refresh(turn)

    decision = models.TurnDecision(
        turn_id=turn.id,
        club_id=club.id,
        decision_state=models.DecisionState.draft,
        payload_json={"sales_expense": 100},
    )
    db.add(decision)
    db.commit()

    return {
        "game": game,
        "club": club,
        "season": season,
        "turn": turn,
        "decision": decision,
        "gm_user": gm_user,
        "owner_user": owner_user,
    }


def test_staff_endpoints(client, seed_basic):
    club = seed_basic["club"]
    owner_headers = {"X-User-Email": "owner@example.com"}

    res = client.get(f"/api/clubs/{club.id}/management/staff", headers=owner_headers)
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 1

    res_hist = client.get(
        f"/api/clubs/{club.id}/management/staff/history",
        headers=owner_headers,
        params={"season_id": seed_basic["season"].id},
    )
    assert res_hist.status_code == 200
    assert res_hist.json() == []


def test_decision_endpoints(client, seed_basic):
    club = seed_basic["club"]
    season = seed_basic["season"]
    turn = seed_basic["turn"]
    owner_headers = {"X-User-Email": "owner@example.com"}

    res_current = client.get(
        f"/api/turns/seasons/{season.id}/decisions/{club.id}/current",
        headers=owner_headers,
    )
    assert res_current.status_code == 200
    body = res_current.json()
    assert body is not None
    assert body["turn_id"] == str(turn.id)
    assert body["payload"]["sales_expense"] == 100

    res_one = client.get(
        f"/api/turns/{turn.id}/decisions/{club.id}",
        headers=owner_headers,
    )
    assert res_one.status_code == 200
    assert res_one.json()["turn_id"] == str(turn.id)

    res_hist = client.get(
        f"/api/turns/seasons/{season.id}/decisions/{club.id}",
        headers=owner_headers,
        params={"from_month": 1, "to_month": 1},
    )
    assert res_hist.status_code == 200
    hist = res_hist.json()
    assert len(hist) == 1
    assert hist[0]["month_index"] == 1


def test_schedule_month_filter(client, seed_basic, db):
    season = seed_basic["season"]
    club = seed_basic["club"]
    gm_headers = {"X-User-Email": "gm@example.com"}
    owner_headers = {"X-User-Email": "owner@example.com"}

    fixture1 = models.Fixture(
        season_id=season.id,
        match_month_index=2,
        match_month_name="Sep",
        home_club_id=club.id,
    )
    fixture2 = models.Fixture(
        season_id=season.id,
        match_month_index=3,
        match_month_name="Oct",
        away_club_id=club.id,
    )
    db.add_all([fixture1, fixture2])
    db.commit()

    res_season = client.get(
        f"/api/seasons/{season.id}/schedule",
        headers=gm_headers,
        params={"month_index": 2},
    )
    assert res_season.status_code == 200
    sched = res_season.json()
    assert list(map(int, sched.keys())) == [2]

    res_club = client.get(
        f"/api/seasons/{season.id}/clubs/{club.id}/schedule",
        headers=owner_headers,
        params={"month_index": 3},
    )
    assert res_club.status_code == 200
    club_sched = res_club.json()
    assert len(club_sched) == 1
    assert club_sched[0]["month_index"] == 3