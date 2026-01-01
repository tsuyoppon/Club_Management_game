from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional
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
    reinforcement_budget: Optional[Decimal] = Field(None, ge=0, description="翌シーズン強化費（6月・7月で合算）")
    
    # 5.4 営業リソース配分（四半期開始月のみ: 8/11/2/5月）
    sales_allocation_new: Optional[float] = Field(None, ge=0.0, le=1.0, description="新規営業配分率 ρ^new")

    class Config:
        # Allow extra fields for backward compatibility
        extra = "allow"


class DecisionValidationResult(BaseModel):
    """バリデーション結果"""
    is_valid: bool
    errors: List[str] = []


class DecisionRead(BaseModel):
    """ターン入力の参照用レスポンス"""
    turn_id: UUID
    season_id: UUID
    club_id: UUID
    month_index: int
    month_name: str
    decision_state: DecisionState
    payload: Optional[dict] = None
    committed_at: Optional[datetime] = None
    committed_by_user_id: Optional[UUID] = None


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


class StaffEntryRead(BaseModel):
    """スタッフ配置の参照用スナップショット"""
    role: str
    count: int
    salary_per_person: float
    next_count: Optional[int] = None
    hiring_target: Optional[int] = None
    updated_at: datetime


class StaffHistoryEntry(BaseModel):
    """月次スタッフコストから再構成した履歴"""
    turn_id: UUID
    season_id: UUID
    month_index: int
    month_name: str
    total_cost: float
    staff: Dict[str, dict]
    created_at: datetime


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


class ClubFinancialLedgerRead(BaseModel):
    turn_id: UUID
    month_index: int
    kind: str
    amount: float
    meta: Optional[dict]

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


# =============================================================================
# PR7: スポンサー営業モデル用スキーマ
# =============================================================================

class SalesAllocationUpdate(BaseModel):
    """四半期営業リソース配分の更新"""
    rho_new: float = Field(..., ge=0.0, le=1.0, description="新規営業配分率 (0.0〜1.0)")


class SalesAllocationRead(BaseModel):
    """四半期営業リソース配分の読み取り"""
    club_id: UUID
    season_id: UUID
    quarter: int
    rho_new: float
    
    class Config:
        orm_mode = True


class SalesEffortRead(BaseModel):
    """営業努力状況"""
    month_index: int
    rho_new: float
    e_ret: float  # 既存向け月次努力
    e_new: float  # 新規向け月次努力
    c_ret: float  # 累積努力（既存）
    c_new: float  # 累積努力（新規）


class PipelineStatusRead(BaseModel):
    """スポンサーパイプライン状況"""
    current_sponsors: int
    next_exist_target: Optional[int]  # N^exist_next
    next_new_target: Optional[int]    # N^new_next
    confirmed_exist: int              # 既存確定数
    confirmed_new: int                # 新規確定数
    total_confirmed: int              # 確定合計
    next_total: Optional[int]         # N_next（7月確定後）
    cumulative_effort_ret: float      # C^ret
    cumulative_effort_new: float      # C^new


class PipelineProgressRead(BaseModel):
    """パイプライン進捗（月次）"""
    month_index: int
    delta_exist: int     # 今月の既存確定増分
    delta_new: int       # 今月の新規確定増分
    confirmed_exist: int # 累計既存確定
    confirmed_new: int   # 累計新規確定
    total_confirmed: int # 累計合計確定


class NextSponsorInfoRead(BaseModel):
    """次年度スポンサー情報（7月UI表示用）"""
    next_sponsors_total: int
    next_sponsors_exist: int
    next_sponsors_new: int
    unit_price: float
    expected_revenue: float
    is_finalized: bool


# =============================================================================
# PR8: 債務超過・勝点剥奪スキーマ - v1Spec Section 1.1, 14.1
# =============================================================================

class BankruptcyStatusRead(BaseModel):
    """債務超過状態レスポンス"""
    club_id: UUID
    is_bankrupt: bool
    bankrupt_since_turn_id: Optional[UUID] = None
    bankrupt_since_month: Optional[str] = None
    point_penalty_applied: bool
    total_penalty_points: int
    can_add_reinforcement: bool

    class Config:
        from_attributes = True


class PointPenaltyRead(BaseModel):
    """勝点剥奪履歴レスポンス"""
    id: UUID
    club_id: UUID
    season_id: UUID
    turn_id: UUID
    points_deducted: int
    reason: str
    created_at: datetime

    class Config:
        from_attributes = True


class BankruptClubSummary(BaseModel):
    """債務超過クラブサマリー"""
    club_id: UUID
    club_name: str
    is_bankrupt: bool
    bankrupt_since_month: Optional[str] = None
    penalty_points: int


class LastPlacePenaltyUpdate(BaseModel):
    """最下位ペナルティ設定更新"""
    enabled: bool


class LastPlacePenaltyRead(BaseModel):
    """最下位ペナルティ設定取得"""
    game_id: UUID
    last_place_penalty_enabled: bool


# =============================================================================
# PR9: 情報公開イベントと最終結果表示（v1Spec Section 1.2, 4, 13）
# =============================================================================

class TeamPowerEntry(BaseModel):
    """チーム力指標エントリ"""
    club_id: UUID
    club_name: str
    team_power: Decimal

    class Config:
        from_attributes = True


class TeamPowerRead(BaseModel):
    """チーム力指標公開レスポンス"""
    clubs: List[TeamPowerEntry]
    disclosure_type: str  # 'team_power_december' or 'team_power_july'
    disclosed_at: datetime


class FinancialSummaryEntry(BaseModel):
    """財務サマリーエントリ"""
    club_id: UUID
    club_name: str
    total_revenue: int
    total_expense: int
    net_income: int
    ending_balance: int
    fiscal_year: str


class FinancialSummaryRead(BaseModel):
    """財務サマリー公開レスポンス"""
    clubs: List[FinancialSummaryEntry]


class PublicDisclosureRead(BaseModel):
    """公開情報レスポンス"""
    id: UUID
    season_id: UUID
    disclosure_type: str
    disclosure_month: int
    disclosed_data: dict
    created_at: datetime

    class Config:
        from_attributes = True


class ExtendedStandingsEntry(BaseModel):
    """拡張順位表エントリ（5月用）"""
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
    penalty: Optional[int] = 0
    title: Optional[str] = None  # '優勝', '準優勝', or None
    avg_home_attendance: Optional[int] = None


class GameFinalResultRead(BaseModel):
    """ゲーム最終結果レスポンス"""
    club_id: UUID
    club_name: str
    final_sales_amount: int
    final_sales_rank: int
    final_equity_amount: int
    final_equity_rank: int
    championship_count: int
    runner_up_count: int
    average_rank: Decimal
    seasons_played: int
    total_home_attendance: int
    average_home_attendance: int
    attendance_rank: int

    class Config:
        from_attributes = True

