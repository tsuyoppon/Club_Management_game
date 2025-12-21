"""
PR9: 最終結果計算サービス
v1Spec Section 1.2

ゲーム終了時の総合結果を計算・保存する。
"""
from decimal import Decimal
from typing import List
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import select, and_, func

from app.db.models import (
    Game, Club, Season, SeasonFinalStanding, 
    ClubFinancialSnapshot, Fixture, GameFinalResult,
)


def generate_final_results(db: Session, game_id: UUID) -> List[dict]:
    """
    ゲーム終了時の最終結果を生成・保存
    
    v1Spec Section 1.2:
    - 売上規模（最終期）：金額＋順位
    - 純資産（＝期末現金残高）：金額＋順位
    - 成績：優勝回数、準優勝回数、平均順位
    - ホームゲーム平均入場者数（全シーズン）：人数＋順位
    """
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        return []
    
    clubs = db.query(Club).filter(Club.game_id == game_id).all()
    seasons = db.query(Season).filter(
        and_(
            Season.game_id == game_id,
            Season.is_finalized == True,
        )
    ).order_by(Season.created_at).all()
    
    if not seasons:
        return []
    
    results = []
    for club in clubs:
        # 売上規模（最終期）
        final_sales = _calculate_final_sales(db, club.id, seasons[-1].id)
        
        # 純資産（期末現金残高）
        final_equity = _get_final_balance(db, club.id, seasons[-1].id)
        
        # 成績
        championship_count = _count_championships(db, club.id, seasons)
        runner_up_count = _count_runner_ups(db, club.id, seasons)
        average_rank = _calculate_average_rank(db, club.id, seasons)
        
        # 入場者数
        total_attendance, avg_attendance = _calculate_attendance_stats(db, club.id, seasons)
        
        result = {
            "club_id": str(club.id),
            "club_name": club.name,
            "final_sales_amount": int(final_sales),
            "final_equity_amount": int(final_equity),
            "championship_count": championship_count,
            "runner_up_count": runner_up_count,
            "average_rank": float(average_rank),
            "seasons_played": len(seasons),
            "total_home_attendance": int(total_attendance),
            "average_home_attendance": int(avg_attendance),
        }
        results.append(result)
    
    # 各指標で順位付け
    _rank_by("final_sales_amount", results, "final_sales_rank", descending=True)
    _rank_by("final_equity_amount", results, "final_equity_rank", descending=True)
    _rank_by("average_home_attendance", results, "attendance_rank", descending=True)
    
    # DB保存
    _save_final_results(db, game_id, results)
    
    return results


def get_final_results(db: Session, game_id: UUID) -> List[dict]:
    """
    保存済みの最終結果を取得
    """
    results = db.query(GameFinalResult).filter(
        GameFinalResult.game_id == game_id
    ).order_by(GameFinalResult.final_sales_rank).all()
    
    return [
        {
            "club_id": str(r.club_id),
            "club_name": r.club.name if r.club else "Unknown",
            "final_sales_amount": int(r.final_sales_amount),
            "final_sales_rank": r.final_sales_rank,
            "final_equity_amount": int(r.final_equity_amount),
            "final_equity_rank": r.final_equity_rank,
            "championship_count": r.championship_count,
            "runner_up_count": r.runner_up_count,
            "average_rank": float(r.average_rank),
            "seasons_played": r.seasons_played,
            "total_home_attendance": int(r.total_home_attendance),
            "average_home_attendance": r.average_home_attendance,
            "attendance_rank": r.attendance_rank,
        }
        for r in results
    ]


def _calculate_final_sales(db: Session, club_id: UUID, season_id: UUID) -> Decimal:
    """
    最終期の売上規模（総収入）を計算
    """
    snapshots = db.query(ClubFinancialSnapshot).filter(
        and_(
            ClubFinancialSnapshot.club_id == club_id,
            ClubFinancialSnapshot.season_id == season_id,
        )
    ).all()

    total_revenue = sum(s.income_total or Decimal("0") for s in snapshots)
    return total_revenue


def _get_final_balance(db: Session, club_id: UUID, season_id: UUID) -> Decimal:
    """
    最終期の期末現金残高を取得
    """
    snapshot = db.query(ClubFinancialSnapshot).filter(
        and_(
            ClubFinancialSnapshot.club_id == club_id,
            ClubFinancialSnapshot.season_id == season_id,
        )
    ).order_by(ClubFinancialSnapshot.month_index.desc()).first()
    
    if not snapshot:
        return Decimal("0")

    return snapshot.closing_balance or Decimal("0")


