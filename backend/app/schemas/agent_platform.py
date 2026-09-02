"""Agent platform productionization schemas (M5.5)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# --------------------------------------------------------------------------- #
# Agent lifecycle versions
# --------------------------------------------------------------------------- #


class VersionPublishRequest(BaseModel):
    """Publish a new draft configuration version (append-only)."""

    version: str = Field(min_length=1, max_length=16, pattern=r"^v\d+$")
    prompt_name: str | None = Field(default=None, max_length=64)
    prompt_version: str = Field(default="v1", min_length=1, max_length=16)
    config_snapshot: dict[str, Any] = Field(default_factory=dict)
    # ``model_settings`` mirrors the ORM ``model_config`` column (the name
    # ``model_config`` is reserved by pydantic and cannot be a field).
    model_settings: dict[str, Any] = Field(default_factory=dict)
    execution_policy_version: str = Field(default="1", max_length=32)
    retry_policy_version: str = Field(default="1", max_length=32)
    budget_policy_version: str = Field(default="1", max_length=32)
    created_by: str | None = Field(default=None, max_length=64)


class VersionOut(BaseModel):
    """One append-only version as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    agent_id: UUID
    version: str
    prompt_name: str | None = None
    prompt_version: str
    config_snapshot: dict[str, Any]
    # ``model_settings`` mirrors the ORM ``model_config`` column; the name
    # avoids clashing with pydantic's reserved ``model_config`` attribute.
    model_settings: dict[str, Any]
    execution_policy_version: str
    retry_policy_version: str
    budget_policy_version: str
    status: str
    created_by: str | None = None
    trace_id: str | None = None
    created_at: datetime
    updated_at: datetime


class LifecycleActionRequest(BaseModel):
    """Actor + optional note for lifecycle transitions."""

    actor: str = Field(min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=500)


class RollbackRequest(BaseModel):
    """Propose a rollback to a historical version (approval required)."""

    target_version: str = Field(min_length=1, max_length=16)
    actor: str = Field(min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=500)


# --------------------------------------------------------------------------- #
# Approval RBAC roles
# --------------------------------------------------------------------------- #


class ApprovalRoleCreate(BaseModel):
    """Create/replace an approval RBAC role."""

    role_name: str = Field(min_length=1, max_length=64)
    permissions: list[str] = Field(default_factory=list)
    actors: list[str] = Field(default_factory=list)
    enabled: bool = True


class ApprovalRoleOut(BaseModel):
    """One approval role as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    role_name: str
    permissions: list[Any]
    actors: list[Any]
    enabled: bool
    trace_id: str | None = None
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# Approval SLA
# --------------------------------------------------------------------------- #


class ApprovalSlaUpsert(BaseModel):
    """Upsert one approval-type SLA."""

    approval_type: str = Field(min_length=1, max_length=32)
    warning_after_seconds: int = Field(ge=0, le=2_592_000)
    expire_after_seconds: int = Field(ge=1, le=31_536_000)
    enabled: bool = True


class ApprovalSlaOut(BaseModel):
    """One approval SLA as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    approval_type: str
    warning_after_seconds: int
    expire_after_seconds: int
    enabled: bool
    trace_id: str | None = None
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# Console audit + runtime metrics
# --------------------------------------------------------------------------- #


class ConsoleAuditRequest(BaseModel):
    """One Runtime Console audit event (server-side recorded)."""

    action: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_.]+$")
    entity_type: str | None = Field(default=None, max_length=64)
    entity_id: str | None = Field(default=None, max_length=128)
    actor: str | None = Field(default=None, max_length=64)
    detail: dict[str, Any] = Field(default_factory=dict)
