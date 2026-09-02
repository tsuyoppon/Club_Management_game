from datetime import datetime, timedelta
from decimal import Decimal
import secrets
from typing import Any, Literal, Optional
from uuid import UUID
from urllib.parse import quote, urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete as sqlalchemy_delete
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.config.constants import CURRENT_FANBASE_RULESET_VERSION
from app.db import models
from app.dependencies import get_db, get_web_current_user, hash_session_token
from app.routers import turns as turn_routes
from app.routers.seasons import _latest_running_season, create_season_core, generate_fixtures_core
from app.schemas import AckRequest, DecisionCommitRequest
from app.services.decision_validation import (
    get_available_actions,
    get_available_input_details,
    get_available_inputs,
    parse_decision_payload,
    validate_decision_payload,
)
from app.services.standings import StandingsCalculator
from app.services import final_results as final_results_service
from app.services import result_exports, result_summary
from app.services import academy as academy_service
from app.services import finance as finance_service
from app.services import staff as staff_service
from app.services.game_backup import (
    GameBackupError,
    create_game_backup,
    latest_game_backup,
)


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

EVENT_INPUT_KEYS = {"additional_reinforcement", "reinforcement_budget"}
AUXILIARY_INPUT_KEYS = {"staff_plan", "academy_budget"}

FINANCE_LABELS = {
    "academy_cost": "アカデミー運営経費",
    "academy_transfer_fee": "移籍金収入",
    "admin_cost": "管理運営経費",
    "distribution_revenue": "配分金",
    "hometown_expense": "ホームタウン活動費",
    "match_operation_cost": "試合関連経費",
    "merchandise_cost": "物販原価",
    "merchandise_rev": "物販収入",
    "merchandise_revenue": "物販収入",
    "next_home_promo_expense": "プロモーション費",
    "prize_revenue": "賞金",
    "promo_expense": "プロモーション費",
    "reinforcement_cost": "強化費",
    "sales_expense": "営業費",
    "sponsor": "スポンサー収入",
    "sponsor_annual": "スポンサー収入",
    "staff_cost": "人件費",
    "staff_severance": "スタッフ退職金",
    "team_operation_cost": "トップチーム運営経費",
    "tax": "税金",
}

FINANCE_ORDER = [
    "sponsor_annual",
    "sponsor",
    "ticket_rev",
    "distribution_revenue",
    "prize_revenue",
    "merchandise_rev",
    "academy_transfer_fee",
    "reinforcement_cost",
    "match_operation_cost",
    "team_operation_cost",
    "academy_cost",
    "merchandise_cost",
    "sales_expense",
    "promo_expense",
    "hometown_expense",
    "staff_cost",
    "admin_cost",
    "tax",
]
FINANCE_ORDER_INDEX = {kind: index for index, kind in enumerate(FINANCE_ORDER)}


class RoomCreate(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=80)
    room_name: str = Field(..., min_length=1, max_length=120)
    club_names: list[str] = Field(default_factory=list)
    host_mode: Literal["player", "dedicated"] = "player"


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


class DeleteGameRequest(BaseModel):
    confirm: str = Field(..., min_length=1)


def _public_backup_metadata(backup: dict[str, Any]) -> dict[str, Any]:
    return {
        "backup_id": backup["backup_id"],
        "game_id": backup["game_id"],
        "created_at": backup["created_at"],
        "size_bytes": backup["size_bytes"],
        "sha256": backup["sha256"],
        "counts": backup["counts"],
        "verified": backup["verified"],
    }


class WebStaffPlan(BaseModel):
    role: str
    count: int = Field(..., ge=1)


class WebAcademyBudget(BaseModel):
    annual_budget: int = Field(..., ge=0)


class WebBudgetEvent(BaseModel):
    key: str
    amount: int = Field(..., ge=0)


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


def _ensure_game_active(room: models.GameRoom):
    if room.status == "archived" or room.game.status == models.GameStatus.archived:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Game is archived")
    if room.status == "completed" or room.game.status == models.GameStatus.completed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Game is completed")


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


def _is_dedicated_host(room: models.GameRoom, user: models.User) -> bool:
    return room.host_mode == "dedicated" and room.host_user_id == user.id


def _forbid_dedicated_host_club_access(room: models.GameRoom, user: models.User) -> None:
    if _is_dedicated_host(room, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dedicated host cannot access a club role",
        )


def _require_host_for_game(db: Session, game_id: UUID, user: models.User) -> models.GameRoom:
    room = _room_for_game_or_404(db, game_id)
    _room_member(db, room, user)
    _require_host(room, user)
    return room


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


def _set_existing_browser_session_cookie(response: Response, raw_token: str):
    response.set_cookie(
        settings.web_session_cookie,
        raw_token,
        httponly=True,
        secure=settings.web_cookie_secure,
        samesite="lax",
        max_age=settings.web_session_ttl_days * 24 * 60 * 60,
        path="/",
    )


