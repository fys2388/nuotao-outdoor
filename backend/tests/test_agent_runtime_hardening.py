"""Tests for M5.1 Agent Runtime Production Hardening.

Covers: versioned execution/budget/retry policies, the Redis-Stream task
queue backend (memory variant), the worker pipeline (happy path, retry,
timeout, budget guard, concurrency gate, idempotent redelivery), tool
gateway handler execution, L3 approval deadline + sweeper, stale-execution
recovery, pending-task reconciliation, daily metrics and workspace
isolation. All flows must emit events with trace_id and never auto-execute
a high-risk business action.
"""

import asyncio
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import get_settings
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.agent_runtime import AgentExecution, AgentRegistry, AgentTask
from app.models.agent_runtime_hardening import (
    AgentExecutionPolicy,
    AgentMetric,
    AgentRetryPolicy,
    AgentTaskAttempt,
)
from app.models.event import EventLog
from app.schemas.agent_runtime import AgentRegisterRequest, TaskCreate
from app.schemas.prompt import PromptCreate
from app.services import (
    agent_metrics,
    agent_policies,
    agent_runtime,
    agent_sweeper,
    prompt_registry,
    retry_engine,
    task_queue,
    tool_gateway,
)
from app.services.llm_gateway import LLMError
from app.services.task_queue import MemoryStreamBackend
from app.worker.agent_worker import ConcurrencyGate, process_message, run_worker_once
from app.worker.executor import ExecutionResult

WORKSPACE = DEFAULT_WORKSPACE_ID
OTHER_WORKSPACE = UUID("00000000-0000-0000-0000-000000000099")

PROMPT_NAME = "AGENT_HARD_ANALYST"


def _headers(workspace: UUID | None = None) -> dict:
    return {"X-Workspace-Id": str(workspace)} if workspace else {}


async def _event_types(session) -> set[str]:
    rows = (await session.execute(select(EventLog.event_type))).scalars().all()
    return set(rows)


async def _seed_prompt(session, workspace: UUID = WORKSPACE, name: str = PROMPT_NAME) -> None:
    await prompt_registry.create_prompt(
        session,
        workspace_id=workspace,
        data=PromptCreate(
            prompt_id=f"prompt-{name.lower()}",
            name=name,
            version="v1",
            template="You are a {role} analyzing product {sku}.",
            variables=["role", "sku"],
        ),
    )


async def _seed_agent_row(
    session,
    *,
    agent_id: str = "HARD_ANALYST",
    level: str = "L2",
    domain: str = "product",
    workspace: UUID = WORKSPACE,
    status: str = "active",
) -> AgentRegistry:
    await _seed_prompt(session, workspace=workspace, name=f"AGENT_{agent_id.upper()}")
    agent = await agent_runtime.register_agent(
        session,
        workspace_id=workspace,
        data=AgentRegisterRequest(
            agent_id=agent_id,
            name="Hardening Test Analyst",
            domain=domain,
            version="v1",
            status=status,
            model_provider="openai",
            model_name="gpt-4o-mini",
            prompt_version="v1",
            permission_level=level,
        ),
    )
    return agent


def _factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


class FakeExecutor:
    """Deterministic executor: pops errors/delays, then returns a result."""

    def __init__(self, result: dict | None = None, errors: list = None, delays: list = None):
        self.result = result if result is not None else {"decision": "test"}
        self.errors = list(errors or [])
        self.delays = list(delays or [])
        self.calls = 0

    async def __call__(self, session, *, workspace_id, agent, task, policy, trace_id):
        self.calls += 1
        if self.delays:
            delay = self.delays.pop(0)
            if delay:
                await asyncio.sleep(delay)
        if self.errors:
            error = self.errors.pop(0)
            if error is not None:
                raise error
        return ExecutionResult(
            output=self.result,
            provider="openai",
            model="gpt-4o-mini",
            tokens={"prompt_tokens": 10, "completion_tokens": 5},
            cost=Decimal("0.001"),
            latency_ms=12,
        )


async def _set_fast_retry(session, *, max_attempts: int = 3) -> None:
    await agent_policies.set_retry_policy(
        session,
        workspace_id=WORKSPACE,
        retry_policy_id="standard",
        name="Instant (test)",
        max_attempts=max_attempts,
        backoff_base_seconds=0,
        backoff_multiplier=Decimal("2"),
        max_backoff_seconds=5,
        retry_on_error_types=["llm", "network", "timeout", "transient"],
        enabled=True,
    )


# --------------------------------------------------------------------------- #
# 1. Policies (versioned + config-driven)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_execution_policy_default_and_versioned_update(db_session) -> None:
    """First use seeds defaults; updates retire the previous version."""
    agent = await _seed_agent_row(db_session)
    policy = await agent_policies.get_execution_policy(
        db_session, workspace_id=WORKSPACE, agent_id=agent.id
    )
    assert policy.is_current is True
    assert policy.max_concurrent == get_settings().agent_default_max_concurrent

    updated = await agent_policies.set_execution_policy(
        db_session,
        workspace_id=WORKSPACE,
        agent_id=agent.id,
        max_concurrent=1,
        execution_timeout_seconds=60,
        approval_timeout_seconds=3600,
        max_context_size=4000,
        retry_policy_id="standard",
        enabled=True,
    )
    assert updated.policy_version == "v2"
    assert updated.is_current is True

    await db_session.refresh(policy)
    assert policy.is_current is False
    events = await _event_types(db_session)
    assert "agent.execution_policy_created" in events
    assert "agent.execution_policy_updated" in events


