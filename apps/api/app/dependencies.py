from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db.models import Membership, MembershipRole, User
from app.db.session import SessionLocal, get_db


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


__all__ = ["get_db", "SessionLocal", "get_current_user", "require_role"]
