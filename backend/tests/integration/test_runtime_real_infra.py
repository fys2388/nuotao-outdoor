"""M5.2.1 real-infrastructure runtime validation (PostgreSQL + Redis).

Drives the M5.1 worker end-to-end against REAL PostgreSQL (migrated schema)
and REAL Redis Streams: happy path audit chain, idempotent redelivery (DB as
source of truth), crash reclaim through the worker, producer idempotency_key
dedup, dead-lettering, and the real LLM gateway fallback (OpenAI 5xx ->
DeepSeek) with provider/model/tokens/cost/latency audit.
"""

from __future__ import annotations

import json
from decimal import Decimal
from functools import partial

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.agent_runtime import AgentExecution, AgentTask
from app.models.event import EventLog
from app.models.product_intelligence import (
    ProductAiEvaluation,
    ProductAnalysisRun,
    ProductDecision,
)
from app.schemas.agent_runtime import TaskCreate
from app.services import agent_runtime, task_queue
from app.services.llm_gateway import LLMError
from app.worker.agent_worker import run_worker_once
from app.worker.product_analyst_executor import product_analyst_executor
from tests.integration.conftest import enable_redis_queue
from tests.integration.runtime_helpers import (
    VALID_OUTPUT,
    factory,
    fake_complete,
    run_worker,
    seed_and_intake,
    set_execution_policy,
    set_fast_retry,
)

WORKSPACE = DEFAULT_WORKSPACE_ID


class _AlwaysFailGateway:
    """Executor gateway that always raises a terminal schema error."""

    async def __call__(self, request, trace_id=None):
        from app.services.llm_gateway import LLMResponse

        return LLMResponse(
            provider="openai",
            model="gpt-4o-mini",
            content="this is not json at all",
            tokens={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            cost=Decimal("0.000100"),
            latency_ms=3,
            trace_id=trace_id,
        )


class _AlwaysProviderFailGateway:
    """Gateway that always raises a retryable provider LLMError."""

    async def __call__(self, request, trace_id=None):
        raise LLMError("provider unavailable", kind="provider")


def _deepseek_ok_content() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": json.dumps(VALID_OUTPUT)}}],
            "usage": {"prompt_tokens": 110, "completion_tokens": 55, "total_tokens": 165},
        },
    )


def _openai_500_deepseek_ok(request: httpx.Request) -> httpx.Response:
    if "openai.com" in str(request.url):
        return httpx.Response(500, json={"error": "openai boom"})
    return _deepseek_ok_content()


def _both_500(request: httpx.Request) -> httpx.Response:
    return httpx.Response(503, json={"error": "all providers down"})


@pytest.fixture()
async def pg_engine(pg_migrated: str):
    """Async engine + migrated real PostgreSQL database for one test."""
    engine = create_async_engine(pg_migrated)
    yield engine
    await engine.dispose()


async def _event_types(session) -> set[str]:
    rows = (await session.execute(select(EventLog.event_type))).scalars().all()
    return set(rows)


