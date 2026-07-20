"""add match penalty shootout scores

Revision ID: j0k1l2m3n4o5
Revises: i9d0e1f2a3b4
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'j0k1l2m3n4o5'
down_revision: Union[str, Sequence[str], None] = 'i9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    cols = {c['name'] for c in inspector.get_columns('matches')}
    if 'penalty_a' not in cols:
        op.add_column('matches', sa.Column('penalty_a', sa.Integer(), nullable=True, comment='点球大战主队得分'))
    if 'penalty_b' not in cols:
        op.add_column('matches', sa.Column('penalty_b', sa.Integer(), nullable=True, comment='点球大战客队得分'))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    cols = {c['name'] for c in inspector.get_columns('matches')}
    if 'penalty_b' in cols:
        op.drop_column('matches', 'penalty_b')
    if 'penalty_a' in cols:
        op.drop_column('matches', 'penalty_a')
