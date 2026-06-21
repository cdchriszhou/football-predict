"""add league real-data fields (season, matchday, external ids)

Revision ID: c3d4e5f6a7b8
Revises: b1c2d3e4f5a6
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(inspector, table: str, col: str) -> bool:
    if table not in inspector.get_table_names():
        return False
    return col in [c['name'] for c in inspector.get_columns(table)]


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    match_cols = [
        ('season', sa.String(20), None),
        ('matchday', sa.Integer(), None),
        ('external_id', sa.Integer(), None),
    ]
    for col, typ, default in match_cols:
        if not _has_column(inspector, 'matches', col):
            with op.batch_alter_table('matches') as batch_op:
                batch_op.add_column(sa.Column(col, typ, nullable=True))

    team_cols = [
        ('external_id', sa.Integer(), None),
        ('season', sa.String(20), None),
    ]
    for col, typ, default in team_cols:
        if not _has_column(inspector, 'teams', col):
            with op.batch_alter_table('teams') as batch_op:
                batch_op.add_column(sa.Column(col, typ, nullable=True))

    if not _has_column(inspector, 'players', 'nationality'):
        with op.batch_alter_table('players') as batch_op:
            batch_op.add_column(sa.Column('nationality', sa.String(50), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    for col in ('nationality',):
        if _has_column(inspector, 'players', col):
            with op.batch_alter_table('players') as batch_op:
                batch_op.drop_column(col)
    for col in ('season', 'external_id'):
        if _has_column(inspector, 'teams', col):
            with op.batch_alter_table('teams') as batch_op:
                batch_op.drop_column(col)
    for col in ('season', 'matchday', 'external_id'):
        if _has_column(inspector, 'matches', col):
            with op.batch_alter_table('matches') as batch_op:
                batch_op.drop_column(col)
