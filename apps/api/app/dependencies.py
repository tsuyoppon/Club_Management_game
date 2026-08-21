from datetime import datetime, timedelta
from hashlib import sha256
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Game, GameStatus, Membership, MembershipRole, User, WebSession
from app.db.session import SessionLocal, get_db

settings = get_settings()


def get_current_user(
    db: Session = Depends(get_db),
    x_user_email: Optional[str] = Header(None),
    x_user_name: Optional[str] = Header(None),
) -> User:
    if not x_user_email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="X-User-Email header required")

    user = db.query(User).filter(User.email == x_user_email).one_or_none()
    if user is None:
        user = User(email=x_user_email, display_name=x_user_name or x_user_email)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def hash_session_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def get_web_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(settings.web_session_cookie)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Browser session required")

    session = (
        db.query(WebSession)
        .filter(
            WebSession.token_hash == hash_session_token(token),
            WebSession.expires_at > datetime.utcnow(),
        )
        .first()
    )
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Browser session expired")

    now = datetime.utcnow()
    if session.last_seen_at < now - timedelta(minutes=1):
        session.last_seen_at = now
        db.commit()
    return session.user


def require_role(
    user: User,
    db: Session,
    game_id,
    role: MembershipRole,
    club_id=None,
) -> Membership:
    memberships = (
        db.query(Membership)
        .filter(Membership.user_id == user.id, Membership.game_id == game_id)
        .all()
    )
    if not memberships:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User not part of game")

    for membership in memberships:
        if membership.role == MembershipRole.gm:
            return membership
        if role == MembershipRole.club_owner and membership.role == MembershipRole.club_owner:
            if club_id and str(membership.club_id) != str(club_id):
                continue
            return membership
        if role == MembershipRole.club_viewer and membership.role in (MembershipRole.club_viewer, MembershipRole.club_owner):
            if club_id and str(membership.club_id) != str(club_id):
                continue
            return membership

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")


def require_game_editable(game: Game) -> None:
    if game.status != GameStatus.active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Game is not editable while status is {game.status.value}",
        )


__all__ = [
    "get_db",
    "SessionLocal",
    "get_current_user",
    "get_web_current_user",
    "hash_session_token",
    "require_game_editable",
    "require_role",
]
