"""add next_season_budget to club_reinforcement_plans"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '8b9c0d1e2f3a'
down_revision = '7a8b9c0d1e2f'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'club_reinforcement_plans',
        sa.Column('next_season_budget', sa.Numeric(14, 2), nullable=False, server_default='0')
    )
    op.alter_column('club_reinforcement_plans', 'next_season_budget', server_default=None)


def downgrade():
    op.drop_column('club_reinforcement_plans', 'next_season_budget')
