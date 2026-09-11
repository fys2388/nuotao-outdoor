"""M5.1: agent runtime production hardening - policies, retry, metrics, tool handlers

Revision ID: 0017
Revises: 0016
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the M5.1 agent runtime hardening tables and columns."""

    # --- agent_retry_policies ---------------------------------------------------
    op.create_table(
        "agent_retry_policies",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column("retry_policy_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("version", sa.String(16), nullable=False, server_default="v1"),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("backoff_base_seconds", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("backoff_multiplier", sa.Numeric(4, 2), nullable=False, server_default="2"),
        sa.Column("max_backoff_seconds", sa.Integer(), nullable=False, server_default="60"),
        sa.Column(
            "retry_on_error_types",
            JSONB(),
            nullable=False,
            server_default=sa.text('\'["llm","timeout","network","transient"]\'::jsonb'),
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "workspace_id", "retry_policy_id", "version", name="uq_agent_retry_pol_ws_code_ver"
        ),
    )
    op.create_index(
        "ix_agent_retry_pol_ws_current", "agent_retry_policies", ["workspace_id", "is_current"]
    )

    # --- agent_execution_policies ------------------------------------------------
    op.create_table(
        "agent_execution_policies",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column(
            "agent_id", UUID(), sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("policy_version", sa.String(16), nullable=False, server_default="v1"),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("max_concurrent", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("execution_timeout_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("approval_timeout_seconds", sa.Integer(), nullable=False, server_default="86400"),
        sa.Column("max_context_size", sa.Integer(), nullable=False, server_default="20000"),
        sa.Column("retry_policy_id", sa.String(64), nullable=False, server_default="standard"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "workspace_id", "agent_id", "policy_version", name="uq_agent_exec_pol_ws_agent_ver"
        ),
    )
    op.create_index(
        "ix_agent_exec_pol_ws_current", "agent_execution_policies", ["workspace_id", "is_current"]
    )
    op.create_index(
        "ix_agent_exec_pol_ws_agent", "agent_execution_policies", ["workspace_id", "agent_id"]
    )
    # Only one current execution policy per (workspace, agent) on PostgreSQL.
    op.create_index(
        "uq_agent_exec_pol_ws_agent_current",
        "agent_execution_policies",
        ["workspace_id", "agent_id"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )

    # --- agent_budget_policies ----------------------------------------------------
    op.create_table(
        "agent_budget_policies",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column(
            "agent_id", UUID(), sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("policy_version", sa.String(16), nullable=False, server_default="v1"),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("monthly_budget", sa.Numeric(12, 2), nullable=False, server_default="100"),
        sa.Column("max_cost_per_execution", sa.Numeric(12, 6), nullable=False, server_default="5"),
        sa.Column("alert_threshold", sa.Numeric(4, 3), nullable=False, server_default="0.8"),
        sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "workspace_id", "agent_id", "policy_version", name="uq_agent_budget_pol_ws_agent_ver"
        ),
    )
    op.create_index(
        "ix_agent_budget_pol_ws_current", "agent_budget_policies", ["workspace_id", "is_current"]
    )
    op.create_index(
        "ix_agent_budget_pol_ws_agent", "agent_budget_policies", ["workspace_id", "agent_id"]
    )
    op.create_index(
        "uq_agent_budget_pol_ws_agent_current",
        "agent_budget_policies",
        ["workspace_id", "agent_id"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )

    # --- agent_task_attempts ------------------------------------------------------
    op.create_table(
        "agent_task_attempts",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column(
            "task_id", UUID(), sa.ForeignKey("agent_tasks.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column(
            "execution_id",
            UUID(),
            sa.ForeignKey("agent_executions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error_type", sa.String(32), nullable=True),
        sa.Column("error_message", sa.String(1000), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("worker_id", sa.String(64), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_agent_task_attempts_ws_task", "agent_task_attempts", ["workspace_id", "task_id"]
    )
    op.create_index(
        "ix_agent_task_attempts_ws_status", "agent_task_attempts", ["workspace_id", "status"]
    )

    # --- agent_metrics -------------------------------------------------------------
    op.create_table(
        "agent_metrics",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column(
            "agent_id", UUID(), sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("executions_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("timeout_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retried_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_cost", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("avg_latency_ms", sa.Numeric(12, 2), nullable=True),
        sa.Column("p95_latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "error_breakdown", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "workspace_id", "agent_id", "metric_date", name="uq_agent_metrics_ws_agent_date"
        ),
    )
    op.create_index("ix_agent_metrics_ws_agent", "agent_metrics", ["workspace_id", "agent_id"])

    # --- Alter existing M5.0 tables ------------------------------------------------
    # agent_tools: bind an in-process handler + JSON args schema to a whitelisted tool.
    op.add_column("agent_tools", sa.Column("handler_name", sa.String(64), nullable=True))
    op.add_column(
        "agent_tools",
        sa.Column("args_schema", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    # agent_executions: L3 approval deadline, worker attribution, attempt number.
    op.add_column(
        "agent_executions",
        sa.Column("approval_deadline", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("agent_executions", sa.Column("error_type", sa.String(32), nullable=True))
    op.add_column("agent_executions", sa.Column("worker_id", sa.String(64), nullable=True))
    op.add_column(
        "agent_executions",
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
    )
    # agent_tasks: retry counter and queue bookkeeping.
    op.add_column(
        "agent_tasks", sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "agent_tasks", sa.Column("enqueued_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    """Drop the M5.1 hardening schema (reverse order)."""
    op.drop_column("agent_tasks", "enqueued_at")
    op.drop_column("agent_tasks", "attempt_count")
    op.drop_column("agent_executions", "error_type")
    op.drop_column("agent_executions", "attempt_number")
    op.drop_column("agent_executions", "worker_id")
    op.drop_column("agent_executions", "approval_deadline")
    op.drop_column("agent_tools", "args_schema")
    op.drop_column("agent_tools", "handler_name")
    op.drop_index("ix_agent_metrics_ws_agent", table_name="agent_metrics")
    op.drop_table("agent_metrics")
    op.drop_index("ix_agent_task_attempts_ws_status", table_name="agent_task_attempts")
    op.drop_index("ix_agent_task_attempts_ws_task", table_name="agent_task_attempts")
    op.drop_table("agent_task_attempts")
    op.drop_index("uq_agent_budget_pol_ws_agent_current", table_name="agent_budget_policies")
    op.drop_index("ix_agent_budget_pol_ws_agent", table_name="agent_budget_policies")
    op.drop_index("ix_agent_budget_pol_ws_current", table_name="agent_budget_policies")
    op.drop_table("agent_budget_policies")
    op.drop_index("uq_agent_exec_pol_ws_agent_current", table_name="agent_execution_policies")
    op.drop_index("ix_agent_exec_pol_ws_agent", table_name="agent_execution_policies")
    op.drop_index("ix_agent_exec_pol_ws_current", table_name="agent_execution_policies")
    op.drop_table("agent_execution_policies")
    op.drop_index("ix_agent_retry_pol_ws_current", table_name="agent_retry_policies")
    op.drop_table("agent_retry_policies")
