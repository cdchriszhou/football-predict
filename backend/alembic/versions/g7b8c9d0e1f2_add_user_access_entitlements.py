"""add user access expiry and allowed competitions

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'g7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(inspector, table: str, col: str) -> bool:
    if table not in inspector.get_table_names():
        return False
    return col in [c['name'] for c in inspector.get_columns(table)]


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not _has_column(inspector, 'users', 'access_expires_at'):
        with op.batch_alter_table('users') as batch_op:
            batch_op.add_column(sa.Column('access_expires_at', sa.DateTime(), nullable=True))
    if not _has_column(inspector, 'users', 'allowed_competitions'):
        with op.batch_alter_table('users') as batch_op:
            batch_op.add_column(sa.Column('allowed_competitions', sa.Text(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if _has_column(inspector, 'users', 'allowed_competitions'):
        with op.batch_alter_table('users') as batch_op:
            batch_op.drop_column('allowed_competitions')
    if _has_column(inspector, 'users', 'access_expires_at'):
        with op.batch_alter_table('users') as batch_op:
            batch_op.drop_column('access_expires_at')