# --------------------------------------------------------------------------- #
# Happy path + audit chain on real infra
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_worker_end_to_end_real_infra(pg_engine, redis_url: str) -> None:
    """Task -> real Redis -> real PG worker -> completed + full audit chain."""
    enable_redis_queue(redis_url)
    backend = task_queue.get_queue_backend()
    session_factory = factory(pg_engine)

    async with session_factory() as session:
        agent, product_id = await seed_and_intake(session)
        await set_fast_retry(session)
        await set_execution_policy(session, agent_id=agent.id)
        task = await agent_runtime.create_task(
            session,
            workspace_id=WORKSPACE,
            data=TaskCreate(
                agent_id=agent.id,
                input={"product_id": str(product_id), "action": "analyze"},
            ),
            trace_id="trace-real-infra",
        )
        task_id = task.id
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)

    executor = partial(product_analyst_executor, gateway_complete=fake_complete(VALID_OUTPUT))
    assert await run_worker(backend, session_factory, executor) >= 1

    async with session_factory() as session:
        task = await session.get(AgentTask, task_id)
        assert task.status == "completed"
        assert task.trace_id == "trace-real-infra"
        execution = (
            (await session.execute(select(AgentExecution).where(AgentExecution.task_id == task_id)))
            .scalars()
            .first()
        )
        assert execution.status == "completed"
        assert execution.provider == "openai"
        assert execution.model == "gpt-4o-mini"
        assert execution.tokens["total_tokens"] == 180
        assert execution.cost == Decimal("0.001500")
        assert execution.latency_ms >= 0
        assert execution.trace_id == "trace-real-infra"
        assert "product_context" in execution.context_snapshot

        runs = (
            (
                await session.execute(
                    select(ProductAnalysisRun).where(ProductAnalysisRun.product_id == product_id)
                )
            )
            .scalars()
            .all()
        )
        # The deterministic intake chain writes a heuristic run; only the
        # LLM agent run carries the gateway provider.
        llm_runs = [run for run in runs if run.provider == "openai"]
        assert len(llm_runs) == 1
        assert llm_runs[0].status == "completed"

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
        assert decisions[0].approval_status == "pending"  # never auto-approved

        evaluations = (await session.execute(select(ProductAiEvaluation))).scalars().all()
        assert len(evaluations) == 1
        events = await _event_types(session)
        assert "agent.task_created" in events
        assert "agent.execution_completed" in events
        assert "product.ai_evaluation.recorded" in events
        assert "agent.evaluation.domain_mirrored" in events
    # Redis Streams retain XADD history by design; the correct "queue is
    # drained" signal is an empty PEL (no unacked deliveries remain).
    pending = await backend.redis.xpending(
        task_queue.task_stream(), get_settings().task_queue_group
    )
    assert pending["pending"] == 0


# --------------------------------------------------------------------------- #
# Idempotency: DB row is the source of truth
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_worker_redelivery_idempotent_real_infra(pg_engine, redis_url: str) -> None:
    """A duplicated stream message for a completed task is skipped."""
    enable_redis_queue(redis_url)
    backend = task_queue.get_queue_backend()
    session_factory = factory(pg_engine)

    async with session_factory() as session:
        agent, product_id = await seed_and_intake(session)
        await set_fast_retry(session)
        await set_execution_policy(session, agent_id=agent.id)
        task = await agent_runtime.create_task(
            session,
            workspace_id=WORKSPACE,
            data=TaskCreate(agent_id=agent.id, input={"product_id": str(product_id)}),
        )
        task_id = task.id
    # The same task is enqueued twice (e.g. producer retry / PEL redelivery).
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)

    executor = partial(product_analyst_executor, gateway_complete=fake_complete(VALID_OUTPUT))
    processed = await run_worker(backend, session_factory, executor, rounds=2)
    assert processed >= 1

    async with session_factory() as session:
        task = await session.get(AgentTask, task_id)
        assert task.status == "completed"
        executions = (
            (await session.execute(select(AgentExecution).where(AgentExecution.task_id == task_id)))
            .scalars()
            .all()
        )
        assert len(executions) == 1  # duplicated delivery never re-executes
    # Redis Streams retain XADD history by design; the correct "queue is
    # drained" signal is an empty PEL (no unacked deliveries remain).
    pending = await backend.redis.xpending(
        task_queue.task_stream(), get_settings().task_queue_group
    )
    assert pending["pending"] == 0