@pytest.mark.asyncio
async def test_budget_policy_versioned_update(db_session) -> None:
    agent = await _seed_agent_row(db_session)
    policy = await agent_policies.get_budget_policy(
        db_session, workspace_id=WORKSPACE, agent_id=agent.id
    )
    assert policy.monthly_budget == get_settings().agent_default_monthly_budget
    updated = await agent_policies.set_budget_policy(
        db_session,
        workspace_id=WORKSPACE,
        agent_id=agent.id,
        monthly_budget=Decimal("50.00"),
        max_cost_per_execution=Decimal("2.00"),
        alert_threshold=Decimal("0.90"),
    )
    assert updated.policy_version == "v2"
    assert updated.is_current is True
    await db_session.refresh(policy)
    assert policy.is_current is False


@pytest.mark.asyncio
async def test_retry_policy_default_and_update(db_session) -> None:
    default = await agent_policies.get_retry_policy(db_session, workspace_id=WORKSPACE)
    assert default.retry_policy_id == "standard"
    assert default.max_attempts == get_settings().retry_standard_max_attempts
    custom = await agent_policies.set_retry_policy(
        db_session,
        workspace_id=WORKSPACE,
        retry_policy_id="aggressive",
        name="Aggressive",
        max_attempts=5,
        backoff_base_seconds=1,
        backoff_multiplier=Decimal("3"),
        max_backoff_seconds=30,
        retry_on_error_types=["llm", "timeout"],
        enabled=True,
    )
    assert custom.version == "v1"
    got = await agent_policies.get_retry_policy(
        db_session, workspace_id=WORKSPACE, retry_policy_id="aggressive"
    )
    assert got.max_attempts == 5
    events = await _event_types(db_session)
    assert "agent.retry_policy_updated" in events


@pytest.mark.asyncio
async def test_policy_validation_errors(db_session) -> None:
    agent = await _seed_agent_row(db_session)
    with pytest.raises(agent_policies.AgentPolicyError):
        await agent_policies.set_execution_policy(
            db_session,
            workspace_id=WORKSPACE,
            agent_id=agent.id,
            max_concurrent=0,
            execution_timeout_seconds=300,
            approval_timeout_seconds=3600,
            max_context_size=5000,
            retry_policy_id="standard",
        )
    with pytest.raises(agent_policies.AgentPolicyError):
        await agent_policies.set_budget_policy(
            db_session,
            workspace_id=WORKSPACE,
            agent_id=agent.id,
            monthly_budget=Decimal("0"),
            max_cost_per_execution=Decimal("1"),
            alert_threshold=Decimal("0.8"),
        )


# --------------------------------------------------------------------------- #
# 2. Retry engine (pure decisions + attempt audit)
# --------------------------------------------------------------------------- #


def _retry_policy(**kwargs) -> AgentRetryPolicy:
    base = dict(
        max_attempts=3,
        backoff_base_seconds=2,
        backoff_multiplier=Decimal("2"),
        max_backoff_seconds=60,
        retry_on_error_types=["llm", "network", "timeout", "transient"],
        enabled=True,
    )
    base.update(kwargs)
    return AgentRetryPolicy(**base)


@pytest.mark.asyncio
async def test_retry_engine_decisions() -> None:
    policy = _retry_policy()
    assert retry_engine.should_retry(policy, error_type="timeout", attempts_used=1) is True
    assert retry_engine.should_retry(policy, error_type="llm", attempts_used=2) is True
    assert retry_engine.should_retry(policy, error_type="unknown", attempts_used=1) is False
    assert retry_engine.should_retry(policy, error_type="auth", attempts_used=1) is False
    assert retry_engine.should_retry(policy, error_type="budget", attempts_used=1) is False
    assert retry_engine.should_retry(policy, error_type="timeout", attempts_used=3) is False
    assert (
        retry_engine.should_retry(
            _retry_policy(enabled=False), error_type="timeout", attempts_used=1
        )
        is False
    )
    assert retry_engine.backoff_seconds(policy, attempts_used=1) == 2
    assert retry_engine.backoff_seconds(policy, attempts_used=2) == 4
    assert retry_engine.backoff_seconds(policy, attempts_used=4) == 16
    capped = _retry_policy(max_backoff_seconds=5)
    assert retry_engine.backoff_seconds(capped, attempts_used=4) == 5


