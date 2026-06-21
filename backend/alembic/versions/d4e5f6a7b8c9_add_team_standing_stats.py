"""add team league standing stats

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(inspector, table: str, col: str) -> bool:
    if table not in inspector.get_table_names():
        return False
    return col in [c['name'] for c in inspector.get_columns(table)]


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    cols = [
        ('points', sa.Integer()),
        ('played', sa.Integer()),
        ('won', sa.Integer()),
        ('draw', sa.Integer()),
        ('lost', sa.Integer()),
        ('goals_for', sa.Integer()),
        ('goals_against', sa.Integer()),
    ]
    for col, typ in cols:
        if not _has_column(inspector, 'teams', col):
            with op.batch_alter_table('teams') as batch_op:
                batch_op.add_column(sa.Column(col, typ, nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    for col in ('goals_against', 'goals_for', 'lost', 'draw', 'won', 'played', 'points'):
        if _has_column(inspector, 'teams', col):
            with op.batch_alter_table('teams') as batch_op:
                batch_op.drop_column(col)
