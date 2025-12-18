import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class GameStatus(str, enum.Enum):
    draft = "draft"
    active = "active"
    archived = "archived"


class MembershipRole(str, enum.Enum):
    gm = "gm"
    club_owner = "club_owner"
    club_viewer = "club_viewer"


class SeasonStatus(str, enum.Enum):
    setup = "setup"
    running = "running"
    finished = "finished"


class TurnState(str, enum.Enum):
    open = "open"
    collecting = "collecting"
    locked = "locked"
    resolved = "resolved"
    acked = "acked"


class DecisionState(str, enum.Enum):
    draft = "draft"
    committed = "committed"
    locked = "locked"


class MatchStatus(str, enum.Enum):
    scheduled = "scheduled"
    played = "played"


class Game(Base):
    __tablename__ = "games"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    status = Column(Enum(GameStatus), nullable=False, default=GameStatus.active)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    clubs = relationship("Club", back_populates="game", cascade="all, delete-orphan")
    memberships = relationship("Membership", back_populates="game", cascade="all, delete-orphan")
    seasons = relationship("Season", back_populates="game", cascade="all, delete-orphan")


class Club(Base):
    __tablename__ = "clubs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_id = Column(UUID(as_uuid=True), ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    short_name = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    game = relationship("Game", back_populates="clubs")
    memberships = relationship("Membership", back_populates="club", cascade="all, delete-orphan")
    turn_decisions = relationship("TurnDecision", back_populates="club", cascade="all, delete-orphan")
    turn_acks = relationship("TurnAck", back_populates="club", cascade="all, delete-orphan")
    fixtures_home = relationship("Fixture", back_populates="home_club", foreign_keys="Fixture.home_club_id")
    fixtures_away = relationship("Fixture", back_populates="away_club", foreign_keys="Fixture.away_club_id")
    bye_fixtures = relationship("Fixture", back_populates="bye_club", foreign_keys="Fixture.bye_club_id")

    financial_profile = relationship("ClubFinancialProfile", back_populates="club", uselist=False, cascade="all, delete-orphan")
    financial_state = relationship("ClubFinancialState", back_populates="club", uselist=False, cascade="all, delete-orphan")
    financial_ledgers = relationship("ClubFinancialLedger", back_populates="club", cascade="all, delete-orphan")
    financial_snapshots = relationship("ClubFinancialSnapshot", back_populates="club", cascade="all, delete-orphan")



class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, nullable=False, unique=True)
    display_name = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    memberships = relationship("Membership", back_populates="user", cascade="all, delete-orphan")