@pytest.mark.asyncio
async def test_retry_engine_records_attempts(db_session) -> None:
    agent = await _seed_agent_row(db_session)
    task = await agent_runtime.create_task(
        db_session,
        workspace_id=WORKSPACE,
        data=TaskCreate(agent_id=agent.id, input={"sku": "S"}),
    )
    await retry_engine.record_attempt(
        db_session,
        workspace_id=WORKSPACE,
        task_id=task.id,
        attempt_number=1,
        status=retry_engine.ATTEMPT_RUNNING,
        worker_id="w1",
    )
    await retry_engine.record_attempt(
        db_session,
        workspace_id=WORKSPACE,
        task_id=task.id,
        attempt_number=1,
        status=retry_engine.ATTEMPT_FAILED,
        error_type="llm",
        error_message="boom",
    )
    await db_session.refresh(task)
    assert task.attempt_count == 1
    rows = (await db_session.execute(select(AgentTaskAttempt))).scalars().all()
    assert len(rows) == 2
    assert {row.status for row in rows} == {"running", "failed"}


# --------------------------------------------------------------------------- #
# 3. Task queue (memory backend round-trip + delayed retries)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_queue_memory_backend_roundtrip() -> None:
    backend = MemoryStreamBackend()
    message_id = await backend.add("s", {"task_id": "t1", "workspace_id": "w1"})
    assert message_id
    assert await backend.stream_length("s") == 1
    messages = await backend.read_group("s", "g", "c1", count=5, block_ms=0)
    assert len(messages) == 1
    assert messages[0].fields["task_id"] == "t1"
    await backend.ack("s", "g", messages[0].message_id)
    assert await backend.stream_length("s") == 0

    await backend.add_delayed("d", "m1", time.time() - 1)
    await backend.add_delayed("d", "m2", time.time() + 100)
    assert await backend.delayed_count("d") == 2
    due = await backend.pop_delayed_due("d", time.time())
    assert due == ["m1"]
    assert await backend.delayed_count("d") == 1


# --------------------------------------------------------------------------- #
# 4. Worker pipeline
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_worker_happy_path(db_engine) -> None:
    backend = task_queue.get_queue_backend()
    factory = _factory(db_engine)
    async with factory() as session:
        agent = await _seed_agent_row(session)
        task = await agent_runtime.create_task(
            session,
            workspace_id=WORKSPACE,
            data=TaskCreate(agent_id=agent.id, input={"sku": "S"}),
        )
        task_id = task.id
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)

    executor = FakeExecutor()
    processed = await run_worker_once(backend, factory, executor=executor)
    assert processed == 1

    async with factory() as session:
        task = await session.get(AgentTask, task_id)
        assert task.status == "completed"
        assert task.attempt_count == 1
        executions = (
            (await session.execute(select(AgentExecution).where(AgentExecution.task_id == task_id)))
            .scalars()
            .all()
        )
        assert len(executions) == 1
        assert executions[0].status == "completed"
        assert executions[0].worker_id == get_settings().worker_id
        assert executions[0].output == {"decision": "test"}
        assert executions[0].cost == Decimal("0.001")
        attempts = (await session.execute(select(AgentTaskAttempt))).scalars().all()
        assert {row.status for row in attempts} == {"running", "succeeded"}
        events = await _event_types(session)
        assert "agent.task_attempt_started" in events
        assert "agent.task_attempt_succeeded" in events
        assert "agent.execution_completed" in events
    assert await backend.stream_length(task_queue.task_stream()) == 0


@pytest.mark.asyncio
async def test_worker_retry_then_success(db_engine) -> None:
    backend = task_queue.get_queue_backend()
    factory = _factory(db_engine)
    async with factory() as session:
        agent = await _seed_agent_row(session)
        await _set_fast_retry(session, max_attempts=3)
        await agent_policies.set_execution_policy(
            session,
            workspace_id=WORKSPACE,
            agent_id=agent.id,
            max_concurrent=2,
            execution_timeout_seconds=60,
            approval_timeout_seconds=3600,
            max_context_size=5000,
            retry_policy_id="standard",
            enabled=True,
        )
        task = await agent_runtime.create_task(
            session,
            workspace_id=WORKSPACE,
            data=TaskCreate(agent_id=agent.id, input={"sku": "S"}),
        )
        task_id = task.id
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)

    executor = FakeExecutor(errors=[LLMError("provider down", kind="provider")])
    processed = await run_worker_once(backend, factory, executor=executor)
    assert processed == 1

    async with factory() as session:
        task = await session.get(AgentTask, task_id)
        assert task.status == "pending"  # requeued, not failed
        assert task.attempt_count == 1
        events = await _event_types(session)
        assert "agent.task_requeued" in events
        assert "agent.task_failed" not in events
        attempts = (await session.execute(select(AgentTaskAttempt))).scalars().all()
        assert {row.status for row in attempts} == {"running", "failed"}
        assert attempts[1].error_type == "llm"
    assert await backend.delayed_count(task_queue.retry_key()) == 1

    processed = await run_worker_once(backend, factory, executor=executor)
    assert processed == 1
    async with factory() as session:
        task = await session.get(AgentTask, task_id)
        assert task.status == "completed"
        assert task.attempt_count == 2
    assert await backend.delayed_count(task_queue.retry_key()) == 0


