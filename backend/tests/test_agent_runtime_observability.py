"""M5.3 Agent Runtime observability & exactly-once hardening tests.

Covers (memory queue backend): stable message dedup identity, duplicate /
concurrent delivery dedup, crash reclaim without double execution, worker
registry + heartbeat + dead detection, queue stats / health computed from
live state, read-only DLQ queries, full-chain trace queries, workspace
isolation and the new API surfaces. Delivery semantics asserted here:
Redis transport = at-least-once, DB business effect = effectively-once.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import get_settings
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.agent_runtime import AgentExecution, AgentRegistry, AgentTask
from app.models.agent_runtime_hardening import AgentTaskAttempt
from app.models.event import EventLog
from app.schemas.agent_runtime import AgentRegisterRequest, TaskCreate
from app.schemas.prompt import PromptCreate
from app.services import (
    agent_queue,
    agent_runtime,
    agent_workers,
    prompt_registry,
    retry_engine,
    task_queue,
)
from app.services.llm_gateway import LLMError
from app.services.task_queue import MemoryStreamBackend
from app.worker.agent_worker import process_message, run_worker_once
from app.worker.executor import ExecutionResult

WORKSPACE = DEFAULT_WORKSPACE_ID
OTHER_WORKSPACE = UUID("00000000-0000-0000-0000-000000000099")


def _factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


async def _seed_prompt(session, workspace: UUID = WORKSPACE) -> None:
    await prompt_registry.create_prompt(
        session,
        workspace_id=workspace,
        data=PromptCreate(
            prompt_id="prompt-obs",
            name="AGENT_OBS_ANALYST",
            version="v1",
            template="You are a {role} analyzing product {sku}.",
            variables=["role", "sku"],
        ),
    )


async def _seed_agent_row(
    session,
    *,
    agent_id: str = "OBS_ANALYST",
    workspace: UUID = WORKSPACE,
) -> AgentRegistry:
    await _seed_prompt(session, workspace=workspace)
    return await agent_runtime.register_agent(
        session,
        workspace_id=workspace,
        data=AgentRegisterRequest(
            agent_id=agent_id,
            name="Observability Test Analyst",
            domain="product",
            version="v1",
            status="active",
            model_provider="openai",
            model_name="gpt-4o-mini",
            prompt_version="v1",
            permission_level="L2",
        ),
    )


async def _create_task(session, *, workspace: UUID = WORKSPACE, agent_id: str = "OBS_ANALYST"):
    agent = await _seed_agent_row(session, workspace=workspace)
    task = await agent_runtime.create_task(
        session,
        workspace_id=workspace,
        data=TaskCreate(agent_id=agent.id, input={"sku": "S"}),
    )
    return task.id


class FakeExecutor:
    """Deterministic executor: fails ``errors`` times then succeeds."""

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
            output={"decision": "ok"},
            provider="openai",
            model="gpt-4o-mini",
            tokens={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            cost=Decimal("0.001"),
            latency_ms=5,
        )


# --------------------------------------------------------------------------- #
# 1. Message-level dedup identity
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_dedup_key_is_stable_and_never_random() -> None:
    key_a = task_queue.build_dedup_key(workspace_id=WORKSPACE, task_id=UUID("1" * 32), attempt=1)
    key_b = task_queue.build_dedup_key(workspace_id=WORKSPACE, task_id=UUID("1" * 32), attempt=1)
    assert key_a == key_b  # stable across producer retries
    attempt_2 = task_queue.build_dedup_key(
        workspace_id=WORKSPACE, task_id=UUID("1" * 32), attempt=2
    )
    assert attempt_2 != key_a  # retries stay distinct
    other_ws = task_queue.build_dedup_key(
        workspace_id=OTHER_WORKSPACE, task_id=UUID("1" * 32), attempt=1
    )
    assert other_ws != key_a  # workspace isolation


@pytest.mark.asyncio
async def test_dedup_key_prefers_idempotency_key() -> None:
    key = task_queue.build_dedup_key(
        workspace_id=WORKSPACE,
        task_id=UUID("2" * 32),
        attempt=1,
        idempotency_key="idem-x",
    )
    assert "idem-x" in key
    assert ":idem:" in key
    # A different task id with the SAME idempotency key collapses to the same
    # dedup identity (producer retries may produce a new UUID, never twice).
    same = task_queue.build_dedup_key(
        workspace_id=WORKSPACE,
        task_id=UUID("3" * 32),
        attempt=1,
        idempotency_key="idem-x",
    )
    assert key == same


@pytest.mark.asyncio
async def test_dedup_claim_concurrent_only_one_wins() -> None:
    backend = MemoryStreamBackend()
    key = "dedup:concurrent:1"
    assert await backend.dedup_claim(key, ttl_seconds=900, stale_after_seconds=60) is True
    assert await backend.dedup_claim(key, ttl_seconds=900, stale_after_seconds=60) is False
    # release lets a retry of the same attempt claim again (defer path)
    await backend.dedup_release(key)
    assert await backend.dedup_claim(key, ttl_seconds=900, stale_after_seconds=60) is True


@pytest.mark.asyncio
async def test_dedup_claim_stale_token_stealable() -> None:
    backend = MemoryStreamBackend()
    key = "dedup:stale:1"
    assert await backend.dedup_claim(key, ttl_seconds=900, stale_after_seconds=60) is True
    # The claim is fresh -> not stealable yet.
    assert await backend.dedup_claim(key, ttl_seconds=900, stale_after_seconds=60) is False
    # With a zero stale threshold the token is treated as orphaned (crashed
    # worker) and becomes stealable, mirroring XAUTOCLAIM recovery.
    assert await backend.dedup_claim(key, ttl_seconds=900, stale_after_seconds=0) is True


# --------------------------------------------------------------------------- #
# 2. Dedup through the worker (memory backend)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_duplicate_delivery_executes_once(db_engine) -> None:
    backend = task_queue.get_queue_backend()
    factory = _factory(db_engine)
    async with factory() as session:
        task_id = await _create_task(session)
    # Producer retry / duplicate XADD: the same attempt is enqueued twice.
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)

    executor = FakeExecutor()
    await run_worker_once(backend, factory, executor=executor)
    await run_worker_once(backend, factory, executor=executor)

    async with factory() as session:
        task = await session.get(AgentTask, task_id)
        assert task.status == "completed"
        executions = (
            (await session.execute(select(AgentExecution).where(AgentExecution.task_id == task_id)))
            .scalars()
            .all()
        )
        assert len(executions) == 1  # exactly-once business effect
        assert executor.calls == 1
        events = {
            row.event_type for row in (await session.execute(select(EventLog))).scalars().all()
        }
        assert "agent.queue.message_skipped" in events


@pytest.mark.asyncio
async def test_completed_task_redelivery_skipped_via_db_guard(db_engine) -> None:
    """Token absent (TTL expired) -> the DB task row deduplicates."""
    backend = task_queue.get_queue_backend()
    factory = _factory(db_engine)
    async with factory() as session:
        task_id = await _create_task(session)
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)
    await run_worker_once(backend, factory, executor=FakeExecutor())

    # Release the dedup token (simulates TTL expiry) so the redelivery
    # exercises the DB task-row guard instead of the Redis token.
    dedup_key = task_queue.build_dedup_key(workspace_id=WORKSPACE, task_id=task_id, attempt=1)
    await backend.dedup_release(dedup_key)
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)

    # Read + process the redelivered message directly.
    messages = await backend.read_group(
        task_queue.task_stream(),
        get_settings().task_queue_group,
        "test",
        count=1,
        block_ms=0,
    )
    assert len(messages) == 1
    executor = FakeExecutor()
    result = await process_message(backend, factory, messages[0], executor=executor)
    assert result == "skipped"
    assert executor.calls == 0
    async with factory() as session:
        events = {
            row.event_type for row in (await session.execute(select(EventLog))).scalars().all()
        }
        assert "agent.queue.message_deduplicated" in events


@pytest.mark.asyncio
async def test_retry_attempts_have_distinct_dedup_identity(db_engine) -> None:
    backend = task_queue.get_queue_backend()
    factory = _factory(db_engine)
    async with factory() as session:
        task_id = await _create_task(session)
        await _set_fast_retry(session)
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)
    executor = FakeExecutor(errors=[LLMError("provider boom", kind="provider")])
    await run_worker_once(backend, factory, executor=executor)
    assert await backend.delayed_count(task_queue.retry_key()) == 1
    await run_worker_once(backend, factory, executor=executor)
    async with factory() as session:
        task = await session.get(AgentTask, task_id)
        assert task.status == "completed"
        assert task.attempt_count == 2
        attempts = (await session.execute(select(AgentTaskAttempt))).scalars().all()
        assert {row.attempt_number for row in attempts} == {1, 2}
        events = {
            row.event_type for row in (await session.execute(select(EventLog))).scalars().all()
        }
        assert "agent.queue.retry_scheduled" in events


async def _set_fast_retry(session) -> None:
    from app.services import agent_policies

    await agent_policies.set_retry_policy(
        session,
        workspace_id=WORKSPACE,
        retry_policy_id="standard",
        name="Instant (test)",
        max_attempts=3,
        backoff_base_seconds=0,
        backoff_multiplier=Decimal("2"),
        max_backoff_seconds=5,
        retry_on_error_types=["llm", "network", "timeout", "transient"],
        enabled=True,
    )


async def _set_no_retry(session) -> None:
    """Dead-letter on the first failure (no automatic retry)."""
    from app.services import agent_policies

    await agent_policies.set_retry_policy(
        session,
        workspace_id=WORKSPACE,
        retry_policy_id="standard",
        name="No retry (test)",
        max_attempts=1,
        backoff_base_seconds=0,
        backoff_multiplier=Decimal("2"),
        max_backoff_seconds=5,
        retry_on_error_types=["llm", "network", "timeout", "transient"],
        enabled=True,
    )


@pytest.mark.asyncio
async def test_crash_reclaim_steals_stale_token_no_double_execution(db_engine) -> None:
    """A crashed worker's token becomes stealable (XAUTOCLAIM recovery)."""
    settings = get_settings()
    settings.task_queue_reclaim_idle_ms = 0  # force immediate reclaim/steal
    backend = task_queue.get_queue_backend()
    factory = _factory(db_engine)
    async with factory() as session:
        task_id = await _create_task(session)
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)

    # Worker A claims the message-level token, then "crashes" before the DB
    # guard / execution (the PEL entry is left unacked).
    messages = await backend.read_group(
        task_queue.task_stream(), settings.task_queue_group, "worker-a", count=1, block_ms=0
    )
    assert len(messages) == 1
    dedup_key = messages[0].fields[task_queue.FIELD_DEDUP_KEY]
    assert (
        await backend.dedup_claim(
            dedup_key,
            ttl_seconds=900,
            stale_after_seconds=settings.task_queue_reclaim_idle_ms / 1000,
        )
        is True
    )

    # Worker B reclaims (XAUTOCLAIM) and reprocesses the same message.
    executor = FakeExecutor()
    processed = await run_worker_once(backend, factory, executor=executor, worker_id="worker-b")
    assert processed >= 1
    async with factory() as session:
        task = await session.get(AgentTask, task_id)
        assert task.status == "completed"
        executions = (
            (await session.execute(select(AgentExecution).where(AgentExecution.task_id == task_id)))
            .scalars()
            .all()
        )
        assert len(executions) == 1
        assert executor.calls == 1


