"""PR9: 情報公開イベントと最終結果表示

v1Spec Section 1.2, 4, 13

Revision ID: 7a8b9c0d1e2f
Revises: 6a7b8c9d0e1f
Create Date: 2025-12-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers, used by Alembic.
revision = "7a8b9c0d1e2f"
down_revision = "6a7b8c9d0e1f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. season_public_disclosures テーブル作成
    op.create_table(
        "season_public_disclosures",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("season_id", UUID(as_uuid=True), sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("disclosure_type", sa.String(50), nullable=False),
        sa.Column("disclosure_month", sa.Integer, nullable=False),
        sa.Column("turn_id", UUID(as_uuid=True), sa.ForeignKey("turns.id", ondelete="CASCADE"), nullable=True),
        sa.Column("disclosed_data", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_unique_constraint(
        "uq_season_disclosure",
        "season_public_disclosures",
        ["season_id", "disclosure_type", "disclosure_month"]
    )
    op.create_index(
        "idx_disclosure_season",
        "season_public_disclosures",
        ["season_id"]
    )

    # 2. game_final_results テーブル作成
    op.create_table(
        "game_final_results",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("game_id", UUID(as_uuid=True), sa.ForeignKey("games.id", ondelete="CASCADE"), nullable=False),
        sa.Column("club_id", UUID(as_uuid=True), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        # 売上規模
        sa.Column("final_sales_amount", sa.Numeric(20, 0), nullable=False),
        sa.Column("final_sales_rank", sa.Integer, nullable=False),
        # 純資産
        sa.Column("final_equity_amount", sa.Numeric(20, 0), nullable=False),
        sa.Column("final_equity_rank", sa.Integer, nullable=False),
        # 成績
        sa.Column("championship_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("runner_up_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("average_rank", sa.Numeric(4, 2), nullable=False),
        sa.Column("seasons_played", sa.Integer, nullable=False),
        # 入場者数
        sa.Column("total_home_attendance", sa.Numeric(20, 0), nullable=False),
        sa.Column("average_home_attendance", sa.Integer, nullable=False),
        sa.Column("attendance_rank", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_unique_constraint(
        "uq_game_club_result",
        "game_final_results",
        ["game_id", "club_id"]
    )
    op.create_index(
        "idx_final_results_game",
        "game_final_results",
        ["game_id"]
    )


def downgrade() -> None:
    op.drop_index("idx_final_results_game", table_name="game_final_results")
    op.drop_constraint("uq_game_club_result", "game_final_results", type_="unique")
    op.drop_table("game_final_results")

    op.drop_index("idx_disclosure_season", table_name="season_public_disclosures")
    op.drop_constraint("uq_season_disclosure", "season_public_disclosures", type_="unique")
    op.drop_table("season_public_disclosures")
