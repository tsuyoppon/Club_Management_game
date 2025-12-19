"""pr4_dynamics_tables"""

revision = '0d462c977af5'
down_revision = '012e4121df94'
branch_labels = None
depends_on = None

from alembic import op  # noqa: E402
import sqlalchemy as sa  # noqa: E402
from sqlalchemy.dialects import postgresql

def upgrade() -> None:
    # 1. Sponsor: Sales Effort History
    op.add_column('club_sponsor_states', sa.Column('sales_effort_history', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    
    # 2. Staff: Hiring Target (per role)
    op.add_column('club_staffs', sa.Column('hiring_target', sa.Integer(), nullable=True))
    
    # 3. Staff: Firing Penalty (Global hidden variable)
    op.add_column('club_financial_states', sa.Column('staff_firing_penalty', sa.Numeric(14, 4), server_default='0', nullable=False))
    
    # 4. Academy: New Table
    op.create_table('club_academies',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('club_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('season_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('annual_budget', sa.Numeric(precision=14, scale=2), server_default='0', nullable=False),
        sa.Column('cumulative_investment', sa.Numeric(precision=14, scale=2), server_default='0', nullable=False),
        sa.Column('transfer_fee_history', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['season_id'], ['seasons.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('club_id', 'season_id', name='uq_academy_club_season')
    )
    
    # 5. Ticket: Base Attendance & Price
    op.add_column('club_financial_profiles', sa.Column('base_attendance', sa.Integer(), server_default='10000', nullable=False))
    op.add_column('club_financial_profiles', sa.Column('ticket_price', sa.Numeric(14, 2), server_default='2000', nullable=False))


def downgrade() -> None:
    op.drop_column('club_financial_profiles', 'ticket_price')
    op.drop_column('club_financial_profiles', 'base_attendance')
    op.drop_table('club_academies')
    op.drop_column('club_financial_states', 'staff_firing_penalty')
    op.drop_column('club_staffs', 'hiring_target')
    op.drop_column('club_sponsor_states', 'sales_effort_history')