@pytest.mark.asyncio
async def test_worker_terminal_failure_dead_letter(db_engine) -> None:
    backend = task_queue.get_queue_backend()
    factory = _factory(db_engine)
    async with factory() as session:
        agent = await _seed_agent_row(session)
        await _set_fast_retry(session, max_attempts=2)
        await agent_policies.set_execution_policy(
            session,
            workspace_id=WORKSPACE,
            agent_id=agent.id,
            max_concurrent=2,
            execution_timeout_seconds=60,
            approval_timeout_seconds=3600,
            max_context_size=5000,
            retry_policy_id="standard",
            enabled=True,
        )
        task = await agent_runtime.create_task(
            session,
            workspace_id=WORKSPACE,
            data=TaskCreate(agent_id=agent.id, input={"sku": "S"}),
        )
        task_id = task.id
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)

    executor = FakeExecutor(errors=[LLMError("bad key", kind="auth")])
    await run_worker_once(backend, factory, executor=executor)
    # auth errors are terminal: no retry, task dead-lettered on attempt 1
    async with factory() as session:
        task = await session.get(AgentTask, task_id)
        assert task.status == "failed"
        assert task.error_message
        events = await _event_types(session)
        assert "agent.task_dead_letter" in events
        assert "agent.task_failed" in events
    assert await backend.delayed_count(task_queue.retry_key()) == 0


@pytest.mark.asyncio
async def test_worker_timeout_then_retry(db_engine) -> None:
    backend = task_queue.get_queue_backend()
    factory = _factory(db_engine)
    async with factory() as session:
        agent = await _seed_agent_row(session)
        await _set_fast_retry(session, max_attempts=3)
        await agent_policies.set_execution_policy(
            session,
            workspace_id=WORKSPACE,
            agent_id=agent.id,
            max_concurrent=2,
            execution_timeout_seconds=1,
            approval_timeout_seconds=3600,
            max_context_size=5000,
            retry_policy_id="standard",
            enabled=True,
        )
        task = await agent_runtime.create_task(
            session,
            workspace_id=WORKSPACE,
            data=TaskCreate(agent_id=agent.id, input={"sku": "S"}),
        )
        task_id = task.id
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)

    executor = FakeExecutor(delays=[2, 0])  # first attempt exceeds the 1s timeout
    await run_worker_once(backend, factory, executor=executor)
    async with factory() as session:
        task = await session.get(AgentTask, task_id)
        assert task.status == "pending"
        attempts = (await session.execute(select(AgentTaskAttempt))).scalars().all()
        assert {row.status for row in attempts} == {"running", retry_engine.ATTEMPT_TIMED_OUT}
        events = await _event_types(session)
        assert "agent.execution_timed_out" in events

    await run_worker_once(backend, factory, executor=executor)
    async with factory() as session:
        task = await session.get(AgentTask, task_id)
        assert task.status == "completed"
        assert task.attempt_count == 2


@pytest.mark.asyncio
async def test_worker_budget_blocked(db_engine) -> None:
    backend = task_queue.get_queue_backend()
    factory = _factory(db_engine)
    async with factory() as session:
        agent = await _seed_agent_row(session)
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
            data=TaskCreate(agent_id=agent.id, input={"sku": "S"}),
        )
        task_id = task.id
        # seed a completed execution with real cost this month
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
    executor = FakeExecutor()
    await run_worker_once(backend, factory, executor=executor)
    assert executor.calls == 0  # no model call was made

    async with factory() as session:
        task = await session.get(AgentTask, task_id)
        assert task.status == "failed"
        assert "budget" in (task.error_message or "").lower()
        attempts = (await session.execute(select(AgentTaskAttempt))).scalars().all()
        assert attempts[0].status == retry_engine.ATTEMPT_BUDGET_BLOCKED
        events = await _event_types(session)
        assert "agent.execution_budget_blocked" in events
    assert await backend.delayed_count(task_queue.retry_key()) == 0


@pytest.mark.asyncio
async def test_worker_concurrency_gate_defers(db_engine) -> None:
    settings = get_settings()
    settings.task_queue_defer_delay = 0
    backend = task_queue.get_queue_backend()
    factory = _factory(db_engine)
    async with factory() as session:
        agent = await _seed_agent_row(session)
        await agent_policies.set_execution_policy(
            session,
            workspace_id=WORKSPACE,
            agent_id=agent.id,
            max_concurrent=1,
            execution_timeout_seconds=60,
            approval_timeout_seconds=3600,
            max_context_size=5000,
            retry_policy_id="standard",
            enabled=True,
        )
        task = await agent_runtime.create_task(
            session,
            workspace_id=WORKSPACE,
            data=TaskCreate(agent_id=agent.id, input={"sku": "S"}),
        )
        task_id = task.id
        agent_key = str(agent.id)
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)

    gate = ConcurrencyGate()
    assert gate.try_acquire(agent_key, 1) is True
    processed = await run_worker_once(backend, factory, executor=FakeExecutor(), gate=gate)
    assert processed == 1  # message consumed but deferred
    assert await backend.delayed_count(task_queue.retry_key()) == 1
    async with factory() as session:
        task = await session.get(AgentTask, task_id)
        assert task.status == "pending"
        events = await _event_types(session)
        assert "agent.task_deferred" in events

    gate.release(agent_key)
    processed = await run_worker_once(backend, factory, executor=FakeExecutor(), gate=gate)
    assert processed == 1
    async with factory() as session:
        task = await session.get(AgentTask, task_id)
        assert task.status == "completed"


