"""
月次入力費用計上サービス（v1Spec Section 5, 7）
入力した月に費用を計上
"""
from uuid import UUID
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db import models


def process_decision_expenses(
    db: Session, 
    club_id: UUID, 
    turn_id: UUID, 
    payload: dict
):
    """
    月次入力項目（営業費用、プロモ費用、ホームタウン活動費用等）の費用計上
    """
    if not payload:
        return
    
    # 営業費用
    sales_exp = Decimal(str(payload.get("sales_expense", 0) or 0))
    if sales_exp > 0:
        _add_expense_ledger(db, club_id, turn_id, "sales_expense", sales_exp, "Sales Expense")
    
    # プロモ費用（当月分）- 既存のpromo_expenseを継続サポート
    promo_exp = Decimal(str(payload.get("promo_expense", 0) or 0))
    if promo_exp > 0:
        _add_expense_ledger(db, club_id, turn_id, "promo_expense", promo_exp, "Promotion Expense")
    
    # ホームタウン活動費用 - 既存のhometown_expenseを継続サポート
    ht_exp = Decimal(str(payload.get("hometown_expense", 0) or 0))
    if ht_exp > 0:
        _add_expense_ledger(db, club_id, turn_id, "hometown_expense", ht_exp, "Hometown Activity Expense")
    
    # 翌月ホーム向けプロモ費（支出は入力月で計上）
    next_promo = Decimal(str(payload.get("next_home_promo", 0) or 0))
    if next_promo > 0:
        _add_expense_ledger(db, club_id, turn_id, "next_home_promo_expense", next_promo, "Next Home Promo Expense")
    
    # 追加強化費（12月）- ClubReinforcementPlan.additional_budget更新のみ
    # 費用計上は reinforcement.py で1月〜7月に分割して行う
    add_reinf = Decimal(str(payload.get("additional_reinforcement", 0) or 0))
    if add_reinf > 0:
        # ClubReinforcementPlan.additional_budget に反映（TP計算用）
        _update_reinforcement_additional_budget(db, club_id, turn_id, add_reinf)
    
    db.flush()


def _add_expense_ledger(
    db: Session, 
    club_id: UUID, 
    turn_id: UUID, 
    kind: str, 
    amount: Decimal, 
    description: str
) -> bool:
    """
    費用Ledgerを追加（冪等性を保証）
    Returns: True if added, False if already exists
    """
    # Idempotency check
    existing = db.execute(
        select(models.ClubFinancialLedger).where(
            models.ClubFinancialLedger.club_id == club_id,
            models.ClubFinancialLedger.turn_id == turn_id,
            models.ClubFinancialLedger.kind == kind
        )
    ).scalar_one_or_none()
    
    if existing:
        return False
    
    db.add(models.ClubFinancialLedger(
        club_id=club_id,
        turn_id=turn_id,
        kind=kind,
        amount=-amount,  # 費用はマイナス
        meta={"description": description}
    ))
    return True


def _update_reinforcement_additional_budget(
    db: Session,
    club_id: UUID,
    turn_id: UUID,
    amount: Decimal
):
    """
    追加強化費をClubReinforcementPlan.additional_budgetに反映（TP計算用）
    冪等性保証: 同一ターンで既に処理済みかをLedgerで確認
    （費用計上はしないが、マーカーとしてamount=0のLedgerを作成）
    """
    # 冪等性チェック: 同一ターンで既に処理済みか
    existing_marker = db.execute(
        select(models.ClubFinancialLedger).where(
            models.ClubFinancialLedger.club_id == club_id,
            models.ClubFinancialLedger.turn_id == turn_id,
            models.ClubFinancialLedger.kind == "additional_reinforcement_applied"
        )
    ).scalar_one_or_none()
    
    if existing_marker:
        return  # 既に処理済み
    
    # turnからseason_idを取得
    turn = db.execute(
        select(models.Turn).where(models.Turn.id == turn_id)
    ).scalar_one_or_none()
    
    if not turn:
        return
    
    # ClubReinforcementPlanを取得または作成
    plan = db.execute(
        select(models.ClubReinforcementPlan).where(
            models.ClubReinforcementPlan.club_id == club_id,
            models.ClubReinforcementPlan.season_id == turn.season_id
        )
    ).scalar_one_or_none()
    
    if not plan:
        plan = models.ClubReinforcementPlan(
            club_id=club_id,
            season_id=turn.season_id,
            annual_budget=0,
            additional_budget=0,
            next_season_budget=0
        )
        db.add(plan)
        db.flush()
    
    # additional_budgetを加算（累積式: シーズン中に複数回入力される可能性を考慮）
    plan.additional_budget = Decimal(plan.additional_budget or 0) + amount
    db.add(plan)
    
    # 処理済みマーカーを追加（冪等性保証用、amount=0なので財務影響なし）
    db.add(models.ClubFinancialLedger(
        club_id=club_id,
        turn_id=turn_id,
        kind="additional_reinforcement_applied",
        amount=Decimal("0"),
        meta={"description": "Additional Reinforcement Applied Marker", "amount": float(amount)}
    ))
