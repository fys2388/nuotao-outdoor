"""Agent runtime foundation models (M5.0).

The runtime layer is deliberately generic: an ``AgentRegistry`` row declares
a registered agent (identity, model routing, prompt version, permission
level); ``AgentTask`` tracks one unit of work through its lifecycle; every
task run produces an ``AgentExecution`` audit row (context snapshot, input,
output, model usage, cost, latency, tool calls). ``AgentTool`` is the
whitelist every tool call must pass, gated by the Permission Engine
(L0-L3). ``AgentMemory`` grounds agents in the four knowledge domains.
``AgentEvaluation`` records prediction vs actual for calibration.

No concrete business agent is defined here; this is the base every future
agent runs on. High-risk actions never execute automatically - they stop at
``waiting_approval`` for a human decision.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
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

# Agent registry domains and lifecycle states (M5.0).
AGENT_DOMAINS: tuple[str, ...] = (
    "product",
    "marketing",
    "customer",
    "supply_chain",
    "operations",
)
# Registry status (M5.0) extended with the M5.5 lifecycle: ``paused`` blocks
# new task creation but leaves running executions alone; ``retired`` blocks
# new tasks too while keeping all history. ``inactive`` is kept for legacy.
AGENT_STATUSES: tuple[str, ...] = ("active", "inactive", "draft", "paused", "retired")

# Task lifecycle states (M5.0).
TASK_STATUSES: tuple[str, ...] = (
    "pending",
    "running",
    "waiting_approval",
    "completed",
    "failed",
    "cancelled",
)

# Execution lifecycle states (M5.0); ``rejected`` is human-rejection of a
# waiting_approval execution (the task itself is marked failed).
EXECUTION_STATUSES: tuple[str, ...] = (
    "running",
    "waiting_approval",
    "completed",
    "failed",
    "cancelled",
    "rejected",
)

# Permission levels (L0 read-public, L1 internal read, L2 proposal,
# L3 high-risk execution). Tools require a level <= the calling agent level.
PERMISSION_LEVELS: tuple[str, ...] = ("L0", "L1", "L2", "L3")

# Agent memory source types (connects to the four knowledge domains).
MEMORY_SOURCE_TYPES: tuple[str, ...] = (
    "product_knowledge",
    "marketing_knowledge",
    "customer_knowledge",
    "supply_chain_knowledge",
    "event",
    "note",
)


class AgentRegistry(Base, TimestampMixin, WorkspaceMixin):
    """A registered agent in the runtime (M5.0)."""

    __tablename__ = "agents"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    agent_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    domain: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[str] = mapped_column(String(16), nullable=False, default="v1")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    model_provider: Mapped[str] = mapped_column(String(32), nullable=False, default="openai")
    model_name: Mapped[str] = mapped_column(String(64), nullable=False, default="gpt-4o-mini")
    prompt_version: Mapped[str] = mapped_column(String(16), nullable=False, default="v1")
    permission_level: Mapped[str] = mapped_column(String(8), nullable=False, default="L1")
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # M5.5: the currently active configuration version (agent_versions.version).
    current_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint("workspace_id", "agent_id", name="uq_agents_workspace_agent_id"),
        Index("ix_agents_workspace_domain", "workspace_id", "domain"),
    )


class AgentTask(Base, TimestampMixin, WorkspaceMixin):
    """One unit of work for a registered agent (M5.0)."""

    __tablename__ = "agent_tasks"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    agent_id: Mapped[Uuid | None] = mapped_column(
        Uuid, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    input: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    result: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enqueued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)

    __table_args__ = (
        Index("ix_agent_tasks_workspace_status", "workspace_id", "status"),
        Index("ix_agent_tasks_workspace_agent", "workspace_id", "agent_id"),
    )


class AgentExecution(Base, TimestampMixin, WorkspaceMixin):
    """Audit row of one agent task run (M5.0)."""

    __tablename__ = "agent_executions"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    agent_id: Mapped[Uuid | None] = mapped_column(
        Uuid, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    task_id: Mapped[Uuid | None] = mapped_column(
        Uuid, ForeignKey("agent_tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    context_snapshot: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    input: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    output: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tokens: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tool_calls: Mapped[list[Any]] = mapped_column(AI_JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    approval: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    approval_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    worker_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_agent_executions_workspace_status", "workspace_id", "status"),
        Index("ix_agent_executions_workspace_agent", "workspace_id", "agent_id"),
    )


class AgentTool(Base, TimestampMixin, WorkspaceMixin):
    """Tool registry whitelist (M5.0); every tool call must match a row."""

    __tablename__ = "agent_tools"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    permission_level: Mapped[str] = mapped_column(String(8), nullable=False, default="L1")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    handler_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    args_schema: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint("workspace_id", "tool_name", name="uq_agent_tools_workspace_name"),
        Index("ix_agent_tools_workspace_level", "workspace_id", "permission_level"),
    )


class AgentMemory(Base, TimestampMixin, WorkspaceMixin):
    """Agent memory grounded in the four knowledge domains (M5.0)."""

    __tablename__ = "agent_memory"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    agent_id: Mapped[Uuid | None] = mapped_column(
        Uuid, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    domain: Mapped[str] = mapped_column(String(32), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content: Mapped[str] = mapped_column(String(4000), nullable=False)
    tags: Mapped[list[Any]] = mapped_column(AI_JSON, nullable=False, default=list)
    meta: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_agent_memory_workspace_domain", "workspace_id", "domain"),
        Index("ix_agent_memory_workspace_agent", "workspace_id", "agent_id"),
    )


class AgentEvaluation(Base, CreatedAtMixin, WorkspaceMixin):
    """Prediction vs actual evaluation for agent calibration (M5.0)."""

    __tablename__ = "agent_evaluations"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    agent_id: Mapped[Uuid | None] = mapped_column(
        Uuid, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    prediction: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    actual_result: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    accuracy: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    calibration: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    prediction_result: Mapped[str | None] = mapped_column(String(16), nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    success_flag: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    confidence_bucket: Mapped[str | None] = mapped_column(String(8), nullable=True)
    human_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_agent_evaluations_workspace_agent", "workspace_id", "agent_id"),
        Index("ix_agent_evaluations_workspace_bucket", "workspace_id", "confidence_bucket"),
    )