@pytest.mark.asyncio
async def test_worker_skips_redelivered_non_pending(db_engine) -> None:
    backend = task_queue.get_queue_backend()
    factory = _factory(db_engine)
    async with factory() as session:
        agent = await _seed_agent_row(session)
        task = await agent_runtime.create_task(
            session,
            workspace_id=WORKSPACE,
            data=TaskCreate(agent_id=agent.id, input={"sku": "S"}),
        )
        task_id = task.id
    # simulate a crashed worker: task already running, message redelivered
    async with factory() as session:
        task = await session.get(AgentTask, task_id)
        task.status = "running"
        await session.commit()
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)
    messages = await backend.read_group(
        task_queue.task_stream(), get_settings().task_queue_group, "test", count=1, block_ms=0
    )
    outcome = await process_message(backend, factory, messages[0], executor=FakeExecutor())
    assert outcome == "skipped"
    async with factory() as session:
        task = await session.get(AgentTask, task_id)
        assert task.status == "running"


@pytest.mark.asyncio
async def test_worker_agent_unavailable_fails_task(db_engine) -> None:
    backend = task_queue.get_queue_backend()
    factory = _factory(db_engine)
    async with factory() as session:
        agent = await _seed_agent_row(session, agent_id="DOWN_1")
        task = await agent_runtime.create_task(
            session,
            workspace_id=WORKSPACE,
            data=TaskCreate(agent_id=agent.id, input={"sku": "S"}),
        )
        task_id = task.id
        agent.status = "inactive"
        await session.commit()
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)
    await run_worker_once(backend, factory, executor=FakeExecutor())
    async with factory() as session:
        task = await session.get(AgentTask, task_id)
        assert task.status == "failed"
        assert "agent" in (task.error_message or "").lower()


# --------------------------------------------------------------------------- #
# 5. Tool gateway + L3 approval deadline + sweepers
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_tool_gateway_handler_execution(db_session, api_client) -> None:
    async def echo_handler(arguments: dict, context) -> dict:
        return {"echo": arguments}

    tool_gateway.register_handler("test.echo", echo_handler)
    try:
        agent = await _seed_agent_row(db_session)
        await _seed_prompt(db_session, name="AGENT_GATE_1")
        response = api_client.post(
            "/api/v1/agent-registry",
            json={
                "agent_id": "GATE_1",
                "name": "Gate",
                "domain": "product",
                "version": "v1",
                "status": "active",
                "model_provider": "openai",
                "model_name": "gpt-4o-mini",
                "prompt_version": "v1",
                "permission_level": "L2",
            },
            headers=_headers(),
        )
        assert response.status_code == 201, response.text
        agent = response.json()
        tool_response = api_client.post(
            "/api/v1/agent-tools",
            json={
                "tool_name": "product.read",
                "description": "read",
                "permission_level": "L1",
                "enabled": True,
                "category": "product",
                "handler_name": "test.echo",
                "args_schema": {"product_id": "string"},
            },
            headers=_headers(),
        )
        assert tool_response.status_code == 201, tool_response.text
        task, execution = await _create_task_and_start(api_client, agent)

        call = api_client.post(
            f"/api/v1/agent-executions/{execution['id']}/tool-calls",
            json={"tool_name": "product.read", "arguments": {"product_id": "SKU-1"}},
            headers=_headers(),
        )
        assert call.status_code == 200, call.text
        body = call.json()
        assert body["status"] == "allowed"
        assert body["handler_name"] == "test.echo"
        assert body["output"] == {"echo": {"product_id": "SKU-1"}}

        executions = (await db_session.execute(select(AgentExecution))).scalars().all()
        latest = executions[-1]
        assert latest.tool_calls[-1]["output"] == {"echo": {"product_id": "SKU-1"}}
        events = await _event_types(db_session)
        assert "agent.tool_call_executed" in events
    finally:
        tool_gateway.unregister_handler("test.echo")


@pytest.mark.asyncio
async def test_tool_gateway_missing_handler_denied(db_session, api_client) -> None:
    agent = await _seed_agent_row(db_session)
    agent_row = {"id": str(agent.id)}
    tool_response = api_client.post(
        "/api/v1/agent-tools",
        json={
            "tool_name": "ghost.tool",
            "description": "ghost",
            "permission_level": "L1",
            "enabled": True,
            "category": "test",
            "handler_name": "ghost.handler",
        },
        headers=_headers(),
    )
    assert tool_response.status_code == 201, tool_response.text
    task, execution = await _create_task_and_start(api_client, agent_row)
    call = api_client.post(
        f"/api/v1/agent-executions/{execution['id']}/tool-calls",
        json={"tool_name": "ghost.tool", "arguments": {}},
        headers=_headers(),
    )
    assert call.status_code == 403
    events = await _event_types(db_session)
    assert "agent.tool_call_denied" in events


