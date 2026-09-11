"""M5.3 real-infrastructure observability & exactly-once tests.

Runs against REAL PostgreSQL (migrated) and REAL Redis Streams:

- message-level dedup: duplicate XADD / concurrent delivery / crash reclaim
  never produce a second business execution (effectively-once);
- worker registry + heartbeat + dead detection on real Redis;
- retry attempts increment with distinct dedup identity;
- DLQ is queryable but never replayed by a normal worker;
- workspace isolation for dedup and observability queries.

Runtime observability tests may use a mock executor; the transport, queue and
database are all real.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.agent_runtime import AgentExecution, AgentTask
from app.models.event import EventLog
from app.schemas.agent_runtime import TaskCreate
from app.services import agent_queue, agent_runtime, agent_workers, task_queue
from app.services.llm_gateway import LLMError
from app.worker.agent_worker import process_message, run_worker_once
from app.worker.executor import ExecutionResult
from tests.integration.conftest import enable_redis_queue
from tests.integration.runtime_helpers import (
    factory,
    run_worker,
    seed_and_intake,
    set_execution_policy,
    set_fast_retry,
)

WORKSPACE = DEFAULT_WORKSPACE_ID
OTHER_WORKSPACE = UUID("00000000-0000-0000-0000-000000000099")


class FakeExecutor:
    """Mock executor for runtime observability (no business logic)."""

    def __init__(self, errors: list | None = None):
        self.errors = list(errors or [])
        self.calls = 0

    async def __call__(self, session, *, workspace_id, agent, task, policy, trace_id):
        self.calls += 1
        if self.errors:
            error = self.errors.pop(0)
            if error is not None:
                raise error
        return ExecutionResult(
            output={"decision": "test"},
            provider="openai",
            model="gpt-4o-mini",
            tokens={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            cost=Decimal("0.001"),
            latency_ms=5,
        )


@pytest.fixture()
async def pg_engine(pg_migrated: str):
    """Async engine + migrated real PostgreSQL database for one test."""
    engine = create_async_engine(pg_migrated)
    yield engine
    await engine.dispose()


async def _event_types(session) -> set[str]:
    rows = (await session.execute(select(EventLog.event_type))).scalars().all()
    return set(rows)


async def _seed_agent(session, *, workspace: UUID = WORKSPACE):
    agent, _product_id = await seed_and_intake(session, workspace=workspace)
    await set_fast_retry(session, workspace=workspace, max_attempts=3)
    await set_execution_policy(session, agent_id=agent.id, workspace=workspace)
    return agent


# --------------------------------------------------------------------------- #
# 1. Message dedup on real Redis + real PostgreSQL
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_redis_duplicate_xadd_executes_once(pg_engine, redis_url: str) -> None:
    """Two XADDs of the same (task, attempt) produce one execution."""
    enable_redis_queue(redis_url)
    backend = task_queue.get_queue_backend()
    session_factory = factory(pg_engine)

    async with session_factory() as session:
        agent = await _seed_agent(session)
        task = await agent_runtime.create_task(
            session,
            workspace_id=WORKSPACE,
            data=TaskCreate(agent_id=agent.id, input={"sku": "dup"}),
        )
        task_id = task.id
    # Producer retry: the same attempt is XADDed twice.
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)

    executor = FakeExecutor()
    processed = await run_worker(backend, session_factory, executor, rounds=3)
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
        assert executor.calls == 1
        events = await _event_types(session)
        assert "agent.queue.message_skipped" in events
    pending = await backend.redis.xpending(
        task_queue.task_stream(), get_settings().task_queue_group
    )
    assert pending["pending"] == 0


@pytest.mark.asyncio
async def test_redis_crash_reclaim_with_dedup_token(pg_engine, redis_url: str) -> None:
    """A crashed worker's token is stolen after reclaim; one execution only."""
    enable_redis_queue(redis_url)
    settings = get_settings()
    settings.task_queue_reclaim_idle_ms = 0  # immediate reclaim + token steal
    backend = task_queue.get_queue_backend()
    session_factory = factory(pg_engine)

    async with session_factory() as session:
        agent = await _seed_agent(session)
        task = await agent_runtime.create_task(
            session,
            workspace_id=WORKSPACE,
            data=TaskCreate(agent_id=agent.id, input={"sku": "crash"}),
        )
        task_id = task.id
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)

    # Worker A claims the message AND the dedup token, then "crashes" before
    # executing or acking (the PEL entry is left behind).
    claimed = await backend.read_group(
        task_queue.task_stream(),
        settings.task_queue_group,
        "worker-a",
        count=1,
        block_ms=0,
    )
    assert len(claimed) == 1
    dedup_key = claimed[0].fields[task_queue.FIELD_DEDUP_KEY]
    assert (
        await backend.dedup_claim(
            dedup_key,
            ttl_seconds=settings.task_queue_dedup_ttl_seconds,
            stale_after_seconds=settings.task_queue_reclaim_idle_ms / 1000.0,
        )
        is True
    )

    # Worker B reclaims via XAUTOCLAIM; the stale token is stealable, the DB
    # task row is still pending -> one execution.
    executor = FakeExecutor()
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
        assert executor.calls == 1
    pending = await backend.redis.xpending(task_queue.task_stream(), settings.task_queue_group)
    assert pending["pending"] == 0


