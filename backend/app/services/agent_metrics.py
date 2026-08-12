"""Agent metrics (M5.1): daily aggregation of execution telemetry.

``snapshot_metrics`` aggregates one agent's executions for a UTC calendar day
into a single ``agent_metrics`` row (upsert on workspace+agent+date): counts
by terminal status, total tokens, total cost (Decimal), average and p95
latency, and an error-class breakdown. All inputs are workspace-scoped and
already audited in ``agent_executions``.
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_runtime import AgentExecution
from app.models.agent_runtime_hardening import AgentMetric
from app.services import event_service

TERMINAL_STATUSES = ("completed", "failed", "rejected")


def _day_bounds(metric_date: date) -> tuple[datetime, datetime]:
    start = datetime.combine(metric_date, time.min, tzinfo=UTC)
    end = datetime.combine(metric_date, time.max, tzinfo=UTC)
    return start, end


def _p95(values: list[int]) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return ordered[index]


async def _collect(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    agent_id: UUID,
    metric_date: date,
) -> dict[str, Any]:
    start, end = _day_bounds(metric_date)
    rows = (
        (
            await session.execute(
                select(AgentExecution).where(
                    AgentExecution.workspace_id == workspace_id,
                    AgentExecution.agent_id == agent_id,
                    AgentExecution.started_at.is_not(None),
                    AgentExecution.started_at >= start,
                    AgentExecution.started_at <= end,
                )
            )
        )
        .scalars()
        .all()
    )
    executions = [row for row in rows if row.status in TERMINAL_STATUSES]
    latencies = [row.latency_ms or 0 for row in executions if row.latency_ms is not None]
    breakdown: dict[str, int] = {}
    timeout_count = 0
    retried_count = 0
    for row in executions:
        error_type = row.error_type or row.status
        breakdown[error_type] = breakdown.get(error_type, 0) + 1
        if error_type == "timeout":
            timeout_count += 1
        if (row.attempt_number or 1) > 1:
            retried_count += 1
    total_cost = sum((row.cost or Decimal("0")) for row in executions)
    total_tokens = sum(
        int(row.tokens.get("prompt_tokens", 0) or 0)
        + int(row.tokens.get("completion_tokens", 0) or 0)
        for row in executions
    )
    return {
        "executions_count": len(executions),
        "success_count": sum(1 for row in executions if row.status == "completed"),
        "failure_count": sum(1 for row in executions if row.status in ("failed", "rejected")),
        "timeout_count": timeout_count,
        "retried_count": retried_count,
        "total_tokens": total_tokens,
        "total_cost": total_cost,
        "avg_latency_ms": (
            Decimal(str(round(sum(latencies) / len(latencies), 2))) if latencies else None
        ),
        "p95_latency_ms": _p95(latencies),
        "error_breakdown": breakdown,
    }


async def snapshot_metrics(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    agent_id: UUID,
    metric_date: date | None = None,
    trace_id: str | None = None,
) -> AgentMetric:
    """Aggregate executions for a UTC day and upsert the metrics row."""
    metric_date = metric_date or datetime.now(UTC).date()
    collected = await _collect(
        session, workspace_id=workspace_id, agent_id=agent_id, metric_date=metric_date
    )
    row = (
        await session.execute(
            select(AgentMetric).where(
                AgentMetric.workspace_id == workspace_id,
                AgentMetric.agent_id == agent_id,
                AgentMetric.metric_date == metric_date,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = AgentMetric(
            workspace_id=workspace_id,
            agent_id=agent_id,
            metric_date=metric_date,
            trace_id=trace_id,
        )
        session.add(row)
    row.executions_count = collected["executions_count"]
    row.success_count = collected["success_count"]
    row.failure_count = collected["failure_count"]
    row.timeout_count = collected["timeout_count"]
    row.retried_count = collected["retried_count"]
    row.total_tokens = collected["total_tokens"]
    row.total_cost = collected["total_cost"]
    row.avg_latency_ms = collected["avg_latency_ms"]
    row.p95_latency_ms = collected["p95_latency_ms"]
    row.error_breakdown = collected["error_breakdown"]
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.metrics_snapshotted",
        entity_type="agent_metric",
        entity_id=str(agent_id),
        payload={
            "metric_date": metric_date.isoformat(),
            "executions_count": collected["executions_count"],
            "total_cost": str(collected["total_cost"]),
        },
        trace_id=trace_id,
    )
    return row


async def list_metrics(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    agent_id: UUID | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[AgentMetric], int]:
    """Query metrics rows, newest first, workspace-scoped."""
    filters = [AgentMetric.workspace_id == workspace_id]
    if agent_id is not None:
        filters.append(AgentMetric.agent_id == agent_id)
    if from_date is not None:
        filters.append(AgentMetric.metric_date >= from_date)
    if to_date is not None:
        filters.append(AgentMetric.metric_date <= to_date)
    count = (
        await session.execute(select(func.count()).select_from(AgentMetric).where(*filters))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                select(AgentMetric)
                .where(*filters)
                .order_by(AgentMetric.metric_date.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return list(rows), int(count)