@pytest.mark.asyncio
async def test_l3_tool_call_sets_approval_deadline(db_session, api_client) -> None:
    agent = await _seed_agent_row(db_session, agent_id="L3_1", level="L3")
    agent_row = {"id": str(agent.id)}
    tool_response = api_client.post(
        "/api/v1/agent-tools",
        json={
            "tool_name": "purchase.create",
            "description": "high risk",
            "permission_level": "L3",
            "enabled": True,
            "category": "supply_chain",
        },
        headers=_headers(),
    )
    assert tool_response.status_code == 201, tool_response.text
    task, execution = await _create_task_and_start(api_client, agent_row)
    call = api_client.post(
        f"/api/v1/agent-executions/{execution['id']}/tool-calls",
        json={"tool_name": "purchase.create", "arguments": {"sku": "S"}},
        headers=_headers(),
    )
    assert call.status_code == 200, call.text
    assert call.json()["status"] == "requires_approval"
    assert call.json()["approval_deadline"]

    rows = (await db_session.execute(select(AgentExecution))).scalars().all()
    latest = rows[-1]
    assert latest.status == "waiting_approval"
    assert latest.approval_deadline is not None
    task_row = await db_session.get(AgentTask, UUID(task["id"]))
    assert task_row.status == "waiting_approval"


@pytest.mark.asyncio
async def test_approval_timeout_sweeper(db_session, api_client) -> None:
    agent = await _seed_agent_row(db_session, agent_id="L3_2", level="L3")
    agent_row = {"id": str(agent.id)}
    api_client.post(
        "/api/v1/agent-tools",
        json={
            "tool_name": "purchase.create",
            "description": "high risk",
            "permission_level": "L3",
            "enabled": True,
            "category": "supply_chain",
        },
        headers=_headers(),
    )
    task, execution = await _create_task_and_start(api_client, agent_row)
    api_client.post(
        f"/api/v1/agent-executions/{execution['id']}/tool-calls",
        json={"tool_name": "purchase.create", "arguments": {"sku": "S"}},
        headers=_headers(),
    )
    rows = (await db_session.execute(select(AgentExecution))).scalars().all()
    latest = rows[-1]
    latest.approval_deadline = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()

    expired = await agent_sweeper.expire_stale_approvals(db_session, workspace_id=WORKSPACE)
    assert expired == 1
    await db_session.refresh(latest)
    assert latest.status == "rejected"
    assert latest.approval["decision"] == "expired"
    task_row = await db_session.get(AgentTask, UUID(task["id"]))
    assert task_row.status == "failed"
    events = await _event_types(db_session)
    assert "agent.approval_expired" in events


@pytest.mark.asyncio
async def test_stale_execution_sweeper_requeues(db_engine) -> None:
    backend = task_queue.get_queue_backend()
    factory = _factory(db_engine)
    async with factory() as session:
        agent = await _seed_agent_row(session)
        await _set_fast_retry(session, max_attempts=3)
        task = await agent_runtime.create_task(
            session,
            workspace_id=WORKSPACE,
            data=TaskCreate(agent_id=agent.id, input={"sku": "S"}),
        )
        task_id = task.id
        execution = await agent_runtime.start_execution(
            session, workspace_id=WORKSPACE, task_id=task_id
        )
        execution.started_at = datetime.now(UTC) - timedelta(minutes=30)
        await session.commit()
        execution_id = execution.id

    async with factory() as session:
        failed, requeued = await agent_sweeper.fail_stale_executions(
            session, workspace_id=WORKSPACE, backend=backend
        )
        assert (failed, requeued) == (1, 1)
        execution = await session.get(AgentExecution, execution_id)
        assert execution.status == "failed"
        assert execution.error_type == "timeout"
        task = await session.get(AgentTask, task_id)
        assert task.status == "pending"
        events = await _event_types(session)
        assert "agent.task_requeued" in events
    assert await backend.delayed_count(task_queue.retry_key()) == 1


@pytest.mark.asyncio
async def test_stale_execution_sweeper_dead_letter(db_engine) -> None:
    backend = task_queue.get_queue_backend()
    factory = _factory(db_engine)
    async with factory() as session:
        agent = await _seed_agent_row(session)
        await _set_fast_retry(session, max_attempts=1)
        task = await agent_runtime.create_task(
            session,
            workspace_id=WORKSPACE,
            data=TaskCreate(agent_id=agent.id, input={"sku": "S"}),
        )
        task_id = task.id
        execution = await agent_runtime.start_execution(
            session, workspace_id=WORKSPACE, task_id=task_id
        )
        execution.started_at = datetime.now(UTC) - timedelta(minutes=30)
        await session.commit()

    async with factory() as session:
        failed, requeued = await agent_sweeper.fail_stale_executions(
            session, workspace_id=WORKSPACE, backend=backend
        )
        assert (failed, requeued) == (1, 0)
        task = await session.get(AgentTask, task_id)
        assert task.status == "failed"
        events = await _event_types(session)
        assert "agent.task_dead_letter" in events