def _validate_demo_redirect(next_url: str, request: Request) -> str:
    parsed = urlparse(next_url)
    if not parsed.scheme and not parsed.netloc:
        if not next_url.startswith("/") or next_url.startswith("//"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid redirect URL")
        return next_url
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid redirect URL")
    if parsed.hostname != request.url.hostname:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Redirect host must match request host")
    return next_url


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
    completion = result_summary.active_completion(db, room.game_id)
    return {
        "id": str(room.id),
        "game_id": str(room.game_id),
        "status": room.status,
        "invite_code": room.invite_code,
        "host_mode": room.host_mode,
        "is_host": room.host_user_id == viewer.id,
        "game_status": room.game.status.value,
        "completed_at": completion.completed_at.isoformat() if completion else None,
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


def _count_query(query) -> int:
    return int(query.count())


def _game_delete_counts(db: Session, game: models.Game, exclude_user_id: Optional[UUID] = None) -> dict[str, int]:
    club_ids = [club.id for club in db.query(models.Club.id).filter(models.Club.game_id == game.id).all()]
    season_ids = [season.id for season in db.query(models.Season.id).filter(models.Season.game_id == game.id).all()]
    turn_ids = [turn.id for turn in db.query(models.Turn.id).filter(models.Turn.season_id.in_(season_ids)).all()] if season_ids else []
    fixture_ids = [fixture.id for fixture in db.query(models.Fixture.id).filter(models.Fixture.season_id.in_(season_ids)).all()] if season_ids else []
    room = db.query(models.GameRoom).filter(models.GameRoom.game_id == game.id).first()

    counts = {
        "clubs": len(club_ids),
        "memberships": _count_query(db.query(models.Membership).filter(models.Membership.game_id == game.id)),
        "seasons": len(season_ids),
        "turns": len(turn_ids),
        "decisions": _count_query(db.query(models.TurnDecision).filter(models.TurnDecision.turn_id.in_(turn_ids))) if turn_ids else 0,
        "acks": _count_query(db.query(models.TurnAck).filter(models.TurnAck.turn_id.in_(turn_ids))) if turn_ids else 0,
        "drafts": _count_query(db.query(models.WebTurnDraft).filter(models.WebTurnDraft.turn_id.in_(turn_ids))) if turn_ids else 0,
        "fixtures": len(fixture_ids),
        "matches": _count_query(db.query(models.Match).filter(models.Match.fixture_id.in_(fixture_ids))) if fixture_ids else 0,
        "financial_profiles": _count_query(db.query(models.ClubFinancialProfile).filter(models.ClubFinancialProfile.club_id.in_(club_ids))) if club_ids else 0,
        "financial_states": _count_query(db.query(models.ClubFinancialState).filter(models.ClubFinancialState.club_id.in_(club_ids))) if club_ids else 0,
        "ledgers": _count_query(db.query(models.ClubFinancialLedger).filter(models.ClubFinancialLedger.club_id.in_(club_ids))) if club_ids else 0,
        "snapshots": _count_query(db.query(models.ClubFinancialSnapshot).filter(models.ClubFinancialSnapshot.season_id.in_(season_ids))) if season_ids else 0,
        "sponsor_states": _count_query(db.query(models.ClubSponsorState).filter(models.ClubSponsorState.season_id.in_(season_ids))) if season_ids else 0,
        "academy_states": _count_query(db.query(models.ClubAcademy).filter(models.ClubAcademy.season_id.in_(season_ids))) if season_ids else 0,
        "reinforcement_plans": _count_query(db.query(models.ClubReinforcementPlan).filter(models.ClubReinforcementPlan.season_id.in_(season_ids))) if season_ids else 0,
        "staffs": _count_query(db.query(models.ClubStaff).filter(models.ClubStaff.club_id.in_(club_ids))) if club_ids else 0,
        "fanbase_states": _count_query(db.query(models.ClubFanbaseState).filter(models.ClubFanbaseState.season_id.in_(season_ids))) if season_ids else 0,
        "sales_allocations": _count_query(db.query(models.ClubSalesAllocation).filter(models.ClubSalesAllocation.season_id.in_(season_ids))) if season_ids else 0,
        "point_penalties": _count_query(db.query(models.ClubPointPenalty).filter(models.ClubPointPenalty.season_id.in_(season_ids))) if season_ids else 0,
        "bankruptcy_states": _count_query(db.query(models.ClubBankruptcyState).filter(models.ClubBankruptcyState.season_id.in_(season_ids))) if season_ids else 0,
        "public_disclosures": _count_query(db.query(models.SeasonPublicDisclosure).filter(models.SeasonPublicDisclosure.season_id.in_(season_ids))) if season_ids else 0,
        "final_results": _count_query(db.query(models.GameFinalResult).filter(models.GameFinalResult.game_id == game.id)),
        "completions": _count_query(db.query(models.GameCompletion).filter(models.GameCompletion.game_id == game.id)),
        "rooms": 1 if room else 0,
        "room_members": _count_query(db.query(models.GameRoomMember).filter(models.GameRoomMember.room_id == room.id)) if room else 0,
    }

    cleanup_user_ids = _guest_user_cleanup_candidates(db, game, room, exclude_user_id)
    counts["guest_users_to_cleanup"] = len(cleanup_user_ids)
    counts["sessions_to_cleanup"] = (
        _count_query(db.query(models.WebSession).filter(models.WebSession.user_id.in_(cleanup_user_ids)))
        if cleanup_user_ids else 0
    )
    return counts


def _guest_user_cleanup_candidates(
    db: Session,
    game: models.Game,
    room: Optional[models.GameRoom],
    exclude_user_id: Optional[UUID] = None,
) -> list[UUID]:
    if not room:
        return []
    members = db.query(models.GameRoomMember).filter(models.GameRoomMember.room_id == room.id).all()
    candidates: list[UUID] = []
    for member in members:
        user = member.user
        if exclude_user_id and user.id == exclude_user_id:
            continue
        if user.email is not None:
            continue
        other_room_memberships = (
            db.query(models.GameRoomMember)
            .filter(models.GameRoomMember.user_id == user.id, models.GameRoomMember.room_id != room.id)
            .count()
        )
        other_game_memberships = (
            db.query(models.Membership)
            .filter(models.Membership.user_id == user.id, models.Membership.game_id != game.id)
            .count()
        )
        if other_room_memberships == 0 and other_game_memberships == 0:
            candidates.append(user.id)
    return candidates


def _finance_kind_key(kind: str) -> str | None:
    if kind == "additional_reinforcement_applied":
        return None
    if kind == "next_home_promo_expense":
        return "promo_expense"
    if kind.startswith("staff_severance_"):
        return "staff_severance"
    for prefix in ["match_operation_cost", "merchandise_cost", "merchandise_rev", "ticket_rev"]:
        if kind.startswith(prefix):
            return prefix
    return kind


def _finance_label(kind: str) -> str:
    key = _finance_kind_key(kind)
    if key is None:
        return kind
    if kind.startswith("ticket_rev_"):
        return "入場料収入"
    if kind.startswith("merchandise_rev_"):
        return "物販収入"
    if kind.startswith("merchandise_cost_"):
        return "物販原価"
    if kind.startswith("match_operation_cost_"):
        return "試合関連経費"
    if kind.startswith("staff_severance_"):
        return "スタッフ退職金"
    return FINANCE_LABELS.get(key, key)


def _statement_from_ledgers(ledgers: list[models.ClubFinancialLedger]) -> dict[str, Any]:
    grouped: dict[str, dict[str, Any]] = {}
    for ledger in ledgers:
        amount = float(ledger.amount)
        if amount == 0:
            continue
        kind_key = _finance_kind_key(ledger.kind)
        if not kind_key:
            continue
        label = _finance_label(ledger.kind)
        sign = "income" if amount > 0 else "expense"
        key = f"{sign}:{kind_key}"
        item = grouped.setdefault(key, {"kind": key, "label": label, "amount": 0.0, "order": FINANCE_ORDER_INDEX.get(kind_key, 999)})
        item["amount"] += amount

    items = sorted(grouped.values(), key=lambda item: (item["amount"] < 0, item["order"], item["label"]))
    income = [item for item in items if item["amount"] > 0]
    expenses = [item for item in items if item["amount"] < 0]
    income_total = sum(item["amount"] for item in income)
    expense_total = sum(item["amount"] for item in expenses)
    for item in income + expenses:
        item.pop("order", None)
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
    first_snapshot = (
        db.query(models.ClubFinancialSnapshot)
        .filter(
            models.ClubFinancialSnapshot.club_id == club_id,
            models.ClubFinancialSnapshot.season_id == season.id,
            models.ClubFinancialSnapshot.month_index <= snapshot.month_index,
        )
        .order_by(models.ClubFinancialSnapshot.month_index.asc())
        .first()
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
        "opening_balance": float(first_snapshot.opening_balance if first_snapshot else snapshot.opening_balance),
        "closing_balance": float(snapshot.closing_balance),
    }


def _serialize_club_fixture(
    fixture: models.Fixture,
    club_id: UUID,
    club_names: dict[UUID, str],
) -> dict[str, Any]:
    match = fixture.match
    has_score = bool(match and match.home_goals is not None and match.away_goals is not None)
    opponent_id = fixture.away_club_id if fixture.home_club_id == club_id else fixture.home_club_id
    return {
        "id": str(fixture.id),
        "month_index": fixture.match_month_index,
        "month": fixture.match_month_name,
        "home": fixture.home_club_id == club_id,
        "opponent": club_names.get(opponent_id),
        "is_bye": fixture.is_bye,
        "status": match.status.value if match else "scheduled",
        "score": [match.home_goals, match.away_goals] if has_score else None,
        "score_for_club": (
            [match.home_goals, match.away_goals]
            if has_score and fixture.home_club_id == club_id
            else [match.away_goals, match.home_goals]
            if has_score and fixture.away_club_id == club_id
            else None
        ),
        "weather": fixture.weather,
        "home_attendance": fixture.home_attendance,
        "away_attendance": fixture.away_attendance,
        "total_attendance": fixture.total_attendance,
    }


def _next_academy_budget(row: Optional[models.ClubAcademy]) -> Optional[float]:
    if not row or not row.transfer_fee_history:
        return None
    for entry in reversed(row.transfer_fee_history):
        if isinstance(entry, dict) and "next_budget" in entry:
            return float(entry["next_budget"])
    return None


def _budget_event_for_turn(turn: models.Turn, saved_amount: Optional[float]) -> Optional[dict[str, Any]]:
    if turn.month_index == 5:
        return {
            "key": "additional_reinforcement",
            "title": "12月イベント",
            "input_label": "追加強化費",
            "saved_amount": saved_amount,
        }
    if turn.month_index == 11:
        return {
            "key": "reinforcement_budget",
            "title": "6月イベント",
            "input_label": "来期強化費",
            "saved_amount": saved_amount,
        }
    if turn.month_index == 12:
        return {
            "key": "reinforcement_budget",
            "title": "7月イベント",
            "input_label": "来期強化費",
            "saved_amount": saved_amount,
        }
    return None


def _event_key_for_turn(turn: models.Turn) -> Optional[str]:
    if turn.month_index == 5:
        return "additional_reinforcement"
    if turn.month_index in (11, 12):
        return "reinforcement_budget"
    return None


def _saved_payload_value(
    draft: Optional[models.WebTurnDraft],
    decision: Optional[models.TurnDecision],
    key: str,
) -> Optional[float]:
    for payload in (draft.payload_json if draft else None, decision.payload_json if decision else None):
        if isinstance(payload, dict) and key in payload:
            value = payload.get(key)
            return float(value) if value is not None else None
    return None


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
    _forbid_dedicated_host_club_access(room, user)
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
    game = models.Game(
        name=payload.room_name.strip(),
        status=models.GameStatus.active,
        fanbase_ruleset_version=CURRENT_FANBASE_RULESET_VERSION,
    )
    db.add_all([user, game])
    db.flush()
    db.add(models.Membership(game_id=game.id, user_id=user.id, role=models.MembershipRole.gm))
    for index, name in enumerate(names, start=1):
        db.add(models.Club(game_id=game.id, name=name, short_name=f"C{index}"))
    room = models.GameRoom(
        game_id=game.id,
        host_user_id=user.id,
        invite_code=_invite_code(db),
        host_mode=payload.host_mode,
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
                "host_mode": room.host_mode,
                "is_host": room.host_user_id == user.id,
            }
            for room in rooms
        ],
    }


