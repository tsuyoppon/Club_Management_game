"""add game completion summary

Revision ID: a4b5c6d7e8f9
Revises: 2b3c4d5e6f7
Create Date: 2026-08-21 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "a4b5c6d7e8f9"
down_revision = "2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL enum additions must be committed before the value can be used.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE gamestatus ADD VALUE IF NOT EXISTS 'completed'")

    op.create_table(
        "game_completions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "game_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("games.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "completed_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("completed_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "reopened_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reopened_at", sa.DateTime(), nullable=True),
        sa.Column("summary_schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("summary_json", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_game_completions_game_id", "game_completions", ["game_id"])
    op.create_index(
        "uq_game_completions_active",
        "game_completions",
        ["game_id"],
        unique=True,
        postgresql_where=sa.text("reopened_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_game_completions_active", table_name="game_completions")
    op.drop_index("ix_game_completions_game_id", table_name="game_completions")
    op.drop_table("game_completions")
    # Keep the additive PostgreSQL enum value. Removing enum members requires
    # rewriting the type and table, which is unsafe for a routine downgrade.