@pytest.mark.asyncio
async def test_dedup_workspace_isolation_through_worker(db_engine) -> None:
    backend = task_queue.get_queue_backend()
    factory = _factory(db_engine)
    async with factory() as session:
        task_a = await _create_task(session, workspace=WORKSPACE)
        task_b = await _create_task(session, workspace=OTHER_WORKSPACE)
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_a, attempt=1)
    await task_queue.enqueue_task(backend, workspace_id=OTHER_WORKSPACE, task_id=task_b, attempt=1)
    await run_worker_once(backend, factory, executor=FakeExecutor(), max_messages=2)
    async with factory() as session:
        for task_id in (task_a, task_b):
            task = await session.get(AgentTask, task_id)
            assert task.status == "completed"


# --------------------------------------------------------------------------- #
# 3. Worker registry / heartbeat
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_worker_runtime_registers_and_heartbeats(db_engine) -> None:
    backend = task_queue.get_queue_backend()
    factory = _factory(db_engine)
    runtime = agent_workers.WorkerRuntime(backend=backend, worker_id="obs-worker-1")
    async with factory() as session:
        await runtime.start(session=session)
        await runtime.beat(session=session)
    workers = await agent_workers.list_workers(backend)
    assert len(workers) == 1
    assert workers[0]["worker_id"] == "obs-worker-1"
    assert workers[0]["is_dead"] is False
    assert workers[0]["status"] == agent_workers.WORKER_IDLE