@router.get("/demo/session-login", include_in_schema=False)
def demo_session_login(
    request: Request,
    token: str = Query(..., min_length=16),
    next: str = Query("/", min_length=1),  # noqa: A002 - query parameter name is part of the demo URL.
    db: Session = Depends(get_db),
):
    session = (
        db.query(models.WebSession)
        .filter(
            models.WebSession.token_hash == hash_session_token(token),
            models.WebSession.expires_at > datetime.utcnow(),
        )
        .first()
    )
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Demo session expired")

    response = RedirectResponse(url=_validate_demo_redirect(next, request), status_code=status.HTTP_303_SEE_OTHER)
    _set_existing_browser_session_cookie(response, token)
    return response


@router.get("/rooms/recent")
def recent_rooms(
    include_archived: bool = False,
    user: models.User = Depends(get_web_current_user),
    db: Session = Depends(get_db),
):
    memberships = (
        db.query(models.GameRoomMember)
        .join(models.GameRoom, models.GameRoom.id == models.GameRoomMember.room_id)
        .join(models.Game, models.Game.id == models.GameRoom.game_id)
        .filter(models.GameRoomMember.user_id == user.id)
        .order_by(models.GameRoomMember.updated_at.desc(), models.GameRoom.created_at.desc())
        .all()
    )
    rooms = []
    for membership in memberships:
        room = membership.room
        if (
            not include_archived
            and (room.status == "archived" or room.game.status == models.GameStatus.archived)
        ):
            continue
        if include_archived and room.host_user_id != user.id:
            continue

        season = _latest_running_season(db, str(room.game_id))
        turn = _current_turn(db, season)
        club = membership.club
        rooms.append(
            {
                "room_id": str(room.id),
                "game_id": str(room.game_id),
                "room_name": room.game.name,
                "game_status": room.game.status.value,
                "room_status": room.status,
                "invite_code": room.invite_code,
                "host_mode": room.host_mode,
                "is_host": room.host_user_id == user.id,
                "club_id": str(club.id) if club else None,
                "club_name": club.name if club else None,
                "season": {
                    "id": str(season.id),
                    "number": season.season_number,
                    "year_label": season.year_label,
                    "status": season.status.value,
                } if season else None,
                "turn": _turn_label(turn),
                "last_seen_at": membership.updated_at.isoformat() if membership.updated_at else None,
                "completed_at": (
                    completion.completed_at.isoformat()
                    if (completion := result_summary.active_completion(db, room.game_id))
                    else None
                ),
            }
        )
    return {"rooms": rooms}


