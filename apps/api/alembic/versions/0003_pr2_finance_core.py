"""PR2 finance core tables

Revision ID: 0003_pr2_finance_core
Revises: 0002_pr1_skeleton
Create Date: 2024-05-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0003_pr2_finance_core'
down_revision = '0002_pr1_skeleton'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Create club_financial_profiles
    op.create_table(
        'club_financial_profiles',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('club_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('currency_code', sa.Text(), server_default='JPY', nullable=False),
        sa.Column('sponsor_base_monthly', sa.Numeric(14, 2), server_default='0', nullable=False),
        sa.Column('sponsor_per_point', sa.Numeric(14, 2), server_default='0', nullable=False),
        sa.Column('monthly_cost', sa.Numeric(14, 2), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('club_id')
    )

    # 2. Create club_financial_states
    op.create_table(
        'club_financial_states',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('club_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('balance', sa.Numeric(14, 2), server_default='0', nullable=False),
        sa.Column('last_applied_turn_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['last_applied_turn_id'], ['turns.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('club_id')
    )

    # 3. Create club_financial_ledgers
    op.create_table(
        'club_financial_ledgers',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('club_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('turn_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('kind', sa.Text(), nullable=False),
        sa.Column('amount', sa.Numeric(14, 2), nullable=False),
        sa.Column('meta', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['turn_id'], ['turns.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('club_id', 'turn_id', 'kind', name='uq_ledger_club_turn_kind')
    )

    # 4. Create club_financial_snapshots
    op.create_table(
        'club_financial_snapshots',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('club_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('season_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('turn_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('month_index', sa.Integer(), nullable=False),
        sa.Column('opening_balance', sa.Numeric(14, 2), nullable=False),
        sa.Column('income_total', sa.Numeric(14, 2), nullable=False),
        sa.Column('expense_total', sa.Numeric(14, 2), nullable=False),
        sa.Column('closing_balance', sa.Numeric(14, 2), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['season_id'], ['seasons.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['turn_id'], ['turns.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('club_id', 'turn_id', name='uq_snapshot_club_turn')
    )

    # 5. Data Migration: Initialize profile and state for existing clubs
    connection = op.get_bind()
    clubs_result = connection.execute(sa.text("SELECT id FROM clubs"))
    
    # We need uuid generation in python or sql. 
    # Since we are in alembic, we can use uuid_generate_v4() if available, or python uuid.
    # Let's use python uuid to be safe and explicit.
    import uuid
    
    for row in clubs_result:
        club_id = row[0]
        
        # Check if profile exists (idempotency for re-runs if needed, though upgrade is usually once)
        # But strictly speaking, upgrade runs on current state.
        
        # Insert Profile
        op.execute(
            sa.text(
                "INSERT INTO club_financial_profiles (id, club_id, currency_code, sponsor_base_monthly, sponsor_per_point, monthly_cost, created_at, updated_at) "
                "VALUES (:id, :club_id, 'JPY', 0, 0, 0, NOW(), NOW()) "
                "ON CONFLICT (club_id) DO NOTHING"
            ).bindparams(id=uuid.uuid4(), club_id=club_id)
        )
        
        # Insert State
        op.execute(
            sa.text(
                "INSERT INTO club_financial_states (id, club_id, balance, created_at, updated_at) "
                "VALUES (:id, :club_id, 0, NOW(), NOW()) "
                "ON CONFLICT (club_id) DO NOTHING"
            ).bindparams(id=uuid.uuid4(), club_id=club_id)
        )


def downgrade():
    op.drop_table('club_financial_snapshots')
    op.drop_table('club_financial_ledgers')
    op.drop_table('club_financial_states')
    op.drop_table('club_financial_profiles')
