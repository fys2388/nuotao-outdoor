"""Agent queue observability (M5.3/5.4).

Computes queue stats / health / dead-letter / trace views from LIVE Redis and
PostgreSQL state - nothing is hardcoded or cached-stale. Delivery semantics
(documented, never overstated):

- Redis Streams = **at-least-once** transport (a message may be delivered more
  than once: producer retry, worker crash + XAUTOCLAIM, duplicate XADD).
- PostgreSQL task/execution rows = **business source of truth**; the worker
  only executes a task whose row is still ``pending``, so the business effect
  is **effectively-once / idempotent**.
- Message-level dedup tokens = a Redis-side optimization on top of the DB
  guard; they never replace it.

Everything is workspace-scoped; health checks and trace queries mirror to
``event_log`` with a ``trace_id``. No replay of dead letters is offered - the
DLQ surface is read-only for viewing / statistics / audit.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.agent import AiAgentRun
from app.models.agent_operations import AgentApproval
from app.models.agent_runtime import AgentEvaluation, AgentExecution, AgentTask
from app.models.agent_runtime_hardening import AgentTaskAttempt
from app.models.event import EventLog
from app.models.product_intelligence import ProductDecision
from app.services import agent_workers, event_service, task_queue

TERMINAL_STATUSES = ("completed", "failed", "rejected")

logger = logging.getLogger(__name__)


class AgentQueueError(Exception):
    """Raised when a queue operation cannot complete."""


def agent_queue_error(message: str) -> AgentQueueError:
    """Return a pre-built queue error (keeps raise sites one-liners)."""
    return AgentQueueError(message)


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _age_ms(value: datetime | None) -> int | None:
    if value is None:
        return None
    return max(0, int((_now() - _aware(value)).total_seconds() * 1000))


def _duration_ms(start: datetime | None, end: datetime | None) -> int | None:
    """Milliseconds between two timestamps (None when either is missing)."""
    if start is None or end is None:
        return None
    delta = _aware(end) - _aware(start)
    return max(0, int(delta.total_seconds() * 1000))


def _json_safe(value: Any) -> Any:
    """Deep-convert non-JSON-native values (Decimal/datetime/UUID)."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


async def _count_tasks(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    agent_id: UUID | None = None,
    status: str | None = None,
) -> int:
    """Count AgentTask rows for one workspace (optionally filtered)."""
    filters = [AgentTask.workspace_id == workspace_id]
    if agent_id is not None:
        filters.append(AgentTask.agent_id == agent_id)
    if status is not None:
        filters.append(AgentTask.status == status)
    return int(
        (
            await session.execute(select(func.count()).select_from(AgentTask).where(*filters))
        ).scalar_one()
    )


async def _oldest_ages(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    agent_id: UUID | None = None,
) -> tuple[datetime | None, datetime | None]:
    """Return ``(oldest_pending_created_at, oldest_running_started_at)``."""
    filters = [AgentTask.workspace_id == workspace_id]
    if agent_id is not None:
        filters.append(AgentTask.agent_id == agent_id)
    oldest_pending = (
        await session.execute(
            select(func.min(AgentTask.created_at)).where(*filters, AgentTask.status == "pending")
        )
    ).scalar_one()
    oldest_running = (
        await session.execute(
            select(func.min(AgentTask.started_at)).where(*filters, AgentTask.status == "running")
        )
    ).scalar_one()
    return oldest_pending, oldest_running


# --------------------------------------------------------------------------- #
# Queue stats
# --------------------------------------------------------------------------- #


