from datetime import datetime, timedelta
from decimal import Decimal
import secrets
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import models
from app.dependencies import get_db, get_web_current_user, hash_session_token
from app.routers import turns as turn_routes
from app.routers.seasons import _latest_running_season, create_season_core, generate_fixtures_core
from app.schemas import AckRequest, DecisionCommitRequest
from app.services.decision_validation import (
    get_available_actions,
    get_available_inputs,
    parse_decision_payload,
    validate_decision_payload,
)
from app.services.standings import StandingsCalculator
from app.services import academy as academy_service
from app.services import finance as finance_service
from app.services import staff as staff_service


router = APIRouter(tags=["web-multiplayer"])
settings = get_settings()

DECISION_LABELS = {
    "sales_expense": "営業費",
    "promo_expense": "プロモーション費",
    "hometown_expense": "ホームタウン活動費",
    "next_home_promo": "翌月ホーム向けプロモ",
    "additional_reinforcement": "追加強化費",
    "reinforcement_budget": "翌シーズン強化費",
    "sales_allocation_new": "新規スポンサー営業配分",
}

FINANCE_LABELS = {
    "academy_cost": "アカデミー費",
    "academy_transfer_fee": "アカデミー移籍金収入",
    "admin_cost": "管理運営費",
    "distribution_revenue": "配分金収入",
    "hometown_expense": "ホームタウン活動費",
    "match_operation_cost": "試合運営費",
    "merchandise_cost": "物販原価",
    "merchandise_revenue": "物販収入",
    "next_home_promo_expense": "翌月ホーム向けプロモ費",
    "prize_revenue": "賞金収入",
    "promo_expense": "プロモーション費",
    "reinforcement_cost": "強化費",
    "sales_expense": "営業費",
    "sponsor": "月次スポンサー収入",
    "sponsor_annual": "年間スポンサー収入",
    "staff_cost": "スタッフ人件費",
    "tax": "税金",
}


class RoomCreate(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=80)
    room_name: str = Field(..., min_length=1, max_length=120)
    club_names: list[str] = Field(default_factory=list)


class RoomJoin(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=80)


class ReadyUpdate(BaseModel):
    ready: bool = True


class RoomStart(BaseModel):
    year_label: Optional[str] = None