@pytest.mark.asyncio
async def test_redis_completed_task_redelivery_skipped(pg_engine, redis_url: str) -> None:
    """A completed task's redelivered message is acked and never re-executed."""
    enable_redis_queue(redis_url)
    backend = task_queue.get_queue_backend()
    session_factory = factory(pg_engine)

    async with session_factory() as session:
        agent = await _seed_agent(session)
        task = await agent_runtime.create_task(
            session,
            workspace_id=WORKSPACE,
            data=TaskCreate(agent_id=agent.id, input={"sku": "redeliver"}),
        )
        task_id = task.id
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)
    assert await run_worker(backend, session_factory, FakeExecutor()) >= 1

    # The same message (same attempt) is redelivered - e.g. PEL redelivery
    # after the token TTL expired. The DB guard deduplicates.
    dedup_key = task_queue.build_dedup_key(workspace_id=WORKSPACE, task_id=task_id, attempt=1)
    await backend.dedup_release(dedup_key)
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)
    messages = await backend.read_group(
        task_queue.task_stream(),
        get_settings().task_queue_group,
        "test",
        count=1,
        block_ms=0,
    )
    assert len(messages) == 1
    executor = FakeExecutor()
    outcome = await process_message(backend, session_factory, messages[0], executor=executor)
    assert outcome == "skipped"
    assert executor.calls == 0
    async with session_factory() as session:
        executions = (
            (await session.execute(select(AgentExecution).where(AgentExecution.task_id == task_id)))
            .scalars()
            .all()
        )
        assert len(executions) == 1


@pytest.mark.asyncio
async def test_redis_retry_attempt_increments_with_distinct_dedup(
    pg_engine, redis_url: str
) -> None:
    """A retried attempt gets a distinct dedup identity and runs once."""
    enable_redis_queue(redis_url)
    backend = task_queue.get_queue_backend()
    session_factory = factory(pg_engine)

    async with session_factory() as session:
        agent = await _seed_agent(session)
        task = await agent_runtime.create_task(
            session,
            workspace_id=WORKSPACE,
            data=TaskCreate(agent_id=agent.id, input={"sku": "retry"}),
        )
        task_id = task.id
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)
    executor = FakeExecutor(errors=[LLMError("provider boom", kind="provider")])
    assert await run_worker(backend, session_factory, executor, rounds=4) >= 1

    async with session_factory() as session:
        task = await session.get(AgentTask, task_id)
        assert task.status == "completed"
        assert task.attempt_count == 2
        executions = (
            (await session.execute(select(AgentExecution).where(AgentExecution.task_id == task_id)))
            .scalars()
            .all()
        )
        assert len(executions) == 2  # one per attempt, never duplicated
        assert {row.attempt_number for row in executions} == {1, 2}
        events = await _event_types(session)
        assert "agent.queue.retry_scheduled" in events
    pending = await backend.redis.xpending(
        task_queue.task_stream(), get_settings().task_queue_group
    )
    assert pending["pending"] == 0


# --------------------------------------------------------------------------- #
# 2. Worker registry / heartbeat on real Redis
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_redis_worker_heartbeat_and_dead_detection(redis_url: str) -> None:
    enable_redis_queue(redis_url)
    backend = task_queue.get_queue_backend()
    runtime = agent_workers.WorkerRuntime(backend=backend, worker_id="redis-worker-1")
    await runtime.start()
    await runtime.beat(status=agent_workers.WORKER_IDLE)

    workers = await agent_workers.list_workers(backend)
    assert len(workers) == 1
    assert workers[0]["worker_id"] == "redis-worker-1"
    assert workers[0]["is_dead"] is False

    # A heartbeat timeout of 0 marks the worker dead (config-driven).
    settings = get_settings()
    settings.worker_heartbeat_timeout_seconds = 0
    workers = await agent_workers.list_workers(backend)
    assert workers[0]["is_dead"] is True
    assert workers[0]["status"] == agent_workers.WORKER_DEAD


