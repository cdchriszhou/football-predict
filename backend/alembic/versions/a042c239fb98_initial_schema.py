"""initial_schema — upgrade invite_codes table from single-use to multi-use

Revision ID: a042c239fb98
Revises:
Create Date: 2026-05-28 23:26:18.221324

This migration is idempotent:
- On fresh install (create_all ran first): all tables already exist with correct schema; this is a no-op.
- On upgrade from old schema: converts invite_codes.is_used → use_count.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a042c239fb98'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if we're upgrading from the old invite_codes schema (has is_used column)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('invite_codes')] if 'invite_codes' in inspector.get_table_names() else []

    if 'is_used' in columns and 'use_count' not in columns:
        # Old schema: add use_count, set it from is_used, drop old columns
        op.add_column('invite_codes', sa.Column('use_count', sa.Integer(), nullable=False, server_default='0'))
        # Mark previously-used codes with use_count = 1
        op.execute("UPDATE invite_codes SET use_count = 1 WHERE is_used = 1")
        # Drop old columns (SQLite doesn't support DROP COLUMN easily, but modern versions do)
        with op.batch_alter_table('invite_codes') as batch_op:
            batch_op.drop_column('is_used')
            batch_op.drop_column('used_by')
            batch_op.drop_column('used_at')


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('invite_codes')] if 'invite_codes' in inspector.get_table_names() else []

    if 'use_count' in columns and 'is_used' not in columns:
        with op.batch_alter_table('invite_codes') as batch_op:
            batch_op.add_column(sa.Column('is_used', sa.Boolean(), nullable=False, server_default='0'))
            batch_op.add_column(sa.Column('used_by', sa.String(50), nullable=True))
            batch_op.add_column(sa.Column('used_at', sa.DateTime(), nullable=True))
        op.execute("UPDATE invite_codes SET is_used = 1 WHERE use_count > 0")
        with op.batch_alter_table('invite_codes') as batch_op:
            batch_op.drop_column('use_count')
