"""Agent platform productionization models (M5.5).

Adds the platform-level capabilities on top of the M5.4 operations layer:

- ``AgentVersion``: immutable, append-only configuration versions for one
  registered agent (prompt binding, model config, policy versions). Only one
  version is ``active`` at a time; rollback creates a NEW active version and
  never mutates history.
- ``AgentApprovalRole``: workspace-scoped RBAC roles. A role lists the actor
  names that belong to it and the approval permissions it grants
  (``tool.approve``, ``calibration.reject``, ``dlq_replay.approve``, ...).
  The Approval Center enforces permissions server-side (403 when missing).
- ``AgentApprovalSla``: per-approval-type SLA configuration
  (``warning_after_seconds`` / ``expire_after_seconds``). Pending approvals
  transition ``pending -> warning -> expired``; an expired proposal is
  immutable and never auto-executes.

Every row is workspace-scoped and audited through ``event_log`` with a
``trace_id``. No business agent and no auto-executed business action lives
here.
"""

from typing import Any
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AI_JSON, Base, TimestampMixin, WorkspaceMixin

# Agent lifecycle states (M5.5).
LIFECYCLE_STATUSES: tuple[str, ...] = ("draft", "active", "paused", "retired")
VERSION_STATUSES: tuple[str, ...] = ("draft", "active", "retired")

# Approval permission namespaces (RBAC permission prefix -> approval_type).
APPROVAL_PERMISSIONS: tuple[str, ...] = (
    "tool.approve",
    "tool.reject",
    "calibration.approve",
    "calibration.reject",
    "recommendation.approve",
    "recommendation.reject",
    "dlq_replay.approve",
    "dlq_replay.reject",
    "agent.lifecycle.approve",
)


class AgentVersion(Base, TimestampMixin, WorkspaceMixin):
    """One append-only configuration version of a registered agent (M5.5)."""

    __tablename__ = "agent_versions"

    id: Mapped[Any] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    agent_id: Mapped[Any] = mapped_column(
        Uuid, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[str] = mapped_column(String(16), nullable=False)
    prompt_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_version: Mapped[str] = mapped_column(String(16), nullable=False, default="v1")
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    model_config: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    execution_policy_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1")
    retry_policy_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1")
    budget_policy_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "agent_id", "version", name="uq_agent_versions_ws_agent_version"
        ),
        # At most ONE active version per agent.
        Index(
            "uq_agent_versions_active",
            "workspace_id",
            "agent_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
        Index("ix_agent_versions_ws_status", "workspace_id", "status"),
    )


class AgentApprovalRole(Base, TimestampMixin, WorkspaceMixin):
    """Workspace RBAC role for the Human Approval Center (M5.5)."""

    __tablename__ = "agent_approval_roles"

    id: Mapped[Any] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    role_name: Mapped[str] = mapped_column(String(64), nullable=False)
    permissions: Mapped[list[Any]] = mapped_column(AI_JSON, nullable=False, default=list)
    actors: Mapped[list[Any]] = mapped_column(AI_JSON, nullable=False, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint("workspace_id", "role_name", name="uq_agent_approval_roles_ws_name"),
        Index("ix_agent_approval_roles_ws_enabled", "workspace_id", "enabled"),
    )


class AgentApprovalSla(Base, TimestampMixin, WorkspaceMixin):
    """Per-approval-type SLA configuration (M5.5).

    ``warning_after_seconds`` moves a pending approval to ``warning`` (still
    decidable); ``expire_after_seconds`` moves it to ``expired`` (immutable,
    never auto-approved). Missing rows fall back to the config-driven
    defaults; a row is only applied when ``enabled``.
    """

    __tablename__ = "agent_approval_slas"

    id: Mapped[Any] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    approval_type: Mapped[str] = mapped_column(String(32), nullable=False)
    warning_after_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)
    expire_after_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=86400)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint("workspace_id", "approval_type", name="uq_agent_approval_slas_ws_type"),
        Index("ix_agent_approval_slas_ws_enabled", "workspace_id", "enabled"),
    )