@pytest.mark.asyncio
async def test_worker_dead_detection_threshold_configurable(db_engine) -> None:
    settings = get_settings()
    settings.worker_heartbeat_timeout_seconds = 0  # any worker is dead now
    backend = task_queue.get_queue_backend()
    factory = _factory(db_engine)
    runtime = agent_workers.WorkerRuntime(backend=backend, worker_id="obs-dead-1")
    async with factory() as session:
        await runtime.start(session=session)
    workers = await agent_workers.list_workers(backend)
    assert workers[0]["is_dead"] is True
    assert workers[0]["status"] == agent_workers.WORKER_DEAD


@pytest.mark.asyncio
async def test_worker_runtime_counts_processed_and_failed(db_engine) -> None:
    backend = task_queue.get_queue_backend()
    factory = _factory(db_engine)
    async with factory() as session:
        task_id = await _create_task(session)
        await _set_fast_retry(session)
    runtime = agent_workers.WorkerRuntime(backend=backend, worker_id="obs-counter")
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)
    await run_worker_once(backend, factory, executor=FakeExecutor(), runtime=runtime)
    workers = await agent_workers.list_workers(backend)
    assert workers[0]["processed_count"] == 1
    assert workers[0]["current_task_id"] in (None, "")


# --------------------------------------------------------------------------- #
# 4. Queue stats / health (computed from live state, never hardcoded)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_queue_stats_computed_from_live_state(db_engine) -> None:
    backend = task_queue.get_queue_backend()
    factory = _factory(db_engine)
    async with factory() as session:
        pending_id = await _create_task(session)
        # One completed execution within the stats window.
        agent = (
            (
                await session.execute(
                    select(AgentRegistry).where(
                        AgentRegistry.workspace_id == WORKSPACE,
                        AgentRegistry.agent_id == "OBS_ANALYST",
                    )
                )
            )
            .scalars()
            .first()
        )
        done_task = await agent_runtime.create_task(
            session,
            workspace_id=WORKSPACE,
            data=TaskCreate(agent_id=agent.id, input={"sku": "done"}),
        )
        execution = await agent_runtime.start_execution(
            session, workspace_id=WORKSPACE, task_id=done_task.id
        )
        await agent_runtime.complete_execution(
            session,
            workspace_id=WORKSPACE,
            execution_id=execution.id,
            output={"decision": "ok"},
            provider="openai",
            model="gpt-4o-mini",
            tokens={"total_tokens": 15},
            cost=Decimal("0.001"),
            latency_ms=5,
        )
        await _set_fast_retry(session)
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=pending_id, attempt=1)
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=done_task.id, attempt=1)

    async with factory() as session:
        stats = await agent_queue.queue_stats(session, backend, workspace_id=WORKSPACE)
        assert stats["backend"] == "memory"
        assert stats["queue_depth"] == stats["stream_length"] >= 2
        assert stats["pending_count"] >= 1
        assert stats["dead_letter_count"] == 0
        assert stats["success_rate"] == 1.0
        assert stats["failure_rate"] == 0.0
        assert stats["throughput_per_minute"] > 0
        assert stats["oldest_pending_age_ms"] is not None


