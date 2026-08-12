"""Product Analyst executor for the M5.1 worker (M5.2).

Plugs the existing M2.2 Product Analyst pipeline (``app.agents.product_analyst``)
into the generic agent runtime. The worker already owns claiming, idempotency,
execution/budget policies, concurrency, attempt audit, timeout, retry and
completion audit; this executor only adds the business step:

    task input -> Product Context Builder -> LLM Gateway -> structured output
    -> schema + hard-rule + Rule Engine validation -> audit rows

No product-intelligence business logic is duplicated here - the M2.2 pipeline
is reused as-is (prompt binding is the runtime ``AGENT_PRODUCT_ANALYST``
prompt instead of the M2.2 default).

Permissions (hard constraints):
- READ:  product intelligence data only through the Context Builder.
- WRITE: ``product_analysis_runs``, pending ``product_decisions`` proposals
  and ``product_ai_evaluations`` predictions.
- FORBIDDEN: approve, publish, purchase, campaigns, inventory allocation;
  L3 tools never execute (the runtime stops them at ``waiting_approval``).
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import product_analyst
from app.models.agent_runtime import AgentExecution, AgentRegistry, AgentTask
from app.models.agent_runtime_hardening import AgentExecutionPolicy
from app.services import agent_runtime
from app.services.evaluation_bridge import ProductDomainLink, record_agent_evaluation
from app.services.llm_gateway import LLMError
from app.worker.executor import ExecutionResult

logger = logging.getLogger(__name__)


class ProductAnalystExecutionError(Exception):
    """Terminal failure in the product analyst executor (invalid input/output).

    Carries ``kind`` so the worker retry engine classifies it as terminal
    (``invalid``): a malformed task input or an LLM output that failed
    schema/business-gate validation is never silently retried.
    """

    def __init__(self, message: str, *, kind: str = "invalid") -> None:
        super().__init__(message)
        self.kind = kind


def parse_product_id(task_input: dict[str, Any]) -> UUID:
    """Extract the product id from the task input (raises on malformed input)."""
    raw = task_input.get("product_id")
    if raw is None:
        raise ProductAnalystExecutionError("task input missing 'product_id'")
    try:
        return UUID(str(raw))
    except (ValueError, TypeError):
        raise ProductAnalystExecutionError(f"invalid 'product_id': {raw!r}") from None


async def _attach_context_snapshot(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    task_id: UUID,
    run: product_analyst.ProductAnalysisRun,
    decision: product_analyst.ProductDecision | None,
) -> None:
    """Merge the built product context into the running execution snapshot."""
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
    snapshot = dict(execution.context_snapshot or {})
    snapshot["product_context"] = run.input_snapshot
    snapshot["analysis_run_id"] = str(run.id)
    snapshot["decision_proposal_id"] = str(decision.id) if decision else None
    execution.context_snapshot = snapshot
    await session.flush()


async def product_analyst_executor(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    agent: AgentRegistry,
    task: AgentTask,
    policy: AgentExecutionPolicy,
    trace_id: str | None = None,
    gateway_complete: Any | None = None,
) -> ExecutionResult:
    """Execute one product-analysis task through the M5.1 runtime.

    On success the structured output is returned so the worker persists it
    into ``agent_executions`` / the task result; the analysis run, pending
    decision proposal and AI evaluation prediction are written here through
    the existing M2.2 pipeline.
    """
    product_id = parse_product_id(task.input or {})

    try:
        result = await product_analyst.analyze_product(
            session,
            workspace_id=workspace_id,
            product_id=product_id,
            gateway_complete=gateway_complete,
            prompt_name=agent_runtime.agent_prompt_name(agent.agent_id),
            re_raise_llm_errors=True,
            trace_id=trace_id,
        )
    except LLMError:
        # Provider/network/timeout failures: let the worker classify and
        # retry through the M5.1 retry engine (budget already gated).
        raise
    except product_analyst.ProductAnalystError as exc:
        # Schema/business-gate/resource failures are deterministic: terminal.
        raise ProductAnalystExecutionError(str(exc)) from exc

    run = result.analysis_run
    await _attach_context_snapshot(
        session,
        workspace_id=workspace_id,
        task_id=task.id,
        run=run,
        decision=result.decision,
    )

    # Prediction for the learning loop: record the M5 agent evaluation AND
    # mirror the M2.3 product-domain row through the unified bridge, so the
    # prediction is reachable from both the runtime audit and M2.3
    # calibration. Actuals arrive later via backfill/experiments (append-only).
    await record_agent_evaluation(
        session,
        workspace_id=workspace_id,
        agent_id=agent.id,
        prediction=dict(run.output),
        domain=ProductDomainLink(product_id=product_id, analysis_run_id=run.id),
        trace_id=trace_id,
    )

    return ExecutionResult(
        output=dict(run.output),
        provider=run.provider,
        model=run.model,
        tokens=dict(run.token_usage or {}),
        cost=run.estimated_cost,
        latency_ms=run.latency_ms,
    )
