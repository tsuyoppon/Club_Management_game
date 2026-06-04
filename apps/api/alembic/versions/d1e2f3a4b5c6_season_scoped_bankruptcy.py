"""Season-scoped bankruptcy state

Revision ID: d1e2f3a4b5c6
Revises: c4d5e6f7a8b9
Create Date: 2026-06-04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d1e2f3a4b5c6"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "club_bankruptcy_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("club_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("season_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_bankrupt", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("bankrupt_since_turn_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_foreign_key(
        "fk_bankruptcy_states_club",
        "club_bankruptcy_states",
        "clubs",
        ["club_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_bankruptcy_states_season",
        "club_bankruptcy_states",
        "seasons",
        ["season_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_bankruptcy_states_turn",
        "club_bankruptcy_states",
        "turns",
        ["bankrupt_since_turn_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        "uq_bankruptcy_state_club_season",
        "club_bankruptcy_states",
        ["club_id", "season_id"],
    )
    op.create_index(
        "ix_bankruptcy_states_season",
        "club_bankruptcy_states",
        ["season_id"],
    )

    op.execute(
        """
        INSERT INTO club_bankruptcy_states (
            id, club_id, season_id, is_bankrupt, bankrupt_since_turn_id, created_at, updated_at
        )
        SELECT
            (
                substr(md5(cfs.club_id::text || ':' || t.season_id::text), 1, 8) || '-' ||
                substr(md5(cfs.club_id::text || ':' || t.season_id::text), 9, 4) || '-' ||
                substr(md5(cfs.club_id::text || ':' || t.season_id::text), 13, 4) || '-' ||
                substr(md5(cfs.club_id::text || ':' || t.season_id::text), 17, 4) || '-' ||
                substr(md5(cfs.club_id::text || ':' || t.season_id::text), 21, 12)
            )::uuid,
            cfs.club_id,
            t.season_id,
            true,
            COALESCE(cfs.bankrupt_since_turn_id, cfs.last_applied_turn_id),
            now(),
            now()
        FROM club_financial_states cfs
        JOIN turns t ON t.id = COALESCE(cfs.bankrupt_since_turn_id, cfs.last_applied_turn_id)
        WHERE cfs.is_bankrupt = true
        ON CONFLICT (club_id, season_id) DO NOTHING
        """
    )


def downgrade():
    op.drop_index("ix_bankruptcy_states_season", table_name="club_bankruptcy_states")
    op.drop_constraint("uq_bankruptcy_state_club_season", "club_bankruptcy_states", type_="unique")
    op.drop_constraint("fk_bankruptcy_states_turn", "club_bankruptcy_states", type_="foreignkey")
    op.drop_constraint("fk_bankruptcy_states_season", "club_bankruptcy_states", type_="foreignkey")
    op.drop_constraint("fk_bankruptcy_states_club", "club_bankruptcy_states", type_="foreignkey")
    op.drop_table("club_bankruptcy_states")
