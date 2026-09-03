"""M5.2 Product Analyst Agent integration tests (worker executor).

Covers the full runtime path: task -> worker -> product analyst executor
(reusing the M2.2 pipeline) -> structured output -> three-layer validation
(schema / business gate / rule veto) -> audit rows (product_analysis_runs,
product_decisions, product_ai_evaluations, ai_agent_runs, agent_executions,
event_log), plus retry/timeout/budget, permission boundaries, workspace
isolation and the trace chain.
"""

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from functools import partial
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.agent import AiAgentRun
from app.models.agent_runtime import AgentExecution, AgentRegistry, AgentTask
from app.models.agent_runtime_hardening import AgentTaskAttempt
from app.models.event import EventLog
from app.models.product_intelligence import (
    ProductAiEvaluation,
    ProductAnalysisRun,
    ProductDecision,
)
from app.models.prompt import Prompt
from app.schemas.agent_runtime import TaskCreate
from app.schemas.product_intelligence import ProductIntakeRequest
from app.schemas.rule import RuleCreate
from app.services import (
    agent_policies,
    agent_runtime,
    product_intelligence,
    retry_engine,
    rule_engine,
    task_queue,
)
from app.services.llm_gateway import LLMError, LLMResponse
from app.worker.agent_worker import run_worker_once
from app.worker.product_analyst_executor import product_analyst_executor

WORKSPACE = DEFAULT_WORKSPACE_ID
OTHER_WORKSPACE = UUID("00000000-0000-0000-0000-000000000099")

VALID_OUTPUT = {
    "decision": "test",
    "confidence": "0.78",
    "market_reasoning": "Strong margin at light weight; demand signals positive.",
    "risks": ["Supplier lead time variability", "Platform competition"],
    "pricing": {
        "recommended_price": "39.99",
        "price_range": ["34.99", "44.99"],
        "max_cac": "20.00",
        "rationale": "Margin supports paid acquisition",
    },
    "test_plan": {
        "quantity": 50,
        "days": 30,
        "channels": ["meta", "google"],
        "budget": "800.00",
        "kpis": {"roas": 2.0},
    },
}


def _factory(db_engine) -> async_sessionmaker:
    return async_sessionmaker(db_engine, expire_on_commit=False)


async def _event_types(session) -> set[str]:
    rows = (await session.execute(select(EventLog.event_type))).scalars().all()
    return set(rows)


async def _seed_rules(session, *, workspace: UUID = WORKSPACE) -> None:
    """Seed the PRODUCT hard gates used by the agent rule check."""
    for rule in (
        RuleCreate(
            rule_id="PROD-GATE-001",
            name="Product cost data must be complete",
            category="PRODUCT",
            rule_type="hard",
            version="v1",
            status="active",
            when_conditions={"field": "cost.total_cost", "op": "gt", "value": 0},
            then_result={"passed_message": "cost ok", "failed_message": "cost missing"},
        ),
        RuleCreate(
            rule_id="PROD-GATE-002",
            name="Shipping within 40% of expected price",
            category="PRODUCT",
            rule_type="hard",
            version="v1",
            status="active",
            when_conditions={
                "field": "logistics.shipping_ratio",
                "op": "lte",
                "value": 0.4,
            },
            then_result={"passed_message": "ship ok", "failed_message": "ship too high"},
        ),
    ):
        await rule_engine.create_rule(session, workspace_id=workspace, data=rule)


async def _intake(session, *, workspace: UUID = WORKSPACE, **overrides) -> UUID:
    payload = {
        "title": "Camping Headlamp Pro",
        "sku": "NTO-HEADLAMP-M52",
        "source_type": "1688",
        "source_url": "https://detail.1688.com/offer/123456789.html",
        "purchase_cost": Decimal("10.00"),
        "domestic_shipping": Decimal("1.00"),
        "first_leg_shipping": Decimal("2.00"),
        "last_leg_shipping": Decimal("3.00"),
        "weight_kg": Decimal("0.30"),
        "target_market": "US",
        "currency": "USD",
    }
    payload.update(overrides)
    result = await product_intelligence.intake_product(
        session, workspace_id=workspace, data=ProductIntakeRequest(**payload)
    )
    return result.product.id


