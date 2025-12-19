"""add season finalization"""

revision = '33b665baeb4d'
down_revision = '0d462c977af5'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade() -> None:
    # Add columns to seasons
    op.add_column('seasons', sa.Column('is_finalized', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('seasons', sa.Column('finalized_at', sa.DateTime(), nullable=True))
    
    # Create season_final_standings table
    op.create_table('season_final_standings',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('season_id', sa.UUID(), nullable=False),
        sa.Column('club_id', sa.UUID(), nullable=False),
        sa.Column('rank', sa.Integer(), nullable=False),
        sa.Column('points', sa.Integer(), nullable=False),
        sa.Column('gd', sa.Integer(), nullable=False),
        sa.Column('gf', sa.Integer(), nullable=False),
        sa.Column('won', sa.Integer(), nullable=False),
        sa.Column('drawn', sa.Integer(), nullable=False),
        sa.Column('lost', sa.Integer(), nullable=False),
        sa.Column('played', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['season_id'], ['seasons.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('season_id', 'club_id', name='uniq_season_club_standing')
    )

def downgrade() -> None:
    op.drop_table('season_final_standings')
    op.drop_column('seasons', 'finalized_at')
    op.drop_column('seasons', 'is_finalized')
