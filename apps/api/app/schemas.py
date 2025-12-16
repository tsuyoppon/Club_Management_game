from datetime import datetime
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


class ClubScheduleItem(BaseModel):
    month_index: int
    month_name: str
    opponent: Optional[str]
    home: bool
    is_bye: bool

