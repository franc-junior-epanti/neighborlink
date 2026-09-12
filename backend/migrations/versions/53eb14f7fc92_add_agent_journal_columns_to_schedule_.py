"""add agent journal columns to schedule versions

Revision ID: 53eb14f7fc92
Revises: e2c3806b0205
Create Date: 2026-09-12 10:29:52.738173
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '53eb14f7fc92'
down_revision: str | None = 'e2c3806b0205'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('schedule_versions', sa.Column('agent_session_id', sa.String(length=64), nullable=True))
    op.add_column('schedule_versions', sa.Column('agent_request_id', sa.String(length=64), nullable=True))
    op.add_column(
        'schedule_versions',
        sa.Column('tool_calls', sa.JSON(), nullable=False, server_default='[]'),
    )
    op.alter_column('schedule_versions', 'tool_calls', server_default=None)


def downgrade() -> None:
    op.drop_column('schedule_versions', 'tool_calls')
    op.drop_column('schedule_versions', 'agent_request_id')
    op.drop_column('schedule_versions', 'agent_session_id')
