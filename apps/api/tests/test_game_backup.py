from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete

from app.db import models
from app.services.game_backup import (
    assert_table_classification,
    create_game_backup,
    latest_game_backup,
    restore_game_backup,
    verify_game_backup,
)


def _backup_graph(db):
    user = models.User(display_name="Backup Host")
    player = models.User(display_name="Backup Player")
    game = models.Game(name="Backup League", status=models.GameStatus.archived)
    db.add_all([user, player, game])
    db.flush()
    club = models.Club(game_id=game.id, name="Backup FC", short_name="BFC")
    db.add(club)
    db.flush()
    membership = models.Membership(
        game_id=game.id,
        user_id=user.id,
        role=models.MembershipRole.gm,
    )
    player_membership = models.Membership(
        game_id=game.id,
        user_id=player.id,
        role=models.MembershipRole.club_owner,
        club_id=club.id,
    )
    room = models.GameRoom(
        game_id=game.id,
        host_user_id=user.id,
        invite_code="BACKUP01",
        host_mode="dedicated",
        status="archived",
        started_at=datetime.utcnow(),
    )
    completion = models.GameCompletion(
        game_id=game.id,
        completed_by_user_id=user.id,
        completed_at=datetime.utcnow(),
        reopened_by_user_id=user.id,
        reopened_at=datetime.utcnow(),
        summary_json={"champion": "Backup FC"},
    )
    db.add_all([membership, player_membership, room, completion])
    db.flush()
    db.add_all(
        [
            models.GameRoomMember(room_id=room.id, user_id=user.id),
            models.GameRoomMember(room_id=room.id, user_id=player.id, club_id=club.id, is_ready=True),
        ]
    )
    season = models.Season(game_id=game.id, season_number=1, year_label="2026")
    db.add(season)
    db.flush()
    turn = models.Turn(
        season_id=season.id,
        month_index=1,
        month_name="Aug",
        month_number=8,
        turn_state=models.TurnState.resolved,
    )
    db.add(turn)
    db.flush()
    db.add_all(
        [
            models.TurnDecision(
                turn_id=turn.id,
                club_id=club.id,
                decision_state=models.DecisionState.locked,
                committed_by_user_id=player.id,
                payload_json={"sales_expense": 1000},
            ),
            models.TurnAck(turn_id=turn.id, club_id=club.id, user_id=player.id, ack=True),
            models.WebTurnDraft(
                turn_id=turn.id,
                club_id=club.id,
                user_id=player.id,
                payload_json={"promo_expense": 250},
            ),
            models.WebSession(
                user_id=user.id,
                token_hash="a" * 64,
                expires_at=datetime.utcnow() + timedelta(days=7),
            ),
            models.ClubFinancialProfile(
                club_id=club.id,
                sponsor_base_monthly=Decimal("100.00"),
                sponsor_per_point=Decimal("10.00"),
                monthly_cost=Decimal("50.00"),
            ),
            models.ClubFinancialLedger(
                club_id=club.id,
                turn_id=turn.id,
                kind="backup_test",
                amount=Decimal("123.45"),
                meta={"source": "test"},
            ),
        ]
    )
    db.commit()
    return game.id, [user.id, player.id]


def test_all_model_tables_are_classified_for_game_backup():
    assert_table_classification()


def test_game_backup_round_trip(db_session, tmp_path):
    game_id, user_ids = _backup_graph(db_session)

    backup = create_game_backup(db_session, game_id, tmp_path, reason="test")
    manifest = verify_game_backup(backup["archive_path"], backup["sha256"])
    assert manifest["game_id"] == str(game_id)
    assert manifest["counts"]["games"] == 1
    assert manifest["counts"]["turn_decisions"] == 1
    assert manifest["counts"]["club_financial_ledgers"] == 1
    assert manifest["counts"]["game_completions"] == 1
    assert manifest["counts"]["web_sessions"] == 1
    assert latest_game_backup(tmp_path, game_id)["backup_id"] == backup["backup_id"]

    db_session.execute(delete(models.Game).where(models.Game.id == game_id))
    db_session.execute(delete(models.User).where(models.User.id.in_(user_ids)))
    db_session.commit()

    restored = restore_game_backup(db_session, backup["archive_path"])
    db_session.commit()

    assert restored["game_id"] == str(game_id)
    restored_game = db_session.get(models.Game, game_id)
    assert restored_game.status == models.GameStatus.archived
    assert restored_game.room.status == "archived"
    assert restored_game.room.host_mode == "dedicated"
    assert db_session.query(models.TurnDecision).count() == 1
    assert db_session.query(models.ClubFinancialLedger).one().amount == Decimal("123.45")
    assert db_session.query(models.GameCompletion).one().summary_json == {"champion": "Backup FC"}
    assert db_session.query(models.WebSession).count() == 1


def test_delete_is_blocked_when_backup_storage_is_invalid(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.routers import web_multiplayer

    host = TestClient(app)
    created = host.post(
        "/api/rooms",
        json={
            "display_name": "Host",
            "room_name": "Blocked Delete",
            "club_names": ["One FC", "Two FC"],
        },
    )
    assert created.status_code == 201
    room = created.json()
    assert host.post(f"/api/games/{room['game_id']}/archive").status_code == 200

    invalid_root = tmp_path / "not-a-directory"
    invalid_root.write_text("file", encoding="utf-8")
    monkeypatch.setattr(web_multiplayer.settings, "game_backup_root", str(invalid_root))

    deleted = host.request(
        "DELETE",
        f"/api/games/{room['game_id']}",
        json={"confirm": room["invite_code"]},
    )
    assert deleted.status_code == 503

    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        assert db.get(models.Game, room["game_id"]) is not None
    finally:
        db.close()


def test_host_can_create_backup_and_unarchive():
    from fastapi.testclient import TestClient
    from app.main import app

    host = TestClient(app)
    created = host.post(
        "/api/rooms",
        json={
            "display_name": "Host",
            "room_name": "Manual Backup",
            "club_names": ["One FC", "Two FC"],
        },
    )
    assert created.status_code == 201
    room = created.json()

    backup = host.post(f"/api/games/{room['game_id']}/backups")
    assert backup.status_code == 201
    assert backup.json()["verified"] is True
    latest = host.get(f"/api/games/{room['game_id']}/backups/latest")
    assert latest.status_code == 200
    assert latest.json()["backup_id"] == backup.json()["backup_id"]

    assert host.post(f"/api/games/{room['game_id']}/archive").status_code == 200
    unarchived = host.post(f"/api/games/{room['game_id']}/unarchive")
    assert unarchived.status_code == 200
    assert unarchived.json()["status"] == "active"
    assert unarchived.json()["room_status"] == "lobby"
