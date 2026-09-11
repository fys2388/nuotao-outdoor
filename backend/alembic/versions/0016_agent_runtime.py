"""M5.0: agent runtime foundation - registry, tasks, executions, tools, memory, evaluations

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the M5.0 agent runtime tables."""

    # --- agents (registry) ----------------------------------------------------
    op.create_table(
        "agents",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("domain", sa.String(32), nullable=False),
        sa.Column("version", sa.String(16), nullable=False, server_default="v1"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("model_provider", sa.String(32), nullable=False, server_default="openai"),
        sa.Column("model_name", sa.String(64), nullable=False, server_default="gpt-4o-mini"),
        sa.Column("prompt_version", sa.String(16), nullable=False, server_default="v1"),
        sa.Column("permission_level", sa.String(8), nullable=False, server_default="L1"),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("workspace_id", "agent_id", name="uq_agents_workspace_agent_id"),
    )
    op.create_index("ix_agents_workspace_domain", "agents", ["workspace_id", "domain"])

    # --- agent_tasks ----------------------------------------------------------
    op.create_table(
        "agent_tasks",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column(
            "agent_id", UUID(), sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("input", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("result", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error_message", sa.String(1000), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_agent_tasks_workspace_status", "agent_tasks", ["workspace_id", "status"])
    op.create_index("ix_agent_tasks_workspace_agent", "agent_tasks", ["workspace_id", "agent_id"])

    # --- agent_executions ------------------------------------------------------
    op.create_table(
        "agent_executions",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column(
            "agent_id", UUID(), sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "task_id", UUID(), sa.ForeignKey("agent_tasks.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "context_snapshot", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("input", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("output", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("provider", sa.String(32), nullable=True),
        sa.Column("model", sa.String(64), nullable=True),
        sa.Column("tokens", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("cost", sa.Numeric(12, 6), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("tool_calls", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("error_message", sa.String(1000), nullable=True),
        sa.Column("approval", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_agent_executions_workspace_status",
        "agent_executions",
        ["workspace_id", "status"],
    )
    op.create_index(
        "ix_agent_executions_workspace_agent",
        "agent_executions",
        ["workspace_id", "agent_id"],
    )

    # --- agent_tools (whitelist) ------------------------------------------------
    op.create_table(
        "agent_tools",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column("tool_name", sa.String(64), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("permission_level", sa.String(8), nullable=False, server_default="L1"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("category", sa.String(32), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("workspace_id", "tool_name", name="uq_agent_tools_workspace_name"),
    )
    op.create_index(
        "ix_agent_tools_workspace_level", "agent_tools", ["workspace_id", "permission_level"]
    )

    # --- agent_memory -----------------------------------------------------------
    op.create_table(
        "agent_memory",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column(
            "agent_id", UUID(), sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("domain", sa.String(32), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_id", sa.String(64), nullable=True),
        sa.Column("content", sa.String(4000), nullable=False),
        sa.Column("tags", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("meta", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_agent_memory_workspace_domain", "agent_memory", ["workspace_id", "domain"])
    op.create_index("ix_agent_memory_workspace_agent", "agent_memory", ["workspace_id", "agent_id"])

    # --- agent_evaluations ------------------------------------------------------
    op.create_table(
        "agent_evaluations",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column(
            "agent_id", UUID(), sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("prediction", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("actual_result", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("accuracy", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("calibration", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("prediction_result", sa.String(16), nullable=True),
        sa.Column("error_type", sa.String(32), nullable=True),
        sa.Column("success_flag", sa.Boolean(), nullable=True),
        sa.Column("confidence", sa.Numeric(6, 4), nullable=True),
        sa.Column("confidence_bucket", sa.String(8), nullable=True),
        sa.Column("human_rating", sa.Integer(), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_agent_evaluations_workspace_agent",
        "agent_evaluations",
        ["workspace_id", "agent_id"],
    )
    op.create_index(
        "ix_agent_evaluations_workspace_bucket",
        "agent_evaluations",
        ["workspace_id", "confidence_bucket"],
    )


def downgrade() -> None:
    """Drop the M5.0 tables (not for production)."""
    op.drop_table("agent_evaluations")
    op.drop_table("agent_memory")
    op.drop_table("agent_tools")
    op.drop_table("agent_executions")
    op.drop_table("agent_tasks")
    op.drop_table("agents")
