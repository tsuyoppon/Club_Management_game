"""add game room host mode

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-08-29 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "b5c6d7e8f9a0"
down_revision = "a4b5c6d7e8f9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "game_rooms",
        sa.Column("host_mode", sa.String(length=24), server_default="player", nullable=False),
    )
    op.create_check_constraint(
        "ck_game_rooms_host_mode",
        "game_rooms",
        "host_mode IN ('player', 'dedicated')",
    )


def downgrade():
    op.drop_constraint("ck_game_rooms_host_mode", "game_rooms", type_="check")
    op.drop_column("game_rooms", "host_mode")