@pytest.mark.asyncio
async def test_queue_health_healthy_when_clean(db_engine) -> None:
    backend = task_queue.get_queue_backend()
    factory = _factory(db_engine)
    async with factory() as session:
        result = await agent_queue.queue_health(session, backend, workspace_id=WORKSPACE)
        assert result["status"] == "healthy"
        assert result["checks"]["redis"] == "ok"
        assert result["checks"]["stream"] == "ok"
        assert result["checks"]["workers"] == "ok"
        assert result["checks"]["dead_letter"] == "ok"


@pytest.mark.asyncio
async def test_queue_health_degraded_on_dead_worker(db_engine) -> None:
    settings = get_settings()
    settings.worker_heartbeat_timeout_seconds = 0
    backend = task_queue.get_queue_backend()
    factory = _factory(db_engine)
    runtime = agent_workers.WorkerRuntime(backend=backend, worker_id="obs-sick-1")
    async with factory() as session:
        await runtime.start(session=session)
        await _set_fast_retry(session)
        result = await agent_queue.queue_health(session, backend, workspace_id=WORKSPACE)
        assert result["status"] == "degraded"
        assert result["checks"]["workers"] == "degraded"
        events = {
            row.event_type for row in (await session.execute(select(EventLog))).scalars().all()
        }
        assert "agent.queue.worker_dead" in events


