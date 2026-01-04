"""
PR9: 情報公開イベントと最終結果表示API
v1Spec Section 1.2, 4, 13
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List, Optional

from app.db.session import get_db
from app.db.models import Season, Game, Turn
from app.schemas import (
    PublicDisclosureRead,
    ExtendedStandingsEntry,
    GameFinalResultRead,
)
from app.services import public_disclosure as disclosure_service
from app.services import final_results as final_results_service
from app.services.standings import StandingsCalculator
from app.config.constants import DISCLOSURE_MONTH_MAY

# Prefix is provided via main.py include_router(prefix=settings.api_prefix)
router = APIRouter(tags=["disclosures"])


# =============================================================================
# 公開情報API
# =============================================================================

@router.get("/seasons/{season_id}/disclosures", response_model=List[PublicDisclosureRead])
def get_all_disclosures(
    season_id: UUID,
    db: Session = Depends(get_db)
):
    """
    シーズンの全公開情報を取得
    """
    season = db.query(Season).filter(Season.id == season_id).first()
    if not season:
        raise HTTPException(status_code=404, detail="Season not found")
    
    disclosures = disclosure_service.get_all_disclosures(db, season_id)
    return disclosures


@router.get("/seasons/{season_id}/disclosures/{disclosure_type}")
def get_disclosure_by_type(
    season_id: UUID,
    disclosure_type: str,
    db: Session = Depends(get_db)
):
    """
    特定種別の公開情報を取得
    
    disclosure_type:
    - financial_summary: 財務サマリー（12月公開）
    - team_power_december: チーム力指標（12月公開）
    - team_power_july: チーム力指標（7月公開、不確実性付き）
    """
    season = db.query(Season).filter(Season.id == season_id).first()
    if not season:
        raise HTTPException(status_code=404, detail="Season not found")
    
    disclosure = disclosure_service.get_latest_disclosure(db, season_id, disclosure_type)
    if not disclosure:
        raise HTTPException(status_code=404, detail=f"Disclosure of type '{disclosure_type}' not found")
    
    return disclosure


@router.get("/seasons/{season_id}/team-power")
def get_team_power(
    season_id: UUID,
    db: Session = Depends(get_db)
):
    """
    最新のチーム力指標を取得（12月または7月の公開値）
    
    v1Spec Section 4.2:
    - 7月ターン終了時：次シーズンのチーム力指標を公開（不確実性付き）
    - 12月ターン終了時：チーム力指標を再公開（"最新"）
    """
    season = db.query(Season).filter(Season.id == season_id).first()
    if not season:
        raise HTTPException(status_code=404, detail="Season not found")
    
    # 7月公開を優先、なければ12月公開、さらに引き継ぎ（7月公開値）を参照
    july_disclosure = disclosure_service.get_latest_disclosure(
        db, season_id, "team_power_july"
    )
    if july_disclosure:
        return july_disclosure
    
    december_disclosure = disclosure_service.get_latest_disclosure(
        db, season_id, "team_power_december"
    )
    if december_disclosure:
        return december_disclosure

    carried_disclosure = disclosure_service.get_latest_disclosure(
        db, season_id, "team_power_july_carried"
    )
    if carried_disclosure:
        return carried_disclosure
    
    raise HTTPException(status_code=404, detail="Team power disclosure not found")


# =============================================================================
# 拡張順位表API（5月用）
# =============================================================================

@router.get("/seasons/{season_id}/standings/extended", response_model=List[ExtendedStandingsEntry])
def get_extended_standings(
    season_id: UUID,
    db: Session = Depends(get_db)
):
    """
    拡張順位表を取得（5月用追加情報含む）
    
    v1Spec Section 13.2:
    - 1位「優勝」、2位「準優勝」を横に表示
    - 各クラブの平均入場者数（ホームゲーム平均）を順位表に追加
    """
    season = db.query(Season).filter(Season.id == season_id).first()
    if not season:
        raise HTTPException(status_code=404, detail="Season not found")
    
    calculator = StandingsCalculator(db, season_id)
    standings = calculator.calculate_with_may_extras()
    
    return standings


# =============================================================================
# 最終結果API
# =============================================================================

@router.get("/games/{game_id}/final-results", response_model=List[GameFinalResultRead])
def get_final_results(
    game_id: UUID,
    db: Session = Depends(get_db)
):
    """
    ゲーム最終結果を取得
    
    v1Spec Section 1.2:
    - 売上規模（最終期）：金額＋順位
    - 純資産（＝期末現金残高）：金額＋順位
    - 成績：優勝回数、準優勝回数、平均順位
    - ホームゲーム平均入場者数（全シーズン）：人数＋順位
    """
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    
    # 既存結果があれば返す
    results = final_results_service.get_final_results(db, game_id)
    if results:
        return results
    
    # なければ計算して返す（保存もされる）
    results = final_results_service.generate_final_results(db, game_id)
    db.commit()
    
    return results


@router.post("/games/{game_id}/final-results/generate", response_model=List[GameFinalResultRead])
def generate_final_results(
    game_id: UUID,
    db: Session = Depends(get_db)
):
    """
    ゲーム最終結果を生成（再計算）
    
    既存の結果がある場合は上書き更新する。
    """
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    
    results = final_results_service.generate_final_results(db, game_id)
    db.commit()
    
    return results