async def _seed_and_intake(
    session,
    *,
    workspace: UUID = WORKSPACE,
    intake_overrides: dict | None = None,
    seed_rules: bool = True,
) -> tuple[AgentRegistry, UUID]:
    if seed_rules:
        await _seed_rules(session, workspace=workspace)
    from app.agents.agent_seed import ensure_product_analyst_agent

    agent = await ensure_product_analyst_agent(session, workspace_id=workspace)
    product_id = await _intake(session, workspace=workspace, **(intake_overrides or {}))
    return agent, product_id


def _fake_complete(content: str | dict, **overrides):
    """Build a fake gateway callable returning a canned LLMResponse."""
    if isinstance(content, dict):
        content = json.dumps(content)

    async def caller(request, trace_id=None):
        return LLMResponse(
            provider=overrides.get("provider", "openai"),
            model=overrides.get("model", "gpt-4o-mini"),
            content=content,
            tokens=overrides.get(
                "tokens",
                {"prompt_tokens": 120, "completion_tokens": 60, "total_tokens": 180},
            ),
            cost=overrides.get("cost", Decimal("0.001500")),
            latency_ms=overrides.get("latency_ms", 41),
            trace_id=trace_id,
        )

    return caller


class _FailOnceGateway:
    """Fails the first ``fail_calls`` calls with a retryable LLM error."""

    def __init__(self, content: dict, *, fail_calls: int = 1, kind: str = "provider"):
        self.content = json.dumps(content)
        self.fail_calls = fail_calls
        self.kind = kind
        self.calls = 0

    async def __call__(self, request, trace_id=None):
        self.calls += 1
        if self.calls <= self.fail_calls:
            raise LLMError("provider boom", kind=self.kind)
        return LLMResponse(
            provider="deepseek",
            model="deepseek-chat",
            content=self.content,
            tokens={"prompt_tokens": 120, "completion_tokens": 60, "total_tokens": 180},
            cost=Decimal("0.000900"),
            latency_ms=30,
            trace_id=trace_id,
        )


class _SlowGateway:
    """Sleeps for the first ``slow_calls`` calls (drives timeout tests)."""

    def __init__(self, content: dict, sleep_seconds: float, *, slow_calls: int = 1):
        self.content = json.dumps(content)
        self.sleep_seconds = sleep_seconds
        self.slow_calls = slow_calls
        self.calls = 0

    async def __call__(self, request, trace_id=None):
        self.calls += 1
        if self.calls <= self.slow_calls:
            await asyncio.sleep(self.sleep_seconds)
        return LLMResponse(
            provider="openai",
            model="gpt-4o-mini",
            content=self.content,
            tokens={"prompt_tokens": 120, "completion_tokens": 60, "total_tokens": 180},
            cost=Decimal("0.001500"),
            latency_ms=41,
            trace_id=trace_id,
        )


async def _set_fast_retry(session, *, workspace: UUID = WORKSPACE, max_attempts: int = 3) -> None:
    await agent_policies.set_retry_policy(
        session,
        workspace_id=workspace,
        retry_policy_id="standard",
        name="Instant (test)",
        max_attempts=max_attempts,
        backoff_base_seconds=0,
        backoff_multiplier=Decimal("2"),
        max_backoff_seconds=5,
        retry_on_error_types=["llm", "network", "timeout", "transient"],
        enabled=True,
    )


async def _set_execution_policy(
    session, *, agent_id: UUID, workspace: UUID = WORKSPACE, execution_timeout: int = 60
) -> None:
    await agent_policies.set_execution_policy(
        session,
        workspace_id=workspace,
        agent_id=agent_id,
        max_concurrent=2,
        execution_timeout_seconds=execution_timeout,
        approval_timeout_seconds=3600,
        max_context_size=5000,
        retry_policy_id="standard",
        enabled=True,
    )


async def _run(backend, factory, executor, *, rounds: int = 4) -> int:
    total = 0
    for _ in range(rounds):
        processed = await run_worker_once(backend, factory, executor=executor)
        total += processed
        if processed == 0:
            break
    return total


