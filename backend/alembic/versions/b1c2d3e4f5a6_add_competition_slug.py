"""add competition_slug to matches and teams

Revision ID: b1c2d3e4f5a6
Revises: a042c239fb98
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, Sequence[str], None] = 'a042c239fb98'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(inspector, table: str, col: str) -> bool:
    if table not in inspector.get_table_names():
        return False
    return col in [c['name'] for c in inspector.get_columns(table)]


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if not _has_column(inspector, 'matches', 'competition_slug'):
        with op.batch_alter_table('matches') as batch_op:
            batch_op.add_column(
                sa.Column('competition_slug', sa.String(40), nullable=False, server_default='worldcup-2026')
            )
        op.create_index('ix_matches_competition_slug', 'matches', ['competition_slug'])

    if not _has_column(inspector, 'teams', 'competition_slug'):
        with op.batch_alter_table('teams') as batch_op:
            batch_op.add_column(
                sa.Column('competition_slug', sa.String(40), nullable=False, server_default='worldcup-2026')
            )
        op.create_index('ix_teams_competition_slug', 'teams', ['competition_slug'])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if _has_column(inspector, 'teams', 'competition_slug'):
        op.drop_index('ix_teams_competition_slug', 'teams')
        with op.batch_alter_table('teams') as batch_op:
            batch_op.drop_column('competition_slug')
    if _has_column(inspector, 'matches', 'competition_slug'):
        op.drop_index('ix_matches_competition_slug', 'matches')
        with op.batch_alter_table('matches') as batch_op:
            batch_op.drop_column('competition_slug')
