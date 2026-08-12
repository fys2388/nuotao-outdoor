"""Agent Runtime hardening endpoints (M5.1).

Policies (execution / budget / retry) are versioned and config-driven; the
metrics snapshot aggregates execution telemetry; queue stats and the sweeper
are operational surfaces. Everything is workspace-scoped and audited via
``event_log`` with a ``trace_id``. No business agent and no auto-executed
business action live here.
"""

import logging
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.tracing import get_trace_id
from app.core.workspace import get_workspace_id
from app.schemas.agent_runtime_hardening import (
    AgentMetricOut,
    BudgetPolicyCreate,
    BudgetPolicyOut,
    ExecutionPolicyCreate,
    ExecutionPolicyOut,
    MetricsSnapshotRequest,
    QueueStatsOut,
    RetryPolicyCreate,
    RetryPolicyOut,
    SweeperRunOut,
)
from app.services import (
    agent_metrics,
    agent_policies,
    agent_sweeper,
    task_queue,
)

router = APIRouter(tags=["agent-runtime-hardening"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
WorkspaceId = Annotated[UUID, Depends(get_workspace_id)]
logger = logging.getLogger(__name__)


def _policy_error(exc: Exception) -> HTTPException:
    if isinstance(exc, agent_policies.AgentPolicyError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


# --------------------------------------------------------------------------- #
# Execution policy
# --------------------------------------------------------------------------- #


@router.post(
    "/agent-policies/execution",
    response_model=ExecutionPolicyOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new version of an agent execution policy",
)
async def set_execution_policy(
    body: ExecutionPolicyCreate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ExecutionPolicyOut:
    """Versioned per-agent execution policy (previous version retired)."""
    try:
        policy = await agent_policies.set_execution_policy(
            db,
            workspace_id=workspace_id,
            agent_id=body.agent_id,
            max_concurrent=body.max_concurrent,
            execution_timeout_seconds=body.execution_timeout_seconds,
            approval_timeout_seconds=body.approval_timeout_seconds,
            max_context_size=body.max_context_size,
            retry_policy_id=body.retry_policy_id,
            enabled=body.enabled,
            trace_id=get_trace_id(),
        )
    except agent_policies.AgentPolicyError as exc:
        raise _policy_error(exc) from exc
    return ExecutionPolicyOut.model_validate(policy)


@router.get(
    "/agent-policies/execution",
    response_model=ExecutionPolicyOut,
    summary="Get the current execution policy for an agent",
)
async def get_execution_policy(
    db: DbSession,
    workspace_id: WorkspaceId,
    agent_id: Annotated[UUID, Query()],
) -> ExecutionPolicyOut:
    """Return the current (active) execution policy; seeds defaults if needed."""
    policy = await agent_policies.get_execution_policy(
        db, workspace_id=workspace_id, agent_id=agent_id, trace_id=get_trace_id()
    )
    return ExecutionPolicyOut.model_validate(policy)


# --------------------------------------------------------------------------- #
# Budget policy
# --------------------------------------------------------------------------- #


@router.post(
    "/agent-policies/budget",
    response_model=BudgetPolicyOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new version of an agent budget policy",
)
async def set_budget_policy(
    body: BudgetPolicyCreate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> BudgetPolicyOut:
    """Versioned per-agent budget policy (previous version retired)."""
    try:
        policy = await agent_policies.set_budget_policy(
            db,
            workspace_id=workspace_id,
            agent_id=body.agent_id,
            monthly_budget=body.monthly_budget,
            max_cost_per_execution=body.max_cost_per_execution,
            alert_threshold=body.alert_threshold,
            currency=body.currency,
            enabled=body.enabled,
            trace_id=get_trace_id(),
        )
    except agent_policies.AgentPolicyError as exc:
        raise _policy_error(exc) from exc
    return BudgetPolicyOut.model_validate(policy)


@router.get(
    "/agent-policies/budget",
    response_model=BudgetPolicyOut,
    summary="Get the current budget policy for an agent",
)
async def get_budget_policy(
    db: DbSession,
    workspace_id: WorkspaceId,
    agent_id: Annotated[UUID, Query()],
) -> BudgetPolicyOut:
    """Return the current budget policy; seeds defaults if needed."""
    policy = await agent_policies.get_budget_policy(
        db, workspace_id=workspace_id, agent_id=agent_id, trace_id=get_trace_id()
    )
    return BudgetPolicyOut.model_validate(policy)


# --------------------------------------------------------------------------- #
# Retry policy
# --------------------------------------------------------------------------- #


@router.post(
    "/agent-retry-policies",
    response_model=RetryPolicyOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new version of a retry policy",
)
async def set_retry_policy(
    body: RetryPolicyCreate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> RetryPolicyOut:
    """Versioned reusable retry policy (previous version retired)."""
    try:
        policy = await agent_policies.set_retry_policy(
            db,
            workspace_id=workspace_id,
            retry_policy_id=body.retry_policy_id,
            name=body.name,
            max_attempts=body.max_attempts,
            backoff_base_seconds=body.backoff_base_seconds,
            backoff_multiplier=body.backoff_multiplier,
            max_backoff_seconds=body.max_backoff_seconds,
            retry_on_error_types=body.retry_on_error_types,
            enabled=body.enabled,
            trace_id=get_trace_id(),
        )
    except agent_policies.AgentPolicyError as exc:
        raise _policy_error(exc) from exc
    return RetryPolicyOut.model_validate(policy)


@router.get(
    "/agent-retry-policies",
    response_model=RetryPolicyOut,
    summary="Get the current retry policy by code",
)
async def get_retry_policy(
    db: DbSession,
    workspace_id: WorkspaceId,
    retry_policy_id: Annotated[str, Query()] = "standard",
) -> RetryPolicyOut:
    """Return the current retry policy; seeds the ``standard`` default."""
    policy = await agent_policies.get_retry_policy(
        db, workspace_id=workspace_id, retry_policy_id=retry_policy_id, trace_id=get_trace_id()
    )
    return RetryPolicyOut.model_validate(policy)


# --------------------------------------------------------------------------- #
# Agent metrics
# --------------------------------------------------------------------------- #


@router.post(
    "/agent-metrics/snapshot",
    response_model=list[AgentMetricOut],
    summary="Snapshot daily metrics for one (or all) agents",
)
async def snapshot_metrics(
    body: MetricsSnapshotRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> list[AgentMetricOut]:
    """Aggregate execution telemetry into daily metric rows (upsert)."""
    from sqlalchemy import select

    from app.models.agent_runtime import AgentRegistry

    if body.agent_id is not None:
        agents = [await db.get(AgentRegistry, body.agent_id)]
        agents = [a for a in agents if a is not None and a.workspace_id == workspace_id]
    else:
        agents = (
            (
                await db.execute(
                    select(AgentRegistry).where(AgentRegistry.workspace_id == workspace_id)
                )
            )
            .scalars()
            .all()
        )
    rows = []
    for agent in agents:
        row = await agent_metrics.snapshot_metrics(
            db,
            workspace_id=workspace_id,
            agent_id=agent.id,
            metric_date=body.metric_date or date.today(),
            trace_id=get_trace_id(),
        )
        rows.append(row)
    return [AgentMetricOut.model_validate(row) for row in rows]


@router.get(
    "/agent-metrics",
    response_model=list[AgentMetricOut],
    summary="Query daily agent metrics",
)
async def list_metrics(
    db: DbSession,
    workspace_id: WorkspaceId,
    agent_id: Annotated[UUID | None, Query()] = None,
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[AgentMetricOut]:
    """Return metrics rows, newest first, workspace-scoped."""
    rows, _total = await agent_metrics.list_metrics(
        db,
        workspace_id=workspace_id,
        agent_id=agent_id,
        from_date=from_date,
        to_date=to_date,
        limit=min(limit, 200),
        offset=max(offset, 0),
    )
    return [AgentMetricOut.model_validate(row) for row in rows]


# --------------------------------------------------------------------------- #
# Queue + sweeper (operational)
# --------------------------------------------------------------------------- #


@router.get(
    "/agent-queue/stats",
    response_model=QueueStatsOut,
    summary="Shallow task queue health stats",
)
async def queue_stats(db: DbSession, workspace_id: WorkspaceId) -> QueueStatsOut:
    """Return queue depth and delayed-retry counts (no business data)."""
    backend = task_queue.get_queue_backend()
    stats = await task_queue.queue_stats(backend)
    return QueueStatsOut.model_validate(stats)


@router.post(
    "/agent-sweeper/run",
    response_model=SweeperRunOut,
    summary="Run stale-approval, stale-execution and reconcile sweepers",
)
async def run_sweeper(db: DbSession, workspace_id: WorkspaceId) -> SweeperRunOut:
    """One hardening pass: expire approvals, fail stale runs, requeue tasks."""
    backend = task_queue.get_queue_backend()
    trace_id = get_trace_id()
    approvals_expired = await agent_sweeper.expire_stale_approvals(
        db, workspace_id=workspace_id, trace_id=trace_id
    )
    stale_failed, tasks_requeued = await agent_sweeper.fail_stale_executions(
        db, workspace_id=workspace_id, backend=backend, trace_id=trace_id
    )
    pending_enqueued = await agent_sweeper.reconcile_pending_tasks(
        db, workspace_id=workspace_id, backend=backend, trace_id=trace_id
    )
    return SweeperRunOut(
        approvals_expired=approvals_expired,
        stale_executions_failed=stale_failed,
        tasks_requeued=tasks_requeued,
        pending_tasks_enqueued=pending_enqueued,
    )
