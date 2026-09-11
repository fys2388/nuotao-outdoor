"""Agent runtime operations schemas (M5.4).

Alert Service, Human Approval Center, DLQ replay proposals and the Runtime
Overview all share this schema module. Monetary / JSON fields follow the
codebase conventions (Decimal for money, ``dict`` for flexible payloads).
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# --------------------------------------------------------------------------- #
# Alerts
# --------------------------------------------------------------------------- #


class AlertAckRequest(BaseModel):
    """Acknowledge an open alert."""

    actor: str = Field(min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=500)


class AlertResolveRequest(BaseModel):
    """Resolve an open/acknowledged alert."""

    actor: str = Field(min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=500)


class AlertOut(BaseModel):
    """One alert row as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    agent_id: UUID | None
    alert_type: str
    status: str
    severity: str
    resource: str
    dedup_key: str
    message: str | None = None
    metadata_: dict[str, Any] = Field(default_factory=dict)
    threshold_snapshot: dict[str, Any] = Field(default_factory=dict)
    ack_by: str | None = None
    ack_at: datetime | None = None
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    trace_id: str | None = None
    created_at: datetime
    updated_at: datetime


class AlertListOut(BaseModel):
    """Paginated alert query result."""

    items: list[AlertOut]
    total: int
    limit: int
    offset: int


# --------------------------------------------------------------------------- #
# Approvals
# --------------------------------------------------------------------------- #


class ApprovalDecideRequest(BaseModel):
    """Approve or reject a pending approval request."""

    actor: str = Field(min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=500)


class ApprovalOut(BaseModel):
    """One approval-center row as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    approval_type: str
    status: str
    entity_type: str
    entity_id: str
    target_task_id: UUID | None = None
    agent_id: UUID | None = None
    actor: str | None = None
    action: str | None = None
    note: str | None = None
    metadata_: dict[str, Any] = Field(default_factory=dict)
    decided_at: datetime | None = None
    trace_id: str | None = None
    created_at: datetime
    updated_at: datetime


class ApprovalListOut(BaseModel):
    """Paginated approval query result."""

    items: list[ApprovalOut]
    total: int
    limit: int
    offset: int


# --------------------------------------------------------------------------- #
# DLQ replay
# --------------------------------------------------------------------------- #


class DlqReplayProposeRequest(BaseModel):
    """Create a DLQ replay PROPOSAL (never a direct replay)."""

    reason: str = Field(min_length=1, max_length=500)


class DlqReplayProposalOut(BaseModel):
    """The replay proposal (an Approval Center row) as returned by the API."""

    proposal_id: UUID
    status: str
    approval_type: str
    task_id: UUID
    reason: str | None = None
    original_error: str | None = None
    original_attempt_count: int = 0
    trace_id: str | None = None


# --------------------------------------------------------------------------- #
# Runtime overview
# --------------------------------------------------------------------------- #


class RuntimeOverviewOut(BaseModel):
    """Runtime Dashboard summary (one-shot, from live Redis + PostgreSQL)."""

    workspace_id: str
    agents: dict[str, Any]
    workers: dict[str, Any]
    queue: dict[str, Any]
    executions: dict[str, Any]
    retry: dict[str, Any]
    dead_letter: dict[str, Any]
    approvals: dict[str, Any]
    alerts: dict[str, Any]
    cost: dict[str, Any]
    tokens: dict[str, Any]
    failure_rate: float = 0.0
    success_rate: float = 0.0
    trace_id: str | None = None
