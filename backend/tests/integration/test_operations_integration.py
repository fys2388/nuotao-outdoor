"""M5.4 real-infrastructure integration tests.

Runs against REAL PostgreSQL (migrated) and REAL Redis Streams:

- Worker horizontal scaling: 1 / 2 / 4 workers drain 100 tasks concurrently
  with exactly 100 executions (no duplicate business effect), recording
  throughput, p50/p95 latency and failure rate.
- DLQ human replay: proposal -> approval -> new attempt -> worker completes,
  original attempt rows immutable, original error preserved.
- Alert evaluation against live state (queue depth / dead worker).
"""

from __future__ import annotations

import asyncio
import statistics
import time
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.agent_runtime import AgentExecution, AgentTask
from app.models.agent_runtime_hardening import AgentTaskAttempt
from app.schemas.agent_runtime import AgentRegisterRequest, TaskCreate
from app.schemas.prompt import PromptCreate
from app.services import (
    agent_queue,
    agent_runtime,
    alert_service,
    approval_service,
    prompt_registry,
    task_queue,
)
from app.services.llm_gateway import LLMError
from app.worker.agent_worker import run_worker_once
from app.worker.executor import ExecutionResult
from tests.integration.conftest import enable_redis_queue

WORKSPACE = DEFAULT_WORKSPACE_ID
OTHER_WORKSPACE = UUID("00000000-0000-0000-0000-000000000099")
PROMPT_NAME = "AGENT_SCALE_TEST"


