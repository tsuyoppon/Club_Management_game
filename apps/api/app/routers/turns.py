from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db, require_role
from app.db.models import (
    Club,
    DecisionState,
    MembershipRole,
    Season,
    Turn,
    TurnAck,
    TurnDecision,
    TurnState,
)
from app.schemas import AckRequest, DecisionCommitRequest, DecisionPayload, TurnStateResponse

router = APIRouter(prefix="/turns", tags=["turns"])


def _get_turn(db: Session, turn_id: str) -> Turn:
    turn = db.query(Turn).filter(Turn.id == turn_id).first()
    if not turn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Turn not found")
    return turn


@router.get("/seasons/{season_id}/current", response_model=Optional[TurnStateResponse])
def current_turn(
    season_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    season = db.query(Season).filter(Season.id == season_id).first()
    if not season:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Season not found")
    require_role(user, db, season.game_id, MembershipRole.club_viewer)
    turn = (
        db.query(Turn)
        .filter(Turn.season_id == season_id, Turn.turn_state != TurnState.acked)
        .order_by(Turn.month_index)
        .first()
    )
    return turn


@router.post("/{turn_id}/open")
def open_turn(turn_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    turn = _get_turn(db, turn_id)
    require_role(user, db, turn.season.game_id, MembershipRole.gm)
    turn.turn_state = TurnState.collecting
    turn.opened_at = datetime.utcnow()
    db.commit()
    return {"state": turn.turn_state}


@router.post("/{turn_id}/decisions/{club_id}/commit")
def commit_decision(
    turn_id: str,
    club_id: str,
    payload: DecisionCommitRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    turn = _get_turn(db, turn_id)
    require_role(user, db, turn.season.game_id, MembershipRole.club_owner, club_id)
    decision = db.query(TurnDecision).filter(TurnDecision.turn_id == turn_id, TurnDecision.club_id == club_id).first()
    if not decision:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Decision not found")
    
    # PR6: バリデーション（オプショナル、エラーがあれば400返却）
    if payload.payload:
        from app.services.decision_validation import validate_decision_payload, parse_decision_payload
        validated = parse_decision_payload(payload.payload)
        errors = validate_decision_payload(db, turn, club_id, validated)
        if errors:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"validation_errors": errors})
        
        # PR8: 債務超過時の追加強化費禁止チェック（12月: month_index=5）
        if turn.month_index == 5:  # 12月
            additional = payload.payload.get("additional_reinforcement")
            if additional is not None:
                from decimal import Decimal
                additional_val = Decimal(str(additional))
                if additional_val > 0:
                    from app.services.bankruptcy import can_add_reinforcement
                    if not can_add_reinforcement(db, club_id):
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST, 
                            detail="債務超過クラブは追加強化費を入力できません"
                        )
    
    decision.decision_state = DecisionState.committed
    decision.committed_at = datetime.utcnow()
    decision.committed_by_user_id = user.id
    decision.payload_json = payload.payload
    db.commit()
    return {"state": decision.decision_state}


@router.post("/{turn_id}/lock")
def lock_turn(turn_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    turn = _get_turn(db, turn_id)
    require_role(user, db, turn.season.game_id, MembershipRole.gm)
    pending = (
        db.query(TurnDecision)
        .filter(TurnDecision.turn_id == turn_id, TurnDecision.decision_state != DecisionState.committed)
        .count()
    )
    if pending > 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not all decisions committed")
    turn.turn_state = TurnState.locked
    turn.locked_at = datetime.utcnow()
    db.query(TurnDecision).filter(TurnDecision.turn_id == turn_id).update({"decision_state": DecisionState.locked})
    db.commit()
    return {"state": turn.turn_state}


@router.post("/{turn_id}/resolve")
def resolve_turn(turn_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    turn = _get_turn(db, turn_id)
    require_role(user, db, turn.season.game_id, MembershipRole.gm)

    # Apply finance (Expenses & Updates)
    from app.services import finance as finance_service
    finance_service.process_turn_expenses(db, turn.season_id, turn.id)

    # Apply Match Results (PR4.5 + PR5 Attendance)
    from app.services import match_results
    match_results.process_matches_for_turn(db, turn.season_id, turn.id, turn.month_index)
    
    # Apply finance (Revenue & Snapshot)
    finance_service.finalize_turn_finance(db, turn.season_id, turn.id)

    turn.turn_state = TurnState.resolved
    turn.resolved_at = datetime.utcnow()
    db.commit()
    return {"state": turn.turn_state}


@router.post("/{turn_id}/ack")
def ack_turn(
    turn_id: str,
    payload: AckRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    turn = _get_turn(db, turn_id)
    require_role(user, db, turn.season.game_id, MembershipRole.club_viewer, payload.club_id)
    ack_record = (
        db.query(TurnAck)
        .filter(
            TurnAck.turn_id == turn_id,
            TurnAck.club_id == payload.club_id,
            TurnAck.user_id == user.id,
        )
        .first()
    )
    if not ack_record:
        ack_record = TurnAck(
            turn_id=turn_id,
            club_id=payload.club_id,
            user_id=user.id,
            ack=payload.ack,
            acked_at=datetime.utcnow(),
        )
        db.add(ack_record)
    else:
        ack_record.ack = payload.ack
        ack_record.acked_at = datetime.utcnow()
    db.commit()
    return {"ack": ack_record.ack}


@router.post("/{turn_id}/advance")
def advance_turn(turn_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    turn = _get_turn(db, turn_id)
    require_role(user, db, turn.season.game_id, MembershipRole.gm)

    clubs = db.query(Club).filter(Club.game_id == turn.season.game_id).all()
    for club in clubs:
        ack_exists = (
            db.query(TurnAck)
            .filter(TurnAck.turn_id == turn_id, TurnAck.club_id == club.id, TurnAck.ack == True)  # noqa: E712
            .count()
        )
        if ack_exists == 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not all clubs acknowledged")

    turn.turn_state = TurnState.acked
    db.commit()

    next_turn = (
        db.query(Turn)
        .filter(Turn.season_id == turn.season_id, Turn.month_index > turn.month_index)
        .order_by(Turn.month_index)
        .first()
    )
    if next_turn:
        next_turn.turn_state = TurnState.collecting
        next_turn.opened_at = datetime.utcnow()
    db.commit()
    return {"state": turn.turn_state}

