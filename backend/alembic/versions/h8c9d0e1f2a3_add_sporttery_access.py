"""add sporttery plan access flag

Revision ID: h8c9d0e1f2a3
Revises: g7b8c9d0e1f2
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'h8c9d0e1f2a3'
down_revision: Union[str, Sequence[str], None] = 'g7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(inspector, table: str, col: str) -> bool:
    if table not in inspector.get_table_names():
        return False
    return col in [c['name'] for c in inspector.get_columns(table)]


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not _has_column(inspector, 'users', 'can_access_sporttery'):
        with op.batch_alter_table('users') as batch_op:
            batch_op.add_column(
                sa.Column('can_access_sporttery', sa.Boolean(), nullable=False, server_default=sa.false())
            )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if _has_column(inspector, 'users', 'can_access_sporttery'):
        with op.batch_alter_table('users') as batch_op:
            batch_op.drop_column('can_access_sporttery')
