"""Agent runtime production-operations endpoints (M5.4).

Alert Service, Human Approval Center, DLQ human replay and the Runtime
Overview. Everything is workspace-scoped and audited through ``event_log``
with a ``trace_id``; approvals never auto-execute and DLQ replay always goes
proposal -> human approval -> new attempt. No business agent and no
auto-executed business action live here.
"""

import logging
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import resolve_actor
from app.core.database import get_db
from app.core.tracing import get_trace_id
from app.core.workspace import get_workspace_id
from app.schemas.agent_operations import (
    AlertAckRequest,
    AlertListOut,
    AlertOut,
    AlertResolveRequest,
    ApprovalDecideRequest,
    ApprovalListOut,
    ApprovalOut,
    DlqReplayProposalOut,
    DlqReplayProposeRequest,
    RuntimeOverviewOut,
)
from app.services import (
    agent_queue,
    alert_service,
    approval_service,
    runtime_ops,
    task_queue,
)
from app.services.approval_rbac import ApprovalRBACError

router = APIRouter(tags=["agent-operations"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
WorkspaceId = Annotated[UUID, Depends(get_workspace_id)]
logger = logging.getLogger(__name__)


def _error(exc: Exception) -> HTTPException:
    """Map ops errors: RBAC -> 403, missing resources -> 404, state -> 400."""
    if isinstance(exc, ApprovalRBACError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    message = str(exc)
    if "not found" in message:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


# --------------------------------------------------------------------------- #
# Alert Service
# --------------------------------------------------------------------------- #


@router.get(
    "/agent-alerts",
    response_model=AlertListOut,
    summary="Query alerts (workspace-scoped)",
)
async def list_alerts(
    db: DbSession,
    workspace_id: WorkspaceId,
    agent_id: Annotated[UUID | None, Query()] = None,
    alert_type: Annotated[str | None, Query()] = None,
    alert_status: Annotated[str | None, Query(alias="status")] = None,
    from_dt: Annotated[datetime | None, Query()] = None,
    to_dt: Annotated[datetime | None, Query()] = None,
    limit: int = 50,
    offset: int = 0,
) -> AlertListOut:
    """Return alerts, newest first, filtered by agent/type/status/time."""
    items, total = await alert_service.list_alerts(
        db,
        workspace_id=workspace_id,
        agent_id=agent_id,
        alert_type=alert_type,
        status=alert_status,
        from_dt=from_dt,
        to_dt=to_dt,
        limit=min(limit, 200),
        offset=max(offset, 0),
    )
    return AlertListOut(
        items=[AlertOut.model_validate(item) for item in items],
        total=total,
        limit=min(limit, 200),
        offset=max(offset, 0),
    )


@router.post(
    "/agent-alerts/evaluate",
    response_model=list[AlertOut],
    summary="Run the alert evaluation pass (opens new alerts only)",
)
async def evaluate_alerts(db: DbSession, workspace_id: WorkspaceId) -> list[AlertOut]:
    """Evaluate every alert rule against live state; returns new alerts."""
    backend = task_queue.get_queue_backend()
    created = await alert_service.evaluate_alerts(
        db, backend, workspace_id=workspace_id, trace_id=get_trace_id()
    )
    return [AlertOut.model_validate(alert) for alert in created]


@router.get(
    "/agent-alerts/{alert_id}",
    response_model=AlertOut,
    summary="Get one alert",
)
async def get_alert(
    alert_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> AlertOut:
    """Return one alert (workspace-scoped)."""
    from app.services.alert_service import _load_alert

    alert = await _load_alert(db, workspace_id=workspace_id, alert_id=alert_id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="alert not found")
    return AlertOut.model_validate(alert)


@router.post(
    "/agent-alerts/{alert_id}/ack",
    response_model=AlertOut,
    summary="Acknowledge an open alert (open -> acknowledged)",
)
async def acknowledge_alert(
    alert_id: UUID,
    body: AlertAckRequest,
    request: Request,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> AlertOut:
    """Acknowledge the alert; the actor and note are audited."""
    try:
        alert = await alert_service.acknowledge_alert(
            db,
            workspace_id=workspace_id,
            alert_id=alert_id,
            actor=resolve_actor(request, body.actor),
            note=body.note,
            trace_id=get_trace_id(),
        )
    except alert_service.AlertServiceError as exc:
        raise _error(exc) from exc
    return AlertOut.model_validate(alert)


@router.post(
    "/agent-alerts/{alert_id}/resolve",
    response_model=AlertOut,
    summary="Resolve an open/acknowledged alert (frees its dedup key)",
)
async def resolve_alert(
    alert_id: UUID,
    body: AlertResolveRequest,
    request: Request,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> AlertOut:
    """Resolve the alert; the actor and note are audited."""
    try:
        alert = await alert_service.resolve_alert(
            db,
            workspace_id=workspace_id,
            alert_id=alert_id,
            actor=resolve_actor(request, body.actor),
            note=body.note,
            trace_id=get_trace_id(),
        )
    except alert_service.AlertServiceError as exc:
        raise _error(exc) from exc
    return AlertOut.model_validate(alert)


# --------------------------------------------------------------------------- #
# Human Approval Center
# --------------------------------------------------------------------------- #


@router.get(
    "/approvals",
    response_model=ApprovalListOut,
    summary="Query approval requests (workspace-scoped)",
)
async def list_approvals(
    db: DbSession,
    workspace_id: WorkspaceId,
    approval_status: Annotated[str | None, Query(alias="status")] = None,
    approval_type: Annotated[str | None, Query()] = None,
    agent_id: Annotated[UUID | None, Query()] = None,
    task_id: Annotated[UUID | None, Query()] = None,
    trace_id: Annotated[str | None, Query()] = None,
    from_dt: Annotated[datetime | None, Query()] = None,
    to_dt: Annotated[datetime | None, Query()] = None,
    limit: int = 50,
    offset: int = 0,
) -> ApprovalListOut:
    """Return approval requests, newest first, with optional filters."""
    items, total = await approval_service.list_approvals(
        db,
        workspace_id=workspace_id,
        status=approval_status,
        approval_type=approval_type,
        agent_id=agent_id,
        task_id=task_id,
        trace_id=trace_id,
        from_dt=from_dt,
        to_dt=to_dt,
        limit=min(limit, 200),
        offset=max(offset, 0),
    )
    return ApprovalListOut(
        items=[ApprovalOut.model_validate(item) for item in items],
        total=total,
        limit=min(limit, 200),
        offset=max(offset, 0),
    )


@router.get(
    "/approvals/{approval_id}",
    response_model=ApprovalOut,
    summary="Get one approval request",
)
async def get_approval(
    approval_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ApprovalOut:
    """Return one approval request (workspace-scoped)."""
    approval = await approval_service._load_approval(  # noqa: SLF001
        db, workspace_id=workspace_id, approval_id=approval_id
    )
    if approval is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="approval not found")
    return ApprovalOut.model_validate(approval)


@router.post(
    "/approvals/{approval_id}/approve",
    response_model=ApprovalOut,
    summary="Approve a pending approval request (human-in-the-loop)",
)
async def approve_approval(
    approval_id: UUID,
    body: ApprovalDecideRequest,
    request: Request,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ApprovalOut:
    """Approve the request and dispatch to the underlying service."""
    backend = task_queue.get_queue_backend()
    try:
        approval = await approval_service.approve_approval(
            db,
            backend,
            workspace_id=workspace_id,
            approval_id=approval_id,
            actor=resolve_actor(request, body.actor),
            note=body.note,
            trace_id=get_trace_id(),
        )
    except (approval_service.ApprovalError, ApprovalRBACError) as exc:
        raise _error(exc) from exc
    return ApprovalOut.model_validate(approval)


@router.post(
    "/approvals/{approval_id}/reject",
    response_model=ApprovalOut,
    summary="Reject a pending approval request (human-in-the-loop)",
)
async def reject_approval(
    approval_id: UUID,
    body: ApprovalDecideRequest,
    request: Request,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ApprovalOut:
    """Reject the request and dispatch to the underlying service."""
    backend = task_queue.get_queue_backend()
    try:
        approval = await approval_service.reject_approval(
            db,
            backend,
            workspace_id=workspace_id,
            approval_id=approval_id,
            actor=resolve_actor(request, body.actor),
            note=body.note,
            trace_id=get_trace_id(),
        )
    except (approval_service.ApprovalError, ApprovalRBACError) as exc:
        raise _error(exc) from exc
    return ApprovalOut.model_validate(approval)


# --------------------------------------------------------------------------- #
# DLQ human replay (proposal only; execution happens after approval)
# --------------------------------------------------------------------------- #


@router.post(
    "/agent-queue/dead-letters/{task_id}/replay",
    response_model=DlqReplayProposalOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a DLQ replay proposal (never a direct replay)",
)
async def propose_dlq_replay(
    task_id: UUID,
    body: DlqReplayProposeRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> DlqReplayProposalOut:
    """Create a replay proposal; it only runs after a human approval."""
    try:
        proposal = await agent_queue.propose_dlq_replay(
            db,
            workspace_id=workspace_id,
            task_id=task_id,
            reason=body.reason,
            trace_id=get_trace_id(),
        )
    except agent_queue.AgentQueueError as exc:
        raise _error(exc) from exc
    metadata_ = proposal.metadata_ or {}
    return DlqReplayProposalOut(
        proposal_id=proposal.id,
        status=proposal.status,
        approval_type=proposal.approval_type,
        task_id=task_id,
        reason=metadata_.get("proposed_reason"),
        original_error=metadata_.get("original_error"),
        original_attempt_count=metadata_.get("original_attempt_count", 0),
        trace_id=proposal.trace_id,
    )


# --------------------------------------------------------------------------- #
# Runtime overview
# --------------------------------------------------------------------------- #


@router.get(
    "/agent-runtime/overview",
    response_model=RuntimeOverviewOut,
    summary="Runtime Dashboard summary (one request)",
)
async def runtime_overview(db: DbSession, workspace_id: WorkspaceId) -> RuntimeOverviewOut:
    """Return agents/workers/queue/executions/retry/DLQ/approvals/alerts/cost."""
    backend = task_queue.get_queue_backend()
    overview = await runtime_ops.runtime_overview(
        db, backend, workspace_id=workspace_id, trace_id=get_trace_id()
    )
    return RuntimeOverviewOut.model_validate(overview)
