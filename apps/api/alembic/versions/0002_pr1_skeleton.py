"""PR1 game skeleton tables

Revision ID: 0002_pr1_skeleton
Revises: 0001_initial
Create Date: 2024-05-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0002_pr1_skeleton"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    game_status = sa.Enum("draft", "active", "archived", name="gamestatus")
    membership_role = sa.Enum("gm", "club_owner", "club_viewer", name="membershiprole")
    season_status = sa.Enum("setup", "running", "finished", name="seasonstatus")
    turn_state = sa.Enum("open", "collecting", "locked", "resolved", "acked", name="turnstate")
    decision_state = sa.Enum("draft", "committed", "locked", name="decisionstate")
    match_status = sa.Enum("scheduled", "played", name="matchstatus")

    game_status.create(op.get_bind(), checkfirst=True)
    membership_role.create(op.get_bind(), checkfirst=True)
    season_status.create(op.get_bind(), checkfirst=True)
    turn_state.create(op.get_bind(), checkfirst=True)
    decision_state.create(op.get_bind(), checkfirst=True)
    match_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "games",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("status", game_status, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(), nullable=False, unique=True),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "clubs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("games.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("short_name", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("games.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", membership_role, nullable=False),
        sa.Column("club_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("(role = 'gm' AND club_id IS NULL) OR (role <> 'gm' AND club_id IS NOT NULL)", name="club_required_for_roles"),
    )

    op.create_table(
        "seasons",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("games.id", ondelete="CASCADE"), nullable=False),
        sa.Column("year_label", sa.String(), nullable=False),
        sa.Column("start_month", sa.Integer(), nullable=False),
        sa.Column("end_month", sa.Integer(), nullable=False),
        sa.Column("status", season_status, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "turns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("season_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("month_index", sa.Integer(), nullable=False),
        sa.Column("month_name", sa.String(), nullable=False),
        sa.Column("month_number", sa.Integer(), nullable=False),
        sa.Column("turn_state", turn_state, nullable=False),
        sa.Column("opened_at", sa.DateTime(), nullable=True),
        sa.Column("locked_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("season_id", "month_index", name="uniq_turn_month"),
    )

    op.create_table(
        "turn_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("turn_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("turns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("club_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("decision_state", decision_state, nullable=False),
        sa.Column("committed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("committed_at", sa.DateTime(), nullable=True),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.UniqueConstraint("turn_id", "club_id", name="uniq_turn_club_decision"),
    )

    op.create_table(
        "turn_acks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("turn_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("turns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("club_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ack", sa.Boolean(), nullable=False),
        sa.Column("acked_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("turn_id", "club_id", "user_id", name="uniq_turn_ack"),
    )

    op.create_table(
        "fixtures",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("season_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("match_month_index", sa.Integer(), nullable=False),
        sa.Column("match_month_name", sa.String(), nullable=False),
        sa.Column("home_club_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=True),
        sa.Column("away_club_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=True),
        sa.Column("is_bye", sa.Boolean(), nullable=False),
        sa.Column("bye_club_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=True),
        sa.UniqueConstraint(
            "season_id",
            "match_month_index",
            "home_club_id",
            "away_club_id",
            "is_bye",
            "bye_club_id",
            name="uniq_fixture",
        ),
    )

    op.create_table(
        "matches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("fixture_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("fixtures.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("status", match_status, nullable=False),
        sa.Column("home_goals", sa.Integer(), nullable=True),
        sa.Column("away_goals", sa.Integer(), nullable=True),
        sa.Column("played_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("matches")
    op.drop_table("fixtures")
    op.drop_table("turn_acks")
    op.drop_table("turn_decisions")
    op.drop_table("turns")
    op.drop_table("seasons")
    op.drop_table("memberships")
    op.drop_table("clubs")
    op.drop_table("users")
    op.drop_table("games")

    op.execute("DROP TYPE IF EXISTS matchstatus")
    op.execute("DROP TYPE IF EXISTS decisionstate")
    op.execute("DROP TYPE IF EXISTS turnstate")
    op.execute("DROP TYPE IF EXISTS seasonstatus")
    op.execute("DROP TYPE IF EXISTS membershiprole")
    op.execute("DROP TYPE IF EXISTS gamestatus")