# --------------------------------------------------------------------------- #
# Happy path + audit chain
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_worker_happy_path_full_audit_chain(db_engine) -> None:
    """Task -> worker -> analyst -> structured output -> all audit rows."""
    backend = task_queue.get_queue_backend()
    factory = _factory(db_engine)
    async with factory() as session:
        agent, product_id = await _seed_and_intake(session)
        task = await agent_runtime.create_task(
            session,
            workspace_id=WORKSPACE,
            data=TaskCreate(
                agent_id=agent.id,
                input={"product_id": str(product_id), "action": "analyze"},
            ),
            trace_id="trace-m52-happy",
        )
        task_id = task.id
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)

    executor = partial(product_analyst_executor, gateway_complete=_fake_complete(VALID_OUTPUT))
    assert await _run(backend, factory, executor) >= 1

    async with factory() as session:
        task = await session.get(AgentTask, task_id)
        assert task.status == "completed"
        assert task.trace_id == "trace-m52-happy"

        execution = (
            (await session.execute(select(AgentExecution).where(AgentExecution.task_id == task_id)))
            .scalars()
            .first()
        )
        assert execution.status == "completed"
        assert execution.output["decision"] == "test"
        assert execution.output["enforced_decision"] is None
        assert execution.trace_id == "trace-m52-happy"
        assert "product_context" in execution.context_snapshot
        assert execution.context_snapshot["analysis_run_id"]
        json.dumps(execution.context_snapshot)  # JSON-safe for storage

        runs = (
            (
                await session.execute(
                    select(ProductAnalysisRun).where(ProductAnalysisRun.product_id == product_id)
                )
            )
            .scalars()
            .all()
        )
        llm_runs = [run for run in runs if run.provider == "openai"]
        assert len(llm_runs) == 1
        assert llm_runs[0].status == "completed"
        assert llm_runs[0].prompt_version == "v1"
        assert llm_runs[0].trace_id == "trace-m52-happy"
        assert llm_runs[0].input_snapshot  # full product context recorded

        decisions = (
            (
                await session.execute(
                    select(ProductDecision).where(ProductDecision.product_id == product_id)
                )
            )
            .scalars()
            .all()
        )
        assert len(decisions) == 1
        assert decisions[0].decision == "test"
        assert decisions[0].approval_status == "pending"
        assert decisions[0].trace_id == "trace-m52-happy"

        evaluations = (await session.execute(select(ProductAiEvaluation))).scalars().all()
        assert len(evaluations) == 1
        assert evaluations[0].analysis_run_id == llm_runs[0].id
        assert evaluations[0].prediction["decision"] == "test"
        assert evaluations[0].trace_id == "trace-m52-happy"

        agent_runs = (await session.execute(select(AiAgentRun))).scalars().all()
        assert len(agent_runs) == 1
        assert agent_runs[0].agent == "product-analyst"
        assert agent_runs[0].trace_id == "trace-m52-happy"

        events = await _event_types(session)
        assert "product.analyst.analyzed" in events
        assert "agent.execution_completed" in events
        assert "product.ai_evaluation.recorded" in events
        chain_events = (
            (await session.execute(select(EventLog).where(EventLog.trace_id == "trace-m52-happy")))
            .scalars()
            .all()
        )
        assert len(chain_events) >= 3
    assert await backend.stream_length(task_queue.task_stream()) == 0


@pytest.mark.asyncio
async def test_api_task_flows_through_worker_to_pending_decision(
    db_session, db_engine, api_client
) -> None:
    """API-created task is consumed by the worker and produces a proposal."""
    agent, product_id = await _seed_and_intake(db_session)
    response = api_client.post(
        "/api/v1/agent-tasks",
        json={"agent_id": str(agent.id), "input": {"product_id": str(product_id)}, "priority": 3},
    )
    assert response.status_code == 201, response.text
    task_id = UUID(response.json()["id"])

    factory = _factory(db_engine)
    backend = task_queue.get_queue_backend()
    executor = partial(product_analyst_executor, gateway_complete=_fake_complete(VALID_OUTPUT))
    assert await _run(backend, factory, executor) == 1

    async with factory() as session:
        task = await session.get(AgentTask, task_id)
        assert task.status == "completed"
        decisions = (await session.execute(select(ProductDecision))).scalars().all()
        assert len(decisions) == 1
        assert decisions[0].approval_status == "pending"