def _count_championships(db: Session, club_id: UUID, seasons: List[Season]) -> int:
    """
    優勝回数をカウント
    """
    count = 0
    for season in seasons:
        standing = db.query(SeasonFinalStanding).filter(
            and_(
                SeasonFinalStanding.season_id == season.id,
                SeasonFinalStanding.club_id == club_id,
                SeasonFinalStanding.rank == 1,
            )
        ).first()
        if standing:
            count += 1
    return count


def _count_runner_ups(db: Session, club_id: UUID, seasons: List[Season]) -> int:
    """
    準優勝回数をカウント
    """
    count = 0
    for season in seasons:
        standing = db.query(SeasonFinalStanding).filter(
            and_(
                SeasonFinalStanding.season_id == season.id,
                SeasonFinalStanding.club_id == club_id,
                SeasonFinalStanding.rank == 2,
            )
        ).first()
        if standing:
            count += 1
    return count


def _calculate_average_rank(db: Session, club_id: UUID, seasons: List[Season]) -> Decimal:
    """
    平均順位を計算
    """
    ranks = []
    for season in seasons:
        standing = db.query(SeasonFinalStanding).filter(
            and_(
                SeasonFinalStanding.season_id == season.id,
                SeasonFinalStanding.club_id == club_id,
            )
        ).first()
        if standing:
            ranks.append(standing.rank)
    
    if not ranks:
        return Decimal("0")
    
    avg = sum(ranks) / len(ranks)
    return Decimal(str(round(avg, 2)))


def _calculate_attendance_stats(
    db: Session, 
    club_id: UUID, 
    seasons: List[Season]
) -> tuple:
    """
    全シーズンのホームゲーム入場者数統計を計算
    
    Returns:
        (total_attendance, average_attendance)
    """
    season_ids = [s.id for s in seasons]
    
    # ホームゲームの入場者数を集計
    fixtures = db.query(Fixture).filter(
        and_(
            Fixture.season_id.in_(season_ids),
            Fixture.home_club_id == club_id,
            Fixture.home_attendance != None,
        )
    ).all()
    
    if not fixtures:
        return (Decimal("0"), 0)
    
    total = sum(f.home_attendance or 0 for f in fixtures)
    avg = total // len(fixtures) if fixtures else 0
    
    return (Decimal(str(total)), avg)


def _rank_by(
    field: str, 
    results: List[dict], 
    rank_field: str,
    descending: bool = True
) -> None:
    """
    指定フィールドで順位付け（同値は同順位）
    """
    # ソート
    sorted_results = sorted(
        results, 
        key=lambda x: x[field], 
        reverse=descending
    )
    
    # 順位付け（同値は同順位）
    current_rank = 1
    prev_value = None
    
    for i, item in enumerate(sorted_results):
        if prev_value is not None and item[field] != prev_value:
            current_rank = i + 1
        item[rank_field] = current_rank
        prev_value = item[field]
    
    # 元のresultsに順位を反映
    rank_map = {r["club_id"]: r[rank_field] for r in sorted_results}
    for r in results:
        r[rank_field] = rank_map[r["club_id"]]


def _save_final_results(
    db: Session, 
    game_id: UUID, 
    results: List[dict]
) -> None:
    """
    最終結果をDBに保存
    """
    for r in results:
        existing = db.query(GameFinalResult).filter(
            and_(
                GameFinalResult.game_id == game_id,
                GameFinalResult.club_id == r["club_id"],
            )
        ).first()
        
        if existing:
            # 更新
            existing.final_sales_amount = r["final_sales_amount"]
            existing.final_sales_rank = r["final_sales_rank"]
            existing.final_equity_amount = r["final_equity_amount"]
            existing.final_equity_rank = r["final_equity_rank"]
            existing.championship_count = r["championship_count"]
            existing.runner_up_count = r["runner_up_count"]
            existing.average_rank = r["average_rank"]
            existing.seasons_played = r["seasons_played"]
            existing.total_home_attendance = r["total_home_attendance"]
            existing.average_home_attendance = r["average_home_attendance"]
            existing.attendance_rank = r["attendance_rank"]
            db.add(existing)
        else:
            # 新規作成
            final_result = GameFinalResult(
                game_id=game_id,
                club_id=r["club_id"],
                final_sales_amount=r["final_sales_amount"],
                final_sales_rank=r["final_sales_rank"],
                final_equity_amount=r["final_equity_amount"],
                final_equity_rank=r["final_equity_rank"],
                championship_count=r["championship_count"],
                runner_up_count=r["runner_up_count"],
                average_rank=r["average_rank"],
                seasons_played=r["seasons_played"],
                total_home_attendance=r["total_home_attendance"],
                average_home_attendance=r["average_home_attendance"],
                attendance_rank=r["attendance_rank"],
            )
            db.add(final_result)
    
    db.flush()
