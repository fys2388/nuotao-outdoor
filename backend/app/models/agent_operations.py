"""Agent runtime production-operations models (M5.4).

Adds the operational layer for production monitoring and human control:

- ``AgentAlert``: one alert opened by the Alert Service (queue backlog,
  oldest pending, dead worker, failure/retry rate, DLQ growth, LLM latency,
  budget warning, approval timeout). Lifecycle ``open -> acknowledged ->
  resolved``; a dedup_key keeps one active alert per problem so the same
  condition never floods the list.
- ``AgentApproval``: the unified Human Approval Center row covering L3 tool
  calls, business recommendations, calibration proposals and DLQ replays.
  Lifecycle ``pending -> approved/rejected`` with actor / action / note /
  decided_at / trace_id. Nothing is ever executed before a human decision.

Both are workspace-scoped; every state change mirrors to ``event_log`` with a
``trace_id``. No business agent and no auto-executed business action lives
here.
"""

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AI_JSON, Base, TimestampMixin, WorkspaceMixin

# Alert lifecycle states (M5.4).
ALERT_STATUSES: tuple[str, ...] = ("open", "acknowledged", "resolved")
ALERT_SEVERITIES: tuple[str, ...] = ("info", "warning", "critical")

# Approval center lifecycle states (M5.4 + M5.5 SLA: pending -> warning ->
# expired; decided states approved/rejected are terminal and immutable).
APPROVAL_STATUSES: tuple[str, ...] = ("pending", "warning", "expired", "approved", "rejected")
APPROVAL_TYPES: tuple[str, ...] = (
    "L3_TOOL",
    "RECOMMENDATION",
    "CALIBRATION",
    "DLQ_REPLAY",
    "AGENT_LIFECYCLE",
)


class AgentAlert(Base, TimestampMixin, WorkspaceMixin):
    """One open/acknowledged/resolved alert raised by the Alert Service."""

    __tablename__ = "agent_alerts"

    id: Mapped[Any] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    agent_id: Mapped[Any | None] = mapped_column(
        Uuid, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    alert_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    severity: Mapped[str] = mapped_column(String(8), nullable=False, default="warning")
    resource: Mapped[str] = mapped_column(String(128), nullable=False)
    dedup_key: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    threshold_snapshot: Mapped[dict[str, Any]] = mapped_column(
        AI_JSON, nullable=False, default=dict
    )
    ack_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ack_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        # At most ONE active (open/acknowledged) alert per dedup key: the same
        # problem cannot flood the list until it is resolved.
        Index(
            "uq_agent_alerts_ws_dedup_active",
            "workspace_id",
            "dedup_key",
            unique=True,
            postgresql_where=text("status IN ('open', 'acknowledged')"),
            sqlite_where=text("status IN ('open', 'acknowledged')"),
        ),
        Index("ix_agent_alerts_ws_status", "workspace_id", "status"),
        Index("ix_agent_alerts_ws_type", "workspace_id", "alert_type"),
        Index("ix_agent_alerts_ws_agent", "workspace_id", "agent_id"),
    )


class AgentApproval(Base, TimestampMixin, WorkspaceMixin):
    """A unified human approval request (M5.4 Human Approval Center).

    ``approval_type`` dispatches to the underlying service: L3_TOOL
    (agent execution), RECOMMENDATION (business recommendation), CALIBRATION
    (score calibration run) or DLQ_REPLAY (dead-letter task replay). The row
    keeps the full human decision audit: actor, action, note, decided_at and
    the trace_id of the whole chain.
    """

    __tablename__ = "agent_approvals"

    id: Mapped[Any] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    approval_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    target_task_id: Mapped[Any | None] = mapped_column(
        Uuid, ForeignKey("agent_tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    agent_id: Mapped[Any | None] = mapped_column(
        Uuid, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str | None] = mapped_column(String(16), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # M5.5 approval SLA: when the pending approval crosses the configured
    # warning threshold it becomes ``warning``; past ``expires_at`` it becomes
    # ``expired`` (immutable - never auto-approved).
    sla_warning_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        # One pending/warning DLQ replay proposal per task at a time: two
        # approvers cannot both replay the same dead letter (the row claim +
        # the task state guard in the replay service protect the execution).
        Index(
            "uq_agent_approvals_dlq_pending",
            "workspace_id",
            "entity_id",
            unique=True,
            postgresql_where=text(
                "approval_type = 'DLQ_REPLAY' AND status IN ('pending', 'warning')"
            ),
            sqlite_where=text("approval_type = 'DLQ_REPLAY' AND status IN ('pending', 'warning')"),
        ),
        Index("ix_agent_approvals_ws_status", "workspace_id", "status"),
        Index("ix_agent_approvals_ws_type", "workspace_id", "approval_type"),
        Index("ix_agent_approvals_ws_entity", "workspace_id", "entity_type", "entity_id"),
        Index("ix_agent_approvals_ws_trace", "workspace_id", "trace_id"),
    )
