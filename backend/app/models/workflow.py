"""Product Factory Orchestrator — workflow execution metadata.

Independent execution tracking for the 13-stage product factory pipeline.
Does NOT replace Product Lifecycle (candidate_status / status / funnel_stage);
it tracks *how* a workflow run progressed through orchestration stages.

Tables:
- workflow_runs: one row per pipeline execution attempt
- workflow_exceptions: unified exception queue for non-retryable failures

Idempotency: same (workspace_id, product_id, workflow_type) reuses an
existing non-terminal run instead of creating a duplicate.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AI_JSON, BIGINT_PK, Base, TimestampMixin, WorkspaceMixin

__all__ = [
    "WORKFLOW_STATUSES",
    "WORKFLOW_STAGES",
    "WorkflowRun",
    "WorkflowException",
]

# ── Execution statuses ──────────────────────────────────────────────
# WAITING_APPROVAL is the idle state for human-in-the-loop stages.
WORKFLOW_STATUSES: tuple[str, ...] = (
    "RUNNING",
    "WAITING_APPROVAL",
    "COMPLETED",
    "FAILED",
    "EXCEPTION",
)

WORKFLOW_TERMINAL_STATUSES: tuple[str, ...] = (
    "COMPLETED",
    "FAILED",
    "EXCEPTION",
)

# ── Stage identifiers (orchestration order) ────────────────────────
WORKFLOW_STAGES: tuple[str, ...] = (
    "CANDIDATE_READY",
    "DATA_READINESS",
    "AI_ANALYSIS",
    "V3_EVALUATION",
    "HARD_RULES",
    "PRODUCT_DECISION",
    "PRODUCT_MASTER",
    "CREATIVE",
    "CREATIVE_QC",
    "LISTING_BUILD",
    "LISTING_GATE",
    "WC_SYNC",
    "WC_VERIFY",
    "LEARNING_EVENT",
)

# ── Stage execution policy ─────────────────────────────────────────
# AUTO: unconditionally advance
# AUTO_WITH_RETRY: advance, retry on transient failure
# POLICY: auto if conditions met, HUMAN_REQUIRED otherwise
# HUMAN_REQUIRED: always wait for human
# HARD_STOP: never advance
STAGE_POLICIES: dict[str, str] = {
    "CANDIDATE_READY": "AUTO",
    "DATA_READINESS": "AUTO_WITH_RETRY",
    "AI_ANALYSIS": "AUTO_WITH_RETRY",
    "V3_EVALUATION": "AUTO",
    "HARD_RULES": "AUTO",
    "PRODUCT_DECISION": "POLICY",
    "PRODUCT_MASTER": "AUTO_AFTER_APPROVAL",
    "CREATIVE": "AUTO_WITH_RETRY",
    "CREATIVE_QC": "AUTO_WITH_RETRY",
    "LISTING_BUILD": "AUTO",
    "LISTING_GATE": "AUTO",
    "WC_SYNC": "AUTO_WITH_RETRY",
    "WC_VERIFY": "AUTO",
    "LEARNING_EVENT": "AUTO",
}

# Max retries per stage (0 = no retry)
STAGE_MAX_RETRIES: dict[str, int] = {
    "DATA_READINESS": 3,
    "AI_ANALYSIS": 2,
    "CREATIVE": 2,
    "CREATIVE_QC": 2,
    "WC_SYNC": 3,
}


class WorkflowRun(Base, TimestampMixin, WorkspaceMixin):
    """One execution of the Product Factory Orchestrator for one product.

    Idempotent: a non-terminal run for the same (workspace_id, product_id,
    workflow_type) is reused rather than duplicated.
    """

    __tablename__ = "workflow_runs"

    id: Mapped[UUID] = mapped_column("id", primary_key=True, default=uuid4)

    # The product this workflow operates on.
    product_id: Mapped[UUID] = mapped_column("product_id", nullable=False, index=True)

    # Workflow type discriminator (V1 = product_factory).
    workflow_type: Mapped[str] = mapped_column(
        "workflow_type", String(32), nullable=False, default="product_factory"
    )

    # Current orchestration stage.
    current_stage: Mapped[str] = mapped_column(
        "current_stage", String(32), nullable=False, default="CANDIDATE_READY", index=True
    )

    # Overall execution status.
    execution_status: Mapped[str] = mapped_column(
        "execution_status", String(24), nullable=False, default="RUNNING", index=True
    )

    # Total retry attempts across all stages.
    retry_count: Mapped[int] = mapped_column(
        "retry_count", Integer, nullable=False, default=0
    )

    # Last error message (for debugging).
    last_error: Mapped[str | None] = mapped_column("last_error", Text, nullable=True)

    # Next scheduled action time (for retry backoff / idle).
    next_action_at: Mapped[datetime | None] = mapped_column(
        "next_action_at", DateTime(timezone=True), nullable=True
    )

    # Full trace ID for cross-system correlation.
    trace_id: Mapped[str | None] = mapped_column("trace_id", String(64), nullable=True)

    # Structured stage-level metadata (per-stage results, IDs produced, etc.)
    stage_metadata: Mapped[dict[str, Any]] = mapped_column(
        "stage_metadata", AI_JSON, nullable=False, default=dict
    )

    # Duration tracking.
    started_at: Mapped[datetime] = mapped_column(
        "started_at", DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        "completed_at", DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        # Partial unique: one active run per (workspace, product, type).
        # Terminal runs (COMPLETED/FAILED/EXCEPTION) don't block new runs.
        Index(
            "uq_workflow_runs_ws_product_type_active",
            "workspace_id",
            "product_id",
            "workflow_type",
            unique=True,
            postgresql_where=text("execution_status NOT IN ('COMPLETED', 'FAILED', 'EXCEPTION')"),
            sqlite_where=text("execution_status NOT IN ('COMPLETED', 'FAILED', 'EXCEPTION')"),
        ),
        Index("ix_workflow_runs_ws_status", "workspace_id", "execution_status"),
        Index("ix_workflow_runs_stage", "workspace_id", "current_stage"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_run_id": str(self.id),
            "product_id": str(self.product_id),
            "workspace_id": str(self.workspace_id),
            "workflow_type": self.workflow_type,
            "current_stage": self.current_stage,
            "execution_status": self.execution_status,
            "retry_count": self.retry_count,
            "last_error": self.last_error,
            "next_action_at": self.next_action_at.isoformat() if self.next_action_at else None,
            "trace_id": self.trace_id,
            "stage_metadata": self.stage_metadata or {},
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class WorkflowException(Base, TimestampMixin, WorkspaceMixin):
    """Unified exception queue for workflow failures.

    Every non-retryable failure, retry exhaustion, or hard-stop condition
    produces a row here. Not just a log — actionable with next_action.
    """

    __tablename__ = "workflow_exceptions"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)

    # Linked workflow run.
    workflow_run_id: Mapped[UUID] = mapped_column(
        "workflow_run_id", Uuid, nullable=False, index=True
    )

    # The product this exception is about.
    product_id: Mapped[UUID] = mapped_column("product_id", nullable=False, index=True)

    # Which stage produced the exception.
    stage: Mapped[str] = mapped_column("stage", String(32), nullable=False)

    # Error classification.
    error_code: Mapped[str] = mapped_column(
        "error_code", String(64), nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(
        "error_message", Text, nullable=True
    )

    # Retry classification.
    retryable: Mapped[bool] = mapped_column(
        "retryable", Boolean, nullable=False, default=False
    )
    retry_count: Mapped[int] = mapped_column(
        "retry_count", Integer, nullable=False, default=0
    )

    # What to do next.
    next_action: Mapped[str | None] = mapped_column(
        "next_action", String(128), nullable=True
    )

    # Trace correlation.
    trace_id: Mapped[str | None] = mapped_column(
        "trace_id", String(64), nullable=True
    )

    # Resolution tracking.
    resolved: Mapped[bool] = mapped_column(
        "resolved", Boolean, nullable=False, default=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        "resolved_at", DateTime(timezone=True), nullable=True
    )
    resolved_by: Mapped[str | None] = mapped_column(
        "resolved_by", String(128), nullable=True
    )

    __table_args__ = (
        Index("ix_workflow_exceptions_ws_created", "workspace_id", text("created_at DESC")),
        Index("ix_workflow_exceptions_run", "workflow_run_id"),
        Index("ix_workflow_exceptions_stage", "workspace_id", "stage"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "exception_id": self.id,
            "workflow_run_id": str(self.workflow_run_id),
            "product_id": str(self.product_id),
            "workspace_id": str(self.workspace_id),
            "stage": self.stage,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "retryable": self.retryable,
            "retry_count": self.retry_count,
            "next_action": self.next_action,
            "trace_id": self.trace_id,
            "resolved": self.resolved,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolved_by": self.resolved_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