@pytest.mark.asyncio
async def test_reconcile_pending_tasks(db_engine) -> None:
    backend = task_queue.get_queue_backend()
    factory = _factory(db_engine)
    async with factory() as session:
        agent = await _seed_agent_row(session)
        task = await agent_runtime.create_task(
            session,
            workspace_id=WORKSPACE,
            data=TaskCreate(agent_id=agent.id, input={"sku": "S"}),
        )
        task_id = task.id
        assert task.enqueued_at is None

    async with factory() as session:
        enqueued = await agent_sweeper.reconcile_pending_tasks(
            session, workspace_id=WORKSPACE, backend=backend
        )
        assert enqueued == 1
        task = await session.get(AgentTask, task_id)
        assert task.enqueued_at is not None
        events = await _event_types(session)
        assert "agent.task_enqueued" in events
    assert await backend.stream_length(task_queue.task_stream()) == 1


# --------------------------------------------------------------------------- #
# 6. Metrics + workspace isolation
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_metrics_snapshot_aggregates_and_upserts(db_session) -> None:
    agent = await _seed_agent_row(db_session)
    now = datetime.now(UTC)
    for status, cost, latency, error_type in [
        ("completed", Decimal("0.10"), 100, None),
        ("completed", Decimal("0.20"), 200, None),
        ("failed", Decimal("0.05"), 300, "timeout"),
        ("rejected", Decimal("0.02"), 400, "rejected"),
    ]:
        db_session.add(
            AgentExecution(
                workspace_id=WORKSPACE,
                agent_id=agent.id,
                context_snapshot={},
                input={},
                status=status,
                cost=cost,
                latency_ms=latency,
                error_type=error_type,
                started_at=now,
                completed_at=now,
            )
        )
    await db_session.commit()

    row = await agent_metrics.snapshot_metrics(
        db_session, workspace_id=WORKSPACE, agent_id=agent.id
    )
    assert row.executions_count == 4
    assert row.success_count == 2
    assert row.failure_count == 2
    assert row.timeout_count == 1
    assert row.total_cost == Decimal("0.37")
    assert row.avg_latency_ms == Decimal("250.00")
    assert row.p95_latency_ms == 400
    assert row.error_breakdown.get("timeout") == 1

    rows_before = (await db_session.execute(select(AgentMetric))).scalars().all()
    await agent_metrics.snapshot_metrics(db_session, workspace_id=WORKSPACE, agent_id=agent.id)
    rows_after = (await db_session.execute(select(AgentMetric))).scalars().all()
    assert len(rows_after) == len(rows_before) == 1  # upsert, not duplicate
    events = await _event_types(db_session)
    assert "agent.metrics_snapshotted" in events


@pytest.mark.asyncio
async def test_workspace_isolation(db_session) -> None:
    agent_a = await _seed_agent_row(db_session, agent_id="ISO_A")
    agent_b = await _seed_agent_row(db_session, agent_id="ISO_B", workspace=OTHER_WORKSPACE)
    await agent_policies.set_execution_policy(
        db_session,
        workspace_id=WORKSPACE,
        agent_id=agent_a.id,
        max_concurrent=1,
        execution_timeout_seconds=60,
        approval_timeout_seconds=3600,
        max_context_size=4000,
        retry_policy_id="standard",
        enabled=True,
    )
    await agent_metrics.snapshot_metrics(db_session, workspace_id=WORKSPACE, agent_id=agent_a.id)
    await agent_metrics.snapshot_metrics(
        db_session, workspace_id=OTHER_WORKSPACE, agent_id=agent_b.id
    )

    policies_a = (
        (
            await db_session.execute(
                select(AgentExecutionPolicy).where(AgentExecutionPolicy.workspace_id == WORKSPACE)
            )
        )
        .scalars()
        .all()
    )
    policies_b = (
        (
            await db_session.execute(
                select(AgentExecutionPolicy).where(
                    AgentExecutionPolicy.workspace_id == OTHER_WORKSPACE
                )
            )
        )
        .scalars()
        .all()
    )
    assert all(p.agent_id == agent_a.id for p in policies_a)
    assert all(p.agent_id == agent_b.id for p in policies_b)

    metrics_a, _ = await agent_metrics.list_metrics(
        db_session, workspace_id=WORKSPACE, agent_id=agent_a.id
    )
    metrics_b_ws, _ = await agent_metrics.list_metrics(
        db_session, workspace_id=OTHER_WORKSPACE, agent_id=agent_a.id
    )
    assert len(metrics_a) == 1
    assert len(metrics_b_ws) == 0


# --------------------------------------------------------------------------- #
# 7. API surfaces
# --------------------------------------------------------------------------- #


async def _create_task_and_start(api_client, agent_row: dict) -> tuple[dict, dict]:
    created = api_client.post(
        "/api/v1/agent-tasks",
        json={"agent_id": agent_row["id"], "input": {"sku": "SKU-TEST"}, "priority": 3},
        headers=_headers(),
    )
    assert created.status_code == 201, created.text
    task = created.json()
    started = api_client.post(
        "/api/v1/agent-executions",
        json={"task_id": task["id"]},
        headers=_headers(),
    )
    assert started.status_code == 201, started.text
    return task, started.json()