# --------------------------------------------------------------------------- #
# 5. DLQ query (read-only)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_dead_letters_query_filters_and_paginates(db_engine) -> None:
    backend = task_queue.get_queue_backend()
    factory = _factory(db_engine)
    async with factory() as session:
        task_id = await _create_task(session)
        await _set_no_retry(session)
        agent = (
            (
                await session.execute(
                    select(AgentRegistry).where(
                        AgentRegistry.workspace_id == WORKSPACE,
                        AgentRegistry.agent_id == "OBS_ANALYST",
                    )
                )
            )
            .scalars()
            .first()
        )
        other_task = await agent_runtime.create_task(
            session,
            workspace_id=WORKSPACE,
            data=TaskCreate(agent_id=agent.id, input={"sku": "other"}),
        )
    # task_id dead-letters via terminal failure; other_task via a different
    # error class (schema).
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)
    await run_worker_once(
        backend,
        factory,
        executor=FakeExecutor(errors=[LLMError("provider boom", kind="provider")]),
        max_messages=2,
    )
    async with factory() as session:
        await _fail_with_error(session, task_id=other_task.id, error_type="schema")
    async with factory() as session:
        items, total = await agent_queue.list_dead_letters(
            session, workspace_id=WORKSPACE, limit=50, offset=0
        )
        assert total == 2
        by_id = {item["task_id"]: item for item in items}
        assert by_id[task_id]["error_type"] == "llm"
        assert by_id[other_task.id]["error_type"] == "schema"
        schema_only, schema_total = await agent_queue.list_dead_letters(
            session, workspace_id=WORKSPACE, error_type="schema"
        )
        assert schema_total == 1
        assert schema_only[0]["task_id"] == other_task.id
        page, page_total = await agent_queue.list_dead_letters(
            session, workspace_id=WORKSPACE, limit=1, offset=0
        )
        assert len(page) == 1
        assert page_total == 2


async def _fail_with_error(session, *, task_id: UUID, error_type: str) -> None:
    task = await session.get(AgentTask, task_id)
    task.status = "failed"
    task.error_message = f"{error_type} failure"
    task.completed_at = datetime.now(UTC)
    execution = AgentExecution(
        workspace_id=WORKSPACE,
        task_id=task_id,
        status="failed",
        error_type=error_type,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )
    session.add(execution)
    await session.commit()