class Membership(Base):
    __tablename__ = "memberships"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_id = Column(UUID(as_uuid=True), ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(Enum(MembershipRole), nullable=False)
    club_id = Column(UUID(as_uuid=True), ForeignKey("clubs.id", ondelete="CASCADE"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    game = relationship("Game", back_populates="memberships")
    user = relationship("User", back_populates="memberships")
    club = relationship("Club", back_populates="memberships")

    __table_args__ = (
        CheckConstraint("(role = 'gm' AND club_id IS NULL) OR (role <> 'gm' AND club_id IS NOT NULL)", name="club_required_for_roles"),
    )


class Season(Base):
    __tablename__ = "seasons"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_id = Column(UUID(as_uuid=True), ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    year_label = Column(String, nullable=False)
    start_month = Column(Integer, nullable=False, default=8)
    end_month = Column(Integer, nullable=False, default=7)
    status = Column(Enum(SeasonStatus), nullable=False, default=SeasonStatus.setup)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    game = relationship("Game", back_populates="seasons")
    turns = relationship("Turn", back_populates="season", cascade="all, delete-orphan")
    fixtures = relationship("Fixture", back_populates="season", cascade="all, delete-orphan")


class Turn(Base):
    __tablename__ = "turns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    season_id = Column(UUID(as_uuid=True), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    month_index = Column(Integer, nullable=False)
    month_name = Column(String, nullable=False)
    month_number = Column(Integer, nullable=False)
    turn_state = Column(Enum(TurnState), nullable=False, default=TurnState.open)
    opened_at = Column(DateTime, nullable=True)
    locked_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    season = relationship("Season", back_populates="turns")
    decisions = relationship("TurnDecision", back_populates="turn", cascade="all, delete-orphan")
    acks = relationship("TurnAck", back_populates="turn", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("season_id", "month_index", name="uniq_turn_month"),
    )


class TurnDecision(Base):
    __tablename__ = "turn_decisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    turn_id = Column(UUID(as_uuid=True), ForeignKey("turns.id", ondelete="CASCADE"), nullable=False)
    club_id = Column(UUID(as_uuid=True), ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False)
    decision_state = Column(Enum(DecisionState), nullable=False, default=DecisionState.draft)
    committed_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    committed_at = Column(DateTime, nullable=True)
    payload_json = Column(JSONB, nullable=True)

    turn = relationship("Turn", back_populates="decisions")
    club = relationship("Club", back_populates="turn_decisions")
    committed_by = relationship("User")

    __table_args__ = (
        UniqueConstraint("turn_id", "club_id", name="uniq_turn_club_decision"),
    )


class TurnAck(Base):
    __tablename__ = "turn_acks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    turn_id = Column(UUID(as_uuid=True), ForeignKey("turns.id", ondelete="CASCADE"), nullable=False)
    club_id = Column(UUID(as_uuid=True), ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    ack = Column(Boolean, nullable=False, default=True)
    acked_at = Column(DateTime, nullable=True)

    turn = relationship("Turn", back_populates="acks")
    club = relationship("Club", back_populates="turn_acks")
    user = relationship("User")

    __table_args__ = (
        UniqueConstraint("turn_id", "club_id", "user_id", name="uniq_turn_ack"),
    )


class Fixture(Base):
    __tablename__ = "fixtures"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    season_id = Column(UUID(as_uuid=True), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    match_month_index = Column(Integer, nullable=False)
    match_month_name = Column(String, nullable=False)
    home_club_id = Column(UUID(as_uuid=True), ForeignKey("clubs.id", ondelete="CASCADE"), nullable=True)
    away_club_id = Column(UUID(as_uuid=True), ForeignKey("clubs.id", ondelete="CASCADE"), nullable=True)
    is_bye = Column(Boolean, nullable=False, default=False)
    bye_club_id = Column(UUID(as_uuid=True), ForeignKey("clubs.id", ondelete="CASCADE"), nullable=True)

    season = relationship("Season", back_populates="fixtures")
    home_club = relationship("Club", foreign_keys=[home_club_id], back_populates="fixtures_home")
    away_club = relationship("Club", foreign_keys=[away_club_id], back_populates="fixtures_away")
    bye_club = relationship("Club", foreign_keys=[bye_club_id], back_populates="bye_fixtures")
    match = relationship("Match", back_populates="fixture", uselist=False, cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint(
            "season_id",
            "match_month_index",
            "home_club_id",
            "away_club_id",
            "is_bye",
            "bye_club_id",
            name="uniq_fixture",
        ),
    )


class Match(Base):
    __tablename__ = "matches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fixture_id = Column(UUID(as_uuid=True), ForeignKey("fixtures.id", ondelete="CASCADE"), nullable=False, unique=True)
    status = Column(Enum(MatchStatus), nullable=False, default=MatchStatus.scheduled)
    home_goals = Column(Integer, nullable=True)
    away_goals = Column(Integer, nullable=True)
    played_at = Column(DateTime, nullable=True)

    fixture = relationship("Fixture", back_populates="match")


def month_mappings():
    months = [
        (1, "Aug", 8),
        (2, "Sep", 9),
        (3, "Oct", 10),
        (4, "Nov", 11),
        (5, "Dec", 12),
        (6, "Jan", 1),
        (7, "Feb", 2),
        (8, "Mar", 3),
        (9, "Apr", 4),
        (10, "May", 5),
        (11, "Jun", 6),
        (12, "Jul", 7),
    ]
    return months


class ClubFinancialProfile(Base):
    __tablename__ = "club_financial_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    club_id = Column(UUID(as_uuid=True), ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, unique=True)
    currency_code = Column(String, nullable=False, default="JPY")
    sponsor_base_monthly = Column(Numeric(14, 2), nullable=False, default=0)
    sponsor_per_point = Column(Numeric(14, 2), nullable=False, default=0)
    monthly_cost = Column(Numeric(14, 2), nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    club = relationship("Club", back_populates="financial_profile")


class ClubFinancialState(Base):
    __tablename__ = "club_financial_states"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    club_id = Column(UUID(as_uuid=True), ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, unique=True)
    balance = Column(Numeric(14, 2), nullable=False, default=0)
    last_applied_turn_id = Column(UUID(as_uuid=True), ForeignKey("turns.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    club = relationship("Club", back_populates="financial_state")
    last_applied_turn = relationship("Turn")


class ClubFinancialLedger(Base):
    __tablename__ = "club_financial_ledgers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    club_id = Column(UUID(as_uuid=True), ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False)
    turn_id = Column(UUID(as_uuid=True), ForeignKey("turns.id", ondelete="CASCADE"), nullable=False)
    kind = Column(String, nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    meta = Column(JSONB, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    club = relationship("Club", back_populates="financial_ledgers")
    turn = relationship("Turn")

    __table_args__ = (
        UniqueConstraint("club_id", "turn_id", "kind", name="uq_ledger_club_turn_kind"),
    )


class ClubFinancialSnapshot(Base):
    __tablename__ = "club_financial_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    club_id = Column(UUID(as_uuid=True), ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False)
    season_id = Column(UUID(as_uuid=True), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    turn_id = Column(UUID(as_uuid=True), ForeignKey("turns.id", ondelete="CASCADE"), nullable=False)
    month_index = Column(Integer, nullable=False)
    opening_balance = Column(Numeric(14, 2), nullable=False)
    income_total = Column(Numeric(14, 2), nullable=False)
    expense_total = Column(Numeric(14, 2), nullable=False)
    closing_balance = Column(Numeric(14, 2), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    club = relationship("Club", back_populates="financial_snapshots")
    season = relationship("Season")
    turn = relationship("Turn")

    __table_args__ = (
        UniqueConstraint("club_id", "turn_id", name="uq_snapshot_club_turn"),
    )