@router.get("/rooms/{room_id}")
def get_room(
    room_id: UUID,
    user: models.User = Depends(get_web_current_user),
    db: Session = Depends(get_db),
):
    room = _room_or_404(db, room_id)
    _room_member(db, room, user)
    return _serialize_room(db, room, user)


def _summary_for_viewer(
    db: Session,
    game_id: UUID,
    user: models.User,
) -> tuple[models.GameRoom, dict[str, Any]]:
    room = _room_for_game_or_404(db, game_id)
    member = _room_member(db, room, user)
    if room.game.status == models.GameStatus.archived and room.host_user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Archived results are host-only")
    completion = result_summary.active_completion(db, game_id)
    if not completion or room.game.status not in (models.GameStatus.completed, models.GameStatus.archived):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Game results are not finalized")
    summary = result_summary.filter_summary_for_viewer(
        completion.summary_json,
        is_host=room.host_user_id == user.id,
        club_id=member.club_id,
    )
    return room, summary


@router.post("/games/{game_id}/complete")
def complete_game(
    game_id: UUID,
    user: models.User = Depends(get_web_current_user),
    db: Session = Depends(get_db),
):
    room = (
        db.query(models.GameRoom)
        .filter(models.GameRoom.game_id == game_id)
        .with_for_update()
        .first()
    )
    if not room:
        _not_found("Game room not found")
    member = _room_member(db, room, user)
    _require_host(room, user)

    existing = result_summary.active_completion(db, game_id)
    if existing and room.game.status == models.GameStatus.completed:
        return result_summary.filter_summary_for_viewer(existing.summary_json, is_host=True, club_id=member.club_id)

    eligibility = result_summary.completion_eligibility(db, room)
    if not eligibility["eligible"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "Game cannot be completed", **eligibility},
        )

    season = db.query(models.Season).filter(models.Season.id == eligibility["season_id"]).with_for_update().one()
    from app.services.season_finalize import SeasonFinalizer

    SeasonFinalizer(db, season.id).finalize(commit=False)
    season.status = models.SeasonStatus.finished
    db.add(season)
    final_results_service.generate_final_results(db, game_id)
    db.flush()

    completed_at = datetime.utcnow()
    summary = result_summary.build_summary(db, room.game, completed_at)
    completion = models.GameCompletion(
        game_id=game_id,
        completed_by_user_id=user.id,
        completed_at=completed_at,
        summary_schema_version=result_summary.SUMMARY_SCHEMA_VERSION,
        summary_json=summary,
    )
    db.add(completion)
    room.game.status = models.GameStatus.completed
    room.status = "completed"
    db.commit()
    return result_summary.filter_summary_for_viewer(summary, is_host=True, club_id=member.club_id)


@router.post("/games/{game_id}/reopen")
def reopen_game(
    game_id: UUID,
    user: models.User = Depends(get_web_current_user),
    db: Session = Depends(get_db),
):
    room = (
        db.query(models.GameRoom)
        .filter(models.GameRoom.game_id == game_id)
        .with_for_update()
        .first()
    )
    if not room:
        _not_found("Game room not found")
    _room_member(db, room, user)
    _require_host(room, user)
    if room.game.status != models.GameStatus.completed or room.status != "completed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only a completed game can be reopened")
    completion = result_summary.active_completion(db, game_id)
    if not completion:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Active completion record not found")
    completion.reopened_by_user_id = user.id
    completion.reopened_at = datetime.utcnow()
    latest_season = (
        db.query(models.Season)
        .filter(models.Season.game_id == game_id)
        .order_by(models.Season.season_number.desc(), models.Season.created_at.desc())
        .first()
    )
    if latest_season:
        latest_season.status = models.SeasonStatus.running
    room.game.status = models.GameStatus.active
    room.status = "active"
    db.commit()
    return {"game_id": str(game_id), "status": "active", "room_status": "active"}


@router.get("/games/{game_id}/result-summary")
def result_summary_endpoint(
    game_id: UUID,
    user: models.User = Depends(get_web_current_user),
    db: Session = Depends(get_db),
):
    _, summary = _summary_for_viewer(db, game_id, user)
    return summary


