"""
PR7: 営業努力計算サービス (v1Spec Section 10.2-10.4)

月次営業努力（E）とEWMA累積営業努力（C）を計算・更新
"""
from uuid import UUID
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db import models
from app.config.constants import (
    SALES_EFFORT_WS_RET, SALES_EFFORT_WM_RET,
    SALES_EFFORT_WS_NEW, SALES_EFFORT_WM_NEW,
    SALES_EFFORT_LAMBDA_RET, SALES_EFFORT_LAMBDA_NEW,
    QUARTER_START_MONTHS,
)


def get_quarter_from_month_index(month_index: int) -> int:
    """
    month_indexから四半期を計算
    Q1: 1-3 (Aug-Oct), Q2: 4-6 (Nov-Jan), Q3: 7-9 (Feb-Apr), Q4: 10-12 (May-Jul)
    """
    return ((month_index - 1) // 3) + 1


def ensure_sales_allocation(
    db: Session, 
    club_id: UUID, 
    season_id: UUID, 
    quarter: int
) -> models.ClubSalesAllocation:
    """
    指定四半期の営業配分を取得（なければデフォルト0.5で作成）
    """
    allocation = db.execute(
        select(models.ClubSalesAllocation).where(
            models.ClubSalesAllocation.club_id == club_id,
            models.ClubSalesAllocation.season_id == season_id,
            models.ClubSalesAllocation.quarter == quarter
        )
    ).scalar_one_or_none()
    
    if not allocation:
        allocation = models.ClubSalesAllocation(
            club_id=club_id,
            season_id=season_id,
            quarter=quarter,
            rho_new=Decimal("0.5")  # デフォルト: 50%新規、50%既存
        )
        db.add(allocation)
        db.flush()
    
    return allocation


def set_sales_allocation(
    db: Session,
    club_id: UUID,
    season_id: UUID,
    quarter: int,
    rho_new: Decimal
) -> models.ClubSalesAllocation:
    """
    四半期の営業配分を設定
    
    Args:
        rho_new: 新規営業配分率 (0.0〜1.0)
    """
    allocation = ensure_sales_allocation(db, club_id, season_id, quarter)
    allocation.rho_new = max(Decimal("0"), min(Decimal("1"), rho_new))
    db.add(allocation)
    db.flush()
    return allocation


def get_current_allocation(
    db: Session,
    club_id: UUID,
    season_id: UUID,
    month_index: int
) -> Decimal:
    """
    現在月の営業配分（ρ^new）を取得
    """
    quarter = get_quarter_from_month_index(month_index)
    allocation = ensure_sales_allocation(db, club_id, season_id, quarter)
    return Decimal(str(allocation.rho_new))


def calculate_monthly_effort(
    sales_staff: int,
    sales_spend: Decimal,
    rho_new: Decimal
) -> tuple[Decimal, Decimal]:
    """
    月次有効営業努力を計算 (v1Spec Section 10.3)
    
    E^ret = w_s^ret * RetStaff + w_m^ret * (RetSpend / 10^6)
    E^new = w_s^new * NewStaff + w_m^new * (NewSpend / 10^6)
    
    Returns:
        (E_ret, E_new): 既存・新規の有効営業努力
    """
    rho_ret = Decimal("1") - rho_new
    
    # 人員配分
    ret_staff = rho_ret * Decimal(sales_staff)
    new_staff = rho_new * Decimal(sales_staff)
    
    # 費用配分
    ret_spend = rho_ret * sales_spend
    new_spend = rho_new * sales_spend
    
    # 有効営業努力
    e_ret = (
        SALES_EFFORT_WS_RET * ret_staff + 
        SALES_EFFORT_WM_RET * (ret_spend / Decimal("1000000"))
    )
    e_new = (
        SALES_EFFORT_WS_NEW * new_staff + 
        SALES_EFFORT_WM_NEW * (new_spend / Decimal("1000000"))
    )
    
    return e_ret, e_new


def update_cumulative_effort(
    sponsor_state: models.ClubSponsorState,
    e_ret: Decimal,
    e_new: Decimal
) -> None:
    """
    累積営業努力をEWMA更新 (v1Spec Section 10.4)
    
    C^ret(t) = (1 - λ_ret) * C^ret(t-1) + λ_ret * E^ret(t)
    C^new(t) = (1 - λ_new) * C^new(t-1) + λ_new * E^new(t)
    """
    c_ret_prev = Decimal(str(sponsor_state.cumulative_effort_ret))
    c_new_prev = Decimal(str(sponsor_state.cumulative_effort_new))
    
    c_ret_new = (
        (Decimal("1") - SALES_EFFORT_LAMBDA_RET) * c_ret_prev +
        SALES_EFFORT_LAMBDA_RET * e_ret
    )
    c_new_new = (
        (Decimal("1") - SALES_EFFORT_LAMBDA_NEW) * c_new_prev +
        SALES_EFFORT_LAMBDA_NEW * e_new
    )
    
    sponsor_state.cumulative_effort_ret = c_ret_new
    sponsor_state.cumulative_effort_new = c_new_new


def process_sales_effort_for_turn(
    db: Session,
    club_id: UUID,
    season_id: UUID,
    turn_id: UUID,
    month_index: int,
    sales_staff: int,
    sales_spend: Decimal
) -> dict:
    """
    ターンの営業努力処理（月次更新）
    
    Args:
        sales_staff: 営業スタッフ数
        sales_spend: 月次営業費用
    
    Returns:
        処理結果の辞書
    """
    from app.services.sponsor import ensure_sponsor_state
    
    # スポンサー状態を取得
    sponsor_state = ensure_sponsor_state(db, club_id, season_id)
    
    # 現在の配分を取得
    rho_new = get_current_allocation(db, club_id, season_id, month_index)
    
    # 月次有効営業努力を計算
    e_ret, e_new = calculate_monthly_effort(sales_staff, sales_spend, rho_new)
    
    # 累積努力を更新
    update_cumulative_effort(sponsor_state, e_ret, e_new)
    
    db.add(sponsor_state)
    db.flush()
    
    return {
        "month_index": month_index,
        "rho_new": float(rho_new),
        "e_ret": float(e_ret),
        "e_new": float(e_new),
        "c_ret": float(sponsor_state.cumulative_effort_ret),
        "c_new": float(sponsor_state.cumulative_effort_new),
    }


def get_sales_staff_count(db: Session, club_id: UUID) -> int:
    """営業スタッフ数を取得"""
    staff = db.execute(
        select(models.ClubStaff).where(
            models.ClubStaff.club_id == club_id,
            models.ClubStaff.role == models.StaffRole.sales
        )
    ).scalar_one_or_none()
    
    return staff.count if staff else 1


def is_quarter_start_month(month_index: int) -> bool:
    """四半期開始月かどうか (1=Aug, 4=Nov, 7=Feb, 10=May)"""
    return month_index in QUARTER_START_MONTHS