# --------------------------------------------------------------------------- #
# Retry / timeout / budget
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_worker_llm_failure_retried_then_success(db_engine) -> None:
    """Retryable LLM failure (provider) is retried; fallback provider wins."""
    backend = task_queue.get_queue_backend()
    factory = _factory(db_engine)
    async with factory() as session:
        agent, product_id = await _seed_and_intake(session)
        await _set_fast_retry(session, max_attempts=3)
        await _set_execution_policy(session, agent_id=agent.id)
        task = await agent_runtime.create_task(
            session,
            workspace_id=WORKSPACE,
            data=TaskCreate(agent_id=agent.id, input={"product_id": str(product_id)}),
        )
        task_id = task.id
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)

    gateway = _FailOnceGateway(VALID_OUTPUT)
    executor = partial(product_analyst_executor, gateway_complete=gateway)
    assert await _run(backend, factory, executor) == 2

    async with factory() as session:
        task = await session.get(AgentTask, task_id)
        assert task.status == "completed"
        assert task.attempt_count == 2
        attempts = (await session.execute(select(AgentTaskAttempt))).scalars().all()
        statuses = {row.status for row in attempts}
        assert "failed" in statuses and "succeeded" in statuses
        failed = next(row for row in attempts if row.status == "failed")
        assert failed.error_type == "llm"
        executions = (
            (
                await session.execute(
                    select(AgentExecution)
                    .where(AgentExecution.task_id == task_id)
                    .order_by(AgentExecution.started_at)
                )
            )
            .scalars()
            .all()
        )
        assert len(executions) == 2
        assert executions[0].status == "failed"
        assert executions[0].error_type == "llm"
        assert executions[1].status == "completed"
        assert executions[1].provider == "deepseek"  # fallback provider on retry


@pytest.mark.asyncio
async def test_worker_schema_failure_dead_letters(db_engine) -> None:
    """Malformed LLM output fails schema validation and dead-letters."""
    backend = task_queue.get_queue_backend()
    factory = _factory(db_engine)
    async with factory() as session:
        agent, product_id = await _seed_and_intake(session)
        await _set_fast_retry(session, max_attempts=3)
        await _set_execution_policy(session, agent_id=agent.id)
        task = await agent_runtime.create_task(
            session,
            workspace_id=WORKSPACE,
            data=TaskCreate(agent_id=agent.id, input={"product_id": str(product_id)}),
        )
        task_id = task.id
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)

    executor = partial(product_analyst_executor, gateway_complete=_fake_complete("not json at all"))
    assert await _run(backend, factory, executor) == 1

    async with factory() as session:
        task = await session.get(AgentTask, task_id)
        assert task.status == "failed"
        execution = (
            (await session.execute(select(AgentExecution).where(AgentExecution.task_id == task_id)))
            .scalars()
            .first()
        )
        assert execution.status == "failed"
        assert execution.error_type == "invalid"
        runs = (
            (
                await session.execute(
                    select(ProductAnalysisRun).where(ProductAnalysisRun.product_id == product_id)
                )
            )
            .scalars()
            .all()
        )
        failed_runs = [run for run in runs if run.provider == "openai"]
        assert len(failed_runs) == 1
        assert failed_runs[0].status == "failed"
        assert "invalid structured output" in failed_runs[0].output["error"]
        decisions = (await session.execute(select(ProductDecision))).scalars().all()
        assert len(decisions) == 0


@pytest.mark.asyncio
async def test_worker_timeout_retried_then_success(db_engine) -> None:
    """Execution timeout is retried and the second attempt succeeds."""
    backend = task_queue.get_queue_backend()
    factory = _factory(db_engine)
    async with factory() as session:
        agent, product_id = await _seed_and_intake(session)
        await _set_fast_retry(session, max_attempts=3)
        await _set_execution_policy(session, agent_id=agent.id, execution_timeout=1)
        task = await agent_runtime.create_task(
            session,
            workspace_id=WORKSPACE,
            data=TaskCreate(agent_id=agent.id, input={"product_id": str(product_id)}),
        )
        task_id = task.id
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)

    gateway = _SlowGateway(VALID_OUTPUT, sleep_seconds=1.5)
    executor = partial(product_analyst_executor, gateway_complete=gateway)
    assert await _run(backend, factory, executor) == 2

    async with factory() as session:
        task = await session.get(AgentTask, task_id)
        assert task.status == "completed"
        assert task.attempt_count == 2
        attempts = (await session.execute(select(AgentTaskAttempt))).scalars().all()
        statuses = {row.status for row in attempts}
        assert "timed_out" in statuses and "succeeded" in statuses