@pytest.mark.asyncio
async def test_idempotency_key_dedup_real_infra(pg_engine, redis_url: str) -> None:
    """The same (workspace, agent, idempotency_key) creates one task only."""
    enable_redis_queue(redis_url)
    backend = task_queue.get_queue_backend()
    session_factory = factory(pg_engine)

    async with session_factory() as session:
        agent, product_id = await seed_and_intake(session)
        await set_fast_retry(session)
        await set_execution_policy(session, agent_id=agent.id)
        body = TaskCreate(
            agent_id=agent.id,
            input={"product_id": str(product_id)},
            idempotency_key="idem-webhook-001",
        )
        first = await agent_runtime.create_task(
            session, workspace_id=WORKSPACE, data=body, trace_id="trace-idem-1"
        )
        second = await agent_runtime.create_task(
            session, workspace_id=WORKSPACE, data=body, trace_id="trace-idem-2"
        )
        assert first.id == second.id
        task_id = first.id

    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)
    executor = partial(product_analyst_executor, gateway_complete=fake_complete(VALID_OUTPUT))
    assert await run_worker(backend, session_factory, executor) >= 1

    async with session_factory() as session:
        tasks = (
            (
                await session.execute(
                    select(AgentTask).where(
                        AgentTask.workspace_id == WORKSPACE,
                        AgentTask.idempotency_key == "idem-webhook-001",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(tasks) == 1
        executions = (
            (await session.execute(select(AgentExecution).where(AgentExecution.task_id == task_id)))
            .scalars()
            .all()
        )
        assert len(executions) == 1  # the same work is never executed twice
        events = await _event_types(session)
        assert "agent.task_idempotent_reused" in events


@pytest.mark.asyncio
async def test_api_idempotency_key_does_not_double_enqueue(db_session, api_client) -> None:
    """POST /agent-tasks with the same key returns the task and enqueues once."""
    from app.agents.agent_seed import ensure_product_analyst_agent

    agent = await ensure_product_analyst_agent(db_session, workspace_id=WORKSPACE)
    body = {
        "agent_id": str(agent.id),
        "input": {"product_id": "00000000-0000-0000-0000-0000000000aa"},
        "idempotency_key": "api-idem-1",
    }
    first = api_client.post("/api/v1/agent-tasks", json=body)
    second = api_client.post("/api/v1/agent-tasks", json=body)
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["id"] == second.json()["id"]
    from app.services import task_queue as tq

    backend = tq.get_queue_backend()
    assert await backend.stream_length(tq.task_stream()) == 1  # enqueued once


# --------------------------------------------------------------------------- #
# Crash recovery: reclaim unacked PEL deliveries through the worker
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_worker_crash_reclaim_real_infra(pg_engine, redis_url: str) -> None:
    """A crashed worker's unacked message is reclaimed and reprocessed."""
    enable_redis_queue(redis_url)
    settings = get_settings()
    settings.task_queue_reclaim_idle_ms = 0  # force immediate reclaim
    backend = task_queue.get_queue_backend()
    session_factory = factory(pg_engine)

    async with session_factory() as session:
        agent, product_id = await seed_and_intake(session)
        await set_fast_retry(session)
        await set_execution_policy(session, agent_id=agent.id)
        task = await agent_runtime.create_task(
            session,
            workspace_id=WORKSPACE,
            data=TaskCreate(agent_id=agent.id, input={"product_id": str(product_id)}),
        )
        task_id = task.id
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)

    # Worker A claims the message and "crashes" before processing/acking.
    claimed = await backend.read_group(
        task_queue.task_stream(),
        settings.task_queue_group,
        "worker-a",
        count=1,
        block_ms=0,
    )
    assert len(claimed) == 1
    pending = await backend.redis.xpending(task_queue.task_stream(), settings.task_queue_group)
    assert pending["pending"] == 1

    # A new worker reclaims and completes the task; the DB row dedupes any
    # earlier partial state (the task is still pending, so it executes once).
    executor = partial(product_analyst_executor, gateway_complete=fake_complete(VALID_OUTPUT))
    processed = await run_worker_once(
        backend, session_factory, executor=executor, worker_id="worker-b"
    )
    assert processed >= 1

    async with session_factory() as session:
        task = await session.get(AgentTask, task_id)
        assert task.status == "completed"
        executions = (
            (await session.execute(select(AgentExecution).where(AgentExecution.task_id == task_id)))
            .scalars()
            .all()
        )
        assert len(executions) == 1
    pending = await backend.redis.xpending(task_queue.task_stream(), settings.task_queue_group)
    assert pending["pending"] == 0


# --------------------------------------------------------------------------- #
# Dead-lettering + LLM gateway fallback through the worker
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_worker_schema_failure_dead_letters_real_infra(pg_engine, redis_url: str) -> None:
    """Malformed LLM output is terminal: dead-letter, never retried."""
    enable_redis_queue(redis_url)
    backend = task_queue.get_queue_backend()
    session_factory = factory(pg_engine)

    async with session_factory() as session:
        agent, product_id = await seed_and_intake(session)
        await set_fast_retry(session, max_attempts=3)
        await set_execution_policy(session, agent_id=agent.id)
        task = await agent_runtime.create_task(
            session,
            workspace_id=WORKSPACE,
            data=TaskCreate(agent_id=agent.id, input={"product_id": str(product_id)}),
        )
        task_id = task.id
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)

    executor = partial(product_analyst_executor, gateway_complete=_AlwaysFailGateway())
    assert await run_worker(backend, session_factory, executor) == 1

    async with session_factory() as session:
        task = await session.get(AgentTask, task_id)
        assert task.status == "failed"
        assert task.attempt_count == 1  # invalid is terminal - no retries
        events = await _event_types(session)
        assert "agent.task_dead_letter" in events
    # Redis Streams retain XADD history by design; the correct "queue is
    # drained" signal is an empty PEL (no unacked deliveries remain).
    pending = await backend.redis.xpending(
        task_queue.task_stream(), get_settings().task_queue_group
    )
    assert pending["pending"] == 0


@pytest.mark.asyncio
async def test_worker_double_provider_failure_dead_letters_real_infra(
    pg_engine, redis_url: str
) -> None:
    """Both LLM providers failing exhausts retries and dead-letters."""
    enable_redis_queue(redis_url)
    backend = task_queue.get_queue_backend()
    session_factory = factory(pg_engine)

    async with session_factory() as session:
        agent, product_id = await seed_and_intake(session)
        await set_fast_retry(session, max_attempts=2)
        await set_execution_policy(session, agent_id=agent.id)
        task = await agent_runtime.create_task(
            session,
            workspace_id=WORKSPACE,
            data=TaskCreate(agent_id=agent.id, input={"product_id": str(product_id)}),
        )
        task_id = task.id
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)

    executor = partial(product_analyst_executor, gateway_complete=_AlwaysProviderFailGateway())
    assert await run_worker(backend, session_factory, executor, rounds=3) == 2  # 2 attempts

    async with session_factory() as session:
        task = await session.get(AgentTask, task_id)
        assert task.status == "failed"
        assert task.attempt_count == 2
        executions = (
            (await session.execute(select(AgentExecution).where(AgentExecution.task_id == task_id)))
            .scalars()
            .all()
        )
        assert len(executions) == 2  # one audit row per attempt
        assert all(execution.status == "failed" for execution in executions)
        events = await _event_types(session)
        assert "agent.task_dead_letter" in events
    # Redis Streams retain XADD history by design; the correct "queue is
    # drained" signal is an empty PEL (no unacked deliveries remain).
    pending = await backend.redis.xpending(
        task_queue.task_stream(), get_settings().task_queue_group
    )
    assert pending["pending"] == 0


@pytest.mark.asyncio
async def test_worker_llm_gateway_fallback_audit_real_infra(pg_engine, redis_url: str) -> None:
    """Real gateway: OpenAI 5xx -> DeepSeek fallback, audited end to end."""
    enable_redis_queue(redis_url)
    settings = get_settings()
    settings.openai_api_key = "test-openai-key"
    settings.deepseek_api_key = "test-deepseek-key"
    backend = task_queue.get_queue_backend()
    session_factory = factory(pg_engine)

    async with session_factory() as session:
        agent, product_id = await seed_and_intake(session)
        await set_fast_retry(session)
        await set_execution_policy(session, agent_id=agent.id)
        task = await agent_runtime.create_task(
            session,
            workspace_id=WORKSPACE,
            data=TaskCreate(agent_id=agent.id, input={"product_id": str(product_id)}),
        )
        task_id = task.id
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)

    transport = httpx.MockTransport(_openai_500_deepseek_ok)
    client = httpx.AsyncClient(transport=transport)
    from app.services import llm_gateway

    gateway = partial(llm_gateway.complete, client=client, allow_fallback=True)
    executor = partial(product_analyst_executor, gateway_complete=gateway)
    assert await run_worker(backend, session_factory, executor) >= 1
    await client.aclose()

    async with session_factory() as session:
        execution = (
            (await session.execute(select(AgentExecution).where(AgentExecution.task_id == task_id)))
            .scalars()
            .first()
        )
        assert execution.status == "completed"
        assert execution.provider == "deepseek"
        assert execution.model == "deepseek-chat"
        assert execution.tokens["total_tokens"] == 165
        assert execution.cost > Decimal("0")
        assert execution.latency_ms >= 0
        runs = (
            (
                await session.execute(
                    select(ProductAnalysisRun).where(ProductAnalysisRun.product_id == product_id)
                )
            )
            .scalars()
            .all()
        )
        llm_runs = [run for run in runs if run.provider == "deepseek"]
        assert len(llm_runs) == 1
        assert llm_runs[0].provider == "deepseek"
        assert llm_runs[0].status == "completed"
        decisions = (await session.execute(select(ProductDecision))).scalars().all()
        assert len(decisions) == 1
        assert decisions[0].approval_status == "pending"
