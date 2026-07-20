"""add HKJC real data cache tables

Revision ID: i9d0e1f2a3b4
Revises: h8c9d0e1f2a3
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'i9d0e1f2a3b4'
down_revision: Union[str, Sequence[str], None] = 'h8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent: init_db() may have already created these via Base.metadata.create_all.
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = set(inspector.get_table_names())

    if 'hkjc_meeting_cache' not in existing:
        op.create_table(
            'hkjc_meeting_cache',
            sa.Column('id', sa.String(32), primary_key=True),
            sa.Column('meeting_date', sa.String(10), nullable=False, index=True),
            sa.Column('venue_code', sa.String(8), nullable=False, index=True),
            sa.Column('payload', sa.Text(), nullable=False),
            sa.Column('source', sa.String(32), server_default='hkjc_graphql'),
            sa.Column('synced_at', sa.DateTime(), nullable=True),
        )

    if 'hkjc_race_results' not in existing:
        op.create_table(
            'hkjc_race_results',
            sa.Column('id', sa.String(48), primary_key=True),
            sa.Column('meeting_date', sa.String(10), nullable=False, index=True),
            sa.Column('venue_code', sa.String(8), nullable=False, index=True),
            sa.Column('race_no', sa.Integer(), nullable=False),
            sa.Column('payload', sa.Text(), nullable=False),
            sa.Column('synced_at', sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    op.drop_table('hkjc_race_results', if_exists=True)
    op.drop_table('hkjc_meeting_cache', if_exists=True)