@pytest.mark.asyncio
async def test_worker_timeout_dead_letters_after_max_attempts(db_engine) -> None:
    """Repeated timeouts exhaust the retry policy and dead-letter the task."""
    backend = task_queue.get_queue_backend()
    factory = _factory(db_engine)
    async with factory() as session:
        agent, product_id = await _seed_and_intake(session)
        await _set_fast_retry(session, max_attempts=2)
        await _set_execution_policy(session, agent_id=agent.id, execution_timeout=1)
        task = await agent_runtime.create_task(
            session,
            workspace_id=WORKSPACE,
            data=TaskCreate(agent_id=agent.id, input={"product_id": str(product_id)}),
        )
        task_id = task.id
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)

    gateway = _SlowGateway(VALID_OUTPUT, sleep_seconds=1.5, slow_calls=99)
    executor = partial(product_analyst_executor, gateway_complete=gateway)
    assert await _run(backend, factory, executor) == 2

    async with factory() as session:
        task = await session.get(AgentTask, task_id)
        assert task.status == "failed"
        assert "timed out" in (task.error_message or "").lower()
        attempts = (await session.execute(select(AgentTaskAttempt))).scalars().all()
        assert {row.status for row in attempts} == {"running", "timed_out"}
        executions = (
            (await session.execute(select(AgentExecution).where(AgentExecution.task_id == task_id)))
            .scalars()
            .all()
        )
        assert all(execution.status == "failed" for execution in executions)
        assert all(execution.error_type == "timeout" for execution in executions)


@pytest.mark.asyncio
async def test_worker_budget_blocks_before_llm(db_engine) -> None:
    """Budget policy blocks the run before any model call."""
    backend = task_queue.get_queue_backend()
    factory = _factory(db_engine)
    async with factory() as session:
        agent, product_id = await _seed_and_intake(session)
        await agent_policies.set_budget_policy(
            session,
            workspace_id=WORKSPACE,
            agent_id=agent.id,
            monthly_budget=Decimal("1.00"),
            max_cost_per_execution=Decimal("5.00"),
            alert_threshold=Decimal("0.80"),
        )
        task = await agent_runtime.create_task(
            session,
            workspace_id=WORKSPACE,
            data=TaskCreate(agent_id=agent.id, input={"product_id": str(product_id)}),
        )
        task_id = task.id
        session.add(
            AgentExecution(
                workspace_id=WORKSPACE,
                agent_id=agent.id,
                task_id=task.id,
                context_snapshot={},
                input={},
                status="completed",
                cost=Decimal("0.50"),
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
            )
        )
        await session.commit()
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)

    gateway = _fake_complete(VALID_OUTPUT)
    executor = partial(product_analyst_executor, gateway_complete=gateway)
    await _run(backend, factory, executor)

    async with factory() as session:
        task = await session.get(AgentTask, task_id)
        assert task.status == "failed"
        assert "budget" in (task.error_message or "").lower()
        attempts = (await session.execute(select(AgentTaskAttempt))).scalars().all()
        assert any(row.status == retry_engine.ATTEMPT_BUDGET_BLOCKED for row in attempts)
        runs = (
            (
                await session.execute(
                    select(ProductAnalysisRun).where(ProductAnalysisRun.product_id == product_id)
                )
            )
            .scalars()
            .all()
        )
        assert not any(run.provider == "openai" for run in runs)


# --------------------------------------------------------------------------- #
# Hard rules / business gates
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_worker_hard_rule_veto_forces_reject(db_engine) -> None:
    """A failing hard rule deterministically overrides the LLM to 'reject'."""
    backend = task_queue.get_queue_backend()
    factory = _factory(db_engine)
    async with factory() as session:
        agent, product_id = await _seed_and_intake(session)
        await _set_execution_policy(session, agent_id=agent.id)
        task = await agent_runtime.create_task(
            session,
            workspace_id=WORKSPACE,
            data=TaskCreate(agent_id=agent.id, input={"product_id": str(product_id)}),
        )
        task_id = task.id
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)

    # International shipping (2+3=5) vs LLM price 8.00 -> ratio 0.625 > 0.4.
    veto_output = dict(VALID_OUTPUT)
    veto_output["decision"] = "hold"
    veto_output["pricing"] = dict(VALID_OUTPUT["pricing"], recommended_price="8.00")
    executor = partial(product_analyst_executor, gateway_complete=_fake_complete(veto_output))
    assert await _run(backend, factory, executor) == 1

    async with factory() as session:
        task = await session.get(AgentTask, task_id)
        assert task.status == "completed"
        execution = (
            (await session.execute(select(AgentExecution).where(AgentExecution.task_id == task_id)))
            .scalars()
            .first()
        )
        # Raw LLM output is preserved; enforcement is recorded explicitly.
        assert execution.output["decision"] == "hold"
        assert execution.output["enforced_decision"] == "reject"
        decision = (await session.execute(select(ProductDecision))).scalars().first()
        assert decision.decision == "reject"
        assert decision.approval_status == "pending"
        assert any("hard product gate failed" in reason for reason in decision.reasons)