# --------------------------------------------------------------------------- #
# 3. DLQ + observability queries on real infra
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_redis_dlq_queryable_and_not_replayed(pg_engine, redis_url: str) -> None:
    """A dead-lettered task is visible to queries and never re-executed."""
    enable_redis_queue(redis_url)
    backend = task_queue.get_queue_backend()
    session_factory = factory(pg_engine)

    async with session_factory() as session:
        agent = await _seed_agent(session)
        await set_fast_retry(session, max_attempts=1)  # dead-letter on failure
        task = await agent_runtime.create_task(
            session,
            workspace_id=WORKSPACE,
            data=TaskCreate(agent_id=agent.id, input={"sku": "dlq"}),
        )
        task_id = task.id
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)
    executor = FakeExecutor(errors=[LLMError("provider boom", kind="provider")])
    assert await run_worker(backend, session_factory, executor, rounds=2) >= 1

    async with session_factory() as session:
        task = await session.get(AgentTask, task_id)
        assert task.status == "failed"
        items, total = await agent_queue.list_dead_letters(
            session, workspace_id=WORKSPACE, task_id=task_id
        )
        assert total == 1
        assert items[0]["error_type"] == "llm"

    # A normal worker pass must NOT re-execute the failed task.
    assert await run_worker(backend, session_factory, FakeExecutor(), rounds=2) == 0
    async with session_factory() as session:
        executions = (
            (await session.execute(select(AgentExecution).where(AgentExecution.task_id == task_id)))
            .scalars()
            .all()
        )
        assert len(executions) == 1
        events = await _event_types(session)
        assert "agent.queue.dead_lettered" in events


@pytest.mark.asyncio
async def test_redis_dedup_and_observability_workspace_isolation(pg_engine, redis_url: str) -> None:
    """Workspace A's dedup/state never leaks into workspace B."""
    enable_redis_queue(redis_url)
    backend = task_queue.get_queue_backend()
    session_factory = factory(pg_engine)

    async with session_factory() as session:
        agent_a = await _seed_agent(session, workspace=WORKSPACE)
        agent_b = await _seed_agent(session, workspace=OTHER_WORKSPACE)
        task_a = await agent_runtime.create_task(
            session,
            workspace_id=WORKSPACE,
            data=TaskCreate(agent_id=agent_a.id, input={"sku": "ws-a"}),
        )
        task_b = await agent_runtime.create_task(
            session,
            workspace_id=OTHER_WORKSPACE,
            data=TaskCreate(agent_id=agent_b.id, input={"sku": "ws-b"}),
        )
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_a.id, attempt=1)
    await task_queue.enqueue_task(
        backend, workspace_id=OTHER_WORKSPACE, task_id=task_b.id, attempt=1
    )
    executor = FakeExecutor()
    await run_worker(backend, session_factory, executor, rounds=3)

    async with session_factory() as session:
        for task_id in (task_a.id, task_b.id):
            task = await session.get(AgentTask, task_id)
            assert task.status == "completed"
        dlq_a, total_a = await agent_queue.list_dead_letters(session, workspace_id=WORKSPACE)
        dlq_b, total_b = await agent_queue.list_dead_letters(session, workspace_id=OTHER_WORKSPACE)
        assert total_a == 0 and total_b == 0
        stats_a = await agent_queue.queue_stats(session, backend, workspace_id=WORKSPACE)
        stats_b = await agent_queue.queue_stats(session, backend, workspace_id=OTHER_WORKSPACE)
        assert stats_a["pending_count"] == 0
        assert stats_b["pending_count"] == 0


@pytest.mark.asyncio
async def test_redis_queue_stats_and_health_live(pg_engine, redis_url: str) -> None:
    """Stats/health are computed from live Redis + PostgreSQL state."""
    enable_redis_queue(redis_url)
    backend = task_queue.get_queue_backend()
    session_factory = factory(pg_engine)

    async with session_factory() as session:
        agent = await _seed_agent(session)
        task = await agent_runtime.create_task(
            session,
            workspace_id=WORKSPACE,
            data=TaskCreate(agent_id=agent.id, input={"sku": "stats"}),
        )
        task_id = task.id
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)
    await run_worker(backend, session_factory, FakeExecutor(), rounds=2)

    async with session_factory() as session:
        stats = await agent_queue.queue_stats(session, backend, workspace_id=WORKSPACE)
        assert stats["backend"] == "redis"
        assert stats["pending_count"] == 0
        assert stats["dead_letter_count"] == 0
        assert stats["success_rate"] == 1.0
        health = await agent_queue.queue_health(session, backend, workspace_id=WORKSPACE)
        assert health["status"] in ("healthy", "degraded")
        assert health["checks"]["redis"] == "ok"
        assert health["checks"]["stream"] == "ok"
        assert health["checks"]["consumer_group"] == "ok"