async def queue_stats(
    session: AsyncSession,
    backend: task_queue.TaskQueueBackend,
    *,
    workspace_id: UUID,
    agent_id: UUID | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Compute queue statistics from live Redis + PostgreSQL state.

    ``queue_depth`` is the Redis stream length; per-status counts come from
    the DB task rows; throughput / success / failure rates come from the
    execution audit trail within the configurable stats window.
    """
    settings = get_settings()
    stream = task_queue.task_stream()
    stream_length = await backend.stream_length(stream)
    delayed_count = await backend.delayed_count(task_queue.retry_key())

    pending_count = await _count_tasks(
        session, workspace_id=workspace_id, agent_id=agent_id, status="pending"
    )
    running_count = await _count_tasks(
        session, workspace_id=workspace_id, agent_id=agent_id, status="running"
    )
    waiting_approval_count = await _count_tasks(
        session, workspace_id=workspace_id, agent_id=agent_id, status="waiting_approval"
    )
    dead_letter_count = await _count_tasks(
        session, workspace_id=workspace_id, agent_id=agent_id, status="failed"
    )
    # A retry is a pending task that already consumed >= 1 attempt.
    retry_filters = [
        AgentTask.workspace_id == workspace_id,
        AgentTask.status == "pending",
        AgentTask.attempt_count > 0,
    ]
    if agent_id is not None:
        retry_filters.append(AgentTask.agent_id == agent_id)
    retry_count = int(
        (
            await session.execute(select(func.count()).select_from(AgentTask).where(*retry_filters))
        ).scalar_one()
    )

    oldest_pending, oldest_running = await _oldest_ages(
        session, workspace_id=workspace_id, agent_id=agent_id
    )

    # Throughput window from the execution audit trail (the same source the
    # metrics service aggregates) - never hardcoded.
    window_start = _now() - timedelta(minutes=max(settings.queue_stats_window_minutes, 1))
    exec_filters = [
        AgentExecution.workspace_id == workspace_id,
        AgentExecution.status.in_(TERMINAL_STATUSES),
        AgentExecution.completed_at.is_not(None),
        AgentExecution.completed_at >= window_start,
    ]
    if agent_id is not None:
        exec_filters.append(AgentExecution.agent_id == agent_id)
    executions = (
        (await session.execute(select(AgentExecution).where(*exec_filters))).scalars().all()
    )
    total = len(executions)
    success = sum(1 for row in executions if row.status == "completed")
    failure = total - success
    window_minutes = max(settings.queue_stats_window_minutes, 1)

    return {
        "backend": settings.task_queue_backend,
        "stream": stream,
        "stream_length": stream_length,
        "delayed_count": delayed_count,
        "queue_depth": stream_length,
        "pending_count": pending_count,
        "running_count": running_count,
        "waiting_approval_count": waiting_approval_count,
        "retry_count": retry_count,
        "dead_letter_count": dead_letter_count,
        "oldest_pending_age_ms": _age_ms(oldest_pending),
        "oldest_running_age_ms": _age_ms(oldest_running),
        "throughput_per_minute": round(total / window_minutes, 3),
        "success_rate": round(success / total, 4) if total else 0.0,
        "failure_rate": round(failure / total, 4) if total else 0.0,
    }


# --------------------------------------------------------------------------- #
# Queue health
# --------------------------------------------------------------------------- #


async def queue_health(
    session: AsyncSession,
    backend: task_queue.TaskQueueBackend,
    *,
    workspace_id: UUID,
    agent_id: UUID | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Evaluate queue health from live Redis + PostgreSQL state.

    Checks (all thresholds config-driven): redis ping, stream + consumer
    group existence, stale PEL messages, dead / missing workers, oversized
    pending and dead-letter queues and long-running tasks. Returns
    ``healthy`` / ``degraded`` / ``unhealthy`` with per-check detail.
    """
    settings = get_settings()
    raw = await backend.healthcheck()
    checks: dict[str, str] = {}
    details: dict[str, Any] = {"raw": _json_safe(raw)}

    if not raw.get("ping"):
        checks["redis"] = "unhealthy"
        return {"status": "unhealthy", "checks": checks, "details": details}
    checks["redis"] = "ok"

    pending_count = await _count_tasks(
        session, workspace_id=workspace_id, agent_id=agent_id, status="pending"
    )
    running_count = await _count_tasks(
        session, workspace_id=workspace_id, agent_id=agent_id, status="running"
    )
    dead_letter_count = await _count_tasks(
        session, workspace_id=workspace_id, agent_id=agent_id, status="failed"
    )
    oldest_pending, oldest_running = await _oldest_ages(
        session, workspace_id=workspace_id, agent_id=agent_id
    )
    oldest_pending_ms = _age_ms(oldest_pending)
    oldest_running_ms = _age_ms(oldest_running)

    # Stream + consumer group.
    if raw.get("stream_exists"):
        checks["stream"] = "ok"
    else:
        idle = pending_count == 0 and running_count == 0
        checks["stream"] = "ok" if idle else "degraded"
        details["stream_missing_with_tasks"] = not idle
    if raw.get("group_exists"):
        checks["consumer_group"] = "ok"
    else:
        checks["consumer_group"] = "degraded"

    # Stale PEL messages (delivered but never acked past the reclaim idle).
    stale_pending = int(raw.get("stale_pending_count") or 0)
    details["stale_pending_count"] = stale_pending
    if stale_pending > 0 or (
        oldest_pending_ms is not None
        and oldest_pending_ms > settings.queue_health_oldest_pending_ms
    ) or pending_count > settings.queue_health_max_pending:
        checks["pending"] = "degraded"
    else:
        checks["pending"] = "ok"

    # Long-running executions (worker lost without a terminal state).
    if (
        oldest_running_ms is not None
        and oldest_running_ms > settings.queue_health_oldest_running_ms
    ):
        checks["long_running"] = "degraded"
    else:
        checks["long_running"] = "ok"

    # Dead letters.
    if dead_letter_count > settings.queue_health_max_dead_letters:
        checks["dead_letter"] = "degraded"
    else:
        checks["dead_letter"] = "ok"

    # Workers: any dead worker is degraded; zero live workers with work
    # pending is degraded too.
    workers = await agent_workers.list_workers(backend)
    dead_workers = [worker for worker in workers if worker["is_dead"]]
    live_workers = [worker for worker in workers if not worker["is_dead"]]
    details["worker_count"] = len(workers)
    details["dead_worker_count"] = len(dead_workers)
    for worker in dead_workers:
        await agent_workers.emit_worker_event(
            session,
            event_type="agent.queue.worker_dead",
            worker_id=worker["worker_id"],
            payload={"last_heartbeat_at": worker["last_heartbeat_at"]},
            trace_id=trace_id,
        )
    if len(dead_workers) > settings.queue_health_max_stale_workers or (not live_workers and (pending_count > 0 or running_count > 0)):
        checks["workers"] = "degraded"
    else:
        checks["workers"] = "ok"

    degraded = [name for name, state in checks.items() if state == "degraded"]
    status = "degraded" if degraded else "healthy"
    return {"status": status, "checks": checks, "details": details}


# --------------------------------------------------------------------------- #
# Dead-letter query (read-only; no replay by design)
# --------------------------------------------------------------------------- #


async def list_dead_letters(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    agent_id: UUID | None = None,
    error_type: str | None = None,
    task_id: UUID | None = None,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
    trace_id: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """List dead-lettered tasks (``status=failed``) newest first.

    The error class is taken from the task's most recent execution audit row
    (``agent_executions.error_type``). Read-only: no automatic replay.
    """
    filters = [AgentTask.workspace_id == workspace_id, AgentTask.status == "failed"]
    if agent_id is not None:
        filters.append(AgentTask.agent_id == agent_id)
    if task_id is not None:
        filters.append(AgentTask.id == task_id)
    if from_dt is not None:
        filters.append(AgentTask.completed_at >= from_dt)
    if to_dt is not None:
        filters.append(AgentTask.completed_at <= to_dt)
    rows = (await session.execute(select(AgentTask).where(*filters))).scalars().all()

    error_by_task: dict[UUID, str | None] = {}
    if rows:
        task_ids = [row.id for row in rows]
        exec_rows = (
            (
                await session.execute(
                    select(AgentExecution).where(
                        AgentExecution.workspace_id == workspace_id,
                        AgentExecution.task_id.in_(task_ids),
                        AgentExecution.error_type.is_not(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        # The latest execution per task wins.
        by_task: dict[UUID, list[AgentExecution]] = {}
        for exec_row in exec_rows:
            if exec_row.task_id is not None:
                by_task.setdefault(exec_row.task_id, []).append(exec_row)
        for task_uuid, executions in by_task.items():
            executions.sort(key=lambda row: row.started_at or _now(), reverse=True)
            error_by_task[task_uuid] = executions[0].error_type

    ordered = sorted(
        rows,
        key=lambda row: row.completed_at or row.created_at or _now(),
        reverse=True,
    )
    items: list[dict[str, Any]] = []
    for row in ordered:
        error = error_by_task.get(row.id)
        if error_type is not None and error != error_type:
            continue
        items.append(
            {
                "task_id": row.id,
                "agent_id": row.agent_id,
                "error_type": error,
                "error_message": row.error_message,
                "created_at": _iso(row.created_at),
                "completed_at": _iso(row.completed_at),
                "trace_id": row.trace_id,
            }
        )
    total = len(items)
    return items[offset : offset + limit], total


# --------------------------------------------------------------------------- #
# Full-chain trace query
# --------------------------------------------------------------------------- #


async def get_trace(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    trace_id: str,
    limit: int = 200,
) -> dict[str, Any] | None:
    """Return the full execution chain for one ``trace_id`` (JSON-safe).

    Aggregates, in time order: task -> execution -> attempt -> LLM call ->
    tool call -> decision -> evaluation -> event log. Returns ``None`` when
    the trace id does not exist (404 at the API layer).
    """
    nodes: list[dict[str, Any]] = []

    tasks = (
        (
            await session.execute(
                select(AgentTask).where(
                    AgentTask.workspace_id == workspace_id,
                    AgentTask.trace_id == trace_id,
                )
            )
        )
        .scalars()
        .all()
    )
    for row in tasks:
        nodes.append(
            {
                "type": "task",
                "id": str(row.id),
                "status": row.status,
                "timestamp": _iso(row.created_at),
                "duration_ms": _duration_ms(row.created_at, row.completed_at),
                "data": {
                    "agent_id": str(row.agent_id) if row.agent_id else None,
                    "attempt_count": row.attempt_count,
                    "priority": row.priority,
                    "error_message": row.error_message,
                    "idempotency_key": row.idempotency_key,
                    "result": _json_safe(row.result),
                },
            }
        )

    executions = (
        (
            await session.execute(
                select(AgentExecution).where(
                    AgentExecution.workspace_id == workspace_id,
                    AgentExecution.trace_id == trace_id,
                )
            )
        )
        .scalars()
        .all()
    )
    for row in executions:
        execution_duration = _duration_ms(row.started_at, row.completed_at)
        nodes.append(
            {
                "type": "execution",
                "id": str(row.id),
                "status": row.status,
                "timestamp": _iso(row.started_at),
                "duration_ms": execution_duration,
                "data": {
                    "task_id": str(row.task_id) if row.task_id else None,
                    "agent_id": str(row.agent_id) if row.agent_id else None,
                    "worker_id": row.worker_id,
                    "attempt_number": row.attempt_number,
                    "error_type": row.error_type,
                    "error_message": row.error_message,
                    "approval": _json_safe(row.approval),
                    "context_snapshot": _json_safe(row.context_snapshot),
                    "input": _json_safe(row.input),
                    "output": _json_safe(row.output),
                },
            }
        )
        # LLM call telemetry lives on the execution audit row.
        nodes.append(
            {
                "type": "llm_call",
                "id": f"{row.id}:llm",
                "status": row.status,
                "timestamp": _iso(row.started_at),
                "duration_ms": row.latency_ms,
                "data": {
                    "provider": row.provider,
                    "model": row.model,
                    "tokens": _json_safe(row.tokens),
                    "cost": str(row.cost) if row.cost is not None else None,
                    "latency_ms": row.latency_ms,
                },
            }
        )
        for index, tool_call in enumerate(row.tool_calls or []):
            nodes.append(
                {
                    "type": "tool_call",
                    "id": f"{row.id}:tool:{index}",
                    "status": None,
                    "timestamp": None,
                    "duration_ms": None,
                    "data": _json_safe(tool_call),
                }
            )

    attempts = (
        (
            await session.execute(
                select(AgentTaskAttempt).where(
                    AgentTaskAttempt.workspace_id == workspace_id,
                    AgentTaskAttempt.trace_id == trace_id,
                )
            )
        )
        .scalars()
        .all()
    )
    for row in attempts:
        nodes.append(
            {
                "type": "attempt",
                "id": str(row.id),
                "status": row.status,
                "timestamp": _iso(row.created_at),
                "duration_ms": row.latency_ms,
                "data": {
                    "task_id": str(row.task_id) if row.task_id else None,
                    "execution_id": str(row.execution_id) if row.execution_id else None,
                    "attempt_number": row.attempt_number,
                    "error_type": row.error_type,
                    "error_message": row.error_message,
                    "worker_id": row.worker_id,
                },
            }
        )

    ai_runs = (
        (
            await session.execute(
                select(AiAgentRun).where(
                    AiAgentRun.workspace_id == workspace_id,
                    AiAgentRun.trace_id == trace_id,
                )
            )
        )
        .scalars()
        .all()
    )
    for row in ai_runs:
        nodes.append(
            {
                "type": "ai_agent_run",
                "id": str(row.id),
                "status": row.status,
                "timestamp": _iso(row.created_at),
                "duration_ms": _duration_ms(row.created_at, row.completed_at),
                "data": {
                    "agent": row.agent,
                    "trigger": row.trigger,
                    "cost": str(row.cost) if row.cost is not None else None,
                    "output": _json_safe(row.output),
                },
            }
        )

    decisions = (
        (
            await session.execute(
                select(ProductDecision).where(
                    ProductDecision.workspace_id == workspace_id,
                    ProductDecision.trace_id == trace_id,
                )
            )
        )
        .scalars()
        .all()
    )
    for row in decisions:
        nodes.append(
            {
                "type": "decision",
                "id": str(row.id),
                "status": row.approval_status,
                "timestamp": _iso(row.created_at),
                "duration_ms": None,
                "data": {
                    "product_id": str(row.product_id),
                    "decision": row.decision,
                    "confidence": str(row.confidence) if row.confidence is not None else None,
                    "approval_status": row.approval_status,
                    "approved_by": row.approved_by,
                    "approved_at": _iso(row.approved_at),
                    "reasons": _json_safe(row.reasons),
                    "risks": _json_safe(row.risks),
                    "recommended_price": (
                        str(row.recommended_price) if row.recommended_price is not None else None
                    ),
                },
            }
        )

    evaluations = (
        (
            await session.execute(
                select(AgentEvaluation).where(
                    AgentEvaluation.workspace_id == workspace_id,
                    AgentEvaluation.trace_id == trace_id,
                )
            )
        )
        .scalars()
        .all()
    )
    for row in evaluations:
        nodes.append(
            {
                "type": "evaluation",
                "id": str(row.id),
                "status": row.prediction_result,
                "timestamp": _iso(row.created_at),
                "duration_ms": None,
                "data": {
                    "agent_id": str(row.agent_id) if row.agent_id else None,
                    "prediction": _json_safe(row.prediction),
                    "actual_result": _json_safe(row.actual_result),
                    "accuracy": _json_safe(row.accuracy),
                    "success_flag": row.success_flag,
                    "confidence": str(row.confidence) if row.confidence is not None else None,
                    "confidence_bucket": row.confidence_bucket,
                    "human_rating": row.human_rating,
                },
            }
        )

    events = (
        (
            await session.execute(
                select(EventLog)
                .where(EventLog.workspace_id == workspace_id, EventLog.trace_id == trace_id)
                .order_by(EventLog.id.asc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    for row in events:
        nodes.append(
            {
                "type": "event",
                "id": str(row.id),
                "status": None,
                "timestamp": _iso(row.created_at),
                "duration_ms": None,
                "data": {
                    "event_type": row.event_type,
                    "entity_type": row.entity_type,
                    "entity_id": row.entity_id,
                    "payload": _json_safe(row.payload),
                },
            }
        )

    if not nodes:
        return None
    nodes.sort(key=lambda node: node["timestamp"] or "")
    return {"trace_id": trace_id, "nodes": nodes}


# --------------------------------------------------------------------------- #
# DLQ human replay (M5.4): proposal -> human approval -> new attempt
# --------------------------------------------------------------------------- #


async def propose_dlq_replay(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    task_id: UUID,
    reason: str,
    trace_id: str | None = None,
) -> AgentApproval:
    """Create a DLQ replay PROPOSAL (never a direct replay).

    The proposal is an ``AgentApproval`` row with ``approval_type=DLQ_REPLAY``
    and status ``pending``. Only a human approval through the Approval Center
    may actually re-enqueue the task (see :func:`replay_dead_letter`). The
    partial unique index guarantees at most one pending proposal per task, so
    two people cannot both propose/approve the same replay.
    """
    task = await session.get(AgentTask, task_id)
    if task is None or task.workspace_id != workspace_id:
        raise agent_queue_error("dead-letter task not found")
    if task.status != "failed":
        raise agent_queue_error(
            f"task is {task.status}; only dead-lettered (failed) tasks can be replayed"
        )
    approval = AgentApproval(
        workspace_id=workspace_id,
        approval_type="DLQ_REPLAY",
        status="pending",
        entity_type="agent_task",
        entity_id=str(task.id),
        target_task_id=task.id,
        agent_id=task.agent_id,
        metadata_={
            "proposed_reason": reason,
            "original_error": task.error_message,
            "original_attempt_count": task.attempt_count,
        },
        trace_id=trace_id,
    )
    session.add(approval)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise agent_queue_error("a replay proposal already exists for this task") from None
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.approval.created",
        entity_type="agent_approval",
        entity_id=str(approval.id),
        payload={
            "approval_type": "DLQ_REPLAY",
            "entity_id": str(task.id),
            "reason": reason,
        },
        trace_id=trace_id,
    )
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.dlq.replay_proposed",
        entity_type="agent_task",
        entity_id=str(task.id),
        payload={
            "proposal_id": str(approval.id),
            "reason": reason,
            "original_error": task.error_message,
            "attempt_count": task.attempt_count,
        },
        trace_id=trace_id,
    )
    logger.info(
        "DLQ replay proposed for task %s (proposal=%s) trace=%s",
        task.id,
        approval.id,
        trace_id,
    )
    await session.refresh(approval)
    return approval


async def replay_dead_letter(
    session: AsyncSession,
    backend: task_queue.TaskQueueBackend,
    *,
    workspace_id: UUID,
    task_id: UUID,
    trace_id: str | None = None,
) -> AgentTask:
    """Execute an APPROVED DLQ replay: requeue one new attempt.

    Called only from the Approval Center after a human approved the replay
    proposal. The original task row is mutated to ``pending`` (fresh attempt
    number) and re-enqueued; the original attempt audit rows are never
    touched. A task that is no longer ``failed`` (someone else already
    replayed it) refuses the replay.
    """
    task = await session.get(AgentTask, task_id)
    if task is None or task.workspace_id != workspace_id:
        raise agent_queue_error("dead-letter task not found")
    if task.status != "failed":
        raise agent_queue_error(
            f"task is {task.status}; only dead-lettered (failed) tasks can be replayed"
        )
    attempt = max(task.attempt_count or 0, 1) + 1
    task.status = "pending"
    task.started_at = None
    task.completed_at = None
    task.error_message = None
    task.attempt_count = attempt
    await session.flush()
    await task_queue.enqueue_task(
        backend,
        workspace_id=workspace_id,
        task_id=task.id,
        attempt=attempt,
        idempotency_key=task.idempotency_key,
    )
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.dlq.replay_started",
        entity_type="agent_task",
        entity_id=str(task.id),
        payload={"attempt": attempt, "source": "human_approved_replay"},
        trace_id=trace_id,
    )
    logger.info(
        "DLQ replay started for task %s (attempt=%s) trace=%s",
        task.id,
        attempt,
        trace_id,
    )
    return task
