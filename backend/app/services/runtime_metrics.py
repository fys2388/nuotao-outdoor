"""Runtime metrics (M5.5): unified operational metrics as plain JSON.

Aggregates the existing surfaces - ``agent_metrics`` daily rows (tokens,
cost), the live task/execution/attempt tables (created/completed/failed,
retries, DLQ), the Approval Center and Alert Service rows, and the Redis
worker registry - into the ``GET /api/v1/agent-runtime/metrics`` response.

No new observability platform is introduced; the JSON endpoint is ready to
be scraped by Prometheus later (M5.5 does not deploy Prometheus). All counts
are workspace-scoped and derived from the actual state, never hardcoded.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_operations import AgentAlert, AgentApproval
from app.models.agent_runtime import AgentExecution, AgentTask
from app.models.agent_runtime_hardening import AgentMetric, AgentTaskAttempt
from app.services import agent_queue, agent_workers, task_queue


def _now() -> datetime:
    return datetime.now(UTC)


async def runtime_metrics(
    session: AsyncSession,
    backend: task_queue.TaskQueueBackend,
    *,
    workspace_id: UUID,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Return the unified runtime metrics snapshot (workspace-scoped)."""
    # Tasks: created/completed/failed totals (all time, per workspace).
    tasks_created = (
        await session.execute(
            select(func.count())
            .select_from(AgentTask)
            .where(AgentTask.workspace_id == workspace_id)
        )
    ).scalar_one()
    tasks_completed = (
        await session.execute(
            select(func.count())
            .select_from(AgentTask)
            .where(AgentTask.workspace_id == workspace_id, AgentTask.status == "completed")
        )
    ).scalar_one()
    tasks_failed = (
        await session.execute(
            select(func.count())
            .select_from(AgentTask)
            .where(AgentTask.workspace_id == workspace_id, AgentTask.status == "failed")
        )
    ).scalar_one()

    # Executions + retries + DLQ.
    executions_total = (
        await session.execute(
            select(func.count())
            .select_from(AgentExecution)
            .where(AgentExecution.workspace_id == workspace_id)
        )
    ).scalar_one()
    attempts = (
        await session.execute(
            select(AgentTaskAttempt.attempt_number, func.count())
            .where(AgentTaskAttempt.workspace_id == workspace_id)
            .group_by(AgentTaskAttempt.attempt_number)
        )
    ).all()
    retry_total = sum(count for attempt, count in attempts if attempt > 1)
    dead_letter_total = tasks_failed  # failed terminal tasks are the DLQ view

    # Tokens / cost from the daily metrics aggregates (today + all-time).
    today = _now().date()
    metric_rows = (
        (
            await session.execute(
                select(AgentMetric).where(
                    AgentMetric.workspace_id == workspace_id,
                    AgentMetric.metric_date == today,
                )
            )
        )
        .scalars()
        .all()
    )
    tokens_today = sum(int(row.total_tokens or 0) for row in metric_rows)
    cost_today = sum(float(row.total_cost or 0) for row in metric_rows)

    # Live queue + approvals + alerts + workers.
    stats = await agent_queue.queue_stats(
        session, backend, workspace_id=workspace_id, trace_id=trace_id
    )
    approval_pending = (
        await session.execute(
            select(func.count())
            .select_from(AgentApproval)
            .where(
                AgentApproval.workspace_id == workspace_id,
                AgentApproval.status.in_(("pending", "warning")),
            )
        )
    ).scalar_one()
    alert_open = (
        await session.execute(
            select(func.count())
            .select_from(AgentAlert)
            .where(
                AgentAlert.workspace_id == workspace_id,
                AgentAlert.status.in_(("open", "acknowledged")),
            )
        )
    ).scalar_one()
    workers = await agent_workers.list_workers(backend)
    worker_active = sum(1 for w in workers if not w["is_dead"])
    worker_dead = sum(1 for w in workers if w["is_dead"])

    return {
        "workspace_id": str(workspace_id),
        "generated_at": _now().isoformat(),
        "agent_tasks_created_total": int(tasks_created),
        "agent_tasks_completed_total": int(tasks_completed),
        "agent_tasks_failed_total": int(tasks_failed),
        "agent_execution_total": int(executions_total),
        "agent_llm_tokens_total": tokens_today,
        "agent_llm_cost_total": round(cost_today, 6),
        "agent_retry_total": int(retry_total),
        "agent_dlq_total": int(dead_letter_total),
        "agent_approval_pending": int(approval_pending),
        "agent_alert_open": int(alert_open),
        "agent_worker_active": worker_active,
        "agent_worker_dead": worker_dead,
        "queue": {
            "queue_depth": stats["queue_depth"],
            "pending": stats["pending_count"],
            "running": stats["running_count"],
            "waiting_approval": stats["waiting_approval_count"],
            "retry": stats["retry_count"],
            "dead_letter": stats["dead_letter_count"],
            "throughput_per_minute": stats["throughput_per_minute"],
            "success_rate": stats["success_rate"],
            "failure_rate": stats["failure_rate"],
        },
    }
