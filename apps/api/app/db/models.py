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
    # PR8: 最下位ペナルティON/OFF設定
    last_place_penalty_enabled = Column(Boolean, nullable=False, default=False)
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
    fanbase_states = relationship("ClubFanbaseState", back_populates="club", cascade="all, delete-orphan")



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
    is_finalized = Column(Boolean, nullable=False, default=False)
    finalized_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    game = relationship("Game", back_populates="seasons")
    turns = relationship("Turn", back_populates="season", cascade="all, delete-orphan")
    fixtures = relationship("Fixture", back_populates="season", cascade="all, delete-orphan")
    final_standings = relationship("SeasonFinalStanding", back_populates="season", cascade="all, delete-orphan")


class SeasonFinalStanding(Base):
    __tablename__ = "season_final_standings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    season_id = Column(UUID(as_uuid=True), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    club_id = Column(UUID(as_uuid=True), ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False)
    rank = Column(Integer, nullable=False)
    points = Column(Integer, nullable=False)
    gd = Column(Integer, nullable=False)
    gf = Column(Integer, nullable=False)
    ga = Column(Integer, nullable=False)
    won = Column(Integer, nullable=False)
    drawn = Column(Integer, nullable=False)
    lost = Column(Integer, nullable=False)
    played = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    season = relationship("Season", back_populates="final_standings")
    club = relationship("Club")

    __table_args__ = (
        UniqueConstraint("season_id", "club_id", name="uniq_season_club_standing"),
    )


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
    
    weather = Column(String, nullable=True)
    home_attendance = Column(Integer, nullable=True)
    away_attendance = Column(Integer, nullable=True)
    total_attendance = Column(Integer, nullable=True)

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
    
    # PR4: Ticket Revenue
    base_attendance = Column(Integer, nullable=False, default=10000)
    ticket_price = Column(Numeric(14, 2), nullable=False, default=2000)
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    club = relationship("Club", back_populates="financial_profile")


