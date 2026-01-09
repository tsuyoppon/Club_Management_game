from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.db import models
from app.schemas import ClubFinancialProfileUpdate

def ensure_finance_initialized_for_club(db: Session, club_id: UUID):
    """
    Ensure that a club has a financial profile and state.
    If not, create them with default values.
    """
    # Check profile
    profile = db.execute(select(models.ClubFinancialProfile).where(models.ClubFinancialProfile.club_id == club_id)).scalar_one_or_none()
    if not profile:
        profile = models.ClubFinancialProfile(club_id=club_id)
        db.add(profile)
    
    # Check state
    state = db.execute(select(models.ClubFinancialState).where(models.ClubFinancialState.club_id == club_id)).scalar_one_or_none()
    if not state:
        state = models.ClubFinancialState(club_id=club_id)
        db.add(state)
    
    db.flush()
    return profile, state

def update_financial_profile(db: Session, club_id: UUID, update_data: ClubFinancialProfileUpdate):
    profile, _ = ensure_finance_initialized_for_club(db, club_id)
    
    if update_data.sponsor_base_monthly is not None:
        profile.sponsor_base_monthly = update_data.sponsor_base_monthly
    if update_data.sponsor_per_point is not None:
        profile.sponsor_per_point = update_data.sponsor_per_point
    if update_data.monthly_cost is not None:
        profile.monthly_cost = update_data.monthly_cost
    
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile

def get_financial_state(db: Session, club_id: UUID):
    _, state = ensure_finance_initialized_for_club(db, club_id)
    return state

def get_financial_snapshots(db: Session, club_id: UUID, season_id: UUID):
    stmt = select(models.ClubFinancialSnapshot).where(
        models.ClubFinancialSnapshot.club_id == club_id,
        models.ClubFinancialSnapshot.season_id == season_id
    ).order_by(models.ClubFinancialSnapshot.month_index)
    return db.execute(stmt).scalars().all()

def apply_finance_for_turn(db: Session, season_id: UUID, turn_id: UUID):
    """
    Calculate and apply finances for all clubs in the given turn.
    Idempotent: if snapshot exists for (club_id, turn_id), skip.
    """
    # Get turn info to know the month (if needed) or just process all clubs
    turn = db.execute(select(models.Turn).where(models.Turn.id == turn_id)).scalar_one_or_none()
    if not turn:
        raise ValueError(f"Turn {turn_id} not found")
    
    # Get all clubs in the game (assuming turn belongs to a season -> game)
    # We need to find the game_id from season_id
    season = db.execute(select(models.Season).where(models.Season.id == season_id)).scalar_one_or_none()
    if not season:
        raise ValueError(f"Season {season_id} not found")
    
    clubs = db.execute(select(models.Club).where(models.Club.game_id == season.game_id)).scalars().all()
    
from app.services import sponsor, reinforcement, staff, academy, ticket, fanbase, standings
from app.services import distribution, decision_expense, merchandise, match_operation, prize
from app.services import sales_effort
from app.services import historical_performance
from decimal import Decimal

def process_turn_expenses(db: Session, season_id: UUID, turn_id: UUID):
    """
    Process expenses and state updates (FB) BEFORE matches.
    """
    turn = db.execute(select(models.Turn).where(models.Turn.id == turn_id)).scalar_one_or_none()
    if not turn:
        raise ValueError(f"Turn {turn_id} not found")
    
    season = db.execute(select(models.Season).where(models.Season.id == season_id)).scalar_one_or_none()
    if not season:
        raise ValueError(f"Season {season_id} not found")
    
    clubs = db.execute(select(models.Club).where(models.Club.game_id == season.game_id)).scalars().all()
    
    # Pre-calculate standings for FB update (previous month)
    perf_map = {}
    if turn.month_index > 1:
        calc = standings.StandingsCalculator(db, season_id)
        st = calc.calculate(up_to_month=turn.month_index - 1)
        num_clubs = len(st)
        if num_clubs > 1:
            for s in st:
                rank = s["rank"]
                perf_map[s["club_id"]] = 1.0 - (rank - 1) / (num_clubs - 1)
    
    hist_perf_cache = {}

    for club in clubs:
        profile, state = ensure_finance_initialized_for_club(db, club.id)
        
        # Ensure FB state
        fb_state = fanbase.ensure_fanbase_state(db, club.id, season_id)
        
        # Get Decision
        decision = db.execute(select(models.TurnDecision).where(
            models.TurnDecision.turn_id == turn_id,
            models.TurnDecision.club_id == club.id
        )).scalar_one_or_none()
        
        promo_spend = Decimal(0)
        ht_spend = Decimal(0)
        sales_spend = Decimal(0)
        if decision and decision.payload_json:
            promo_spend = Decimal(str(decision.payload_json.get("promo_expense", 0) or 0))
            ht_spend = Decimal(str(decision.payload_json.get("hometown_expense", 0) or 0))
            sales_spend = Decimal(str(decision.payload_json.get("sales_expense", 0) or 0))
            
        # Update FB
        perf = perf_map.get(club.id, 0.5)
        if club.id not in hist_perf_cache:
            hist_perf_cache[club.id] = historical_performance.get_hist_perf_value(
                db, season_id, club.id
            )
        hist_perf = hist_perf_cache[club.id]
        fanbase.update_fanbase_for_turn(db, fb_state, promo_spend, ht_spend, perf, hist_perf)
        
        # PR7: 営業努力更新（毎月）
        sales_staff = sales_effort.get_sales_staff_count(db, club.id)
        sales_effort.process_sales_effort_for_turn(
            db, club.id, season_id, turn_id, turn.month_index, sales_staff, sales_spend
        )
        
        # PR7: パイプライン進捗（4〜6月 = month_index 9,10,11）
        if turn.month_index in [9, 10, 11]:
            sponsor.process_pipeline_progress(db, club.id, season_id, turn.month_index)
        
        # Existing Expenses
        if turn.month_index == 1: # August
            sponsor.process_sponsor_revenue(db, club.id, season_id, turn_id)
            
        if turn.month_index == 12: # July
            sponsor.determine_next_sponsors(db, club.id, season_id)
            
        reinforcement.process_reinforcement_cost(db, club.id, season_id, turn_id, turn.month_index)
        if turn.month_index in [11, 12]:
            # オフシーズン(6月・7月)の翌シーズン強化費を集計して次季プランに反映
            reinforcement.update_next_season_reinforcement_plan(db, club.id, season_id)
        staff.process_staff_cost(db, club.id, turn_id, turn.month_index, season_id)
        academy.process_monthly_cost(db, club.id, season_id, turn_id)
        
        if turn.month_index == 12: # July
            academy.process_transfer_fee(db, club.id, season_id, turn_id)
            
        # PR6: 月次入力費用の計上（decision_expenseサービス経由）
        if decision and decision.payload_json:
            decision_expense.process_decision_expenses(db, club.id, turn_id, decision.payload_json)
            
    db.flush()