class TurnDraftUpdate(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class HostTurnAction(BaseModel):
    action: str


class WebStaffPlan(BaseModel):
    role: str
    count: int = Field(..., ge=1)


class WebAcademyBudget(BaseModel):
    annual_budget: int = Field(..., ge=0)


def _not_found(detail: str):
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _room_or_404(db: Session, room_id: UUID) -> models.GameRoom:
    room = db.query(models.GameRoom).filter(models.GameRoom.id == room_id).first()
    if not room:
        _not_found("Room not found")
    return room


def _room_for_game_or_404(db: Session, game_id: UUID) -> models.GameRoom:
    room = db.query(models.GameRoom).filter(models.GameRoom.game_id == game_id).first()
    if not room:
        _not_found("Game room not found")
    return room


def _room_member(db: Session, room: models.GameRoom, user: models.User) -> models.GameRoomMember:
    member = (
        db.query(models.GameRoomMember)
        .filter(models.GameRoomMember.room_id == room.id, models.GameRoomMember.user_id == user.id)
        .first()
    )
    if not member:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not in this room")
    return member


def _require_host(room: models.GameRoom, user: models.User):
    if room.host_user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Host role required")


def _set_browser_session(response: Response, db: Session, user: models.User):
    raw_token = secrets.token_urlsafe(40)
    expires_at = datetime.utcnow() + timedelta(days=settings.web_session_ttl_days)
    db.add(
        models.WebSession(
            user_id=user.id,
            token_hash=hash_session_token(raw_token),
            expires_at=expires_at,
        )
    )
    response.set_cookie(
        settings.web_session_cookie,
        raw_token,
        httponly=True,
        secure=settings.web_cookie_secure,
        samesite="lax",
        max_age=settings.web_session_ttl_days * 24 * 60 * 60,
        path="/",
    )


def _invite_code(db: Session) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    for _ in range(12):
        code = "".join(secrets.choice(alphabet) for _ in range(8))
        if not db.query(models.GameRoom).filter(models.GameRoom.invite_code == code).first():
            return code
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Unable to allocate invite code")


def _serialize_room(db: Session, room: models.GameRoom, viewer: models.User) -> dict[str, Any]:
    clubs = db.query(models.Club).filter(models.Club.game_id == room.game_id).order_by(models.Club.created_at).all()
    members = db.query(models.GameRoomMember).filter(models.GameRoomMember.room_id == room.id).all()
    member_by_club = {member.club_id: member for member in members if member.club_id}
    viewer_member = next((member for member in members if member.user_id == viewer.id), None)
    return {
        "id": str(room.id),
        "game_id": str(room.game_id),
        "status": room.status,
        "invite_code": room.invite_code,
        "is_host": room.host_user_id == viewer.id,
        "self": {
            "user_id": str(viewer.id),
            "display_name": viewer.display_name,
            "club_id": str(viewer_member.club_id) if viewer_member and viewer_member.club_id else None,
            "ready": bool(viewer_member.is_ready) if viewer_member else False,
        },
        "clubs": [
            {
                "id": str(club.id),
                "name": club.name,
                "short_name": club.short_name,
                "claimed_by": str(member.user_id) if (member := member_by_club.get(club.id)) else None,
                "claimed_by_name": member.user.display_name if member else None,
                "ready": bool(member.is_ready) if member else False,
            }
            for club in clubs
        ],
        "members": [
            {
                "id": str(member.id),
                "user_id": str(member.user_id),
                "display_name": member.user.display_name,
                "club_id": str(member.club_id) if member.club_id else None,
                "ready": bool(member.is_ready),
                "is_host": member.user_id == room.host_user_id,
            }
            for member in members
        ],
    }


def _finance_label(kind: str) -> str:
    if kind.startswith("ticket_rev_"):
        return "チケット収入"
    if kind.startswith("merchandise_rev_"):
        return "物販収入"
    if kind.startswith("merchandise_cost_"):
        return "物販原価"
    if kind.startswith("match_operation_cost_"):
        return "試合運営費"
    if kind.startswith("staff_severance_"):
        return "スタッフ退職金"
    return FINANCE_LABELS.get(kind, kind)


def _statement_from_ledgers(ledgers: list[models.ClubFinancialLedger]) -> dict[str, Any]:
    grouped: dict[str, dict[str, Any]] = {}
    for ledger in ledgers:
        amount = float(ledger.amount)
        if amount == 0:
            continue
        item = grouped.setdefault(
            ledger.kind,
            {"kind": ledger.kind, "label": _finance_label(ledger.kind), "amount": 0.0},
        )
        item["amount"] += amount

    items = sorted(grouped.values(), key=lambda item: (item["amount"] < 0, item["label"]))
    income = [item for item in items if item["amount"] > 0]
    expenses = [item for item in items if item["amount"] < 0]
    income_total = sum(item["amount"] for item in income)
    expense_total = sum(item["amount"] for item in expenses)
    return {
        "income": income,
        "expenses": expenses,
        "income_total": income_total,
        "expense_total": expense_total,
        "net": income_total + expense_total,
    }


def _finance_report(
    db: Session,
    club_id: UUID,
    season: models.Season,
    snapshot: Optional[models.ClubFinancialSnapshot],
) -> dict[str, Any]:
    if not snapshot:
        return {
            "period": {
                "season_number": season.season_number,
                "year_label": season.year_label,
                "month_index": None,
                "month_name": None,
            },
            "monthly": _statement_from_ledgers([]),
            "cumulative": _statement_from_ledgers([]),
            "opening_balance": None,
            "closing_balance": None,
        }

    month_lookup = {index: name for index, name, _ in models.month_mappings()}
    monthly_ledgers = (
        db.query(models.ClubFinancialLedger)
        .filter(
            models.ClubFinancialLedger.club_id == club_id,
            models.ClubFinancialLedger.turn_id == snapshot.turn_id,
        )
        .all()
    )
    cumulative_ledgers = (
        db.query(models.ClubFinancialLedger)
        .join(models.Turn, models.Turn.id == models.ClubFinancialLedger.turn_id)
        .filter(
            models.ClubFinancialLedger.club_id == club_id,
            models.Turn.season_id == season.id,
            models.Turn.month_index <= snapshot.month_index,
        )
        .all()
    )
    return {
        "period": {
            "season_number": season.season_number,
            "year_label": season.year_label,
            "month_index": snapshot.month_index,
            "month_name": month_lookup.get(snapshot.month_index),
        },
        "monthly": _statement_from_ledgers(monthly_ledgers),
        "cumulative": _statement_from_ledgers(cumulative_ledgers),
        "opening_balance": float(snapshot.opening_balance),
        "closing_balance": float(snapshot.closing_balance),
    }


def _current_turn(db: Session, season: Optional[models.Season]) -> Optional[models.Turn]:
    if not season:
        return None
    return (
        db.query(models.Turn)
        .filter(models.Turn.season_id == season.id, models.Turn.turn_state != models.TurnState.acked)
        .order_by(models.Turn.month_index)
        .first()
    )


def _web_club_access(
    db: Session,
    room: models.GameRoom,
    user: models.User,
    club_id: UUID,
) -> tuple[models.GameRoomMember, models.Club]:
    member = _room_member(db, room, user)
    club = db.query(models.Club).filter(models.Club.id == club_id, models.Club.game_id == room.game_id).first()
    if not club:
        _not_found("Club not found")
    if member.club_id != club.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the claimed club is private")
    return member, club


def _turn_label(turn: Optional[models.Turn]) -> Optional[dict[str, Any]]:
    if not turn:
        return None
    return {
        "id": str(turn.id),
        "season_id": str(turn.season_id),
        "season_number": turn.season_number,
        "month_index": turn.month_index,
        "month_name": turn.month_name,
        "state": turn.turn_state.value,
    }


@router.post("/rooms", status_code=status.HTTP_201_CREATED)
def create_room(payload: RoomCreate, response: Response, db: Session = Depends(get_db)):
    names = [name.strip() for name in payload.club_names if name.strip()]
    if not 2 <= len(names) <= 5:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Room needs 2 to 5 named clubs")

    user = models.User(display_name=payload.display_name.strip())
    game = models.Game(name=payload.room_name.strip(), status=models.GameStatus.active)
    db.add_all([user, game])
    db.flush()
    db.add(models.Membership(game_id=game.id, user_id=user.id, role=models.MembershipRole.gm))
    for index, name in enumerate(names, start=1):
        db.add(models.Club(game_id=game.id, name=name, short_name=f"C{index}"))
    room = models.GameRoom(
        game_id=game.id,
        host_user_id=user.id,
        invite_code=_invite_code(db),
        status="lobby",
    )
    db.add(room)
    db.flush()
    db.add(models.GameRoomMember(room_id=room.id, user_id=user.id))
    _set_browser_session(response, db, user)
    db.commit()
    db.refresh(room)
    return _serialize_room(db, room, user)


@router.post("/rooms/{invite_code}/join")
def join_room(invite_code: str, payload: RoomJoin, response: Response, db: Session = Depends(get_db)):
    room = db.query(models.GameRoom).filter(models.GameRoom.invite_code == invite_code.upper()).first()
    if not room:
        _not_found("Invite code not found")
    if room.status != "lobby":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Room already started")

    user = models.User(display_name=payload.display_name.strip())
    db.add(user)
    db.flush()
    db.add(models.GameRoomMember(room_id=room.id, user_id=user.id))
    _set_browser_session(response, db, user)
    db.commit()
    return _serialize_room(db, room, user)


@router.get("/me")
def current_browser_user(user: models.User = Depends(get_web_current_user), db: Session = Depends(get_db)):
    rooms = [membership.room for membership in user.room_memberships]
    return {
        "id": str(user.id),
        "display_name": user.display_name,
        "rooms": [
            {
                "id": str(room.id),
                "game_id": str(room.game_id),
                "invite_code": room.invite_code,
                "status": room.status,
                "is_host": room.host_user_id == user.id,
            }
            for room in rooms
        ],
    }


@router.get("/rooms/{room_id}")
def get_room(
    room_id: UUID,
    user: models.User = Depends(get_web_current_user),
    db: Session = Depends(get_db),
):
    room = _room_or_404(db, room_id)
    _room_member(db, room, user)
    return _serialize_room(db, room, user)


@router.post("/rooms/{room_id}/clubs/{club_id}/claim")
def claim_club(
    room_id: UUID,
    club_id: UUID,
    user: models.User = Depends(get_web_current_user),
    db: Session = Depends(get_db),
):
    room = _room_or_404(db, room_id)
    member = _room_member(db, room, user)
    if room.status != "lobby":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Club claims close after start")
    club = db.query(models.Club).filter(models.Club.id == club_id, models.Club.game_id == room.game_id).first()
    if not club:
        _not_found("Club not found")
    claim = (
        db.query(models.GameRoomMember)
        .filter(
            models.GameRoomMember.room_id == room.id,
            models.GameRoomMember.club_id == club.id,
            models.GameRoomMember.user_id != user.id,
        )
        .first()
    )
    if claim:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Club is already claimed")

    db.query(models.Membership).filter(
        models.Membership.user_id == user.id,
        models.Membership.game_id == room.game_id,
        models.Membership.role == models.MembershipRole.club_owner,
    ).delete()
    member.club_id = club.id
    member.is_ready = False
    db.add(
        models.Membership(
            game_id=room.game_id,
            user_id=user.id,
            role=models.MembershipRole.club_owner,
            club_id=club.id,
        )
    )
    db.commit()
    return _serialize_room(db, room, user)


@router.patch("/rooms/{room_id}/memberships/me/ready")
def set_ready(
    room_id: UUID,
    payload: ReadyUpdate,
    user: models.User = Depends(get_web_current_user),
    db: Session = Depends(get_db),
):
    room = _room_or_404(db, room_id)
    member = _room_member(db, room, user)
    if room.status != "lobby":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Room already started")
    if not member.club_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Claim a club before readying")
    member.is_ready = payload.ready
    db.commit()
    return _serialize_room(db, room, user)


@router.post("/rooms/{room_id}/start")
def start_room(
    room_id: UUID,
    payload: RoomStart,
    user: models.User = Depends(get_web_current_user),
    db: Session = Depends(get_db),
):
    room = _room_or_404(db, room_id)
    _room_member(db, room, user)
    _require_host(room, user)
    if room.status != "lobby":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Room already started")

    clubs = db.query(models.Club).filter(models.Club.game_id == room.game_id).all()
    claims = db.query(models.GameRoomMember).filter(models.GameRoomMember.room_id == room.id).all()
    ready_clubs = {claim.club_id for claim in claims if claim.club_id and claim.is_ready}
    if set(club.id for club in clubs) != ready_clubs:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Every club needs a ready player")

    year_label = payload.year_label or str(datetime.utcnow().year)
    season = create_season_core(db, room.game, year_label)
    generate_fixtures_core(db, season)
    room.status = "active"
    room.started_at = datetime.utcnow()
    db.commit()
    return {"room": _serialize_room(db, room, user), "season_id": str(season.id)}


@router.get("/games/{game_id}/play-state")
def play_state(
    game_id: UUID,
    user: models.User = Depends(get_web_current_user),
    db: Session = Depends(get_db),
):
    room = _room_for_game_or_404(db, game_id)
    member = _room_member(db, room, user)
    season = _latest_running_season(db, str(game_id))
    turn = _current_turn(db, season)
    clubs = db.query(models.Club).filter(models.Club.game_id == game_id).order_by(models.Club.name).all()
    decisions = {}
    acks = set()
    if turn:
        decisions = {
            decision.club_id: decision
            for decision in db.query(models.TurnDecision).filter(models.TurnDecision.turn_id == turn.id).all()
        }
        acks = {
            ack.club_id
            for ack in db.query(models.TurnAck).filter(models.TurnAck.turn_id == turn.id, models.TurnAck.ack.is_(True)).all()
        }
    standings = StandingsCalculator(db, season.id).calculate() if season else []
    return {
        "room": {
            "id": str(room.id),
            "invite_code": room.invite_code,
            "status": room.status,
        },
        "game_id": str(game_id),
        "season": {
            "id": str(season.id),
            "number": season.season_number,
            "year_label": season.year_label,
            "status": season.status.value,
        } if season else None,
        "turn": _turn_label(turn),
        "self": {
            "user_id": str(user.id),
            "display_name": user.display_name,
            "club_id": str(member.club_id) if member.club_id else None,
            "is_host": room.host_user_id == user.id,
        },
        "clubs": [
            {
                "id": str(club.id),
                "name": club.name,
                "decision_state": decisions[club.id].decision_state.value if club.id in decisions else None,
                "committed": bool(
                    club.id in decisions
                    and decisions[club.id].decision_state in (models.DecisionState.committed, models.DecisionState.locked)
                ),
                "acked": club.id in acks,
            }
            for club in clubs
        ],
        "standings": standings,
    }


@router.get("/games/{game_id}/clubs/{club_id}/turn-console")
def turn_console(
    game_id: UUID,
    club_id: UUID,
    user: models.User = Depends(get_web_current_user),
    db: Session = Depends(get_db),
):
    room = _room_for_game_or_404(db, game_id)
    _web_club_access(db, room, user, club_id)
    season = _latest_running_season(db, str(game_id))
    turn = _current_turn(db, season)
    if not turn or not season:
        return {"turn": None, "available_inputs": [], "available_actions": []}

    decision = (
        db.query(models.TurnDecision)
        .filter(models.TurnDecision.turn_id == turn.id, models.TurnDecision.club_id == club_id)
        .first()
    )
    draft = (
        db.query(models.WebTurnDraft)
        .filter(models.WebTurnDraft.turn_id == turn.id, models.WebTurnDraft.club_id == club_id)
        .first()
    )
    state = db.query(models.ClubFinancialState).filter(models.ClubFinancialState.club_id == club_id).first()
    snapshot = (
        db.query(models.ClubFinancialSnapshot)
        .filter(models.ClubFinancialSnapshot.club_id == club_id, models.ClubFinancialSnapshot.season_id == season.id)
        .order_by(models.ClubFinancialSnapshot.month_index.desc())
        .first()
    )
    fanbase = (
        db.query(models.ClubFanbaseState)
        .filter(models.ClubFanbaseState.club_id == club_id, models.ClubFanbaseState.season_id == season.id)
        .first()
    )
    sponsor = (
        db.query(models.ClubSponsorState)
        .filter(models.ClubSponsorState.club_id == club_id, models.ClubSponsorState.season_id == season.id)
        .first()
    )
    staffs = db.query(models.ClubStaff).filter(models.ClubStaff.club_id == club_id).order_by(models.ClubStaff.role).all()
    fixtures = (
        db.query(models.Fixture)
        .filter(
            models.Fixture.season_id == season.id,
            (
                (models.Fixture.home_club_id == club_id)
                | (models.Fixture.away_club_id == club_id)
                | (models.Fixture.bye_club_id == club_id)
            ),
        )
        .order_by(models.Fixture.match_month_index)
        .all()
    )
    club_names = {club.id: club.name for club in db.query(models.Club).filter(models.Club.game_id == game_id).all()}
    available_inputs = get_available_inputs(db, turn, club_id)
    return {
        "turn": _turn_label(turn),
        "decision": {
            "state": decision.decision_state.value if decision else None,
            "payload": decision.payload_json if decision else None,
            "committed_at": decision.committed_at.isoformat() if decision and decision.committed_at else None,
        },
        "draft": draft.payload_json if draft else None,
        "available_inputs": [
            {"key": key, "label": DECISION_LABELS.get(key, key)}
            for key in available_inputs
        ],
        "available_actions": get_available_actions(db, turn, club_id),
        "finance": {
            "balance": float(state.balance) if state else 0,
            "latest_closing_balance": float(snapshot.closing_balance) if snapshot else None,
            "latest_income": float(snapshot.income_total) if snapshot else None,
            "latest_expense": float(snapshot.expense_total) if snapshot else None,
            "report": _finance_report(db, club_id, season, snapshot),
        },
        "fanbase": {
            "followers": fanbase.followers_public if fanbase else None,
            "fb_count": fanbase.fb_count if fanbase else None,
        },
        "sponsor": {
            "count": sponsor.count if sponsor else 0,
            "confirmed_next": (
                sponsor.pipeline_confirmed_exist + sponsor.pipeline_confirmed_new
                if sponsor else 0
            ),
        },
        "staff": [
            {"role": staff.role.value, "count": staff.count, "next_count": staff.next_count}
            for staff in staffs
        ],
        "fixtures": [
            {
                "id": str(fixture.id),
                "month_index": fixture.match_month_index,
                "month": fixture.match_month_name,
                "home": fixture.home_club_id == club_id,
                "opponent": club_names.get(fixture.away_club_id if fixture.home_club_id == club_id else fixture.home_club_id),
                "is_bye": fixture.is_bye,
                "status": fixture.match.status.value if fixture.match else "scheduled",
                "score": (
                    [fixture.match.home_goals, fixture.match.away_goals]
                    if fixture.match and fixture.match.home_goals is not None else None
                ),
                "score_for_club": (
                    [fixture.match.home_goals, fixture.match.away_goals]
                    if fixture.match and fixture.match.home_goals is not None and fixture.home_club_id == club_id
                    else [fixture.match.away_goals, fixture.match.home_goals]
                    if fixture.match and fixture.match.home_goals is not None and fixture.away_club_id == club_id
                    else None
                ),
                "weather": fixture.weather,
                "home_attendance": fixture.home_attendance,
                "away_attendance": fixture.away_attendance,
                "total_attendance": fixture.total_attendance,
            }
            for fixture in fixtures
        ],
        "standings": StandingsCalculator(db, season.id).calculate(),
    }


@router.put("/games/{game_id}/clubs/{club_id}/turn-draft")
def save_turn_draft(
    game_id: UUID,
    club_id: UUID,
    payload: TurnDraftUpdate,
    user: models.User = Depends(get_web_current_user),
    db: Session = Depends(get_db),
):
    room = _room_for_game_or_404(db, game_id)
    _web_club_access(db, room, user, club_id)
    season = _latest_running_season(db, str(game_id))
    turn = _current_turn(db, season)
    if not turn:
        _not_found("Current turn not found")
    if turn.turn_state not in (models.TurnState.open, models.TurnState.collecting):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Turn input is closed")

    normalized = dict(payload.payload)
    available = set(get_available_inputs(db, turn, club_id))
    invalid_fields = sorted(set(normalized) - available)
    if invalid_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Inputs not available this turn: {', '.join(invalid_fields)}",
        )
    parsed = parse_decision_payload(normalized)
    errors = validate_decision_payload(db, turn, club_id, parsed)
    if errors:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"validation_errors": errors})

    draft = (
        db.query(models.WebTurnDraft)
        .filter(models.WebTurnDraft.turn_id == turn.id, models.WebTurnDraft.club_id == club_id)
        .first()
    )
    if not draft:
        draft = models.WebTurnDraft(turn_id=turn.id, club_id=club_id, user_id=user.id, payload_json=normalized)
        db.add(draft)
    else:
        draft.user_id = user.id
        draft.payload_json = normalized
    db.commit()
    return {"payload": draft.payload_json, "updated_at": draft.updated_at}


