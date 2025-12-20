"""PR8: 債務超過ペナルティとゲーム終了条件

v1Spec Section 1.1, 14.1:
- club_financial_states: is_bankrupt, bankrupt_since_turn_id, point_penalty_applied追加
- club_point_penalties: 勝点剥奪履歴テーブル新規作成
- games: last_place_penalty_enabled追加

Revision ID: 6a7b8c9d0e1f
Revises: 5b6c7d8e9f0a
Create Date: 2024-12-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '6a7b8c9d0e1f'
down_revision = '5b6c7d8e9f0a'
branch_labels = None
depends_on = None


def upgrade():
    # 1. club_financial_states拡張
    op.add_column('club_financial_states', 
        sa.Column('is_bankrupt', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('club_financial_states', 
        sa.Column('bankrupt_since_turn_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('club_financial_states', 
        sa.Column('point_penalty_applied', sa.Boolean(), nullable=False, server_default='false'))
    op.create_foreign_key(
        'fk_fin_state_bankrupt_turn', 
        'club_financial_states',
        'turns', 
        ['bankrupt_since_turn_id'], 
        ['id'], 
        ondelete='SET NULL'
    )
    
    # 2. club_point_penalties新規作成
    op.create_table('club_point_penalties',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('club_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('season_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('turn_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('points_deducted', sa.Integer(), nullable=False),
        sa.Column('reason', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_foreign_key(
        'fk_point_penalties_club',
        'club_point_penalties',
        'clubs',
        ['club_id'],
        ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'fk_point_penalties_season',
        'club_point_penalties',
        'seasons',
        ['season_id'],
        ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'fk_point_penalties_turn',
        'club_point_penalties',
        'turns',
        ['turn_id'],
        ['id'],
        ondelete='CASCADE'
    )
    op.create_unique_constraint(
        'uq_penalty_club_season_reason',
        'club_point_penalties',
        ['club_id', 'season_id', 'reason']
    )
    op.create_index(
        'ix_point_penalties_club_season',
        'club_point_penalties',
        ['club_id', 'season_id']
    )
    
    # 3. games拡張
    op.add_column('games',
        sa.Column('last_place_penalty_enabled', sa.Boolean(), nullable=False, server_default='false'))


def downgrade():
    # 3. games - rollback
    op.drop_column('games', 'last_place_penalty_enabled')
    
    # 2. club_point_penalties - rollback
    op.drop_index('ix_point_penalties_club_season', table_name='club_point_penalties')
    op.drop_constraint('uq_penalty_club_season_reason', 'club_point_penalties', type_='unique')
    op.drop_constraint('fk_point_penalties_turn', 'club_point_penalties', type_='foreignkey')
    op.drop_constraint('fk_point_penalties_season', 'club_point_penalties', type_='foreignkey')
    op.drop_constraint('fk_point_penalties_club', 'club_point_penalties', type_='foreignkey')
    op.drop_table('club_point_penalties')
    
    # 1. club_financial_states - rollback
    op.drop_constraint('fk_fin_state_bankrupt_turn', 'club_financial_states', type_='foreignkey')
    op.drop_column('club_financial_states', 'point_penalty_applied')
    op.drop_column('club_financial_states', 'bankrupt_since_turn_id')
    op.drop_column('club_financial_states', 'is_bankrupt')
