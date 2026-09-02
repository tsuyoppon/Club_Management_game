"""add fanbase ruleset version

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-08-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "c6d7e8f9a0b1"
down_revision = "b5c6d7e8f9a0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add without a default first so every pre-existing game can be
    # unambiguously pinned to the legacy ruleset.
    op.add_column(
        "games",
        sa.Column("fanbase_ruleset_version", sa.Integer(), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE games SET fanbase_ruleset_version = 1 "
            "WHERE fanbase_ruleset_version IS NULL"
        )
    )
    op.alter_column(
        "games",
        "fanbase_ruleset_version",
        existing_type=sa.Integer(),
        nullable=False,
        server_default="2",
    )
    op.create_check_constraint(
        "ck_games_fanbase_ruleset_version",
        "games",
        "fanbase_ruleset_version IN (1, 2)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_games_fanbase_ruleset_version",
        "games",
        type_="check",
    )
    op.drop_column("games", "fanbase_ruleset_version")
