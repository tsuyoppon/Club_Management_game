from app.db import models
from app.services import public_disclosure


def _seed_season(db, *, season_number=1, year_label="2026"):
    game = models.Game(name=f"Estimate Game {season_number}")
    db.add(game)
    db.flush()

    club = models.Club(name="Tokyo", game_id=game.id)
    db.add(club)
    db.flush()

    season = models.Season(
        game_id=game.id,
        year_label=year_label,
        season_number=season_number,
        status=models.SeasonStatus.running,
    )
    db.add(season)
    db.flush()
    return game, club, season


def _add_turn_with_decision(db, season, club, month_index, state, payload):
    turn = models.Turn(
        season_id=season.id,
        month_index=month_index,
        month_name=str(month_index),
        month_number=((month_index + 6) % 12) + 1,
        turn_state=state,
    )
    db.add(turn)
    db.flush()
    db.add(
        models.TurnDecision(
            turn_id=turn.id,
            club_id=club.id,
            decision_state=models.DecisionState.locked,
            payload_json=payload,
        )
    )
    db.flush()
    return turn


def test_june_reinforcement_estimate_is_visible_until_july_resolve(
    client, db, monkeypatch
):
    _game, club, season = _seed_season(db)
    june = _add_turn_with_decision(
        db,
        season,
        club,
        11,
        models.TurnState.resolved,
        {"reinforcement_budget": 100_000_000},
    )
    july = _add_turn_with_decision(
        db, season, club, 12, models.TurnState.collecting, {}
    )
    monkeypatch.setattr(public_disclosure.random, "uniform", lambda _low, _high: 1.1)
    monkeypatch.setattr(
        public_disclosure,
        "get_all_clubs_team_power_for_monthly_input",
        lambda *_args, **_kwargs: [
            {
                "club_id": str(club.id),
                "club_name": club.name,
                "team_power": 11.0,
                "actual_team_power": 10.5,
            }
        ],
    )

    public_disclosure.publish_team_power_june_preview(db, season.id, june.id)
    db.commit()

    visible = client.get(f"/api/seasons/{season.id}/team-power").json()
    club_row = visible["disclosed_data"]["clubs"][0]
    assert club_row["estimated_reinforcement_budget"] == 110_000_000
    assert club_row["estimated_reinforcement_budget"] != 100_000_000
    assert club_row["reinforcement_estimate_label"] == "来期強化費（概算）"

    july.turn_state = models.TurnState.resolved
    db.commit()

    assert client.get(f"/api/seasons/{season.id}/team-power").status_code == 404


def test_december_additional_reinforcement_estimate_expires_after_january_resolve(
    client, db, monkeypatch
):
    _game, club, season = _seed_season(db)
    december = _add_turn_with_decision(
        db,
        season,
        club,
        5,
        models.TurnState.resolved,
        {"additional_reinforcement": 50_000_000},
    )
    january = _add_turn_with_decision(
        db, season, club, 6, models.TurnState.collecting, {}
    )
    monkeypatch.setattr(public_disclosure.random, "uniform", lambda _low, _high: 1.1)
    monkeypatch.setattr(
        public_disclosure,
        "get_all_clubs_team_power",
        lambda *_args, **_kwargs: [
            {"club_id": str(club.id), "club_name": club.name, "team_power": 10.0}
        ],
    )

    public_disclosure.publish_team_power_december(db, season.id, december.id)
    db.commit()

    visible = client.get(f"/api/seasons/{season.id}/team-power").json()
    club_row = visible["disclosed_data"]["clubs"][0]
    assert club_row["estimated_reinforcement_budget"] == 55_000_000
    assert club_row["estimated_reinforcement_budget"] != 50_000_000
    assert club_row["reinforcement_estimate_label"] == "追加強化費（概算）"

    january.turn_state = models.TurnState.resolved
    db.commit()

    expired = client.get(f"/api/seasons/{season.id}/team-power").json()
    assert "estimated_reinforcement_budget" not in expired["disclosed_data"]["clubs"][0]
    assert "reinforcement_estimate_label" not in expired["disclosed_data"]["clubs"][0]

    expired_direct = client.get(
        f"/api/seasons/{season.id}/disclosures/team_power_december"
    ).json()
    assert (
        "estimated_reinforcement_budget"
        not in expired_direct["disclosed_data"]["clubs"][0]
    )

    expired_all = client.get(f"/api/seasons/{season.id}/disclosures").json()
    team_power_disclosure = next(
        row for row in expired_all if row["disclosure_type"] == "team_power_december"
    )
    assert (
        "estimated_reinforcement_budget"
        not in team_power_disclosure["disclosed_data"]["clubs"][0]
    )


def test_july_reinforcement_estimate_carries_until_next_august_resolve(
    client, db, monkeypatch
):
    game, club, old_season = _seed_season(db)
    july = _add_turn_with_decision(
        db,
        old_season,
        club,
        12,
        models.TurnState.resolved,
        {"reinforcement_budget": 100_000_000},
    )
    new_season = models.Season(
        game_id=game.id,
        year_label="2027",
        season_number=2,
        status=models.SeasonStatus.running,
    )
    db.add(new_season)
    db.flush()
    august = _add_turn_with_decision(
        db, new_season, club, 1, models.TurnState.collecting, {}
    )
    monkeypatch.setattr(public_disclosure.random, "uniform", lambda _low, _high: 0.9)
    monkeypatch.setattr(
        public_disclosure,
        "get_all_clubs_team_power_for_july",
        lambda *_args, **_kwargs: [
            {
                "club_id": str(club.id),
                "club_name": club.name,
                "team_power": 12.0,
                "actual_team_power": 12.5,
            }
        ],
    )

    public_disclosure.publish_team_power_july(db, old_season.id, july.id)
    public_disclosure.copy_team_power_july_to_new_season(
        db, old_season.id, new_season.id
    )
    db.commit()

    visible = client.get(f"/api/seasons/{new_season.id}/team-power").json()
    club_row = visible["disclosed_data"]["clubs"][0]
    assert club_row["estimated_reinforcement_budget"] == 90_000_000
    assert club_row["reinforcement_estimate_label"] == "来期強化費（概算）"

    august.turn_state = models.TurnState.resolved
    db.commit()

    expired = client.get(f"/api/seasons/{new_season.id}/team-power").json()
    assert "estimated_reinforcement_budget" not in expired["disclosed_data"]["clubs"][0]
