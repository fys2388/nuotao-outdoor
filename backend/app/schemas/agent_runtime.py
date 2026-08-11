"""Agent runtime foundation schemas (M5.0)."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

AGENT_DOMAINS: tuple[str, ...] = (
    "product",
    "marketing",
    "customer",
    "supply_chain",
    "operations",
)
AGENT_STATUSES: tuple[str, ...] = ("active", "inactive", "draft")
TASK_STATUSES: tuple[str, ...] = (
    "pending",
    "running",
    "waiting_approval",
    "completed",
    "failed",
    "cancelled",
)
PERMISSION_LEVELS: tuple[str, ...] = ("L0", "L1", "L2", "L3")
MEMORY_SOURCE_TYPES: tuple[str, ...] = (
    "product_knowledge",
    "marketing_knowledge",
    "customer_knowledge",
    "supply_chain_knowledge",
    "event",
    "note",
)


# --------------------------------------------------------------------------- #
# Agent registry
# --------------------------------------------------------------------------- #


class AgentRegisterRequest(BaseModel):
    """Register (or update) one agent in the runtime registry."""

    agent_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    domain: Literal["product", "marketing", "customer", "supply_chain", "operations"]
    version: str = Field(default="v1", pattern=r"^v\d+$")
    status: Literal["active", "inactive", "draft"] = "active"
    model_provider: Literal["openai", "deepseek"] = "openai"
    model_name: str = Field(default="gpt-4o-mini", min_length=1, max_length=64)
    prompt_version: str = Field(default="v1", pattern=r"^v\d+$")
    permission_level: Literal["L0", "L1", "L2", "L3"] = "L1"
    description: str | None = Field(default=None, max_length=500)


class AgentOut(BaseModel):
    """A registered agent as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    agent_id: str
    name: str
    domain: str
    version: str
    status: str
    model_provider: str
    model_name: str
    prompt_version: str
    permission_level: str
    description: str | None
    trace_id: str | None
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# Agent tasks
# --------------------------------------------------------------------------- #


class TaskCreate(BaseModel):
    """Create one agent task (starts in ``pending``)."""

    agent_id: UUID
    input: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=3, ge=1, le=5)


class TaskOut(BaseModel):
    """An agent task as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    agent_id: UUID | None
    input: dict[str, Any]
    status: str
    priority: int
    result: dict[str, Any]
    error_message: str | None
    trace_id: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# Agent executions
# --------------------------------------------------------------------------- #


class ExecutionStartRequest(BaseModel):
    """Start an execution for a pending task."""

    task_id: UUID


class ExecutionCompleteRequest(BaseModel):
    """Complete a running execution with the model call metrics."""

    output: dict[str, Any] = Field(default_factory=dict)
    provider: str = Field(default="openai", min_length=1, max_length=32)
    model: str = Field(default="gpt-4o-mini", min_length=1, max_length=64)
    tokens: dict[str, int] = Field(default_factory=dict)
    cost: Decimal = Field(default=Decimal("0"), ge=0)
    latency_ms: int = Field(default=0, ge=0)


class ExecutionFailRequest(BaseModel):
    """Fail a running execution."""

    error_message: str = Field(min_length=1, max_length=1000)


class ExecutionApproveRequest(BaseModel):
    """Human decision on a waiting_approval execution."""

    actor: str = Field(min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=500)


class ToolCallRequest(BaseModel):
    """One agent tool call (must pass the whitelist + permission gate)."""

    tool_name: str = Field(min_length=1, max_length=64)
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolCallOut(BaseModel):
    """Outcome of a gated tool call."""

    status: Literal["allowed", "requires_approval", "denied"]
    tool_name: str
    message: str
    execution_id: UUID
    requires_approval: bool = False


class ExecutionOut(BaseModel):
    """An agent execution as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    agent_id: UUID | None
    task_id: UUID | None
    context_snapshot: dict[str, Any]
    input: dict[str, Any]
    output: dict[str, Any]
    provider: str | None
    model: str | None
    tokens: dict[str, Any]
    cost: Decimal | None
    latency_ms: int | None
    tool_calls: list[Any]
    status: str
    error_message: str | None
    approval: dict[str, Any]
    trace_id: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# Tool registry
# --------------------------------------------------------------------------- #


class ToolRegisterRequest(BaseModel):
    """Register (or update) one tool in the whitelist."""

    tool_name: str = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=500)
    permission_level: Literal["L0", "L1", "L2", "L3"] = "L1"
    enabled: bool = True
    category: str | None = Field(default=None, max_length=32)


class ToolUpdateRequest(BaseModel):
    """Toggle a registered tool's enabled state."""

    enabled: bool
    description: str | None = Field(default=None, max_length=500)


class ToolOut(BaseModel):
    """A registered tool as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    tool_name: str
    description: str | None
    permission_level: str
    enabled: bool
    category: str | None
    trace_id: str | None
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# Agent memory
# --------------------------------------------------------------------------- #


class MemoryCreate(BaseModel):
    """Store one agent memory entry (grounded in a knowledge domain)."""

    agent_id: UUID | None = None
    domain: Literal["product", "marketing", "customer", "supply_chain", "operations"]
    source_type: Literal[
        "product_knowledge",
        "marketing_knowledge",
        "customer_knowledge",
        "supply_chain_knowledge",
        "event",
        "note",
    ]
    source_id: str | None = Field(default=None, max_length=64)
    content: str = Field(min_length=1, max_length=4000)
    tags: list[str] = Field(default_factory=list, max_length=50)
    meta: dict[str, Any] = Field(default_factory=dict)


class MemoryOut(BaseModel):
    """An agent memory entry as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    agent_id: UUID | None
    domain: str
    source_type: str
    source_id: str | None
    content: str
    tags: list[Any]
    meta: dict[str, Any]
    trace_id: str | None
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# Agent evaluation
# --------------------------------------------------------------------------- #


class AgentEvaluationCreate(BaseModel):
    """Record a prediction vs actual evaluation for an agent."""

    agent_id: UUID | None = None
    prediction: dict[str, Any] = Field(default_factory=dict)
    actual_result: dict[str, Any] = Field(default_factory=dict)
    human_rating: int | None = Field(default=None, ge=1, le=5)
    notes: str | None = Field(default=None, max_length=500)


class AgentEvaluationOut(BaseModel):
    """An agent evaluation as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    agent_id: UUID | None
    prediction: dict[str, Any]
    actual_result: dict[str, Any]
    accuracy: dict[str, Any]
    calibration: dict[str, Any]
    prediction_result: str | None
    error_type: str | None
    success_flag: bool | None
    confidence: Decimal | None
    confidence_bucket: str | None
    human_rating: int | None
    notes: str | None
    trace_id: str | None
    created_at: datetime