class ClubFinancialState(Base):
    __tablename__ = "club_financial_states"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    club_id = Column(UUID(as_uuid=True), ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, unique=True)
    balance = Column(Numeric(14, 2), nullable=False, default=0)
    
    # PR4: Hidden Variables
    staff_firing_penalty = Column(Numeric(14, 4), nullable=False, default=0)
    
    # PR8: 債務超過状態 - v1Spec Section 1.1, 14.1
    is_bankrupt = Column(Boolean, nullable=False, default=False)
    bankrupt_since_turn_id = Column(UUID(as_uuid=True), ForeignKey("turns.id", ondelete="SET NULL"), nullable=True)
    point_penalty_applied = Column(Boolean, nullable=False, default=False)
    
    last_applied_turn_id = Column(UUID(as_uuid=True), ForeignKey("turns.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    club = relationship("Club", back_populates="financial_state")
    last_applied_turn = relationship("Turn", foreign_keys=[last_applied_turn_id])
    bankrupt_since_turn = relationship("Turn", foreign_keys=[bankrupt_since_turn_id])


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


class ClubSponsorState(Base):
    __tablename__ = "club_sponsor_states"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    club_id = Column(UUID(as_uuid=True), ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False)
    season_id = Column(UUID(as_uuid=True), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    
    # N_next determined in July for the NEXT season.
    # But we need to store it somewhere.
    # Let's assume this record represents the state FOR a specific season.
    # So `count` is the number of sponsors active in THIS season.
    # `next_count` is the number of sponsors determined for the NEXT season.
    
    count = Column(Integer, nullable=False, default=0)
    # Determined count for the NEXT season (set in July)
    next_count = Column(Integer, nullable=True)
    unit_price = Column(Numeric(14, 2), nullable=False, default=5000000)
    
    # For tracking if the lump sum revenue has been recorded for this season
    is_revenue_recorded = Column(Boolean, nullable=False, default=False)
    
    # PR4: Sales Effort History (Apr-Jun)
    # Format: {"9": effort_val, "10": effort_val, "11": effort_val}
    sales_effort_history = Column(JSONB, nullable=True, default={})
    
    # PR7: 累積営業努力（EWMA） - Section 10.4
    cumulative_effort_ret = Column(Numeric(14, 4), nullable=False, default=0)  # C^ret(t)
    cumulative_effort_new = Column(Numeric(14, 4), nullable=False, default=0)  # C^new(t)
    
    # PR7: パイプライン進捗（内定累計） - Section 10.7
    pipeline_confirmed_exist = Column(Integer, nullable=False, default=0)  # 既存確定数
    pipeline_confirmed_new = Column(Integer, nullable=False, default=0)    # 新規確定数
    next_exist_count = Column(Integer, nullable=True)  # N^exist_next（7月確定）
    next_new_count = Column(Integer, nullable=True)    # N^new_next（7月確定）
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    club = relationship("Club")
    season = relationship("Season")
    
    __table_args__ = (
        UniqueConstraint("club_id", "season_id", name="uq_sponsor_club_season"),
    )


class ClubAcademy(Base):
    __tablename__ = "club_academies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    club_id = Column(UUID(as_uuid=True), ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False)
    season_id = Column(UUID(as_uuid=True), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    
    annual_budget = Column(Numeric(14, 2), nullable=False, default=0)
    cumulative_investment = Column(Numeric(14, 2), nullable=False, default=0)
    
    # History of transfer fees generated
    transfer_fee_history = Column(JSONB, nullable=True, default=[])
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    club = relationship("Club")
    season = relationship("Season")

    __table_args__ = (
        UniqueConstraint("club_id", "season_id", name="uq_academy_club_season"),
    )


class ClubReinforcementPlan(Base):
    __tablename__ = "club_reinforcement_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    club_id = Column(UUID(as_uuid=True), ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False)
    season_id = Column(UUID(as_uuid=True), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    
    annual_budget = Column(Numeric(14, 2), nullable=False, default=0)
    additional_budget = Column(Numeric(14, 2), nullable=False, default=0)
    next_season_budget = Column(Numeric(14, 2), nullable=False, default=0)
    
    # To track if additional budget has been applied (re-distributed)
    is_additional_applied = Column(Boolean, nullable=False, default=False)
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    club = relationship("Club")
    season = relationship("Season")

    __table_args__ = (
        UniqueConstraint("club_id", "season_id", name="uq_reinforcement_club_season"),
    )


class StaffRole(str, enum.Enum):
    director = "director"
    coach = "coach"
    scout = "scout"
    # Add others as needed


class ClubStaff(Base):
    __tablename__ = "club_staffs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    club_id = Column(UUID(as_uuid=True), ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False)
    
    role = Column(Enum(StaffRole), nullable=False)
    
    # Current active count
    count = Column(Integer, nullable=False, default=1)
    
    # Count for next season (decided in May)
    next_count = Column(Integer, nullable=True)
    
    # PR4: Hiring Target (User request in May)
    hiring_target = Column(Integer, nullable=True)
    
    salary_per_person = Column(Numeric(14, 2), nullable=False, default=0)
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    club = relationship("Club")

    __table_args__ = (
        UniqueConstraint("club_id", "role", name="uq_staff_club_role"),
    )


class ClubFanbaseState(Base):
    __tablename__ = "club_fanbase_states"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    club_id = Column(UUID(as_uuid=True), ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False)
    season_id = Column(UUID(as_uuid=True), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    
    fb_count = Column(Integer, nullable=False, default=60000)
    fb_rate = Column(Numeric(10, 6), nullable=False, default=0.06)
    cumulative_promo = Column(Numeric(14, 2), nullable=False, default=0)
    cumulative_ht = Column(Numeric(14, 2), nullable=False, default=0)
    last_ht_spend = Column(Numeric(14, 2), nullable=False, default=0)
    followers_public = Column(Integer, nullable=True)
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    club = relationship("Club", back_populates="fanbase_states")
    season = relationship("Season")

    __table_args__ = (
        UniqueConstraint("club_id", "season_id", name="uniq_club_season_fanbase"),
    )


class ClubSalesAllocation(Base):
    """PR7: 四半期営業リソース配分 - v1Spec Section 10.2"""
    __tablename__ = "club_sales_allocations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    club_id = Column(UUID(as_uuid=True), ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False)
    season_id = Column(UUID(as_uuid=True), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    quarter = Column(Integer, nullable=False)  # 1=Q1(Aug-Oct), 2=Q2(Nov-Jan), 3=Q3(Feb-Apr), 4=Q4(May-Jul)
    
    # 新規営業配分率 ρ^new (0.0〜1.0)
    rho_new = Column(Numeric(5, 4), nullable=False, default=0.5)
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    club = relationship("Club")
    season = relationship("Season")

    __table_args__ = (
        UniqueConstraint("club_id", "season_id", "quarter", name="uq_sales_allocation_club_season_quarter"),
    )


class ClubPointPenalty(Base):
    """PR8: 勝点剥奪履歴（監査用） - v1Spec Section 14.1"""
    __tablename__ = "club_point_penalties"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    club_id = Column(UUID(as_uuid=True), ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False)
    season_id = Column(UUID(as_uuid=True), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    turn_id = Column(UUID(as_uuid=True), ForeignKey("turns.id", ondelete="CASCADE"), nullable=False)
    points_deducted = Column(Integer, nullable=False)  # 剥奪点数（負の値: -6）
    reason = Column(String, nullable=False)  # 理由（"bankruptcy" など）
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    club = relationship("Club")
    season = relationship("Season")
    turn = relationship("Turn")

    __table_args__ = (
        UniqueConstraint("club_id", "season_id", "reason", name="uq_penalty_club_season_reason"),
    )


class SeasonPublicDisclosure(Base):
    """PR9: 公開情報履歴 - v1Spec Section 4"""
    __tablename__ = "season_public_disclosures"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    season_id = Column(UUID(as_uuid=True), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    disclosure_type = Column(String(50), nullable=False)  # 'financial_summary', 'team_power_december', 'team_power_july'
    disclosure_month = Column(Integer, nullable=False)  # 12 or 7
    turn_id = Column(UUID(as_uuid=True), ForeignKey("turns.id", ondelete="CASCADE"), nullable=True)
    disclosed_data = Column(JSONB, nullable=False)  # 全クラブの公開データ
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    season = relationship("Season")
    turn = relationship("Turn")

    __table_args__ = (
        UniqueConstraint("season_id", "disclosure_type", "disclosure_month", name="uq_season_disclosure"),
    )


class GameFinalResult(Base):
    """PR9: ゲーム最終結果 - v1Spec Section 1.2"""
    __tablename__ = "game_final_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_id = Column(UUID(as_uuid=True), ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    club_id = Column(UUID(as_uuid=True), ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False)

    # 売上規模（最終期）
    final_sales_amount = Column(Numeric(20, 0), nullable=False)
    final_sales_rank = Column(Integer, nullable=False)

    # 純資産（期末現金残高）
    final_equity_amount = Column(Numeric(20, 0), nullable=False)
    final_equity_rank = Column(Integer, nullable=False)

    # 成績
    championship_count = Column(Integer, nullable=False, default=0)
    runner_up_count = Column(Integer, nullable=False, default=0)
    average_rank = Column(Numeric(4, 2), nullable=False)
    seasons_played = Column(Integer, nullable=False)

    # 入場者数
    total_home_attendance = Column(Numeric(20, 0), nullable=False)
    average_home_attendance = Column(Integer, nullable=False)
    attendance_rank = Column(Integer, nullable=False)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    game = relationship("Game")
    club = relationship("Club")

    __table_args__ = (
        UniqueConstraint("game_id", "club_id", name="uq_game_club_result"),
    )

