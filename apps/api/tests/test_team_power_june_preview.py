import math

from app.db import models
from app.services import public_disclosure


def _seed_june_preview_game(db):
    game = models.Game(name="June Preview Game")
    db.add(game)
    db.flush()

    tokyo = models.Club(name="Tokyo", game_id=game.id)
    osaka = models.Club(name="Osaka", game_id=game.id)
    db.add_all([tokyo, osaka])
    db.flush()

    season = models.Season(
        game_id=game.id,
        year_label="2026",
        season_number=1,
        status=models.SeasonStatus.running,
    )
    db.add(season)
    db.flush()

    june_turn = models.Turn(
        season_id=season.id,
        month_index=11,
        month_name="Jun",
        month_number=6,
        turn_state=models.TurnState.resolved,
    )
    july_turn = models.Turn(
        season_id=season.id,
        month_index=12,
        month_name="Jul",
        month_number=7,
        turn_state=models.TurnState.collecting,
    )
    db.add_all([june_turn, july_turn])
    db.flush()

    db.add_all([
        models.TurnDecision(
            turn_id=june_turn.id,
            club_id=tokyo.id,
            decision_state=models.DecisionState.locked,
            payload_json={"reinforcement_budget": 100_000_000},
        ),
        models.TurnDecision(
            turn_id=june_turn.id,
            club_id=osaka.id,
            decision_state=models.DecisionState.locked,
            payload_json={"reinforcement_budget": 0},
        ),
    ])
    db.flush()
    return season, june_turn, july_turn, tokyo, osaka


def test_team_power_endpoint_returns_june_preview_only_until_july_resolve(client, db, monkeypatch):
    monkeypatch.setattr("app.services.team_power.random.gauss", lambda _mu, _sigma: 0)
    season, june_turn, july_turn, tokyo, _osaka = _seed_june_preview_game(db)

    public_disclosure.publish_team_power_june_preview(db, season.id, june_turn.id)
    db.commit()

    response = client.get(f"/api/seasons/{season.id}/team-power")

    assert response.status_code == 200
    payload = response.json()
    assert payload["disclosure_type"] == "team_power_june_preview"
    assert payload["disclosed_data"]["disclosure_type"] == "team_power_june_preview"
    assert payload["disclosed_data"]["clubs"][0]["club_id"] == str(tokyo.id)
    assert payload["disclosed_data"]["clubs"][0]["team_power"] == round(10 * math.log(2), 2)

    july_turn.turn_state = models.TurnState.resolved
    db.add(july_turn)
    db.commit()

    hidden_response = client.get(f"/api/seasons/{season.id}/team-power")

    assert hidden_response.status_code == 404
