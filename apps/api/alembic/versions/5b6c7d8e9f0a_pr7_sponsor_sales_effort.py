"""PR7: Sponsor Sales Effort Model

Revision ID: 5b6c7d8e9f0a
Revises: 4a2b3c4d5e6f
Create Date: 2024-12-20

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '5b6c7d8e9f0a'
down_revision = '4a2b3c4d5e6f'
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns to club_sponsor_states
    op.add_column('club_sponsor_states', sa.Column('cumulative_effort_ret', sa.Numeric(14, 4), nullable=False, server_default='0'))
    op.add_column('club_sponsor_states', sa.Column('cumulative_effort_new', sa.Numeric(14, 4), nullable=False, server_default='0'))
    op.add_column('club_sponsor_states', sa.Column('pipeline_confirmed_exist', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('club_sponsor_states', sa.Column('pipeline_confirmed_new', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('club_sponsor_states', sa.Column('next_exist_count', sa.Integer(), nullable=True))
    op.add_column('club_sponsor_states', sa.Column('next_new_count', sa.Integer(), nullable=True))

    # Create club_sales_allocations table
    op.create_table('club_sales_allocations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('club_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('season_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('quarter', sa.Integer(), nullable=False),
        sa.Column('rho_new', sa.Numeric(5, 4), nullable=False, server_default='0.5'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['season_id'], ['seasons.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('club_id', 'season_id', 'quarter', name='uq_sales_allocation_club_season_quarter')
    )


def downgrade():
    # Drop club_sales_allocations table
    op.drop_table('club_sales_allocations')

    # Remove columns from club_sponsor_states
    op.drop_column('club_sponsor_states', 'next_new_count')
    op.drop_column('club_sponsor_states', 'next_exist_count')
    op.drop_column('club_sponsor_states', 'pipeline_confirmed_new')
    op.drop_column('club_sponsor_states', 'pipeline_confirmed_exist')
    op.drop_column('club_sponsor_states', 'cumulative_effort_new')
    op.drop_column('club_sponsor_states', 'cumulative_effort_ret')
