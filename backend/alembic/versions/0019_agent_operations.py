"""M5.4: agent alerts + unified human approval center

Revision ID: 0019
Revises: 0018
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the Alert Service and Human Approval Center tables (M5.4)."""
    op.create_table(
        "agent_alerts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=True),
        sa.Column("alert_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("severity", sa.String(length=8), nullable=False),
        sa.Column("resource", sa.String(length=128), nullable=False),
        sa.Column("dedup_key", sa.String(length=255), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=True),
        sa.Column("metadata_", sa.JSON(), nullable=False),
        sa.Column("threshold_snapshot", sa.JSON(), nullable=False),
        sa.Column("ack_by", sa.String(length=64), nullable=True),
        sa.Column("ack_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(length=64), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_agent_alerts_ws_dedup_active",
        "agent_alerts",
        ["workspace_id", "dedup_key"],
        unique=True,
        postgresql_where=sa.text("status IN ('open', 'acknowledged')"),
        sqlite_where=sa.text("status IN ('open', 'acknowledged')"),
    )
    op.create_index("ix_agent_alerts_ws_status", "agent_alerts", ["workspace_id", "status"])
    op.create_index("ix_agent_alerts_ws_type", "agent_alerts", ["workspace_id", "alert_type"])
    op.create_index("ix_agent_alerts_ws_agent", "agent_alerts", ["workspace_id", "agent_id"])

    op.create_table(
        "agent_approvals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("approval_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("target_task_id", sa.Uuid(), nullable=True),
        sa.Column("agent_id", sa.Uuid(), nullable=True),
        sa.Column("actor", sa.String(length=64), nullable=True),
        sa.Column("action", sa.String(length=16), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("metadata_", sa.JSON(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_task_id"], ["agent_tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_agent_approvals_dlq_pending",
        "agent_approvals",
        ["workspace_id", "entity_id"],
        unique=True,
        postgresql_where=sa.text("approval_type = 'DLQ_REPLAY' AND status = 'pending'"),
        sqlite_where=sa.text("approval_type = 'DLQ_REPLAY' AND status = 'pending'"),
    )
    op.create_index("ix_agent_approvals_ws_status", "agent_approvals", ["workspace_id", "status"])
    op.create_index(
        "ix_agent_approvals_ws_type", "agent_approvals", ["workspace_id", "approval_type"]
    )
    op.create_index(
        "ix_agent_approvals_ws_entity",
        "agent_approvals",
        ["workspace_id", "entity_type", "entity_id"],
    )
    op.create_index("ix_agent_approvals_ws_trace", "agent_approvals", ["workspace_id", "trace_id"])


def downgrade() -> None:
    """Drop the approval center and alert tables."""
    op.drop_index("ix_agent_approvals_ws_trace", table_name="agent_approvals")
    op.drop_index("ix_agent_approvals_ws_entity", table_name="agent_approvals")
    op.drop_index("ix_agent_approvals_ws_type", table_name="agent_approvals")
    op.drop_index("ix_agent_approvals_ws_status", table_name="agent_approvals")
    op.drop_index("uq_agent_approvals_dlq_pending", table_name="agent_approvals")
    op.drop_table("agent_approvals")

    op.drop_index("ix_agent_alerts_ws_agent", table_name="agent_alerts")
    op.drop_index("ix_agent_alerts_ws_type", table_name="agent_alerts")
    op.drop_index("ix_agent_alerts_ws_status", table_name="agent_alerts")
    op.drop_index("uq_agent_alerts_ws_dedup_active", table_name="agent_alerts")
    op.drop_table("agent_alerts")
