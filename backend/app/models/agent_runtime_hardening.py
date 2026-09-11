"""Agent runtime production-hardening models (M5.1).

Extends the M5.0 runtime with the operational layer:

- ``AgentExecutionPolicy``: per-agent, versioned execution policy (concurrency,
  execution/approval timeouts, context size, retry binding). Defaults are
  config-driven; per-agent overrides are versioned rows (``is_current`` marks
  the active version).
- ``AgentBudgetPolicy``: per-agent, versioned budget policy (monthly budget,
  max cost per execution, alert threshold) enforced by the worker before any
  model call.
- ``AgentRetryPolicy``: reusable, versioned retry policy (max attempts,
  exponential backoff, retryable error classes).
- ``AgentTaskAttempt``: one row per task attempt - the durable retry audit
  trail (worker id, error classification, latency, trace_id).
- ``AgentMetric``: daily aggregated agent metrics (counts, tokens, cost,
  latency percentiles, error breakdown).

All rows are workspace-scoped; every state change emits an ``event_log`` row
with a ``trace_id``. No concrete business agent is defined here.
"""

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AI_JSON, Base, CreatedAtMixin, TimestampMixin, WorkspaceMixin


class AgentExecutionPolicy(Base, TimestampMixin, WorkspaceMixin):
    """Per-agent, versioned execution policy (M5.1)."""

    __tablename__ = "agent_execution_policies"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    agent_id: Mapped[Uuid | None] = mapped_column(
        Uuid, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    policy_version: Mapped[str] = mapped_column(String(16), nullable=False, default="v1")
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    max_concurrent: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    execution_timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    approval_timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=86400)
    max_context_size: Mapped[int] = mapped_column(Integer, nullable=False, default=20000)
    retry_policy_id: Mapped[str] = mapped_column(String(64), nullable=False, default="standard")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "agent_id", "policy_version", name="uq_agent_exec_pol_ws_agent_ver"
        ),
        Index("ix_agent_exec_pol_ws_current", "workspace_id", "is_current"),
        Index("ix_agent_exec_pol_ws_agent", "workspace_id", "agent_id"),
    )


class AgentBudgetPolicy(Base, TimestampMixin, WorkspaceMixin):
    """Per-agent, versioned budget policy (M5.1)."""

    __tablename__ = "agent_budget_policies"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    agent_id: Mapped[Uuid | None] = mapped_column(
        Uuid, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    policy_version: Mapped[str] = mapped_column(String(16), nullable=False, default="v1")
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    monthly_budget: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=100)
    max_cost_per_execution: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), nullable=False, default=5
    )
    alert_threshold: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False, default=0.8)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "agent_id", "policy_version", name="uq_agent_budget_pol_ws_agent_ver"
        ),
        Index("ix_agent_budget_pol_ws_current", "workspace_id", "is_current"),
        Index("ix_agent_budget_pol_ws_agent", "workspace_id", "agent_id"),
    )


class AgentRetryPolicy(Base, TimestampMixin, WorkspaceMixin):
    """Reusable, versioned retry policy (M5.1)."""

    __tablename__ = "agent_retry_policies"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    retry_policy_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(16), nullable=False, default="v1")
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    backoff_base_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    backoff_multiplier: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False, default=2)
    max_backoff_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    retry_on_error_types: Mapped[list[Any]] = mapped_column(AI_JSON, nullable=False, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "retry_policy_id",
            "version",
            name="uq_agent_retry_pol_ws_code_ver",
        ),
        Index("ix_agent_retry_pol_ws_current", "workspace_id", "is_current"),
    )


class AgentTaskAttempt(Base, CreatedAtMixin, WorkspaceMixin):
    """One attempt row per task retry (M5.1, immutable audit)."""

    __tablename__ = "agent_task_attempts"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    task_id: Mapped[Uuid | None] = mapped_column(
        Uuid, ForeignKey("agent_tasks.id", ondelete="CASCADE"), nullable=True, index=True
    )
    execution_id: Mapped[Uuid | None] = mapped_column(
        Uuid, ForeignKey("agent_executions.id", ondelete="SET NULL"), nullable=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_agent_task_attempts_ws_task", "workspace_id", "task_id"),
        Index("ix_agent_task_attempts_ws_status", "workspace_id", "status"),
    )


class AgentMetric(Base, TimestampMixin, WorkspaceMixin):
    """Daily aggregated agent metrics (M5.1)."""

    __tablename__ = "agent_metrics"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    agent_id: Mapped[Uuid | None] = mapped_column(
        Uuid, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    metric_date: Mapped[date] = mapped_column(Date, nullable=False)
    executions_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    timeout_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retried_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, default=0)
    avg_latency_ms: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    p95_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_breakdown: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "agent_id", "metric_date", name="uq_agent_metrics_ws_agent_date"
        ),
        Index("ix_agent_metrics_ws_agent", "workspace_id", "agent_id"),
    )
