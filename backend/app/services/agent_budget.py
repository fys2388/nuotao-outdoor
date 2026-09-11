"""Agent budget guard (M5.1): blocks model spend before it happens.

The worker checks the budget *before* any LLM call: the monthly usage is
computed from completed execution costs (workspace-scoped) and compared
against the versioned budget policy. When the projected next execution would
exceed the monthly budget the execution is blocked (no model call). When
usage crosses the alert threshold an ``agent.budget_alert`` event is emitted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_runtime import AgentExecution, AgentRegistry
from app.models.agent_runtime_hardening import AgentBudgetPolicy
from app.services import event_service


@dataclass(frozen=True)
class BudgetDecision:
    """Outcome of a pre-execution budget check."""

    allowed: bool
    monthly_usage: Decimal
    monthly_budget: Decimal
    projected_cost: Decimal
    reason: str


def _month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def monthly_usage(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    agent_id: UUID,
) -> Decimal:
    """Sum execution costs for the current calendar month (UTC)."""
    total = (
        await session.execute(
            select(func.coalesce(func.sum(AgentExecution.cost), 0)).where(
                AgentExecution.workspace_id == workspace_id,
                AgentExecution.agent_id == agent_id,
                AgentExecution.status.in_(("completed", "failed", "rejected")),
                AgentExecution.started_at >= _month_start(datetime.now(UTC)),
            )
        )
    ).scalar_one()
    return Decimal(str(total or 0))


async def check_budget(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    agent: AgentRegistry,
    policy: AgentBudgetPolicy,
    projected_cost: Decimal,
    trace_id: str | None = None,
) -> BudgetDecision:
    """Return whether an execution may proceed under the budget policy.

    Never auto-executes anything: it only blocks (or permits) the next model
    call. Crossing the alert threshold emits ``agent.budget_alert``.
    """
    usage = await monthly_usage(session, workspace_id=workspace_id, agent_id=agent.id)
    budget = policy.monthly_budget
    threshold = budget * policy.alert_threshold
    if budget <= 0:
        return BudgetDecision(
            allowed=False,
            monthly_usage=usage,
            monthly_budget=budget,
            projected_cost=projected_cost,
            reason="monthly budget is zero (execution disabled)",
        )

    if usage >= threshold:
        await event_service.create_event(
            session,
            workspace_id=workspace_id,
            event_type="agent.budget_alert",
            entity_type="agent",
            entity_id=agent.agent_id,
            payload={
                "monthly_usage": str(usage),
                "monthly_budget": str(budget),
                "alert_threshold": str(policy.alert_threshold),
                "usage_ratio": str((usage / budget).quantize(Decimal("0.001"))),
            },
            trace_id=trace_id,
        )

    if usage + projected_cost > budget:
        return BudgetDecision(
            allowed=False,
            monthly_usage=usage,
            monthly_budget=budget,
            projected_cost=projected_cost,
            reason="projected cost would exceed monthly budget",
        )
    return BudgetDecision(
        allowed=True,
        monthly_usage=usage,
        monthly_budget=budget,
        projected_cost=projected_cost,
        reason="within monthly budget",
    )
