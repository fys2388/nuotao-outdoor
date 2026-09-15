"""Worker executor for the P2 B2B advisory agents."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.agents import b2b_agents
from app.models.agent_runtime import AgentExecution, AgentRegistry, AgentTask
from app.models.agent_runtime_hardening import AgentExecutionPolicy
from app.services import b2b_advisory_suggestion_service
from app.worker.executor import ExecutionResult

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

B2BAnalysisFn = Callable[..., Awaitable[dict[str, Any]]]

B2B_EXECUTORS: dict[str, tuple[str, B2BAnalysisFn]] = {
    "b2b_sales_agent": ("b2b-sales-v1", b2b_agents.analyze_sales_pipeline),
    "b2b_quotation_agent": ("b2b-quotation-v1", b2b_agents.recommend_quote),
    "b2b_collection_agent": ("b2b-collections-v1", b2b_agents.analyze_collections),
}


class B2BAgentExecutionError(Exception):
    """Terminal B2B agent failure caused by malformed input or missing data."""

    def __init__(self, message: str, *, kind: str = "invalid") -> None:
        super().__init__(message)
        self.kind = kind


async def _attach_context_snapshot(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    task_id: UUID,
    snapshot: dict[str, Any],
) -> None:
    execution = (
        (
            await session.execute(
                select(AgentExecution)
                .where(
                    AgentExecution.workspace_id == workspace_id,
                    AgentExecution.task_id == task_id,
                    AgentExecution.status == "running",
                )
                .order_by(AgentExecution.started_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    if execution is None:
        return
    current = dict(execution.context_snapshot or {})
    current["b2b_evidence"] = snapshot
    execution.context_snapshot = current
    await session.flush()


async def b2b_agent_executor(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    agent: AgentRegistry,
    task: AgentTask,
    policy: AgentExecutionPolicy,
    trace_id: str | None = None,
) -> ExecutionResult:
    """Run one B2B advisory agent without performing business writes."""
    del policy  # The runtime owns timeout, budget, concurrency, and retry.
    if agent.business_scope != "B2B":
        raise B2BAgentExecutionError(
            f"agent '{agent.agent_id}' is not allowed to run B2B analysis"
        )
    registered = B2B_EXECUTORS.get(agent.agent_id)
    if registered is None:
        raise B2BAgentExecutionError(f"unsupported B2B agent: {agent.agent_id}")

    model_name, analyze = registered
    started = time.perf_counter()
    try:
        output = await analyze(
            session,
            workspace_id=workspace_id,
            task_input=dict(task.input or {}),
        )
    except b2b_agents.B2BAgentInputError as exc:
        raise B2BAgentExecutionError(str(exc)) from exc
    latency_ms = int((time.perf_counter() - started) * 1000)

    suggestions, omitted = await b2b_advisory_suggestion_service.create_advisory_suggestions(
        session,
        workspace_id=workspace_id,
        agent=agent,
        task=task,
        output=output,
    )
    result_output = dict(output)
    result_output["advisory_suggestion_ids"] = [suggestion.id for suggestion in suggestions]
    if omitted:
        result_output["advisory_suggestions_omitted"] = omitted

    evidence = {
        key: value
        for key, value in result_output.items()
        if key
        in {
            "analysis_type",
            "as_of",
            "summary",
            "blockers",
            "requires_human_approval",
            "advisory_suggestion_ids",
            "advisory_suggestions_omitted",
        }
    }
    await _attach_context_snapshot(
        session,
        workspace_id=workspace_id,
        task_id=task.id,
        snapshot=evidence,
    )
    return ExecutionResult(
        output=result_output,
        provider="internal-rules",
        model=model_name,
        tokens={},
        cost=Decimal("0"),
        latency_ms=latency_ms,
    )
