"""Unify stored ticket prices with the central configuration.

Revision ID: 2b3c4d5e6f7
Revises: 1a2b3c4d5e6f
"""

from alembic import op
import sqlalchemy as sa


revision = "2b3c4d5e6f7"
down_revision = "1a2b3c4d5e6f"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE club_financial_profiles SET ticket_price = 2000")
    op.alter_column(
        "club_financial_profiles",
        "ticket_price",
        existing_type=sa.Numeric(14, 2),
        # Do not duplicate the application setting as a database default.
        # ORM inserts receive the current value from constants.TICKET_PRICE.
        server_default=None,
        existing_nullable=False,
    )


def downgrade():
    op.execute("UPDATE club_financial_profiles SET ticket_price = 2000")
    op.alter_column(
        "club_financial_profiles",
        "ticket_price",
        existing_type=sa.Numeric(14, 2),
        server_default=sa.text("2000"),
        existing_nullable=False,
    )