@router.get("/games/{game_id}/result-summary/exports/pdf")
def result_summary_pdf(
    game_id: UUID,
    user: models.User = Depends(get_web_current_user),
    db: Session = Depends(get_db),
):
    room, summary = _summary_for_viewer(db, game_id, user)
    content = result_exports.build_pdf(summary)
    filename = result_exports.safe_export_filename(
        f"{room.game.name}_result-summary_{summary['game']['completed_at'][:10]}"
    )
    encoded_filename = quote(f"{filename}.pdf")
    return StreamingResponse(
        iter([content]),
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="result-summary.pdf"; filename*=UTF-8\'\'{encoded_filename}'
            ),
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/games/{game_id}/result-summary/exports/csv-zip")
def result_summary_csv_zip(
    game_id: UUID,
    user: models.User = Depends(get_web_current_user),
    db: Session = Depends(get_db),
):
    room, summary = _summary_for_viewer(db, game_id, user)
    content = result_exports.build_csv_zip(summary)
    filename = result_exports.safe_export_filename(
        f"{room.game.name}_result-summary_{summary['game']['completed_at'][:10]}"
    )
    encoded_filename = quote(f"{filename}.zip")
    return StreamingResponse(
        iter([content]),
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f'attachment; filename="result-summary.zip"; filename*=UTF-8\'\'{encoded_filename}'
            ),
            "Cache-Control": "private, no-store",
        },
    )


@router.post("/games/{game_id}/archive")
def archive_game(
    game_id: UUID,
    user: models.User = Depends(get_web_current_user),
    db: Session = Depends(get_db),
):
    room = _require_host_for_game(db, game_id, user)
    room.game.status = models.GameStatus.archived
    room.status = "archived"
    db.commit()
    return {
        "game_id": str(game_id),
        "status": room.game.status.value,
        "room_status": room.status,
    }


@router.post("/games/{game_id}/unarchive")
def unarchive_game(
    game_id: UUID,
    user: models.User = Depends(get_web_current_user),
    db: Session = Depends(get_db),
):
    room = _require_host_for_game(db, game_id, user)
    if room.game.status != models.GameStatus.archived or room.status != "archived":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Game is not archived")
    has_season = db.query(models.Season.id).filter(models.Season.game_id == game_id).first() is not None
    room.game.status = models.GameStatus.active
    room.status = "active" if room.started_at is not None or has_season else "lobby"
    db.commit()
    return {
        "game_id": str(game_id),
        "status": room.game.status.value,
        "room_status": room.status,
    }


@router.post("/games/{game_id}/backups", status_code=status.HTTP_201_CREATED)
def backup_game(
    game_id: UUID,
    user: models.User = Depends(get_web_current_user),
    db: Session = Depends(get_db),
):
    _require_host_for_game(db, game_id, user)
    game = db.query(models.Game).filter(models.Game.id == game_id).with_for_update().first()
    if game is None:
        _not_found("Game not found")
    try:
        backup = create_game_backup(db, game_id, settings.game_backup_root, reason="manual")
    except (GameBackupError, OSError) as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Game backup failed; no game data was changed: {exc}",
        ) from exc
    db.rollback()
    return _public_backup_metadata(backup)


@router.get("/games/{game_id}/backups/latest")
def get_latest_game_backup(
    game_id: UUID,
    user: models.User = Depends(get_web_current_user),
    db: Session = Depends(get_db),
):
    _require_host_for_game(db, game_id, user)
    backup = latest_game_backup(settings.game_backup_root, game_id)
    if backup is None:
        _not_found("No verified game backup found")
    return _public_backup_metadata(backup)


@router.get("/games/{game_id}/delete-preview")
def delete_game_preview(
    game_id: UUID,
    user: models.User = Depends(get_web_current_user),
    db: Session = Depends(get_db),
):
    room = _require_host_for_game(db, game_id, user)
    return {
        "game_id": str(game_id),
        "room_name": room.game.name,
        "invite_code": room.invite_code,
        "game_status": room.game.status.value,
        "room_status": room.status,
        "counts": _game_delete_counts(db, room.game, user.id),
        "confirm_options": [room.game.name, room.invite_code],
        "verified_backup_required": True,
    }


@router.delete("/games/{game_id}")
def delete_game(
    game_id: UUID,
    payload: DeleteGameRequest,
    user: models.User = Depends(get_web_current_user),
    db: Session = Depends(get_db),
):
    room = _require_host_for_game(db, game_id, user)
    game = room.game
    if game.status != models.GameStatus.archived or room.status != "archived":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Archive the game before deleting it")
    if payload.confirm not in {game.name, room.invite_code}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Confirmation did not match")

    locked_game = db.query(models.Game).filter(models.Game.id == game.id).with_for_update().first()
    if locked_game is None:
        _not_found("Game not found")
    try:
        backup = create_game_backup(db, game.id, settings.game_backup_root, reason="pre-delete")
    except (GameBackupError, OSError) as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Verified backup could not be created; the game was not deleted: {exc}",
        ) from exc

    counts = _game_delete_counts(db, locked_game, user.id)
    cleanup_user_ids = _guest_user_cleanup_candidates(db, game, room, user.id)
    db.execute(sqlalchemy_delete(models.Game).where(models.Game.id == game.id))
    db.flush()
    for user_id in cleanup_user_ids:
        remaining_room_memberships = (
            db.query(models.GameRoomMember).filter(models.GameRoomMember.user_id == user_id).count()
        )
        remaining_game_memberships = (
            db.query(models.Membership).filter(models.Membership.user_id == user_id).count()
        )
        if remaining_room_memberships == 0 and remaining_game_memberships == 0:
            db.execute(sqlalchemy_delete(models.User).where(models.User.id == user_id))
    db.commit()
    return {
        "deleted": True,
        "game_id": str(game_id),
        "counts": counts,
        "backup": _public_backup_metadata(backup),
    }


