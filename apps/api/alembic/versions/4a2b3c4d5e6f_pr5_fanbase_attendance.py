"""pr5 fanbase attendance

Revision ID: 4a2b3c4d5e6f
Revises: 2e064bf6ee85
Create Date: 2025-12-20 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '4a2b3c4d5e6f'
down_revision = '2e064bf6ee85'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create club_fanbase_states table
    op.create_table('club_fanbase_states',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('club_id', sa.UUID(), nullable=False),
        sa.Column('season_id', sa.UUID(), nullable=False),
        sa.Column('fb_count', sa.Integer(), server_default='60000', nullable=False),
        sa.Column('fb_rate', sa.Numeric(precision=10, scale=6), server_default='0.06', nullable=False),
        sa.Column('cumulative_promo', sa.Numeric(precision=14, scale=2), server_default='0', nullable=False),
        sa.Column('cumulative_ht', sa.Numeric(precision=14, scale=2), server_default='0', nullable=False),
        sa.Column('last_ht_spend', sa.Numeric(precision=14, scale=2), server_default='0', nullable=False),
        sa.Column('followers_public', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['season_id'], ['seasons.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('club_id', 'season_id', name='uniq_club_season_fanbase')
    )

    # Add columns to fixtures table
    op.add_column('fixtures', sa.Column('weather', sa.String(), nullable=True))
    op.add_column('fixtures', sa.Column('home_attendance', sa.Integer(), nullable=True))
    op.add_column('fixtures', sa.Column('away_attendance', sa.Integer(), nullable=True))
    op.add_column('fixtures', sa.Column('total_attendance', sa.Integer(), nullable=True))


def downgrade() -> None:
    # Remove columns from fixtures table
    op.drop_column('fixtures', 'total_attendance')
    op.drop_column('fixtures', 'away_attendance')
    op.drop_column('fixtures', 'home_attendance')
    op.drop_column('fixtures', 'weather')

    # Drop club_fanbase_states table
    op.drop_table('club_fanbase_states')
