"""update initial scenario defaults

Revision ID: 0f1e2d3c4b5a
Revises: f3a4b5c6d7e8
Create Date: 2026-07-07
"""
from alembic import op


revision = "0f1e2d3c4b5a"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("club_fanbase_states", "fb_count", server_default="10000")
    op.alter_column("club_fanbase_states", "fb_rate", server_default="0.01")


def downgrade() -> None:
    op.alter_column("club_fanbase_states", "fb_count", server_default="60000")
    op.alter_column("club_fanbase_states", "fb_rate", server_default="0.06")