@pytest.mark.asyncio
async def test_create_task_via_api_enqueues(db_session, api_client) -> None:
    """API task creation enqueues on the (memory) queue and records enqueued_at."""
    await _seed_prompt(db_session, name="AGENT_ENQ_1")
    agent_response = api_client.post(
        "/api/v1/agent-registry",
        json={
            "agent_id": "ENQ_1",
            "name": "Enqueue",
            "domain": "product",
            "version": "v1",
            "status": "active",
            "model_provider": "openai",
            "model_name": "gpt-4o-mini",
            "prompt_version": "v1",
            "permission_level": "L1",
        },
        headers=_headers(),
    )
    assert agent_response.status_code == 201, agent_response.text
    agent = agent_response.json()
    created = api_client.post(
        "/api/v1/agent-tasks",
        json={"agent_id": agent["id"], "input": {"sku": "S"}, "priority": 3},
        headers=_headers(),
    )
    assert created.status_code == 201, created.text
    task = created.json()
    assert task["enqueued_at"] is not None
    backend = task_queue.get_queue_backend()
    assert await backend.stream_length(task_queue.task_stream()) >= 1


@pytest.mark.asyncio
async def test_policy_api_endpoints(db_session, api_client) -> None:
    agent = await _seed_agent_row(db_session)
    # execution policy
    created = api_client.post(
        "/api/v1/agent-policies/execution",
        json={
            "agent_id": str(agent.id),
            "max_concurrent": 2,
            "execution_timeout_seconds": 120,
            "approval_timeout_seconds": 7200,
            "max_context_size": 8000,
            "retry_policy_id": "standard",
            "enabled": True,
        },
        headers=_headers(),
    )
    assert created.status_code == 201, created.text
    assert created.json()["policy_version"] == "v1"  # first version
    got = api_client.get(
        f"/api/v1/agent-policies/execution?agent_id={agent.id}", headers=_headers()
    )
    assert got.status_code == 200
    assert got.json()["max_concurrent"] == 2
    bad = api_client.post(
        "/api/v1/agent-policies/execution",
        json={
            "agent_id": str(agent.id),
            "max_concurrent": 0,
            "execution_timeout_seconds": 120,
            "approval_timeout_seconds": 7200,
            "max_context_size": 8000,
            "retry_policy_id": "standard",
        },
        headers=_headers(),
    )
    assert bad.status_code in (400, 422)

    # budget policy
    budget = api_client.post(
        "/api/v1/agent-policies/budget",
        json={
            "agent_id": str(agent.id),
            "monthly_budget": "20.00",
            "max_cost_per_execution": "1.00",
            "alert_threshold": "0.75",
            "currency": "USD",
        },
        headers=_headers(),
    )
    assert budget.status_code == 201, budget.text
    got_budget = api_client.get(
        f"/api/v1/agent-policies/budget?agent_id={agent.id}", headers=_headers()
    )
    assert got_budget.status_code == 200
    assert got_budget.json()["monthly_budget"] == "20.00"

    # retry policy
    retry = api_client.post(
        "/api/v1/agent-retry-policies",
        json={
            "retry_policy_id": "custom",
            "name": "Custom",
            "max_attempts": 4,
            "backoff_base_seconds": 3,
            "backoff_multiplier": "2.5",
            "max_backoff_seconds": 60,
            "retry_on_error_types": ["llm", "timeout"],
            "enabled": True,
        },
        headers=_headers(),
    )
    assert retry.status_code == 201, retry.text
    got_retry = api_client.get(
        "/api/v1/agent-retry-policies?retry_policy_id=custom", headers=_headers()
    )
    assert got_retry.status_code == 200
    assert got_retry.json()["max_attempts"] == 4


@pytest.mark.asyncio
async def test_metrics_and_queue_and_sweeper_api(db_session, api_client) -> None:
    agent = await _seed_agent_row(db_session)
    now = datetime.now(UTC)
    db_session.add(
        AgentExecution(
            workspace_id=WORKSPACE,
            agent_id=agent.id,
            context_snapshot={},
            input={},
            status="completed",
            cost=Decimal("0.10"),
            latency_ms=50,
            started_at=now,
            completed_at=now,
        )
    )
    await db_session.commit()

    snapshot = api_client.post(
        "/api/v1/agent-metrics/snapshot",
        json={"agent_id": str(agent.id)},
        headers=_headers(),
    )
    assert snapshot.status_code == 200, snapshot.text
    assert len(snapshot.json()) == 1
    assert snapshot.json()[0]["executions_count"] == 1

    metrics = api_client.get(f"/api/v1/agent-metrics?agent_id={agent.id}", headers=_headers())
    assert metrics.status_code == 200
    assert metrics.json()[0]["success_count"] == 1

    stats = api_client.get("/api/v1/agent-queue/stats", headers=_headers())
    assert stats.status_code == 200
    assert stats.json()["backend"] == "memory"

    sweeper = api_client.post("/api/v1/agent-sweeper/run", headers=_headers())
    assert sweeper.status_code == 200, sweeper.text
    body = sweeper.json()
    assert set(body) == {
        "approvals_expired",
        "stale_executions_failed",
        "tasks_requeued",
        "pending_tasks_enqueued",
    }
