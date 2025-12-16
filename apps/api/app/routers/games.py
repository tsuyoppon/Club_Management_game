from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db, require_role
from app.db.models import Club, Game, GameStatus, Membership, MembershipRole, User
from app.schemas import ClubCreate, ClubRead, GameCreate, GameRead, MembershipCreate

router = APIRouter(prefix="/games", tags=["games"])


@router.post("", response_model=GameRead)
def create_game(
    payload: GameCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    game = Game(name=payload.name, status=GameStatus.active)
    db.add(game)
    db.commit()
    db.refresh(game)

    existing = (
        db.query(Membership)
        .filter(Membership.game_id == game.id, Membership.user_id == user.id, Membership.role == MembershipRole.gm)
        .first()
    )
    if not existing:
        membership = Membership(game_id=game.id, user_id=user.id, role=MembershipRole.gm)
        db.add(membership)
        db.commit()

    return game


@router.post("/{game_id}/clubs", response_model=ClubRead)
def create_club(
    game_id: str,
    payload: ClubCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_role(user, db, game_id, MembershipRole.gm)
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")
    club_count = db.query(Club).filter(Club.game_id == game_id).count()
    if club_count >= 5:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Club limit reached")
    club = Club(game_id=game_id, name=payload.name, short_name=payload.short_name)
    db.add(club)
    db.commit()
    db.refresh(club)
    return club


@router.post("/{game_id}/memberships", status_code=status.HTTP_201_CREATED)
def create_membership(
    game_id: str,
    payload: MembershipCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_role(user, db, game_id, MembershipRole.gm)

    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")

    target_user = db.query(User).filter(User.email == payload.email).one_or_none()
    if target_user is None:
        target_user = User(email=payload.email, display_name=payload.display_name or payload.email)
        db.add(target_user)
        db.commit()
        db.refresh(target_user)

    if payload.role in (MembershipRole.club_owner, MembershipRole.club_viewer) and not payload.club_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="club_id required for club roles")

    membership = Membership(
        game_id=game_id,
        user_id=target_user.id,
        club_id=payload.club_id,
        role=payload.role,
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return {"id": str(membership.id)}

