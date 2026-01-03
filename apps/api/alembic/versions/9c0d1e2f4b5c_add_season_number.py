"""add season_number to seasons"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '9c0d1e2f4b5c'
down_revision = '8b9c0d1e2f3a'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'seasons',
        sa.Column('season_number', sa.Integer(), nullable=False, server_default='1'),
    )

    op.execute(
        """
        WITH numbered AS (
            SELECT id, row_number() OVER (PARTITION BY game_id ORDER BY created_at) AS rn
            FROM seasons
        )
        UPDATE seasons s
        SET season_number = n.rn
        FROM numbered n
        WHERE s.id = n.id;
        """
    )

    op.alter_column('seasons', 'season_number', server_default=None)
    op.create_unique_constraint('uniq_game_season_number', 'seasons', ['game_id', 'season_number'])


def downgrade():
    op.drop_constraint('uniq_game_season_number', 'seasons', type_='unique')
    op.drop_column('seasons', 'season_number')