@pytest.mark.asyncio
async def test_worker_unknown_cost_gate_blocks_test_decision(db_engine) -> None:
    """PROFIT-003: UNKNOWN cost forbids a high-confidence 'test' decision."""
    backend = task_queue.get_queue_backend()
    factory = _factory(db_engine)
    async with factory() as session:
        agent, product_id = await _seed_and_intake(
            session,
            intake_overrides={
                "purchase_cost": Decimal("0.00"),
                "domestic_shipping": Decimal("0.00"),
                "first_leg_shipping": Decimal("0.00"),
                "last_leg_shipping": Decimal("0.00"),
            },
        )
        await _set_fast_retry(session, max_attempts=2)
        await _set_execution_policy(session, agent_id=agent.id)
        task = await agent_runtime.create_task(
            session,
            workspace_id=WORKSPACE,
            data=TaskCreate(agent_id=agent.id, input={"product_id": str(product_id)}),
        )
        task_id = task.id
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)

    risky = dict(VALID_OUTPUT)
    risky["confidence"] = "0.90"  # > 0.5 with UNKNOWN cost
    executor = partial(product_analyst_executor, gateway_complete=_fake_complete(risky))
    assert await _run(backend, factory, executor) == 1

    async with factory() as session:
        task = await session.get(AgentTask, task_id)
        assert task.status == "failed"
        execution = (
            (await session.execute(select(AgentExecution).where(AgentExecution.task_id == task_id)))
            .scalars()
            .first()
        )
        assert execution.error_type == "invalid"
        runs = (
            (
                await session.execute(
                    select(ProductAnalysisRun).where(ProductAnalysisRun.product_id == product_id)
                )
            )
            .scalars()
            .all()
        )
        failed = [run for run in runs if run.provider == "openai"]
        assert len(failed) == 1
        assert failed[0].status == "failed"
        assert "PROFIT-003" in failed[0].output["error"]
        assert len((await session.execute(select(ProductDecision))).scalars().all()) == 0


# --------------------------------------------------------------------------- #
# Permissions / isolation / input handling
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_worker_permission_boundary(db_engine) -> None:
    """The analyst only proposes; never approves or runs L3 tool actions."""
    backend = task_queue.get_queue_backend()
    factory = _factory(db_engine)
    async with factory() as session:
        agent, product_id = await _seed_and_intake(session)
        task = await agent_runtime.create_task(
            session,
            workspace_id=WORKSPACE,
            data=TaskCreate(agent_id=agent.id, input={"product_id": str(product_id)}),
            trace_id="trace-m52-perm",
        )
        task_id = task.id
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)

    executor = partial(product_analyst_executor, gateway_complete=_fake_complete(VALID_OUTPUT))
    assert await _run(backend, factory, executor) == 1

    async with factory() as session:
        agent = await session.get(AgentRegistry, agent.id)
        assert agent.permission_level == "L2"  # never L3
        execution = (
            (await session.execute(select(AgentExecution).where(AgentExecution.task_id == task_id)))
            .scalars()
            .first()
        )
        assert execution.status == "completed"  # never waiting_approval
        assert execution.tool_calls == []  # no tool calls were made
        assert not (execution.approval or {}).get("required")
        decisions = (await session.execute(select(ProductDecision))).scalars().all()
        assert decisions and all(d.approval_status == "pending" for d in decisions)
        # No business object was created outside the analyst's write scope.
        from app.models.marketing import Campaign

        assert len((await session.execute(select(Campaign))).scalars().all()) == 0