@router.post("/rooms/{room_id}/clubs/{club_id}/claim")
def claim_club(
    room_id: UUID,
    club_id: UUID,
    user: models.User = Depends(get_web_current_user),
    db: Session = Depends(get_db),
):
    room = _room_or_404(db, room_id)
    _ensure_game_active(room)
    member = _room_member(db, room, user)
    if room.status != "lobby":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Club claims close after start")
    _forbid_dedicated_host_club_access(room, user)
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
    _ensure_game_active(room)
    member = _room_member(db, room, user)
    _forbid_dedicated_host_club_access(room, user)
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
    _ensure_game_active(room)
    host_member = _room_member(db, room, user)
    _require_host(room, user)
    if room.status != "lobby":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Room already started")

    clubs = db.query(models.Club).filter(models.Club.game_id == room.game_id).all()
    claims = db.query(models.GameRoomMember).filter(models.GameRoomMember.room_id == room.id).all()
    if room.host_mode == "dedicated" and (host_member.club_id is not None or host_member.is_ready):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Dedicated host must remain unassigned",
        )
    eligible_claims = (
        [claim for claim in claims if claim.user_id != room.host_user_id]
        if room.host_mode == "dedicated"
        else claims
    )
    ready_clubs = {claim.club_id for claim in eligible_claims if claim.club_id and claim.is_ready}
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
    _ensure_game_active(room)
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
            "host_mode": room.host_mode,
        },
        "game_id": str(game_id),
        "game_status": room.game.status.value,
        "completion": result_summary.completion_eligibility(db, room),
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
    _ensure_game_active(room)
    _web_club_access(db, room, user, club_id)
    season = _latest_running_season(db, str(game_id))
    turn = _current_turn(db, season)
    if not turn or not season:
        return {"turn": None, "available_inputs": [], "available_actions": []}

    # Repair seasons that were created before new-season staffing was applied
    # at creation time. This makes an already-open August Staff tab correct
    # immediately, without waiting for resolve. New seasons have no pending plan
    # here, so the operation is a no-op and cannot double-apply the transition.
    if turn.month_index == 1 and staff_service.resolve_hiring(
        db, club_id, season.id, only_if_pending=True
    ):
        db.commit()

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
    academy = (
        db.query(models.ClubAcademy)
        .filter(models.ClubAcademy.club_id == club_id, models.ClubAcademy.season_id == season.id)
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
    clubs_for_game = db.query(models.Club).filter(models.Club.game_id == game_id).order_by(models.Club.name).all()
    club_names = {club.id: club.name for club in clubs_for_game}
    fanbase_states = {
        state.club_id: state
        for state in (
            db.query(models.ClubFanbaseState)
            .filter(models.ClubFanbaseState.season_id == season.id)
            .all()
        )
    }
    available_inputs = get_available_inputs(db, turn, club_id)
    normal_available_input_details = [
        detail
        for detail in get_available_input_details(db, turn, club_id)
        if detail["key"] not in EVENT_INPUT_KEYS
    ]
    event_key = _event_key_for_turn(turn)
    event_budget = (
        _budget_event_for_turn(turn, _saved_payload_value(draft, decision, event_key))
        if event_key in available_inputs
        else None
    )
    return {
        "turn": _turn_label(turn),
        "decision": {
            "state": decision.decision_state.value if decision else None,
            "payload": decision.payload_json if decision else None,
            "committed_at": decision.committed_at.isoformat() if decision and decision.committed_at else None,
        },
        "draft": draft.payload_json if draft else None,
        "available_inputs": [
            {
                **detail,
                "label": (
                    f"{detail['label']}（vs {detail['target']['opponent_name']}）"
                    if turn.month_index == 12 and detail.get("target")
                    else DECISION_LABELS.get(detail["key"], detail["label"])
                ),
            }
            for detail in normal_available_input_details
        ],
        "available_actions": get_available_actions(db, turn, club_id),
        "event_budget": event_budget,
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
            "comparison": [
                {
                    "club_id": str(club.id),
                    "club_name": club.name,
                    "is_self": club.id == club_id,
                    "followers": (
                        fan_state.followers_public
                        if (fan_state := fanbase_states.get(club.id)) and fan_state.followers_public is not None
                        else None
                    ),
                    "fb_count": fan_state.fb_count if (fan_state := fanbase_states.get(club.id)) else None,
                }
                for club in clubs_for_game
            ],
        },
        "sponsor": {
            "count": sponsor.count if sponsor else 0,
            "confirmed_next": (
                sponsor.pipeline_confirmed_exist + sponsor.pipeline_confirmed_new
                if sponsor else 0
            ),
            "confirmed_next_new": sponsor.pipeline_confirmed_new if sponsor else 0,
            "confirmed_next_existing": sponsor.pipeline_confirmed_exist if sponsor else 0,
        },
        "academy": {
            "annual_budget": float(academy.annual_budget) if academy else 0,
            "next_annual_budget": _next_academy_budget(academy),
        },
        "staff": [
            {
                "role": staff.role.value,
                "count": staff.count,
                "next_count": staff.next_count,
                "hiring_target": staff.hiring_target,
                "input_count": staff.next_count if staff.next_count is not None else staff.hiring_target,
            }
            for staff in staffs
        ],
        "fixtures": [
            _serialize_club_fixture(fixture, club_id, club_names)
            for fixture in fixtures
        ],
        "standings": StandingsCalculator(db, season.id).calculate(),
    }


@router.get("/games/{game_id}/clubs/{club_id}/match-history")
def club_match_history(
    game_id: UUID,
    club_id: UUID,
    user: models.User = Depends(get_web_current_user),
    db: Session = Depends(get_db),
):
    room = _room_for_game_or_404(db, game_id)
    _ensure_game_active(room)
    _web_club_access(db, room, user, club_id)

    seasons = (
        db.query(models.Season)
        .filter(models.Season.game_id == game_id)
        .order_by(models.Season.season_number.desc(), models.Season.created_at.desc())
        .all()
    )
    season_ids = [season.id for season in seasons]
    fixtures = []
    if season_ids:
        fixtures = (
            db.query(models.Fixture)
            .options(selectinload(models.Fixture.match))
            .filter(
                models.Fixture.season_id.in_(season_ids),
                (
                    (models.Fixture.home_club_id == club_id)
                    | (models.Fixture.away_club_id == club_id)
                    | (models.Fixture.bye_club_id == club_id)
                ),
            )
            .order_by(models.Fixture.match_month_index)
            .all()
        )

    clubs = db.query(models.Club).filter(models.Club.game_id == game_id).all()
    club_names = {club.id: club.name for club in clubs}
    fixtures_by_season: dict[str, list[dict[str, Any]]] = {
        str(season.id): [] for season in seasons
    }
    for fixture in fixtures:
        fixtures_by_season[str(fixture.season_id)].append(
            _serialize_club_fixture(fixture, club_id, club_names)
        )

    return {
        "seasons": [
            {
                "id": str(season.id),
                "game_id": str(season.game_id),
                "season_number": season.season_number,
                "year_label": season.year_label,
                "status": season.status.value,
            }
            for season in seasons
        ],
        "fixtures": fixtures_by_season,
    }