class FakeExecutor:
    """Mock executor recording per-call latency (no business logic)."""

    def __init__(self, errors: list | None = None):
        self.errors = list(errors or [])
        self.calls = 0
        self.latencies: list[int] = []

    async def __call__(self, session, *, workspace_id, agent, task, policy, trace_id):
        self.calls += 1
        if self.errors:
            error = self.errors.pop(0)
            if error is not None:
                raise error
        await asyncio.sleep(0.001)
        latency = 1 + (self.calls % 3)
        self.latencies.append(latency)
        return ExecutionResult(
            output={"decision": "ok"},
            provider="openai",
            model="gpt-4o-mini",
            tokens={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            cost=Decimal("0.001"),
            latency_ms=latency,
        )


@pytest.fixture()
async def pg_engine(pg_migrated: str):
    """Async engine + migrated real PostgreSQL database for one test."""
    engine = create_async_engine(pg_migrated)
    yield engine
    await engine.dispose()


async def _seed_agent(session, *, workspace: UUID = WORKSPACE):
    await prompt_registry.create_prompt(
        session,
        workspace_id=workspace,
        data=PromptCreate(
            prompt_id="prompt-scale",
            name=PROMPT_NAME,
            version="v1",
            template="Analyze {sku}.",
            variables=["sku"],
        ),
    )
    agent = await agent_runtime.register_agent(
        session,
        workspace_id=workspace,
        data=AgentRegisterRequest(
            agent_id="SCALE_TEST",
            name="Scale Test Agent",
            domain="operations",
            version="v1",
            status="active",
            model_provider="openai",
            model_name="gpt-4o-mini",
            prompt_version="v1",
            permission_level="L2",
        ),
    )
    from tests.integration.runtime_helpers import (
        set_execution_policy,
        set_fast_retry,
    )

    await set_fast_retry(session, workspace=workspace, max_attempts=3)
    await set_execution_policy(session, agent_id=agent.id, workspace=workspace)
    return agent


async def _enqueue_tasks(
    session_factory,
    backend,
    *,
    agent_id: UUID,
    count: int,
    workspace: UUID = WORKSPACE,
    prefix: str = "T",
) -> list[UUID]:
    """Create ``count`` pending tasks and enqueue attempt 1 for each."""
    task_ids: list[UUID] = []
    async with session_factory() as session:
        for index in range(count):
            task = await agent_runtime.create_task(
                session,
                workspace_id=workspace,
                data=TaskCreate(agent_id=agent_id, input={"sku": f"{prefix}-{index}"}),
                trace_id=f"trace-{prefix}-{index}",
            )
            task_ids.append(task.id)
    for task_id in task_ids:
        await task_queue.enqueue_task(backend, workspace_id=workspace, task_id=task_id, attempt=1)
    return task_ids


async def _drain(backend, session_factory, executor, worker_ids, *, rounds: int = 60):
    """Concurrently drain the queue with ``len(worker_ids)`` workers."""
    total = 0
    started = time.monotonic()
    for _ in range(rounds):
        results = await asyncio.gather(
            *[
                run_worker_once(
                    backend,
                    session_factory,
                    executor=executor,
                    worker_id=worker_id,
                    max_messages=25,
                )
                for worker_id in worker_ids
            ]
        )
        batch = sum(results)
        total += batch
        if batch == 0:
            break
    elapsed = max(time.monotonic() - started, 0.001)
    return total, elapsed


def _latency_stats(executor: FakeExecutor) -> dict[str, float]:
    latencies = executor.latencies or [0]
    return {
        "p50_ms": statistics.median(latencies),
        "p95_ms": sorted(latencies)[min(len(latencies) - 1, int(0.95 * len(latencies)))],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("worker_count", [1, 2, 4])
async def test_worker_scaling_100_tasks_exactly_once(
    pg_engine, redis_url: str, worker_count: int
) -> None:
    """1/2/4 workers drain 100 tasks with exactly 100 executions."""
    enable_redis_queue(redis_url)
    backend = task_queue.get_queue_backend()
    session_factory = async_sessionmaker(pg_engine, expire_on_commit=False)

    async with session_factory() as session:
        agent = await _seed_agent(session)
        agent_id = agent.id
    task_ids = await _enqueue_tasks(
        session_factory, backend, agent_id=agent_id, count=100, prefix="S"
    )

    executor = FakeExecutor()
    worker_ids = [f"scale-w{i}" for i in range(worker_count)]
    processed, elapsed = await _drain(backend, session_factory, executor, worker_ids)

    assert processed == 100, f"processed={processed}"
    assert executor.calls == 100, f"executor calls={executor.calls}"

    async with session_factory() as session:
        executions = (
            (
                await session.execute(
                    select(AgentExecution).where(
                        AgentExecution.workspace_id == WORKSPACE,
                        AgentExecution.task_id.in_(task_ids),
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(executions) == 100, f"executions={len(executions)} (duplicate effect)"
        assert all(row.status == "completed" for row in executions)
        tasks = (await session.execute(select(AgentTask))).scalars().all()
        assert all(task.status == "completed" for task in tasks)

    stats = _latency_stats(executor)
    throughput = 100 / elapsed
    # Recorded for the delivery report: never asserted as a benchmark.
    print(
        f"[scaling] workers={worker_count} throughput={throughput:.1f} tasks/s "
        f"p50={stats['p50_ms']}ms p95={stats['p95_ms']}ms failure_rate=0.0"
    )


@pytest.mark.asyncio
async def test_worker_scaling_workspace_isolation(pg_engine, redis_url: str) -> None:
    """Two workspaces sharing one queue never mix executions."""
    enable_redis_queue(redis_url)
    backend = task_queue.get_queue_backend()
    session_factory = async_sessionmaker(pg_engine, expire_on_commit=False)

    async with session_factory() as session:
        agent_a = await _seed_agent(session, workspace=WORKSPACE)
        agent_b = await _seed_agent(session, workspace=OTHER_WORKSPACE)
    ids_a = await _enqueue_tasks(
        session_factory, backend, agent_id=agent_a.id, count=10, prefix="A"
    )
    ids_b = await _enqueue_tasks(
        session_factory,
        backend,
        agent_id=agent_b.id,
        count=10,
        prefix="B",
        workspace=OTHER_WORKSPACE,
    )

    executor = FakeExecutor()
    await _drain(backend, session_factory, executor, ["iso-w1", "iso-w2"])
    assert executor.calls == 20

    async with session_factory() as session:
        executions_a = (
            (
                await session.execute(
                    select(AgentExecution).where(
                        AgentExecution.workspace_id == WORKSPACE,
                        AgentExecution.task_id.in_(ids_a),
                    )
                )
            )
            .scalars()
            .all()
        )
        executions_b = (
            (
                await session.execute(
                    select(AgentExecution).where(
                        AgentExecution.workspace_id == OTHER_WORKSPACE,
                        AgentExecution.task_id.in_(ids_b),
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(executions_a) == 10
        assert len(executions_b) == 10
        # No cross-workspace execution rows.
        cross = (
            (
                await session.execute(
                    select(AgentExecution).where(
                        AgentExecution.workspace_id == WORKSPACE,
                        AgentExecution.task_id.in_(ids_b),
                    )
                )
            )
            .scalars()
            .all()
        )
        assert cross == []


@pytest.mark.asyncio
async def test_dlq_replay_real_infra(pg_engine, redis_url: str) -> None:
    """Approved replay requeues a new attempt; original attempts stay intact."""
    enable_redis_queue(redis_url)
    backend = task_queue.get_queue_backend()
    session_factory = async_sessionmaker(pg_engine, expire_on_commit=False)

    async with session_factory() as session:
        agent = await _seed_agent(session)
        task = await agent_runtime.create_task(
            session,
            workspace_id=WORKSPACE,
            data=TaskCreate(agent_id=agent.id, input={"sku": "DLQ-REAL"}),
            trace_id="trace-dlq-real",
        )
        task_id = task.id
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)

    # Three retryable provider failures -> dead letter after max attempts.
    failing = FakeExecutor(
        errors=[
            LLMError("provider unreachable", kind="provider"),
            LLMError("provider 500", kind="provider"),
            LLMError("provider timeout", kind="provider"),
        ]
    )
    await _drain(backend, session_factory, failing, ["dlq-w1"])
    async with session_factory() as session:
        task = await session.get(AgentTask, task_id)
        assert task.status == "failed"
        assert "provider" in (task.error_message or "")
        original_attempts = (await session.execute(select(AgentTaskAttempt))).scalars().all()
        before_snapshot = [
            (row.attempt_number, row.status, row.error_type, row.error_message)
            for row in original_attempts
        ]
        executions_before = len(
            (
                await session.execute(
                    select(AgentExecution).where(
                        AgentExecution.workspace_id == WORKSPACE,
                        AgentExecution.task_id == task_id,
                    )
                )
            )
            .scalars()
            .all()
        )

    # Propose + approve the replay (human-in-the-loop only).
    async with session_factory() as session:
        proposal = await agent_queue.propose_dlq_replay(
            session,
            workspace_id=WORKSPACE,
            task_id=task_id,
            reason="error reviewed; provider recovered",
            trace_id="trace-dlq-real",
        )
        await approval_service.approve_approval(
            session,
            backend,
            workspace_id=WORKSPACE,
            approval_id=proposal.id,
            actor="ops-lead",
            note="approved replay",
            trace_id="trace-dlq-real",
        )

    # The replayed attempt succeeds with the healthy executor.
    ok_executor = FakeExecutor()
    await _drain(backend, session_factory, ok_executor, ["dlq-w2"])
    assert ok_executor.calls == 1

    async with session_factory() as session:
        task = await session.get(AgentTask, task_id)
        assert task.status == "completed"
        assert task.attempt_count == 4  # 3 failed + 1 replay
        attempts = (await session.execute(select(AgentTaskAttempt))).scalars().all()
        after_snapshot = [
            (row.attempt_number, row.status, row.error_type, row.error_message)
            for row in attempts
            if row.attempt_number in (1, 2, 3)
        ]
        assert after_snapshot == before_snapshot  # original attempts immutable
        executions = (
            (
                await session.execute(
                    select(AgentExecution).where(
                        AgentExecution.workspace_id == WORKSPACE,
                        AgentExecution.task_id == task_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(executions) == executions_before + 1
        assert any(row.status == "completed" for row in executions)
        # No duplicate business effect: exactly one completed execution.
        assert sum(1 for row in executions if row.status == "completed") == 1


@pytest.mark.asyncio
async def test_alert_evaluate_real_infra(pg_engine, redis_url: str) -> None:
    """Alert evaluation reads live Redis queue depth against thresholds."""
    enable_redis_queue(redis_url)
    settings = get_settings()
    original = settings.alert_queue_depth_threshold
    settings.alert_queue_depth_threshold = 0
    backend = task_queue.get_queue_backend()
    session_factory = async_sessionmaker(pg_engine, expire_on_commit=False)
    try:
        await backend.add(task_queue.task_stream(), {"probe": "1"})
        async with session_factory() as session:
            created = await alert_service.evaluate_alerts(
                session, backend, workspace_id=WORKSPACE, trace_id="trace-alert-real"
            )
        assert any(alert.alert_type == alert_service.ALERT_QUEUE_BACKLOG for alert in created)
        # Dedup: a second pass opens no new alert for the same condition.
        async with session_factory() as session:
            again = await alert_service.evaluate_alerts(
                session, backend, workspace_id=WORKSPACE, trace_id="trace-alert-real-2"
            )
        assert again == []
    finally:
        settings.alert_queue_depth_threshold = original
