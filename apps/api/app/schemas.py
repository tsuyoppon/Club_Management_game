from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.db.models import DecisionState, MatchStatus, MembershipRole, SeasonStatus, TurnState


class GameCreate(BaseModel):
    name: str


class GameRead(BaseModel):
    id: UUID
    name: str
    status: str
    created_at: datetime

    class Config:
        orm_mode = True


class ClubCreate(BaseModel):
    name: str
    short_name: Optional[str] = None


class ClubRead(BaseModel):
    id: UUID
    name: str
    short_name: Optional[str] = None
    game_id: UUID

    class Config:
        orm_mode = True


class MembershipCreate(BaseModel):
    email: str
    display_name: Optional[str] = None
    role: MembershipRole
    club_id: Optional[UUID] = None


class SeasonCreate(BaseModel):
    year_label: str


class SeasonRead(BaseModel):
    id: UUID
    game_id: UUID
    year_label: str
    status: SeasonStatus

    class Config:
        orm_mode = True


class FixtureGenerateRequest(BaseModel):
    force: bool = False


class SeasonScheduleItem(BaseModel):
    month_index: int
    month_name: str
    fixtures: list


class DecisionCommitRequest(BaseModel):
    payload: Optional[dict] = None


class DecisionPayload(BaseModel):
    """
    月次入力項目（v1Spec Section 5）
    すべてOptionalとし、未入力は0として扱う
    """
    # 5.1 毎月入力（通年：8〜7月）
    sales_expense: Optional[Decimal] = Field(None, ge=0, description="営業費用（当月）")
    promo_expense: Optional[Decimal] = Field(None, ge=0, description="プロモーション費用（当月）")
    hometown_expense: Optional[Decimal] = Field(None, ge=0, description="ホームタウン活動費用（当月）")
    
    # 5.2 条件付き入力
    next_home_promo: Optional[Decimal] = Field(None, ge=0, description="翌月ホームゲーム向けプロモ費")
    additional_reinforcement: Optional[Decimal] = Field(None, ge=0, description="追加強化費（12月のみ）")
    
    # 5.4 営業リソース配分（四半期開始月のみ: 8/11/2/5月）
    sales_allocation_new: Optional[float] = Field(None, ge=0.0, le=1.0, description="新規営業配分率 ρ^new")

    class Config:
        # Allow extra fields for backward compatibility
        extra = "allow"


class DecisionValidationResult(BaseModel):
    """バリデーション結果"""
    is_valid: bool
    errors: List[str] = []


class AckRequest(BaseModel):
    club_id: UUID
    ack: bool = Field(True)


class TurnStateResponse(BaseModel):
    id: UUID
    season_id: UUID
    month_index: int
    month_name: str
    month_number: int
    turn_state: TurnState

    class Config:
        orm_mode = True


class FixtureView(BaseModel):
    id: UUID
    match_month_index: int
    match_month_name: str
    home_club_id: Optional[UUID]
    away_club_id: Optional[UUID]
    is_bye: bool
    bye_club_id: Optional[UUID]
    status: MatchStatus
    weather: Optional[str] = None
    home_attendance: Optional[int] = None
    away_attendance: Optional[int] = None
    total_attendance: Optional[int] = None


class SponsorEffortUpdate(BaseModel):
    effort: int = Field(..., ge=0, le=100, description="Sales effort percentage (0-100)")


class StaffPlanUpdate(BaseModel):
    role: str
    count: int = Field(..., ge=1, description="Target number of staff")


class AcademyBudgetUpdate(BaseModel):
    annual_budget: int = Field(..., ge=0, description="Annual budget for next season")


class ClubScheduleItem(BaseModel):
    month_index: int
    month_name: str
    opponent: Optional[str]
    home: bool
    is_bye: bool
    status: Optional[MatchStatus] = None
    home_goals: Optional[int] = None
    away_goals: Optional[int] = None


class ClubFinancialProfileUpdate(BaseModel):
    sponsor_base_monthly: Optional[float] = None
    sponsor_per_point: Optional[float] = None
    monthly_cost: Optional[float] = None


class ClubFinancialProfileRead(BaseModel):
    id: UUID
    club_id: UUID
    currency_code: str
    sponsor_base_monthly: float
    sponsor_per_point: float
    monthly_cost: float
    updated_at: datetime

    class Config:
        orm_mode = True


class ClubFinancialStateRead(BaseModel):
    id: UUID
    club_id: UUID
    balance: float
    last_applied_turn_id: Optional[UUID]
    updated_at: datetime

    class Config:
        orm_mode = True


class ClubFinancialSnapshotRead(BaseModel):
    id: UUID
    club_id: UUID
    season_id: UUID
    turn_id: UUID
    month_index: int
    opening_balance: float
    income_total: float
    expense_total: float
    closing_balance: float
    created_at: datetime

    class Config:
        orm_mode = True

class StandingRead(BaseModel):
    rank: int
    club_id: UUID
    club_name: str
    played: int
    won: int
    drawn: int
    lost: int
    gf: int
    ga: int
    gd: int
    points: int

    class Config:
        orm_mode = True

class SeasonStatusRead(BaseModel):
    season_id: UUID
    is_finalized: bool
    finalized_at: Optional[datetime]
    is_completed: bool
    total_fixtures: int
    played_matches: int
    missing_matches: int
    unplayed_matches: int
    warnings: List[str] = []


class FanbaseStateRead(BaseModel):
    id: UUID
    club_id: UUID
    season_id: UUID
    fb_count: int
    fb_rate: float
    cumulative_promo: float
    cumulative_ht: float
    last_ht_spend: float
    followers_public: Optional[int]
    updated_at: datetime

    class Config:
        orm_mode = True


class FanIndicatorRead(BaseModel):
    club_id: UUID
    followers: int
