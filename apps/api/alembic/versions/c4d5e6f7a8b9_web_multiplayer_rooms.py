"""web multiplayer rooms and sessions

Revision ID: c4d5e6f7a8b9
Revises: b2c3d4e5f6g7
Create Date: 2026-05-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "c4d5e6f7a8b9"
down_revision = "b2c3d4e5f6g7"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("users", "email", existing_type=sa.String(), nullable=True)

    op.create_table(
        "game_rooms",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("host_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invite_code", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["host_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id"),
        sa.UniqueConstraint("invite_code"),
    )
    op.create_table(
        "game_room_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("room_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("club_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_ready", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["club_id"], ["clubs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["room_id"], ["game_rooms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("room_id", "club_id", name="uq_room_member_club"),
        sa.UniqueConstraint("room_id", "user_id", name="uq_room_member_user"),
    )
    op.create_table(
        "web_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_table(
        "web_turn_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("turn_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("club_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["club_id"], ["clubs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["turn_id"], ["turns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("turn_id", "club_id", name="uq_web_turn_draft_club"),
    )


def downgrade():
    op.drop_table("web_turn_drafts")
    op.drop_table("web_sessions")
    op.drop_table("game_room_members")
    op.drop_table("game_rooms")
    op.alter_column("users", "email", existing_type=sa.String(), nullable=False)