@pytest.mark.asyncio
async def test_worker_workspace_isolation(db_engine) -> None:
    """Cross-workspace product ids are rejected; data never leaks."""
    backend = task_queue.get_queue_backend()
    factory = _factory(db_engine)
    async with factory() as session:
        other_product_id = await _intake(session, workspace=OTHER_WORKSPACE)
        agent, _ = await _seed_and_intake(session)  # WORKSPACE agent + product
        bad_task = await agent_runtime.create_task(
            session,
            workspace_id=WORKSPACE,
            data=TaskCreate(agent_id=agent.id, input={"product_id": str(other_product_id)}),
        )
        bad_task_id = bad_task.id
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=bad_task_id, attempt=1)

    executor = partial(product_analyst_executor, gateway_complete=_fake_complete(VALID_OUTPUT))
    assert await _run(backend, factory, executor) == 1

    async with factory() as session:
        task = await session.get(AgentTask, bad_task_id)
        assert task.status == "failed"
        assert "product not found" in (task.error_message or "").lower()
        execution = (
            (
                await session.execute(
                    select(AgentExecution).where(AgentExecution.task_id == bad_task_id)
                )
            )
            .scalars()
            .first()
        )
        assert execution.error_type == "invalid"
        # No analysis rows were created for the foreign product.
        runs = (
            (
                await session.execute(
                    select(ProductAnalysisRun).where(
                        ProductAnalysisRun.product_id == other_product_id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert not any(run.provider == "openai" for run in runs)


@pytest.mark.asyncio
async def test_worker_missing_product_id_fails_terminal(db_engine) -> None:
    """A task without product_id is a terminal invalid input."""
    backend = task_queue.get_queue_backend()
    factory = _factory(db_engine)
    async with factory() as session:
        agent, _ = await _seed_and_intake(session)
        task = await agent_runtime.create_task(
            session,
            workspace_id=WORKSPACE,
            data=TaskCreate(agent_id=agent.id, input={"action": "analyze"}),
        )
        task_id = task.id
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)

    executor = partial(product_analyst_executor, gateway_complete=_fake_complete(VALID_OUTPUT))
    assert await _run(backend, factory, executor) == 1

    async with factory() as session:
        task = await session.get(AgentTask, task_id)
        assert task.status == "failed"
        assert "product_id" in (task.error_message or "")
        execution = (
            (await session.execute(select(AgentExecution).where(AgentExecution.task_id == task_id)))
            .scalars()
            .first()
        )
        assert execution.error_type == "invalid"


@pytest.mark.asyncio
async def test_seed_helper_idempotent(db_session) -> None:
    """ensure_product_analyst_agent creates prompt + agent exactly once."""
    from app.agents.agent_seed import ensure_product_analyst_agent

    first = await ensure_product_analyst_agent(db_session, workspace_id=WORKSPACE)
    second = await ensure_product_analyst_agent(db_session, workspace_id=WORKSPACE)
    assert first.id == second.id

    prompts = (
        (await db_session.execute(select(Prompt).where(Prompt.name == "AGENT_PRODUCT_ANALYST")))
        .scalars()
        .all()
    )
    assert len(prompts) == 1
    assert prompts[0].version == "v1"
    assert prompts[0].status == "active"

    agents = (
        (
            await db_session.execute(
                select(AgentRegistry).where(AgentRegistry.agent_id == "product_analyst")
            )
        )
        .scalars()
        .all()
    )
    assert len(agents) == 1
    assert agents[0].permission_level == "L2"


@pytest.mark.asyncio
async def test_worker_dispatch_routes_product_analyst_executor(db_engine, monkeypatch) -> None:
    """Default worker dispatch routes product_analyst tasks to its executor."""
    from app.agents import product_analyst as product_analyst_module
    from app.worker.agent_worker import register_executor
    from app.worker.product_analyst_executor import product_analyst_executor as real_executor

    register_executor("product_analyst", real_executor)
    monkeypatch.setattr(
        product_analyst_module.llm_gateway, "complete", _fake_complete(VALID_OUTPUT)
    )

    backend = task_queue.get_queue_backend()
    factory = _factory(db_engine)
    async with factory() as session:
        agent, product_id = await _seed_and_intake(session)
        task = await agent_runtime.create_task(
            session,
            workspace_id=WORKSPACE,
            data=TaskCreate(agent_id=agent.id, input={"product_id": str(product_id)}),
        )
        task_id = task.id
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)

    # No executor passed: the worker must resolve product_analyst_executor.
    assert await _run(backend, factory, executor=None) == 1

    async with factory() as session:
        task = await session.get(AgentTask, task_id)
        assert task.status == "completed"
        decisions = (await session.execute(select(ProductDecision))).scalars().all()
        assert len(decisions) == 1
        assert decisions[0].approval_status == "pending"
