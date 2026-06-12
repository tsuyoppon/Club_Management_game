"""add fanbase trend streak

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-06-12 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e2f3a4b5c6d7"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "club_fanbase_states",
        sa.Column("fb_trend_streak", sa.Integer(), server_default="0", nullable=False),
    )
    op.alter_column("club_fanbase_states", "fb_trend_streak", server_default=None)


def downgrade() -> None:
    op.drop_column("club_fanbase_states", "fb_trend_streak")
