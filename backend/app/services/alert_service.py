"""Alert Service (M5.4): deterministic, config-driven runtime alerts.

Evaluates LIVE Redis + PostgreSQL state (queue stats, worker heartbeat,
execution telemetry, budget policies, pending approvals) against config-driven
thresholds and opens one ``AgentAlert`` per problem. Alert lifecycle:

    open -> acknowledged -> resolved

Dedup: ``workspace_id + agent_id + alert_type + resource`` forms the
``dedup_key``; a partial unique index keeps at most ONE active
(open/acknowledged) alert per key, so a condition that has not recovered
never floods the list. Resolving frees the key for a future recurrence.

No Sentry/Prometheus hard dependency - this is the internal deterministic
alert layer. Every state change mirrors to ``event_log`` with a ``trace_id``.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.agent_operations import AgentAlert
from app.models.agent_runtime import AgentExecution, AgentRegistry
from app.models.event import EventLog
from app.services import (
    agent_budget,
    agent_policies,
    agent_queue,
    agent_workers,
    event_service,
    task_queue,
)

logger = logging.getLogger(__name__)

# Alert types (M5.4).
ALERT_QUEUE_BACKLOG = "queue_backlog"
ALERT_OLDEST_PENDING = "oldest_pending"
ALERT_WORKER_DEAD = "worker_dead"
ALERT_FAILURE_RATE = "failure_rate"
ALERT_RETRY_RATE = "retry_rate"
ALERT_DLQ_GROWTH = "dlq_growth"
ALERT_LLM_LATENCY = "llm_latency"
ALERT_BUDGET_WARNING = "budget_warning"
ALERT_APPROVAL_TIMEOUT = "approval_timeout"

ALERT_TYPES: tuple[str, ...] = (
    ALERT_QUEUE_BACKLOG,
    ALERT_OLDEST_PENDING,
    ALERT_WORKER_DEAD,
    ALERT_FAILURE_RATE,
    ALERT_RETRY_RATE,
    ALERT_DLQ_GROWTH,
    ALERT_LLM_LATENCY,
    ALERT_BUDGET_WARNING,
    ALERT_APPROVAL_TIMEOUT,
)

# Alert lifecycle states.
ALERT_OPEN = "open"
ALERT_ACKNOWLEDGED = "acknowledged"
ALERT_RESOLVED = "resolved"
ALERT_STATUSES: tuple[str, ...] = (ALERT_OPEN, ALERT_ACKNOWLEDGED, ALERT_RESOLVED)

ACTIVE_ALERT_STATUSES: tuple[str, ...] = (ALERT_OPEN, ALERT_ACKNOWLEDGED)


class AlertServiceError(Exception):
    """Raised when an alert operation cannot complete."""


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def dedup_key(*, workspace_id: UUID, agent_id: UUID | None, alert_type: str, resource: str) -> str:
    """Stable alert identity: workspace + agent + type + resource."""
    return f"{workspace_id}:{agent_id or '*'}:{alert_type}:{resource}"


async def _has_active_alert(session: AsyncSession, *, workspace_id: UUID, key: str) -> bool:
    """Return True when an open/acknowledged alert already exists for the key."""
    row = (
        await session.execute(
            select(AgentAlert.id).where(
                AgentAlert.workspace_id == workspace_id,
                AgentAlert.dedup_key == key,
                AgentAlert.status.in_(ACTIVE_ALERT_STATUSES),
            )
        )
    ).scalar_one_or_none()
    return row is not None


async def _open_alert(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    agent_id: UUID | None,
    alert_type: str,
    severity: str,
    resource: str,
    message: str,
    metadata_: dict[str, Any],
    threshold_snapshot: dict[str, Any],
    trace_id: str | None,
) -> AgentAlert | None:
    """Create one alert unless an active alert already exists (dedup)."""
    key = dedup_key(
        workspace_id=workspace_id, agent_id=agent_id, alert_type=alert_type, resource=resource
    )
    if await _has_active_alert(session, workspace_id=workspace_id, key=key):
        return None
    alert = AgentAlert(
        workspace_id=workspace_id,
        agent_id=agent_id,
        alert_type=alert_type,
        status=ALERT_OPEN,
        severity=severity,
        resource=resource,
        dedup_key=key,
        message=message,
        metadata_=metadata_,
        threshold_snapshot=threshold_snapshot,
        trace_id=trace_id,
    )
    session.add(alert)
    try:
        await session.flush()
    except IntegrityError:
        # A concurrent evaluation opened the same alert first - keep theirs.
        await session.rollback()
        logger.info("alert dedup raced for %s (key=%s)", alert_type, key)
        return None
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.alert.created",
        entity_type="agent_alert",
        entity_id=str(alert.id),
        payload={
            "alert_type": alert_type,
            "severity": severity,
            "resource": resource,
            "message": message,
            "threshold_snapshot": threshold_snapshot,
        },
        trace_id=trace_id,
    )
    logger.warning("alert opened type=%s resource=%s trace=%s", alert_type, resource, trace_id)
    await session.refresh(alert)
    return alert


async def _window_start() -> datetime:
    return _now() - timedelta(minutes=max(get_settings().alert_stats_window_minutes, 1))


async def _execution_telemetry(session: AsyncSession, *, workspace_id: UUID) -> dict[str, Any]:
    """Aggregate terminal executions within the alert stats window."""
    window_start = await _window_start()
    rows = (
        (
            await session.execute(
                select(AgentExecution).where(
                    AgentExecution.workspace_id == workspace_id,
                    AgentExecution.status.in_(("completed", "failed", "rejected")),
                    AgentExecution.completed_at.is_not(None),
                    AgentExecution.completed_at >= window_start,
                )
            )
        )
        .scalars()
        .all()
    )
    total = len(rows)
    success = sum(1 for row in rows if row.status == "completed")
    failure = total - success
    latencies = [row.latency_ms for row in rows if row.latency_ms is not None]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    dlq_count = sum(1 for row in rows if row.status == "failed")
    return {
        "total": total,
        "success": success,
        "failure": failure,
        "failure_rate": round(failure / total, 4) if total else 0.0,
        "avg_latency_ms": round(avg_latency, 2) if latencies else 0.0,
        "dlq_count": dlq_count,
    }


async def _dlq_events_in_window(session: AsyncSession, *, workspace_id: UUID) -> int:
    """Count dead-letter events appended within the alert window."""
    window_start = await _window_start()
    return int(
        (
            await session.execute(
                select(func.count())
                .select_from(EventLog)
                .where(
                    EventLog.workspace_id == workspace_id,
                    EventLog.event_type == "agent.task_dead_letter",
                    EventLog.created_at >= window_start,
                )
            )
        ).scalar_one()
    )


async def _budget_warnings(
    session: AsyncSession, *, workspace_id: UUID
) -> list[tuple[AgentRegistry, str, dict[str, Any]]]:
    """Return agents whose monthly LLM usage crossed the budget threshold."""
    agents = (
        (
            await session.execute(
                select(AgentRegistry).where(
                    AgentRegistry.workspace_id == workspace_id,
                    AgentRegistry.status == "active",
                )
            )
        )
        .scalars()
        .all()
    )
    warnings: list[tuple[AgentRegistry, str, dict[str, Any]]] = []
    for agent in agents:
        policy = await agent_policies.get_budget_policy(
            session, workspace_id=workspace_id, agent_id=agent.id
        )
        if not policy.enabled or policy.monthly_budget <= 0:
            continue
        usage = await agent_budget.monthly_usage(
            session, workspace_id=workspace_id, agent_id=agent.id
        )
        threshold = policy.monthly_budget * policy.alert_threshold
        if usage >= threshold:
            warnings.append(
                (
                    agent,
                    f"agent:{agent.agent_id}",
                    {
                        "monthly_usage": str(usage),
                        "monthly_budget": str(policy.monthly_budget),
                        "alert_threshold": str(policy.alert_threshold),
                    },
                )
            )
    return warnings


async def _approval_timeouts(
    session: AsyncSession, *, workspace_id: UUID
) -> list[tuple[str, dict[str, Any]]]:
    """Waiting-approval executions whose decision deadline is close/past."""
    threshold = timedelta(seconds=get_settings().alert_approval_timeout_threshold_seconds)
    now = _now()
    rows = (
        (
            await session.execute(
                select(AgentExecution).where(
                    AgentExecution.workspace_id == workspace_id,
                    AgentExecution.status == "waiting_approval",
                    AgentExecution.approval_deadline.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    results: list[tuple[str, dict[str, Any]]] = []
    for execution in rows:
        deadline = _aware(execution.approval_deadline)
        if deadline is None:
            continue
        remaining = (deadline - now).total_seconds()
        if remaining <= threshold.total_seconds():
            results.append(
                (
                    f"execution:{execution.id}",
                    {
                        "execution_id": str(execution.id),
                        "task_id": str(execution.task_id) if execution.task_id else None,
                        "remaining_seconds": max(0, int(remaining)),
                    },
                )
            )
    return results


async def evaluate_alerts(
    session: AsyncSession,
    backend: task_queue.TaskQueueBackend,
    *,
    workspace_id: UUID,
    trace_id: str | None = None,
) -> list[AgentAlert]:
    """Evaluate all alert rules against live state; open new alerts only.

    Never auto-resolves or auto-executes anything: it only opens alerts when
    a threshold trips. Returns the alerts newly created by this pass.
    """
    settings = get_settings()
    created: list[AgentAlert] = []
    stats = await agent_queue.queue_stats(
        session, backend, workspace_id=workspace_id, trace_id=trace_id
    )
    telemetry = await _execution_telemetry(session, workspace_id=workspace_id)
    workers = await agent_workers.list_workers(backend)

    # 1. Queue backlog.
    severity = (
        "critical"
        if stats["queue_depth"] > settings.alert_max_severity_queue_backlog
        else "warning"
    )
    if stats["queue_depth"] > settings.alert_queue_depth_threshold:
        alert = await _open_alert(
            session,
            workspace_id=workspace_id,
            agent_id=None,
            alert_type=ALERT_QUEUE_BACKLOG,
            severity=severity,
            resource="queue",
            message=f"queue depth {stats['queue_depth']} exceeds threshold "
            f"{settings.alert_queue_depth_threshold}",
            metadata_={"queue_depth": stats["queue_depth"], "stream": stats["stream"]},
            threshold_snapshot={"queue_depth_threshold": settings.alert_queue_depth_threshold},
            trace_id=trace_id,
        )
        if alert is not None:
            created.append(alert)

    # 2. Oldest pending task.
    if (
        stats["oldest_pending_age_ms"] is not None
        and stats["oldest_pending_age_ms"] > settings.alert_oldest_pending_age_ms
    ):
        alert = await _open_alert(
            session,
            workspace_id=workspace_id,
            agent_id=None,
            alert_type=ALERT_OLDEST_PENDING,
            severity="warning",
            resource="queue",
            message=f"oldest pending task is {stats['oldest_pending_age_ms']}ms old "
            f"(threshold {settings.alert_oldest_pending_age_ms}ms)",
            metadata_={"oldest_pending_age_ms": stats["oldest_pending_age_ms"]},
            threshold_snapshot={"oldest_pending_age_ms": settings.alert_oldest_pending_age_ms},
            trace_id=trace_id,
        )
        if alert is not None:
            created.append(alert)

    # 3. Dead workers.
    for worker in workers:
        if not worker["is_dead"]:
            continue
        alert = await _open_alert(
            session,
            workspace_id=workspace_id,
            agent_id=None,
            alert_type=ALERT_WORKER_DEAD,
            severity="critical",
            resource=f"worker:{worker['worker_id']}",
            message=f"worker {worker['worker_id']} is dead (no heartbeat within "
            f"{settings.alert_worker_dead_timeout_seconds}s)",
            metadata_={
                "worker_id": worker["worker_id"],
                "hostname": worker["hostname"],
                "last_heartbeat_at": worker["last_heartbeat_at"],
            },
            threshold_snapshot={
                "worker_dead_timeout_seconds": settings.alert_worker_dead_timeout_seconds
            },
            trace_id=trace_id,
        )
        if alert is not None:
            created.append(alert)

    # 4. Failure rate.
    if telemetry["total"] > 0 and telemetry["failure_rate"] > settings.alert_failure_rate_threshold:
        alert = await _open_alert(
            session,
            workspace_id=workspace_id,
            agent_id=None,
            alert_type=ALERT_FAILURE_RATE,
            severity="warning",
            resource="runtime",
            message=f"failure rate {telemetry['failure_rate']} exceeds threshold "
            f"{settings.alert_failure_rate_threshold}",
            metadata_={
                "total": telemetry["total"],
                "failure": telemetry["failure"],
                "failure_rate": telemetry["failure_rate"],
            },
            threshold_snapshot={"failure_rate_threshold": settings.alert_failure_rate_threshold},
            trace_id=trace_id,
        )
        if alert is not None:
            created.append(alert)

    # 5. Retry rate (retries among pending work).
    retry_denominator = max(stats["pending_count"] + stats["retry_count"], 1)
    retry_rate = stats["retry_count"] / retry_denominator
    if stats["retry_count"] > 0 and retry_rate > settings.alert_retry_rate_threshold:
        alert = await _open_alert(
            session,
            workspace_id=workspace_id,
            agent_id=None,
            alert_type=ALERT_RETRY_RATE,
            severity="warning",
            resource="runtime",
            message=f"retry rate {round(retry_rate, 4)} exceeds threshold "
            f"{settings.alert_retry_rate_threshold}",
            metadata_={
                "retry_count": stats["retry_count"],
                "pending_count": stats["pending_count"],
                "retry_rate": round(retry_rate, 4),
            },
            threshold_snapshot={"retry_rate_threshold": settings.alert_retry_rate_threshold},
            trace_id=trace_id,
        )
        if alert is not None:
            created.append(alert)

    # 6. DLQ growth (new dead letters within the window).
    dlq_events = await _dlq_events_in_window(session, workspace_id=workspace_id)
    if dlq_events > settings.alert_dlq_growth_threshold:
        alert = await _open_alert(
            session,
            workspace_id=workspace_id,
            agent_id=None,
            alert_type=ALERT_DLQ_GROWTH,
            severity="warning",
            resource="queue",
            message=f"{dlq_events} dead letters in the alert window "
            f"(threshold {settings.alert_dlq_growth_threshold})",
            metadata_={"dlq_events": dlq_events},
            threshold_snapshot={"dlq_growth_threshold": settings.alert_dlq_growth_threshold},
            trace_id=trace_id,
        )
        if alert is not None:
            created.append(alert)

    # 7. LLM latency.
    if (
        telemetry["total"] > 0
        and telemetry["avg_latency_ms"] > settings.alert_llm_latency_threshold_ms
    ):
        alert = await _open_alert(
            session,
            workspace_id=workspace_id,
            agent_id=None,
            alert_type=ALERT_LLM_LATENCY,
            severity="warning",
            resource="llm",
            message=f"average LLM latency {telemetry['avg_latency_ms']}ms exceeds threshold "
            f"{settings.alert_llm_latency_threshold_ms}ms",
            metadata_={"avg_latency_ms": telemetry["avg_latency_ms"]},
            threshold_snapshot={
                "llm_latency_threshold_ms": settings.alert_llm_latency_threshold_ms
            },
            trace_id=trace_id,
        )
        if alert is not None:
            created.append(alert)

    # 8. Budget warnings (per agent).
    for agent, resource, snapshot in await _budget_warnings(session, workspace_id=workspace_id):
        alert = await _open_alert(
            session,
            workspace_id=workspace_id,
            agent_id=agent.id,
            alert_type=ALERT_BUDGET_WARNING,
            severity="warning",
            resource=resource,
            message=f"agent {agent.agent_id} monthly LLM usage crossed the budget alert threshold",
            metadata_={"agent_id": agent.agent_id, **snapshot},
            threshold_snapshot={
                "budget_warning_threshold": str(settings.alert_budget_warning_threshold)
            },
            trace_id=trace_id,
        )
        if alert is not None:
            created.append(alert)

    # 9. Approval timeout.
    for resource, metadata_ in await _approval_timeouts(session, workspace_id=workspace_id):
        alert = await _open_alert(
            session,
            workspace_id=workspace_id,
            agent_id=None,
            alert_type=ALERT_APPROVAL_TIMEOUT,
            severity="warning",
            resource=resource,
            message="a waiting_approval execution is within the approval timeout threshold",
            metadata_=metadata_,
            threshold_snapshot={
                "approval_timeout_threshold_seconds": (
                    settings.alert_approval_timeout_threshold_seconds
                )
            },
            trace_id=trace_id,
        )
        if alert is not None:
            created.append(alert)

    return created


async def _load_alert(
    session: AsyncSession, *, workspace_id: UUID, alert_id: UUID
) -> AgentAlert | None:
    return (
        await session.execute(
            select(AgentAlert).where(
                AgentAlert.workspace_id == workspace_id,
                AgentAlert.id == alert_id,
            )
        )
    ).scalar_one_or_none()


async def list_alerts(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    agent_id: UUID | None = None,
    alert_type: str | None = None,
    status: str | None = None,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[AgentAlert], int]:
    """Query alerts (workspace-scoped) with optional filters, newest first."""
    filters = [AgentAlert.workspace_id == workspace_id]
    if agent_id is not None:
        filters.append(AgentAlert.agent_id == agent_id)
    if alert_type is not None:
        filters.append(AgentAlert.alert_type == alert_type)
    if status is not None:
        filters.append(AgentAlert.status == status)
    if from_dt is not None:
        filters.append(AgentAlert.created_at >= from_dt)
    if to_dt is not None:
        filters.append(AgentAlert.created_at <= to_dt)
    total = (
        await session.execute(select(func.count()).select_from(AgentAlert).where(*filters))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                select(AgentAlert)
                .where(*filters)
                .order_by(AgentAlert.created_at.desc(), AgentAlert.id)
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return list(rows), int(total)


async def acknowledge_alert(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    alert_id: UUID,
    actor: str,
    note: str | None = None,
    trace_id: str | None = None,
) -> AgentAlert:
    """Acknowledge an open alert (open -> acknowledged)."""
    alert = await _load_alert(session, workspace_id=workspace_id, alert_id=alert_id)
    if alert is None:
        raise AlertServiceError("alert not found")
    if alert.status != ALERT_OPEN:
        raise AlertServiceError(
            f"alert already {alert.status}; only open alerts can be acknowledged"
        )
    now = _now()
    alert.status = ALERT_ACKNOWLEDGED
    alert.ack_by = actor
    alert.ack_at = now
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.alert.acknowledged",
        entity_type="agent_alert",
        entity_id=str(alert.id),
        payload={"actor": actor, "note": note},
        trace_id=trace_id,
    )
    await session.refresh(alert)
    return alert


async def resolve_alert(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    alert_id: UUID,
    actor: str,
    note: str | None = None,
    trace_id: str | None = None,
) -> AgentAlert:
    """Resolve an open/acknowledged alert (-> resolved, dedup key freed)."""
    alert = await _load_alert(session, workspace_id=workspace_id, alert_id=alert_id)
    if alert is None:
        raise AlertServiceError("alert not found")
    if alert.status == ALERT_RESOLVED:
        raise AlertServiceError("alert already resolved")
    now = _now()
    alert.status = ALERT_RESOLVED
    alert.resolved_by = actor
    alert.resolved_at = now
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.alert.resolved",
        entity_type="agent_alert",
        entity_id=str(alert.id),
        payload={"actor": actor, "note": note},
        trace_id=trace_id,
    )
    await session.refresh(alert)
    return alert
