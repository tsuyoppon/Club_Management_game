"""add fanbase staff cumulatives

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-06-19 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f3a4b5c6d7e8"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "club_fanbase_states",
        sa.Column(
            "cumulative_promotion_staff",
            sa.Numeric(precision=10, scale=4),
            server_default="1",
            nullable=False,
        ),
    )
    op.add_column(
        "club_fanbase_states",
        sa.Column(
            "cumulative_hometown_staff",
            sa.Numeric(precision=10, scale=4),
            server_default="1",
            nullable=False,
        ),
    )
    op.alter_column("club_fanbase_states", "cumulative_promotion_staff", server_default=None)
    op.alter_column("club_fanbase_states", "cumulative_hometown_staff", server_default=None)


def downgrade() -> None:
    op.drop_column("club_fanbase_states", "cumulative_hometown_staff")
    op.drop_column("club_fanbase_states", "cumulative_promotion_staff")
