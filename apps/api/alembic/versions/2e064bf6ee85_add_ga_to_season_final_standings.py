"""add ga to season final standings"""

revision = '2e064bf6ee85'
down_revision = '33b665baeb4d'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

def upgrade() -> None:
    op.add_column('season_final_standings', sa.Column('ga', sa.Integer(), nullable=False, server_default='0'))

def downgrade() -> None:
    op.drop_column('season_final_standings', 'ga')
