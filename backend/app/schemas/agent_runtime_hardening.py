"""Agent runtime hardening schemas (M5.1).

Policies (execution/budget/retry) are versioned and config-driven; metrics
are daily aggregates; queue stats and sweeper results are operational views.
All monetary fields stay Decimal/Numeric.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# --------------------------------------------------------------------------- #
# Execution policy
# --------------------------------------------------------------------------- #


class ExecutionPolicyCreate(BaseModel):
    """Create a new version of an agent's execution policy."""

    agent_id: UUID
    max_concurrent: int = Field(default=3, ge=1, le=50)
    execution_timeout_seconds: int = Field(default=300, ge=1, le=86400)
    approval_timeout_seconds: int = Field(default=86400, ge=60, le=2_592_000)
    max_context_size: int = Field(default=20000, ge=100, le=1_000_000)
    retry_policy_id: str = Field(default="standard", min_length=1, max_length=64)
    enabled: bool = True


class ExecutionPolicyOut(BaseModel):
    """An execution policy row as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    agent_id: UUID | None
    policy_version: str
    is_current: bool
    max_concurrent: int
    execution_timeout_seconds: int
    approval_timeout_seconds: int
    max_context_size: int
    retry_policy_id: str
    enabled: bool
    trace_id: str | None
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# Budget policy
# --------------------------------------------------------------------------- #


class BudgetPolicyCreate(BaseModel):
    """Create a new version of an agent's budget policy."""

    agent_id: UUID
    monthly_budget: Decimal = Field(
        default=Decimal("100.00"), gt=0, max_digits=12, decimal_places=2
    )
    max_cost_per_execution: Decimal = Field(
        default=Decimal("5.00"), gt=0, max_digits=12, decimal_places=6
    )
    alert_threshold: Decimal = Field(
        default=Decimal("0.80"), gt=0, le=1, max_digits=4, decimal_places=3
    )
    currency: Literal["USD"] = "USD"
    enabled: bool = True


class BudgetPolicyOut(BaseModel):
    """A budget policy row as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    agent_id: UUID | None
    policy_version: str
    is_current: bool
    monthly_budget: Decimal
    max_cost_per_execution: Decimal
    alert_threshold: Decimal
    currency: str
    enabled: bool
    trace_id: str | None
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# Retry policy
# --------------------------------------------------------------------------- #


class RetryPolicyCreate(BaseModel):
    """Create a new version of a reusable retry policy."""

    retry_policy_id: str = Field(default="standard", min_length=1, max_length=64)
    name: str = Field(default="Standard exponential backoff", min_length=1, max_length=128)
    max_attempts: int = Field(default=3, ge=1, le=10)
    backoff_base_seconds: int = Field(default=2, ge=0, le=3600)
    backoff_multiplier: Decimal = Field(
        default=Decimal("2.0"), ge=1, max_digits=4, decimal_places=2
    )
    max_backoff_seconds: int = Field(default=60, ge=1, le=86400)
    retry_on_error_types: list[str] = Field(
        default_factory=lambda: ["llm", "network", "timeout", "transient"]
    )
    enabled: bool = True


class RetryPolicyOut(BaseModel):
    """A retry policy row as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    retry_policy_id: str
    name: str
    version: str
    is_current: bool
    max_attempts: int
    backoff_base_seconds: int
    backoff_multiplier: Decimal
    max_backoff_seconds: int
    retry_on_error_types: list[Any]
    enabled: bool
    trace_id: str | None
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# Metrics / queue / sweeper
# --------------------------------------------------------------------------- #


class MetricsSnapshotRequest(BaseModel):
    """Request a metrics snapshot (defaults: all agents, today UTC)."""

    agent_id: UUID | None = None
    metric_date: date | None = None


class AgentMetricOut(BaseModel):
    """A daily metrics row as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    agent_id: UUID | None
    metric_date: date
    executions_count: int
    success_count: int
    failure_count: int
    timeout_count: int
    retried_count: int
    total_tokens: int
    total_cost: Decimal
    avg_latency_ms: Decimal | None
    p95_latency_ms: int | None
    error_breakdown: dict[str, Any]
    trace_id: str | None
    created_at: datetime
    updated_at: datetime


class QueueStatsOut(BaseModel):
    """Queue statistics computed from live Redis + PostgreSQL state (M5.3).

    ``backend`` / ``stream`` / ``stream_length`` / ``delayed_count`` keep the
    M5.1 surface; the remaining fields are the M5.3 observability view. All
    numbers come from the actual queue + DB state, never hardcoded.
    """

    backend: str
    stream: str
    stream_length: int
    delayed_count: int
    queue_depth: int
    pending_count: int
    running_count: int
    waiting_approval_count: int
    retry_count: int
    dead_letter_count: int
    oldest_pending_age_ms: int | None = None
    oldest_running_age_ms: int | None = None
    throughput_per_minute: float = 0.0
    success_rate: float = 0.0
    failure_rate: float = 0.0


class QueueHealthOut(BaseModel):
    """Queue health verdict with per-check detail (M5.3)."""

    status: Literal["healthy", "degraded", "unhealthy"]
    checks: dict[str, str]
    details: dict[str, Any] = Field(default_factory=dict)


class DeadLetterOut(BaseModel):
    """One dead-lettered task (read-only view, no replay in M5.3)."""

    task_id: UUID
    agent_id: UUID | None = None
    error_type: str | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None
    trace_id: str | None = None


class DeadLetterListOut(BaseModel):
    """Paginated dead-letter query result."""

    items: list[DeadLetterOut]
    total: int
    limit: int
    offset: int


class WorkerHeartbeatIn(BaseModel):
    """Worker heartbeat reported to the registry (M5.3)."""

    worker_id: str = Field(min_length=1, max_length=64)
    hostname: str | None = Field(default=None, max_length=255)
    status: str | None = Field(default=None, max_length=16)
    current_task_id: str | None = Field(default=None, max_length=64)
    current_execution_id: str | None = Field(default=None, max_length=64)
    processed_count: int | None = Field(default=None, ge=0)
    failed_count: int | None = Field(default=None, ge=0)


class WorkerOut(BaseModel):
    """A worker registry entry (``dead`` is derived from heartbeat age)."""

    worker_id: str
    hostname: str
    status: str
    is_dead: bool
    started_at: str | None = None
    last_heartbeat_at: str | None = None
    current_task_id: str | None = None
    current_execution_id: str | None = None
    processed_count: int = 0
    failed_count: int = 0


class TraceNodeOut(BaseModel):
    """One node of a full-chain trace (M5.3)."""

    type: str
    id: str
    status: str | None = None
    timestamp: str | None = None
    duration_ms: int | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class TraceOut(BaseModel):
    """The full execution chain for one ``trace_id`` (JSON-safe)."""

    trace_id: str
    nodes: list[TraceNodeOut]


class SweeperRunOut(BaseModel):
    """Result of one sweeper pass."""

    approvals_expired: int
    stale_executions_failed: int
    tasks_requeued: int
    pending_tasks_enqueued: int