def finalize_turn_finance(db: Session, season_id: UUID, turn_id: UUID):
    """
    Process revenue (Ticket) and create Snapshot AFTER matches.
    """
    turn = db.execute(select(models.Turn).where(models.Turn.id == turn_id)).scalar_one_or_none()
    if not turn:
        raise ValueError(f"Turn {turn_id} not found")
    
    season = db.execute(select(models.Season).where(models.Season.id == season_id)).scalar_one_or_none()
    if not season:
        raise ValueError(f"Season {season_id} not found")
    
    clubs = db.execute(select(models.Club).where(models.Club.game_id == season.game_id)).scalars().all()
    
    for club in clubs:
        profile, state = ensure_finance_initialized_for_club(db, club.id)
        
        # Check idempotency (Snapshot)
        existing = db.execute(select(models.ClubFinancialSnapshot).where(
            models.ClubFinancialSnapshot.club_id == club.id,
            models.ClubFinancialSnapshot.turn_id == turn_id
        )).scalar_one_or_none()
        
        if existing:
            continue
            
        # PR6: 配分金（8月一括入金）
        distribution.process_distribution_revenue(db, club.id, season_id, turn_id, turn.month_index)

        # Ticket Revenue (Now uses Fixture attendance)
        ticket.process_ticket_revenue(db, club.id, season_id, turn_id, turn.month_index)
        
        # PR6: 物販収入・費用（ホームゲーム月）
        merchandise.process_merchandise(db, club.id, season_id, turn_id, turn.month_index)
        
        # PR6: 試合運営費（ホームゲーム月）
        match_operation.process_match_operation_cost(db, club.id, season_id, turn_id, turn.month_index)
        
        # PR6: 賞金（6月）
        prize.process_prize_revenue(db, club.id, season_id, turn_id, turn.month_index)
        
        # Base Monthly Items (Legacy/Fixed)
        income_sponsor = profile.sponsor_base_monthly
        expense_fixed = profile.monthly_cost

        # Skip zero-value sponsor entries to avoid cluttering PL with meaningless rows.
        if income_sponsor and income_sponsor != 0:
            db.add(models.ClubFinancialLedger(
                club_id=club.id,
                turn_id=turn_id,
                kind="sponsor",
                amount=income_sponsor,
                meta={"description": "Monthly Sponsor Income (Base)"}
            ))
        
        db.add(models.ClubFinancialLedger(
            club_id=club.id,
            turn_id=turn_id,
            kind="admin_cost",
            amount=-expense_fixed,
            meta={"description": "Monthly Administrative Cost"}
        ))
        
        db.flush()
        
        # Snapshot
        ledgers = db.execute(select(models.ClubFinancialLedger).where(
            models.ClubFinancialLedger.club_id == club.id,
            models.ClubFinancialLedger.turn_id == turn_id
        )).scalars().all()
        
        turn_income = sum(l.amount for l in ledgers if l.amount > 0)
        turn_expense = sum(l.amount for l in ledgers if l.amount < 0)
        
        opening_balance = state.balance
        net_change = turn_income + turn_expense
        closing_balance = opening_balance + net_change
        
        snapshot = models.ClubFinancialSnapshot(
            club_id=club.id,
            season_id=season_id,
            turn_id=turn_id,
            month_index=turn.month_index,
            opening_balance=opening_balance,
            income_total=turn_income,
            expense_total=turn_expense,
            closing_balance=closing_balance
        )
        db.add(snapshot)
        
        # Update State
        state.balance = closing_balance
        state.last_applied_turn_id = turn_id
        db.add(state)
        
        # PR8: 債務超過チェック（balance < 0 で債務超過判定）
        from app.services.bankruptcy import check_bankruptcy, apply_point_penalty
        if check_bankruptcy(db, club.id, turn_id):
            # 債務超過になった場合、勝点剥奪を適用
            apply_point_penalty(db, club.id, season_id, turn_id)
        
    db.commit()

# Deprecated wrapper for backward compatibility (if needed, but we will update caller)
def apply_finance_for_turn(db: Session, season_id: UUID, turn_id: UUID):
    process_turn_expenses(db, season_id, turn_id)
    finalize_turn_finance(db, season_id, turn_id)