@router.post("/games/{game_id}/clubs/{club_id}/turn-staff-plan")
def save_web_staff_plan(
    game_id: UUID,
    club_id: UUID,
    payload: WebStaffPlan,
    user: models.User = Depends(get_web_current_user),
    db: Session = Depends(get_db),
):
    room = _room_for_game_or_404(db, game_id)
    _web_club_access(db, room, user, club_id)
    season = _latest_running_season(db, str(game_id))
    turn = _current_turn(db, season)
    if not turn:
        _not_found("Current turn not found")
    try:
        role = models.StaffRole(payload.role)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown staff role")
    finance_service.ensure_finance_initialized_for_club(db, club_id)
    staff_service.ensure_staff_state(db, club_id)
    try:
        row = staff_service.update_staff_plan(db, club_id, role, payload.count, turn.month_index, turn.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    db.commit()
    return {
        "role": row.role.value,
        "count": row.count,
        "next_count": row.next_count,
        "hiring_target": row.hiring_target,
    }


@router.post("/games/{game_id}/clubs/{club_id}/turn-academy-budget")
def save_web_academy_budget(
    game_id: UUID,
    club_id: UUID,
    payload: WebAcademyBudget,
    user: models.User = Depends(get_web_current_user),
    db: Session = Depends(get_db),
):
    room = _room_for_game_or_404(db, game_id)
    _web_club_access(db, room, user, club_id)
    season = _latest_running_season(db, str(game_id))
    turn = _current_turn(db, season)
    if not turn or not season:
        _not_found("Current turn not found")
    if turn.month_index != 10:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Academy budget only opens in May")
    row = academy_service.update_academy_plan(db, club_id, season.id, payload.annual_budget)
    db.commit()
    return {"annual_budget": payload.annual_budget, "club_id": str(row.club_id)}


@router.post("/games/{game_id}/clubs/{club_id}/turn-commit")
def commit_turn_draft(
    game_id: UUID,
    club_id: UUID,
    user: models.User = Depends(get_web_current_user),
    db: Session = Depends(get_db),
):
    room = _room_for_game_or_404(db, game_id)
    _web_club_access(db, room, user, club_id)
    season = _latest_running_season(db, str(game_id))
    turn = _current_turn(db, season)
    if not turn:
        _not_found("Current turn not found")
    draft = (
        db.query(models.WebTurnDraft)
        .filter(models.WebTurnDraft.turn_id == turn.id, models.WebTurnDraft.club_id == club_id)
        .first()
    )
    decision = (
        db.query(models.TurnDecision)
        .filter(models.TurnDecision.turn_id == turn.id, models.TurnDecision.club_id == club_id)
        .first()
    )
    final_payload = draft.payload_json if draft else (decision.payload_json if decision else None)
    if not final_payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Save input before committing")
    result = turn_routes.commit_decision(
        str(turn.id),
        str(club_id),
        DecisionCommitRequest(payload=final_payload),
        db,
        user,
    )
    if draft:
        db.delete(draft)
        db.commit()
    return result


@router.post("/games/{game_id}/clubs/{club_id}/turn-ack")
def ack_current_turn(
    game_id: UUID,
    club_id: UUID,
    user: models.User = Depends(get_web_current_user),
    db: Session = Depends(get_db),
):
    room = _room_for_game_or_404(db, game_id)
    _web_club_access(db, room, user, club_id)
    season = _latest_running_season(db, str(game_id))
    turn = _current_turn(db, season)
    if not turn:
        _not_found("Current turn not found")
    return turn_routes.ack_turn(str(turn.id), AckRequest(club_id=club_id, ack=True), db, user)


@router.post("/games/{game_id}/host/turn-action")
def host_turn_action(
    game_id: UUID,
    payload: HostTurnAction,
    user: models.User = Depends(get_web_current_user),
    db: Session = Depends(get_db),
):
    room = _room_for_game_or_404(db, game_id)
    _room_member(db, room, user)
    _require_host(room, user)
    season = _latest_running_season(db, str(game_id))
    turn = _current_turn(db, season)
    if not turn:
        _not_found("Current turn not found")
    handlers = {
        "open": turn_routes.open_turn,
        "lock": turn_routes.lock_turn,
        "resolve": turn_routes.resolve_turn,
        "advance": turn_routes.advance_turn,
    }
    handler = handlers.get(payload.action)
    if not handler:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown turn action")
    return handler(str(turn.id), db, user)
