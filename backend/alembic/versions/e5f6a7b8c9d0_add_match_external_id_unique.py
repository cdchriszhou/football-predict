"""add unique index on matches (competition_slug, external_id)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'matches' not in inspector.get_table_names():
        return
    existing = {idx['name'] for idx in inspector.get_indexes('matches')}
    if 'uq_matches_competition_external_id' not in existing:
        with op.batch_alter_table('matches') as batch_op:
            batch_op.create_index(
                'uq_matches_competition_external_id',
                ['competition_slug', 'external_id'],
                unique=True,
            )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'matches' not in inspector.get_table_names():
        return
    existing = {idx['name'] for idx in inspector.get_indexes('matches')}
    if 'uq_matches_competition_external_id' in existing:
        with op.batch_alter_table('matches') as batch_op:
            batch_op.drop_index('uq_matches_competition_external_id')