@router.get("/games/{game_id}/final-standings")
def final_standings_by_season(
    game_id: UUID,
    user: models.User = Depends(get_web_current_user),
    db: Session = Depends(get_db),
):
    room = _room_for_game_or_404(db, game_id)
    _room_member(db, room, user)

    seasons = (
        db.query(models.Season)
        .filter(models.Season.game_id == game_id, models.Season.is_finalized.is_(True))
        .order_by(models.Season.season_number.desc())
        .all()
    )
    standings_by_season = {
        str(season.id): StandingsCalculator(db, season.id).calculate()
        for season in seasons
    }

    return {
        "seasons": [
            {
                "id": str(season.id),
                "game_id": str(season.game_id),
                "season_number": season.season_number,
                "year_label": season.year_label,
                "status": season.status.value,
                "finalized_at": season.finalized_at.isoformat() if season.finalized_at else None,
            }
            for season in seasons
        ],
        "standings": standings_by_season,
    }


@router.get("/games/{game_id}/clubs/{club_id}/finance-ledger")
def web_finance_ledger(
    game_id: UUID,
    club_id: UUID,
    season_id: UUID,
    user: models.User = Depends(get_web_current_user),
    db: Session = Depends(get_db),
):
    room = _room_for_game_or_404(db, game_id)
    _ensure_game_active(room)
    _web_club_access(db, room, user, club_id)

    season = db.query(models.Season).filter(models.Season.id == season_id).first()
    if not season:
        _not_found("Season not found")
    if season.game_id != game_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Season does not belong to game")

    records = (
        db.query(models.ClubFinancialLedger, models.Turn)
        .join(models.Turn, models.Turn.id == models.ClubFinancialLedger.turn_id)
        .filter(
            models.ClubFinancialLedger.club_id == club_id,
            models.Turn.season_id == season_id,
        )
        .order_by(models.Turn.month_index)
        .all()
    )
    snapshots = (
        db.query(models.ClubFinancialSnapshot)
        .filter(
            models.ClubFinancialSnapshot.club_id == club_id,
            models.ClubFinancialSnapshot.season_id == season_id,
        )
        .order_by(models.ClubFinancialSnapshot.month_index)
        .all()
    )

    return {
        "ledger": [
            {
                "turn_id": str(ledger.turn_id),
                "month_index": turn.month_index,
                "kind": ledger.kind,
                "amount": float(ledger.amount),
                "meta": ledger.meta,
            }
            for ledger, turn in records
        ],
        "balances": [
            {
                "month_index": snapshot.month_index,
                "closing_balance": float(snapshot.closing_balance),
            }
            for snapshot in snapshots
        ],
    }


@router.get("/games/{game_id}/clubs/{club_id}/annual-finance-ledger")
def web_annual_finance_ledger(
    game_id: UUID,
    club_id: UUID,
    user: models.User = Depends(get_web_current_user),
    db: Session = Depends(get_db),
):
    room = _room_for_game_or_404(db, game_id)
    _ensure_game_active(room)
    _web_club_access(db, room, user, club_id)

    season_end_snapshots = (
        db.query(models.ClubFinancialSnapshot, models.Season)
        .join(models.Season, models.Season.id == models.ClubFinancialSnapshot.season_id)
        .filter(
            models.ClubFinancialSnapshot.club_id == club_id,
            models.ClubFinancialSnapshot.month_index == 12,
            models.Season.game_id == game_id,
        )
        .order_by(models.Season.season_number)
        .all()
    )
    season_ids = [season.id for _, season in season_end_snapshots]
    records = []
    if season_ids:
        records = (
            db.query(models.ClubFinancialLedger, models.Turn)
            .join(models.Turn, models.Turn.id == models.ClubFinancialLedger.turn_id)
            .filter(
                models.ClubFinancialLedger.club_id == club_id,
                models.Turn.season_id.in_(season_ids),
            )
            .order_by(models.Turn.season_id, models.Turn.month_index)
            .all()
        )

    return {
        "seasons": [
            {
                "id": str(season.id),
                "season_number": season.season_number,
                "year_label": season.year_label,
                "closing_balance": float(snapshot.closing_balance),
            }
            for snapshot, season in season_end_snapshots
        ],
        "ledger": [
            {
                "season_id": str(turn.season_id),
                "kind": ledger.kind,
                "amount": float(ledger.amount),
            }
            for ledger, turn in records
        ],
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
    _ensure_game_active(room)
    _web_club_access(db, room, user, club_id)
    season = _latest_running_season(db, str(game_id))
    turn = _current_turn(db, season)
    if not turn:
        _not_found("Current turn not found")
    if turn.turn_state not in (models.TurnState.open, models.TurnState.collecting):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Turn input is closed")

    normalized = dict(payload.payload)
    available = set(key for key in get_available_inputs(db, turn, club_id) if key not in EVENT_INPUT_KEYS)
    invalid_fields = sorted(set(normalized) - available)
    if invalid_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Inputs not available this turn: {', '.join(invalid_fields)}",
        )
    decision = (
        db.query(models.TurnDecision)
        .filter(models.TurnDecision.turn_id == turn.id, models.TurnDecision.club_id == club_id)
        .first()
    )
    existing_payload = (
        dict(draft.payload_json)
        if (draft := db.query(models.WebTurnDraft)
            .filter(models.WebTurnDraft.turn_id == turn.id, models.WebTurnDraft.club_id == club_id)
            .first())
        else dict(decision.payload_json)
        if decision and decision.payload_json
        else {}
    )
    preserved = {
        key: existing_payload[key]
        for key in EVENT_INPUT_KEYS | AUXILIARY_INPUT_KEYS
        if key in existing_payload
    }
    merged_payload = {**preserved, **normalized}
    parsed = parse_decision_payload(merged_payload)
    errors = validate_decision_payload(db, turn, club_id, parsed)
    if errors:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"validation_errors": errors})

    if not draft:
        draft = models.WebTurnDraft(turn_id=turn.id, club_id=club_id, user_id=user.id, payload_json=merged_payload)
        db.add(draft)
    else:
        draft.user_id = user.id
        draft.payload_json = merged_payload
    db.commit()
    return {"payload": draft.payload_json, "updated_at": draft.updated_at}