# --------------------------------------------------------------------------- #
# 6. Full-chain trace query
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_trace_query_returns_full_chain_and_404(db_engine, api_client) -> None:
    factory = _factory(db_engine)
    trace_id = "trace-obs-001"
    async with factory() as session:
        agent = await _seed_agent_row(session)
        task = await agent_runtime.create_task(
            session,
            workspace_id=WORKSPACE,
            data=TaskCreate(agent_id=agent.id, input={"sku": "S"}),
            trace_id=trace_id,
        )
        execution = await agent_runtime.start_execution(
            session, workspace_id=WORKSPACE, task_id=task.id, trace_id=trace_id
        )
        execution.worker_id = "obs-worker"
        await retry_engine.record_attempt(
            session,
            workspace_id=WORKSPACE,
            task_id=task.id,
            attempt_number=1,
            status=retry_engine.ATTEMPT_SUCCEEDED,
            execution_id=execution.id,
            worker_id="obs-worker",
            trace_id=trace_id,
        )
        await agent_runtime.complete_execution(
            session,
            workspace_id=WORKSPACE,
            execution_id=execution.id,
            output={"decision": "ok"},
            provider="openai",
            model="gpt-4o-mini",
            tokens={"total_tokens": 15},
            cost=Decimal("0.001"),
            latency_ms=7,
            trace_id=trace_id,
        )
        task.status = "completed"
        await session.flush()

    async with factory() as session:
        trace = await agent_queue.get_trace(session, workspace_id=WORKSPACE, trace_id=trace_id)
        assert trace is not None
        node_types = {node["type"] for node in trace["nodes"]}
        assert {"task", "execution", "attempt", "llm_call", "event"} <= node_types
        timestamps = [node["timestamp"] for node in trace["nodes"] if node["timestamp"]]
        assert timestamps == sorted(timestamps)
        missing = await agent_queue.get_trace(
            session, workspace_id=WORKSPACE, trace_id="trace-unknown"
        )
        assert missing is None

    # API surface: 200 for the real trace, 404 for an unknown one.
    response = api_client.get(f"/api/v1/agent-traces/{trace_id}", headers=_headers())
    assert response.status_code == 200, response.text
    assert response.json()["trace_id"] == trace_id
    missing_response = api_client.get("/api/v1/agent-traces/trace-unknown")
    assert missing_response.status_code == 404


def _headers(workspace: UUID | None = None) -> dict:
    return {"X-Workspace-Id": str(workspace)} if workspace else {}


# --------------------------------------------------------------------------- #
# 7. API surfaces
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_queue_stats_and_health_api(db_session, api_client) -> None:
    response = api_client.get("/api/v1/agent-queue/stats", headers=_headers())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["backend"] == "memory"
    assert "queue_depth" in body
    assert "pending_count" in body
    assert "success_rate" in body

    health = api_client.get("/api/v1/agent-queue/health", headers=_headers())
    assert health.status_code == 200, health.text
    assert health.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_dead_letters_api(db_engine, api_client) -> None:
    backend = task_queue.get_queue_backend()
    factory = _factory(db_engine)
    async with factory() as session:
        task_id = await _create_task(session)
        await _set_no_retry(session)
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)
    await run_worker_once(
        backend,
        factory,
        executor=FakeExecutor(errors=[LLMError("provider boom", kind="provider")]),
    )
    response = api_client.get("/api/v1/agent-queue/dead-letters", headers=_headers())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] >= 1
    assert body["items"][0]["task_id"] == str(task_id)


@pytest.mark.asyncio
async def test_worker_api_heartbeat_and_list(api_client) -> None:
    response = api_client.post(
        "/api/v1/agent-workers/heartbeat",
        json={
            "worker_id": "api-worker-1",
            "hostname": "host-a",
            "status": "idle",
            "processed_count": 3,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["worker_id"] == "api-worker-1"
    assert response.json()["processed_count"] == 3
    workers = api_client.get("/api/v1/agent-workers")
    assert workers.status_code == 200
    assert any(worker["worker_id"] == "api-worker-1" for worker in workers.json())


@pytest.mark.asyncio
async def test_workspace_isolation_for_observability(db_engine) -> None:
    backend = task_queue.get_queue_backend()
    factory = _factory(db_engine)
    async with factory() as session:
        task_id = await _create_task(session, workspace=WORKSPACE)
        await _set_no_retry(session)
    await task_queue.enqueue_task(backend, workspace_id=WORKSPACE, task_id=task_id, attempt=1)
    await run_worker_once(
        backend,
        factory,
        executor=FakeExecutor(errors=[LLMError("provider boom", kind="provider")]),
    )
    async with factory() as session:
        own = await agent_queue.list_dead_letters(session, workspace_id=WORKSPACE)
        other = await agent_queue.list_dead_letters(session, workspace_id=OTHER_WORKSPACE)
        assert own[1] >= 1
        assert other[1] == 0
        trace = await agent_queue.get_trace(session, workspace_id=OTHER_WORKSPACE, trace_id="any")
        assert trace is None
