"""update operating cost defaults

Revision ID: 1a2b3c4d5e6f
Revises: 0f1e2d3c4b5a
Create Date: 2026-07-14
"""
from alembic import op


revision = "1a2b3c4d5e6f"
down_revision = "0f1e2d3c4b5a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("club_financial_profiles", "monthly_cost", server_default="1000000")
    # Apply the new standard rate without overwriting clubs that have set a
    # custom administration cost.
    op.execute(
        """
        UPDATE club_financial_profiles
        SET monthly_cost = 1000000
        WHERE monthly_cost IN (0, 3000000, 5000000)
        """
    )


def downgrade() -> None:
    op.alter_column("club_financial_profiles", "monthly_cost", server_default="0")