def _save_auxiliary_decision_input(
    db: Session,
    turn: models.Turn,
    club_id: UUID,
    user_id: UUID,
    key: str,
    value: Any,
) -> None:
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
    merged = dict(draft.payload_json) if draft else dict(decision.payload_json or {}) if decision else {}
    merged[key] = value
    if draft:
        draft.payload_json = merged
        draft.user_id = user_id
    else:
        db.add(
            models.WebTurnDraft(
                turn_id=turn.id,
                club_id=club_id,
                user_id=user_id,
                payload_json=merged,
            )
        )


@router.post("/games/{game_id}/clubs/{club_id}/turn-budget-event")
def save_web_budget_event(
    game_id: UUID,
    club_id: UUID,
    payload: WebBudgetEvent,
    user: models.User = Depends(get_web_current_user),
    db: Session = Depends(get_db),
):
    room = _room_for_game_or_404(db, game_id)
    _ensure_game_active(room)
    _web_club_access(db, room, user, club_id)
    season = _latest_running_season(db, str(game_id))
    turn = _current_turn(db, season)
    if not turn:
        _not_found("Current turn not found")
    if turn.turn_state not in (models.TurnState.open, models.TurnState.collecting):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Turn input is closed")
    expected_key = _event_key_for_turn(turn)
    if payload.key != expected_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Budget event is not available this turn")

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
    merged_payload = (
        dict(draft.payload_json)
        if draft
        else dict(decision.payload_json)
        if decision and decision.payload_json
        else {}
    )
    merged_payload[payload.key] = payload.amount
    parsed = parse_decision_payload(merged_payload)
    errors = validate_decision_payload(db, turn, club_id, parsed)
    if errors:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"validation_errors": errors})

    if not draft:
        draft = models.WebTurnDraft(turn_id=turn.id, club_id=club_id, user_id=user.id, payload_json=merged_payload)
        db.add(draft)
    else:
        draft.user_id = user.id
        draft.payload_json = merged_payload
    db.commit()
    return {"key": payload.key, "amount": payload.amount, "payload": draft.payload_json}


@router.post("/games/{game_id}/clubs/{club_id}/turn-staff-plan")
def save_web_staff_plan(
    game_id: UUID,
    club_id: UUID,
    payload: WebStaffPlan,
    user: models.User = Depends(get_web_current_user),
    db: Session = Depends(get_db),
):
    room = _room_for_game_or_404(db, game_id)
    _ensure_game_active(room)
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
    existing_plan = {}
    existing_draft = (
        db.query(models.WebTurnDraft)
        .filter(models.WebTurnDraft.turn_id == turn.id, models.WebTurnDraft.club_id == club_id)
        .first()
    )
    if existing_draft:
        existing_plan = dict((existing_draft.payload_json or {}).get("staff_plan") or {})
    existing_plan[role.value] = payload.count
    _save_auxiliary_decision_input(db, turn, club_id, user.id, "staff_plan", existing_plan)
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
    _ensure_game_active(room)
    _web_club_access(db, room, user, club_id)
    season = _latest_running_season(db, str(game_id))
    turn = _current_turn(db, season)
    if not turn or not season:
        _not_found("Current turn not found")
    if turn.month_index != 10:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Academy budget only opens in May")
    row = academy_service.update_academy_plan(db, club_id, season.id, payload.annual_budget)
    _save_auxiliary_decision_input(db, turn, club_id, user.id, "academy_budget", payload.annual_budget)
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
    _ensure_game_active(room)
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


@router.post("/games/{game_id}/host/clubs/{club_id}/turn-uncommit")
def host_uncommit_turn(
    game_id: UUID,
    club_id: UUID,
    user: models.User = Depends(get_web_current_user),
    db: Session = Depends(get_db),
):
    room = _room_for_game_or_404(db, game_id)
    _ensure_game_active(room)
    _room_member(db, room, user)
    _require_host(room, user)
    season = _latest_running_season(db, str(game_id))
    turn = _current_turn(db, season)
    if not turn:
        _not_found("Current turn not found")
    if turn.turn_state not in (models.TurnState.open, models.TurnState.collecting):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Committed input can only be reopened before lock")
    club = db.query(models.Club).filter(models.Club.id == club_id, models.Club.game_id == game_id).first()
    if not club:
        _not_found("Club not found")
    decision = (
        db.query(models.TurnDecision)
        .filter(models.TurnDecision.turn_id == turn.id, models.TurnDecision.club_id == club_id)
        .first()
    )
    if not decision:
        _not_found("Decision not found")
    decision.decision_state = models.DecisionState.draft
    decision.committed_at = None
    decision.committed_by_user_id = None
    db.commit()
    return {"state": decision.decision_state, "club_id": str(club_id)}


@router.post("/games/{game_id}/clubs/{club_id}/turn-ack")
def ack_current_turn(
    game_id: UUID,
    club_id: UUID,
    user: models.User = Depends(get_web_current_user),
    db: Session = Depends(get_db),
):
    room = _room_for_game_or_404(db, game_id)
    _ensure_game_active(room)
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
    _ensure_game_active(room)
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
