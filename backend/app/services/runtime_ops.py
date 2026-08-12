"""Runtime operations overview (M5.4): one-shot dashboard summary.

``runtime_overview`` aggregates live Redis + PostgreSQL state so the Runtime
Console can render its dashboard with a single request: agent registry,
workers, queue stats, execution counts, retry / dead-letter, pending human
approvals, alert counts, LLM cost and tokens, and the failure rate. All
numbers come from the actual runtime state - nothing is hardcoded.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.agent_operations import AgentAlert, AgentApproval
from app.models.agent_runtime import AgentExecution, AgentRegistry
from app.services import agent_queue, agent_workers, event_service, task_queue

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = ("completed", "failed", "rejected")


def _now() -> datetime:
    return datetime.now(UTC)


async def runtime_overview(
    session: AsyncSession,
    backend: task_queue.TaskQueueBackend,
    *,
    workspace_id: UUID,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Return the Runtime Dashboard summary for one workspace."""
    settings = get_settings()
    stats = await agent_queue.queue_stats(
        session, backend, workspace_id=workspace_id, trace_id=trace_id
    )
    workers = await agent_workers.list_workers(backend)

    # Agents.
    agent_rows = (
        (
            await session.execute(
                select(AgentRegistry).where(AgentRegistry.workspace_id == workspace_id)
            )
        )
        .scalars()
        .all()
    )
    active_agents = sum(1 for row in agent_rows if row.status == "active")

    # Executions within the stats window.
    window_start = _now() - timedelta(minutes=max(settings.queue_stats_window_minutes, 1))
    exec_rows = (
        (
            await session.execute(
                select(AgentExecution).where(
                    AgentExecution.workspace_id == workspace_id,
                    AgentExecution.status.in_(TERMINAL_STATUSES),
                    AgentExecution.completed_at.is_not(None),
                    AgentExecution.completed_at >= window_start,
                )
            )
        )
        .scalars()
        .all()
    )
    status_counts: dict[str, int] = {}
    total_cost = Decimal("0")
    total_tokens = 0
    for row in exec_rows:
        status_counts[row.status] = status_counts.get(row.status, 0) + 1
        total_cost += row.cost or Decimal("0")
        total_tokens += int(row.tokens.get("prompt_tokens", 0) or 0) + int(
            row.tokens.get("completion_tokens", 0) or 0
        )
    exec_total = len(exec_rows)

    # Pending human approvals.
    pending_approvals = int(
        (
            await session.execute(
                select(func.count())
                .select_from(AgentApproval)
                .where(
                    AgentApproval.workspace_id == workspace_id,
                    AgentApproval.status == "pending",
                )
            )
        ).scalar_one()
    )

    # Alert counts.
    alert_counts: dict[str, int] = {}
    for status in ("open", "acknowledged", "resolved"):
        alert_counts[status] = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(AgentAlert)
                    .where(
                        AgentAlert.workspace_id == workspace_id,
                        AgentAlert.status == status,
                    )
                )
            ).scalar_one()
        )

    overview = {
        "workspace_id": str(workspace_id),
        "agents": {"total": len(agent_rows), "active": active_agents},
        "workers": {
            "total": len(workers),
            "dead": sum(1 for worker in workers if worker["is_dead"]),
            "items": workers,
        },
        "queue": stats,
        "executions": {
            "total_in_window": exec_total,
            "by_status": status_counts,
        },
        "retry": {"retry_count": stats["retry_count"]},
        "dead_letter": {"dead_letter_count": stats["dead_letter_count"]},
        "approvals": {"pending": pending_approvals},
        "alerts": alert_counts,
        "cost": {
            "total_cost": str(total_cost),
            "currency": "USD",
            "executions_in_window": exec_total,
        },
        "tokens": {"total_tokens": total_tokens},
        "failure_rate": stats["failure_rate"],
        "success_rate": stats["success_rate"],
        "trace_id": trace_id,
    }
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.runtime.overview_queried",
        entity_type="agent_runtime",
        entity_id="overview",
        payload={
            "agents": len(agent_rows),
            "workers": len(workers),
            "queue_depth": stats["queue_depth"],
            "pending_approvals": pending_approvals,
            "open_alerts": alert_counts["open"],
        },
        trace_id=trace_id,
    )
    return overview
