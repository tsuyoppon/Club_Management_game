"""
PR9: 公開イベント処理サービス
v1Spec Section 4

12月・7月のターン終了時に行う情報公開処理を実装。
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from app.db.models import (
    Season, Turn, Club, ClubFinancialSnapshot,
    SeasonPublicDisclosure, SeasonFinalStanding,
)
from app.config.constants import (
    DISCLOSURE_MONTH_DECEMBER,
    DISCLOSURE_MONTH_JULY,
)
from app.services.team_power import get_all_clubs_team_power, get_all_clubs_team_power_for_july


def publish_financial_summary(
    db: Session,
    season_id: UUID,
    turn_id: UUID,
) -> dict:
    """
    12月ターン終了時：全クラブの前期財務サマリーを公開
    
    v1Spec Section 4.3:
    - 12月ターン終了時：全クラブの前期財務サマリー（PL/BS簡易）を公開
    
    注意: 「前期」= 前シーズン（8月〜7月）のデータ
    最初のシーズンの場合は前期データがないため、当期の途中データを使用
    """
    season = db.query(Season).filter(Season.id == season_id).first()
    if not season:
        return {}
    
    # 前シーズンを取得（同じゲームで、finalized済みの最新シーズン）
    previous_season = db.query(Season).filter(
        and_(
            Season.game_id == season.game_id,
            Season.is_finalized == True,
            Season.id != season_id,
        )
    ).order_by(Season.created_at.desc()).first()
    
    clubs = db.query(Club).filter(Club.game_id == season.game_id).all()
    
    disclosed_data = []
    for club in clubs:
        if previous_season:
            # 前シーズンの財務サマリーを取得
            summary = _get_season_financial_summary(db, club.id, previous_season.id)
            summary["fiscal_year"] = previous_season.year_label
        else:
            # 前シーズンがない場合、当期の途中データを使用
            summary = _get_partial_season_summary(db, club.id, season_id)
            summary["fiscal_year"] = f"{season.year_label} (途中)"
        
        summary["club_id"] = str(club.id)
        summary["club_name"] = club.name
        disclosed_data.append(summary)
    
    # 公開情報を保存
    disclosure = SeasonPublicDisclosure(
        season_id=season_id,
        disclosure_type="financial_summary",
        disclosure_month=DISCLOSURE_MONTH_DECEMBER,
        turn_id=turn_id,
        disclosed_data={"clubs": disclosed_data},
    )
    
    # 既存があれば更新
    existing = db.query(SeasonPublicDisclosure).filter(
        and_(
            SeasonPublicDisclosure.season_id == season_id,
            SeasonPublicDisclosure.disclosure_type == "financial_summary",
            SeasonPublicDisclosure.disclosure_month == DISCLOSURE_MONTH_DECEMBER,
        )
    ).first()
    
    if existing:
        existing.disclosed_data = {"clubs": disclosed_data}
        existing.turn_id = turn_id
        db.add(existing)
    else:
        db.add(disclosure)
    
    db.flush()
    
    return {"clubs": disclosed_data}


def publish_team_power_december(
    db: Session,
    season_id: UUID,
    turn_id: UUID,
) -> dict:
    """
    12月ターン終了時：チーム力指標（最新）を公開
    
    v1Spec Section 4.2:
    - 12月ターン終了時：チーム力指標を再公開（"最新"）
    """
    team_powers = get_all_clubs_team_power(db, season_id, with_uncertainty=False)
    
    disclosed_data = {
        "clubs": team_powers,
        "disclosure_type": "team_power_december",
        "disclosed_at": datetime.utcnow().isoformat(),
    }
    
    # 公開情報を保存
    existing = db.query(SeasonPublicDisclosure).filter(
        and_(
            SeasonPublicDisclosure.season_id == season_id,
            SeasonPublicDisclosure.disclosure_type == "team_power_december",
            SeasonPublicDisclosure.disclosure_month == DISCLOSURE_MONTH_DECEMBER,
        )
    ).first()
    
    if existing:
        existing.disclosed_data = disclosed_data
        existing.turn_id = turn_id
        db.add(existing)
    else:
        disclosure = SeasonPublicDisclosure(
            season_id=season_id,
            disclosure_type="team_power_december",
            disclosure_month=DISCLOSURE_MONTH_DECEMBER,
            turn_id=turn_id,
            disclosed_data=disclosed_data,
        )
        db.add(disclosure)
    
    db.flush()
    
    return disclosed_data


def publish_team_power_july(
    db: Session,
    season_id: UUID,
    turn_id: UUID,
) -> dict:
    """
    7月ターン終了時：次シーズンのチーム力指標を公開（不確実性付き）
    
    v1Spec Section 4.2:
    - 7月ターン終了時：次シーズンのチーム力指標を公開（不確実性付き）
    """
    team_powers = get_all_clubs_team_power_for_july(db, season_id)
    
    # actual_team_powerは公開データから除外
    public_team_powers = []
    for tp in team_powers:
        public_tp = {
            "club_id": tp["club_id"],
            "club_name": tp["club_name"],
            "team_power": tp["team_power"],
        }
        public_team_powers.append(public_tp)
    
    disclosed_data = {
        "clubs": public_team_powers,
        "disclosure_type": "team_power_july",
        "disclosed_at": datetime.utcnow().isoformat(),
        "note": "次シーズン予測値（不確実性あり）",
    }
    
    # 公開情報を保存
    existing = db.query(SeasonPublicDisclosure).filter(
        and_(
            SeasonPublicDisclosure.season_id == season_id,
            SeasonPublicDisclosure.disclosure_type == "team_power_july",
            SeasonPublicDisclosure.disclosure_month == DISCLOSURE_MONTH_JULY,
        )
    ).first()
    
    if existing:
        existing.disclosed_data = disclosed_data
        existing.turn_id = turn_id
        db.add(existing)
    else:
        disclosure = SeasonPublicDisclosure(
            season_id=season_id,
            disclosure_type="team_power_july",
            disclosure_month=DISCLOSURE_MONTH_JULY,
            turn_id=turn_id,
            disclosed_data=disclosed_data,
        )
        db.add(disclosure)
    
    db.flush()
    
    return disclosed_data


def get_latest_disclosure(
    db: Session,
    season_id: UUID,
    disclosure_type: str,
) -> Optional[dict]:
    """
    最新の公開情報を取得
    """
    disclosure = db.query(SeasonPublicDisclosure).filter(
        and_(
            SeasonPublicDisclosure.season_id == season_id,
            SeasonPublicDisclosure.disclosure_type == disclosure_type,
        )
    ).order_by(SeasonPublicDisclosure.created_at.desc()).first()
    
    if not disclosure:
        return None
    
    return {
        "id": str(disclosure.id),
        "season_id": str(disclosure.season_id),
        "disclosure_type": disclosure.disclosure_type,
        "disclosure_month": disclosure.disclosure_month,
        "disclosed_data": disclosure.disclosed_data,
        "created_at": disclosure.created_at.isoformat(),
    }


def get_all_disclosures(
    db: Session,
    season_id: UUID,
) -> List[dict]:
    """
    シーズンの全公開情報を取得
    """
    disclosures = db.query(SeasonPublicDisclosure).filter(
        SeasonPublicDisclosure.season_id == season_id
    ).order_by(SeasonPublicDisclosure.created_at.desc()).all()
    
    return [
        {
            "id": str(d.id),
            "season_id": str(d.season_id),
            "disclosure_type": d.disclosure_type,
            "disclosure_month": d.disclosure_month,
            "disclosed_data": d.disclosed_data,
            "created_at": d.created_at.isoformat(),
        }
        for d in disclosures
    ]


def _get_season_financial_summary(
    db: Session,
    club_id: UUID,
    season_id: UUID,
) -> dict:
    """
    完了したシーズンの財務サマリーを取得
    """
    snapshots = db.query(ClubFinancialSnapshot).filter(
        and_(
            ClubFinancialSnapshot.club_id == club_id,
            ClubFinancialSnapshot.season_id == season_id,
        )
    ).order_by(ClubFinancialSnapshot.month_index).all()
    
    if not snapshots:
        return {
            "total_revenue": 0,
            "total_expense": 0,
            "net_income": 0,
            "ending_balance": 0,
        }
    
    total_revenue = sum(int(s.income_total or 0) for s in snapshots)
    total_expense = sum(int(s.expense_total or 0) for s in snapshots)
    net_income = total_revenue + total_expense  # expense_total is negative
    ending_balance = int(snapshots[-1].closing_balance or 0)
    
    return {
        "total_revenue": total_revenue,
        "total_expense": total_expense,
        "net_income": net_income,
        "ending_balance": ending_balance,
    }


def _get_partial_season_summary(
    db: Session,
    club_id: UUID,
    season_id: UUID,
) -> dict:
    """
    進行中シーズンの途中財務サマリーを取得
    """
    snapshots = db.query(ClubFinancialSnapshot).filter(
        and_(
            ClubFinancialSnapshot.club_id == club_id,
            ClubFinancialSnapshot.season_id == season_id,
        )
    ).order_by(ClubFinancialSnapshot.month_index).all()
    
    if not snapshots:
        return {
            "total_revenue": 0,
            "total_expense": 0,
            "net_income": 0,
            "ending_balance": 0,
        }
    
    total_revenue = sum(int(s.income_total or 0) for s in snapshots)
    total_expense = sum(int(s.expense_total or 0) for s in snapshots)
    net_income = total_revenue + total_expense  # expense_total is negative
    ending_balance = int(snapshots[-1].closing_balance or 0)
    
    return {
        "total_revenue": total_revenue,
        "total_expense": total_expense,
        "net_income": net_income,
        "ending_balance": ending_balance,
    }


def process_disclosure_for_turn(
    db: Session,
    season_id: UUID,
    turn_id: UUID,
    month_index: int,
) -> dict:
    """
    ターン解決時に呼び出される公開処理
    
    12月（month_index=5）: 財務サマリー + チーム力指標
    7月（month_index=12）: チーム力指標（不確実性付き）
    """
    results = {}
    
    if month_index == DISCLOSURE_MONTH_DECEMBER:
        # 12月ターン終了時
        results["financial_summary"] = publish_financial_summary(db, season_id, turn_id)
        results["team_power"] = publish_team_power_december(db, season_id, turn_id)
    
    elif month_index == DISCLOSURE_MONTH_JULY:
        # 7月ターン終了時
        results["team_power"] = publish_team_power_july(db, season_id, turn_id)
    
    return results


def copy_team_power_july_to_new_season(
    db: Session,
    prev_season_id: UUID,
    new_season_id: UUID,
) -> Optional[dict]:
    """
    前シーズンの7月公開team_powerを新シーズンに引き継ぐ
    
    前シーズンで公開された「次シーズンのチーム力予測値（不確実性付き）」を
    新シーズンの開始時点で参照できるように、disclosure_type='team_power_july_carried'として保存
    
    Returns:
        コピーされた公開データ、または前シーズンにデータがない場合はNone
    """
    # 前シーズンの team_power_july を取得
    prev_disclosure = db.query(SeasonPublicDisclosure).filter(
        and_(
            SeasonPublicDisclosure.season_id == prev_season_id,
            SeasonPublicDisclosure.disclosure_type == "team_power_july",
        )
    ).first()
    
    if not prev_disclosure:
        return None
    
    # 新シーズン用にデータをコピー
    carried_data = prev_disclosure.disclosed_data.copy() if prev_disclosure.disclosed_data else {}
    carried_data["carried_from_season_id"] = str(prev_season_id)
    carried_data["note"] = "前シーズン7月公開値（引き継ぎ）"
    
    # 既存チェック
    existing = db.query(SeasonPublicDisclosure).filter(
        and_(
            SeasonPublicDisclosure.season_id == new_season_id,
            SeasonPublicDisclosure.disclosure_type == "team_power_july_carried",
        )
    ).first()
    
    if existing:
        existing.disclosed_data = carried_data
        db.add(existing)
    else:
        new_disclosure = SeasonPublicDisclosure(
            season_id=new_season_id,
            disclosure_type="team_power_july_carried",
            disclosure_month=DISCLOSURE_MONTH_JULY,  # 7月
            turn_id=None,  # シーズン開始時なのでturnはない
            disclosed_data=carried_data,
        )
        db.add(new_disclosure)
    
    db.flush()
    
    return carried_data
