"""M5.2.1: agent task idempotency key

Revision ID: 0018
Revises: 0017
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the producer idempotency key for agent tasks (M5.2.1).

    The DB row is the source of truth for dedup: the same
    (workspace_id, agent_id, idempotency_key) may only create one task, so a
    producer retrying a POST can never double-enqueue the same work.
    """
    op.add_column(
        "agent_tasks",
        sa.Column("idempotency_key", sa.String(128), nullable=True),
    )
    op.create_index(
        "uq_agent_tasks_ws_agent_idem",
        "agent_tasks",
        ["workspace_id", "agent_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    """Drop the idempotency key column and its partial unique index."""
    op.drop_index("uq_agent_tasks_ws_agent_idem", table_name="agent_tasks")
    op.drop_column("agent_tasks", "idempotency_key")
