"""admin cost migration

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-01-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6g7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Update existing clubs' monthly_cost to 5,000,000 if it's still 0
    op.execute("""
        UPDATE club_financial_profiles
        SET monthly_cost = 5000000
        WHERE monthly_cost = 0
    """)
    
    # 2. Update existing ledger entries: kind='cost' -> kind='admin_cost'
    op.execute("""
        UPDATE club_financial_ledgers
        SET kind = 'admin_cost',
            meta = jsonb_set(
                COALESCE(meta, '{}'::jsonb),
                '{description}',
                '"Monthly Administrative Cost"'::jsonb
            )
        WHERE kind = 'cost'
    """)


def downgrade():
    # Revert ledger entries: kind='admin_cost' -> kind='cost'
    op.execute("""
        UPDATE club_financial_ledgers
        SET kind = 'cost',
            meta = jsonb_set(
                COALESCE(meta, '{}'::jsonb),
                '{description}',
                '"Monthly Fixed Cost (Base)"'::jsonb
            )
        WHERE kind = 'admin_cost'
    """)
    
    # Note: Not reverting monthly_cost to 0 as it would lose data
