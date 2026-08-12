"""Human Approval Center (M5.4): one place to see and decide every pending
human decision.

Covers, through one unified ``AgentApproval`` row and API:

- ``L3_TOOL``          -> agent execution waiting for a high-risk tool decision
- ``RECOMMENDATION``   -> business recommendation proposals
- ``CALIBRATION``      -> score calibration proposals
- ``DLQ_REPLAY``       -> dead-letter replay proposals

Lifecycle: ``pending -> approved/rejected``. Approve/reject dispatches to the
underlying service (which owns the business state machine); the approval row
records actor, action, note, decided_at and trace_id. A second decision on the
same row is rejected with an error (double approve/reject = 400). Nothing is
ever executed before a human decision, and no business rule is auto-modified.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_operations import (
    AgentApproval,
)
from app.services import event_service, task_queue

logger = logging.getLogger(__name__)

APPROVAL_PENDING = "pending"
APPROVAL_APPROVED = "approved"
APPROVAL_REJECTED = "rejected"


class ApprovalError(Exception):
    """Raised when an approval operation cannot complete."""


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


async def _find_pending(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    approval_type: str,
    entity_id: str,
) -> AgentApproval | None:
    """Return the pending approval row for one (type, entity), if any."""
    return (
        await session.execute(
            select(AgentApproval).where(
                AgentApproval.workspace_id == workspace_id,
                AgentApproval.approval_type == approval_type,
                AgentApproval.entity_id == entity_id,
                AgentApproval.status == APPROVAL_PENDING,
            )
        )
    ).scalar_one_or_none()


async def ensure_approval(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    approval_type: str,
    entity_type: str,
    entity_id: str,
    target_task_id: UUID | None = None,
    agent_id: UUID | None = None,
    metadata_: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> AgentApproval:
    """Create an approval request row when none is pending for the entity.

    Called by the underlying services (execution waiting_approval,
    recommendation proposed, calibration proposed) so every human decision
    automatically appears in the Approval Center. Idempotent: a pending row
    for the same (type, entity) is returned as-is.
    """
    existing = await _find_pending(
        session,
        workspace_id=workspace_id,
        approval_type=approval_type,
        entity_id=entity_id,
    )
    if existing is not None:
        return existing
    approval = AgentApproval(
        workspace_id=workspace_id,
        approval_type=approval_type,
        status=APPROVAL_PENDING,
        entity_type=entity_type,
        entity_id=entity_id,
        target_task_id=target_task_id,
        agent_id=agent_id,
        metadata_=metadata_ or {},
        trace_id=trace_id,
    )
    session.add(approval)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.approval.created",
        entity_type="agent_approval",
        entity_id=str(approval.id),
        payload={
            "approval_type": approval_type,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "target_task_id": str(target_task_id) if target_task_id else None,
        },
        trace_id=trace_id,
    )
    await session.refresh(approval)
    return approval


async def sync_approval(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    approval_type: str,
    entity_id: str,
    decision: str,
    actor: str,
    note: str | None = None,
    trace_id: str | None = None,
) -> None:
    """Mirror a decision made through the underlying service into the row.

    Keeps the Approval Center consistent when a human decides through the
    legacy endpoint (e.g. ``/agent-executions/{id}/approve``) or when the
    sweeper auto-rejects an expired approval. No extra event is emitted here -
    the underlying service already emitted its own audit event.
    """
    await session.execute(
        update(AgentApproval)
        .where(
            AgentApproval.workspace_id == workspace_id,
            AgentApproval.approval_type == approval_type,
            AgentApproval.entity_id == entity_id,
            AgentApproval.status == APPROVAL_PENDING,
        )
        .values(
            status=decision,
            actor=actor,
            action=decision,
            note=note,
            decided_at=_now(),
        )
    )
    await session.flush()


async def list_approvals(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    status: str | None = None,
    approval_type: str | None = None,
    agent_id: UUID | None = None,
    task_id: UUID | None = None,
    trace_id: str | None = None,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[AgentApproval], int]:
    """Query approval requests (workspace-scoped), newest first."""
    filters = [AgentApproval.workspace_id == workspace_id]
    if status is not None:
        filters.append(AgentApproval.status == status)
    if approval_type is not None:
        filters.append(AgentApproval.approval_type == approval_type)
    if agent_id is not None:
        filters.append(AgentApproval.agent_id == agent_id)
    if task_id is not None:
        filters.append(AgentApproval.target_task_id == task_id)
    if trace_id is not None:
        filters.append(AgentApproval.trace_id == trace_id)
    if from_dt is not None:
        filters.append(AgentApproval.created_at >= from_dt)
    if to_dt is not None:
        filters.append(AgentApproval.created_at <= to_dt)
    total = (
        await session.execute(select(func.count()).select_from(AgentApproval).where(*filters))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                select(AgentApproval)
                .where(*filters)
                .order_by(AgentApproval.created_at.desc(), AgentApproval.id)
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return list(rows), int(total)


async def _load_approval(
    session: AsyncSession, *, workspace_id: UUID, approval_id: UUID
) -> AgentApproval | None:
    return (
        await session.execute(
            select(AgentApproval).where(
                AgentApproval.workspace_id == workspace_id,
                AgentApproval.id == approval_id,
            )
        )
    ).scalar_one_or_none()


async def _dispatch(
    session: AsyncSession,
    backend: task_queue.TaskQueueBackend,
    *,
    approval: AgentApproval,
    decision: str,
    actor: str,
    note: str | None,
    trace_id: str | None,
) -> None:
    """Apply the human decision to the underlying entity (lazy imports avoid
    module cycles; the underlying services own their state machines)."""
    if approval.approval_type == "L3_TOOL":
        from app.services import agent_runtime

        execution_id = UUID(approval.entity_id)
        if decision == APPROVAL_APPROVED:
            await agent_runtime.approve_execution(
                session,
                workspace_id=approval.workspace_id,
                execution_id=execution_id,
                actor=actor,
                note=note,
                trace_id=trace_id,
            )
        else:
            await agent_runtime.reject_execution(
                session,
                workspace_id=approval.workspace_id,
                execution_id=execution_id,
                actor=actor,
                note=note,
                trace_id=trace_id,
            )
    elif approval.approval_type == "RECOMMENDATION":
        from app.services import recommendation_service

        recommendation_id = UUID(approval.entity_id)
        if decision == APPROVAL_APPROVED:
            await recommendation_service.approve_recommendation(
                session,
                workspace_id=approval.workspace_id,
                recommendation_id=recommendation_id,
                actor=actor,
                note=note,
                trace_id=trace_id,
            )
        else:
            await recommendation_service.reject_recommendation(
                session,
                workspace_id=approval.workspace_id,
                recommendation_id=recommendation_id,
                actor=actor,
                note=note,
                trace_id=trace_id,
            )
    elif approval.approval_type == "CALIBRATION":
        from app.schemas.product_analyst import CalibrationApproveRequest
        from app.services import calibration

        run_id = UUID(approval.entity_id)
        data = CalibrationApproveRequest(actor=actor, note=note)
        if decision == APPROVAL_APPROVED:
            await calibration.approve_calibration(
                session,
                workspace_id=approval.workspace_id,
                run_id=run_id,
                data=data,
                trace_id=trace_id,
            )
        else:
            await calibration.reject_calibration(
                session,
                workspace_id=approval.workspace_id,
                run_id=run_id,
                data=data,
                trace_id=trace_id,
            )
    elif approval.approval_type == "DLQ_REPLAY":
        from app.services import agent_queue

        task_id = UUID(approval.entity_id)
        if decision == APPROVAL_APPROVED:
            await agent_queue.replay_dead_letter(
                session,
                backend,
                workspace_id=approval.workspace_id,
                task_id=task_id,
                trace_id=trace_id,
            )
        # Rejection of a replay proposal needs no business side effect.
    else:  # pragma: no cover - validated on creation
        raise ApprovalError(f"unsupported approval_type '{approval.approval_type}'")


async def _decide(
    session: AsyncSession,
    backend: task_queue.TaskQueueBackend,
    *,
    workspace_id: UUID,
    approval_id: UUID,
    actor: str,
    note: str | None,
    decision: str,
    trace_id: str | None,
) -> AgentApproval:
    """Approve or reject one pending approval request (state machine guard).

    The row is claimed with a conditional UPDATE first so two concurrent
    approvers cannot both act on the same request (double approve/reject is
    rejected with an error). Dispatch runs against the underlying entity,
    which guards its own state as well (e.g. the task must still be failed
    for a DLQ replay).
    """
    approval = await _load_approval(session, workspace_id=workspace_id, approval_id=approval_id)
    if approval is None:
        raise ApprovalError("approval not found")
    if approval.status != APPROVAL_PENDING:
        raise ApprovalError(
            f"approval already {approval.status}; only pending approvals can be decided"
        )
    claimed = await session.execute(
        update(AgentApproval)
        .where(
            AgentApproval.id == approval.id,
            AgentApproval.workspace_id == workspace_id,
            AgentApproval.status == APPROVAL_PENDING,
        )
        .values(
            status=decision,
            actor=actor,
            action=decision,
            note=note,
            decided_at=_now(),
        )
    )
    if claimed.rowcount == 0:
        raise ApprovalError("approval already decided")
    await session.flush()
    await _dispatch(
        session,
        backend,
        approval=approval,
        decision=decision,
        actor=actor,
        note=note,
        trace_id=trace_id,
    )
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type=f"agent.approval.{decision}",
        entity_type="agent_approval",
        entity_id=str(approval.id),
        payload={
            "approval_type": approval.approval_type,
            "entity_type": approval.entity_type,
            "entity_id": approval.entity_id,
            "actor": actor,
            "note": note,
        },
        trace_id=trace_id,
    )
    logger.info(
        "approval %s %s by %s (type=%s) trace=%s",
        approval.id,
        decision,
        actor,
        approval.approval_type,
        trace_id,
    )
    await session.refresh(approval)
    return approval


async def approve_approval(
    session: AsyncSession,
    backend: task_queue.TaskQueueBackend,
    *,
    workspace_id: UUID,
    approval_id: UUID,
    actor: str,
    note: str | None = None,
    trace_id: str | None = None,
) -> AgentApproval:
    """Approve a pending approval request (human-in-the-loop gate)."""
    return await _decide(
        session,
        backend,
        workspace_id=workspace_id,
        approval_id=approval_id,
        actor=actor,
        note=note,
        decision=APPROVAL_APPROVED,
        trace_id=trace_id,
    )


async def reject_approval(
    session: AsyncSession,
    backend: task_queue.TaskQueueBackend,
    *,
    workspace_id: UUID,
    approval_id: UUID,
    actor: str,
    note: str | None = None,
    trace_id: str | None = None,
) -> AgentApproval:
    """Reject a pending approval request (human-in-the-loop gate)."""
    return await _decide(
        session,
        backend,
        workspace_id=workspace_id,
        approval_id=approval_id,
        actor=actor,
        note=note,
        decision=APPROVAL_REJECTED,
        trace_id=trace_id,
    )
