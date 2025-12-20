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
    
    # 追加強化費（12月）
    add_reinf = Decimal(str(payload.get("additional_reinforcement", 0) or 0))
    if add_reinf > 0:
        _add_expense_ledger(db, club_id, turn_id, "additional_reinforcement", add_reinf, "Additional Reinforcement")
    
    db.flush()


def _add_expense_ledger(
    db: Session, 
    club_id: UUID, 
    turn_id: UUID, 
    kind: str, 
    amount: Decimal, 
    description: str
):
    """
    費用Ledgerを追加（冪等性を保証）
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
        return
    
    db.add(models.ClubFinancialLedger(
        club_id=club_id,
        turn_id=turn_id,
        kind=kind,
        amount=-amount,  # 費用はマイナス
        meta={"description": description}
    ))
