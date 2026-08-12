"""Agent worker: the production runtime loop (M5.1).

Consumes the Redis-Stream task queue through a consumer group and drives the
generic execution pipeline per message:

    claim -> task check (idempotent) -> policies -> budget gate ->
    concurrency gate -> attempt audit -> start execution -> executor ->
    complete/fail -> retry decision -> ack

Safety rules (hard constraints):
- no business agent is defined here; the executor extension point binds one
  later (M5.2+);
- no high-risk business action is ever auto-executed (L3 tools still stop at
  ``waiting_approval`` for a human);
- every state change writes ``event_log`` with a ``trace_id``;
- the task row is the source of truth: redeliveries are idempotent because a
  non-``pending`` task is skipped.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import get_settings
from app.core.tracing import new_trace_id
from app.models.agent_runtime import AgentRegistry, AgentTask
from app.services import (
    agent_budget,
    agent_policies,
    agent_runtime,
    agent_workers,
    event_service,
    retry_engine,
    task_queue,
)
from app.worker.executor import ExecutionResult, llm_executor

logger = logging.getLogger(__name__)

ExecutorFn = Callable[..., Awaitable[ExecutionResult]]


# Per-agent executor dispatch (M5.2): registered business agents plug their
# executor here; unregistered agents fall back to the generic LLM executor.
_EXECUTORS: dict[str, ExecutorFn] = {}


def register_executor(agent_id: str, executor: ExecutorFn) -> None:
    """Bind an executor to a concrete agent id (M5.2+)."""
    _EXECUTORS[agent_id] = executor


def resolve_executor(agent: AgentRegistry) -> ExecutorFn:
    """Return the executor bound to an agent (generic LLM fallback)."""
    return _EXECUTORS.get(agent.agent_id, llm_executor)


def _now() -> datetime:
    return datetime.now(UTC)


class ConcurrencyGate:
    """In-process per-agent concurrency gate (single-worker Phase 1)."""

    def __init__(self) -> None:
        self._active: dict[str, int] = {}

    def try_acquire(self, agent_key: str, max_concurrent: int) -> bool:
        current = self._active.get(agent_key, 0)
        if current >= max_concurrent:
            return False
        self._active[agent_key] = current + 1
        return True

    def release(self, agent_key: str) -> None:
        current = self._active.get(agent_key, 0)
        if current <= 1:
            self._active.pop(agent_key, None)
        else:
            self._active[agent_key] = current - 1

    def active_count(self, agent_key: str) -> int:
        return self._active.get(agent_key, 0)


async def _emit(
    session: Any,
    *,
    workspace_id: UUID,
    event_type: str,
    entity_type: str,
    entity_id: str,
    payload: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> None:
    """Append an event (commits the session like the rest of the codebase)."""
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
        trace_id=trace_id,
    )


async def _handle_failure(
    session: Any,
    backend: task_queue.TaskQueueBackend,
    *,
    workspace_id: UUID,
    task: AgentTask,
    agent: AgentRegistry,
    policy: Any,
    execution: Any,
    attempt: int,
    error_type: str,
    error_message: str,
    worker_id: str,
    trace_id: str,
    message_id: str,
) -> str:
    """Fail the attempt; retry or dead-letter per the retry policy."""
    await agent_runtime.fail_execution(
        session,
        workspace_id=workspace_id,
        execution_id=execution.id,
        error_message=error_message,
        error_type=error_type,
        fail_task=False,
        trace_id=trace_id,
    )
    status = (
        retry_engine.ATTEMPT_TIMED_OUT if error_type == "timeout" else retry_engine.ATTEMPT_FAILED
    )
    await retry_engine.record_attempt(
        session,
        workspace_id=workspace_id,
        task_id=task.id,
        attempt_number=attempt,
        status=status,
        execution_id=execution.id,
        error_type=error_type,
        error_message=error_message,
        worker_id=worker_id,
        trace_id=trace_id,
    )
    if error_type == "timeout":
        await _emit(
            session,
            workspace_id=workspace_id,
            event_type="agent.execution_timed_out",
            entity_type="agent_execution",
            entity_id=str(execution.id),
            payload={"task_id": str(task.id), "attempt": attempt},
            trace_id=trace_id,
        )
    retry_policy = await agent_policies.get_retry_policy(
        session,
        workspace_id=workspace_id,
        retry_policy_id=policy.retry_policy_id,
        trace_id=trace_id,
    )
    if retry_engine.should_retry(retry_policy, error_type=error_type, attempts_used=attempt):
        delay = retry_engine.backoff_seconds(retry_policy, attempts_used=attempt)
        task.status = "pending"
        task.error_message = None
        task.started_at = None
        await session.flush()
        await task_queue.enqueue_delayed_retry(
            backend,
            workspace_id=workspace_id,
            task_id=task.id,
            attempt=attempt + 1,
            delay_seconds=delay,
            idempotency_key=task.idempotency_key,
        )
        await _emit(
            session,
            workspace_id=workspace_id,
            event_type="agent.task_requeued",
            entity_type="agent_task",
            entity_id=str(task.id),
            payload={"attempt": attempt + 1, "delay_seconds": delay, "error_type": error_type},
            trace_id=trace_id,
        )
        await _emit(
            session,
            workspace_id=workspace_id,
            event_type="agent.queue.retry_scheduled",
            entity_type="agent_task",
            entity_id=str(task.id),
            payload={
                "attempt": attempt + 1,
                "delay_seconds": delay,
                "error_type": error_type,
                "execution_id": str(execution.id),
            },
            trace_id=trace_id,
        )
        await backend.ack(task_queue.task_stream(), get_settings().task_queue_group, message_id)
        return "retried"

    task.status = "failed"
    task.error_message = error_message[:1000]
    task.completed_at = _now()
    await _emit(
        session,
        workspace_id=workspace_id,
        event_type="agent.task_failed",
        entity_type="agent_task",
        entity_id=str(task.id),
        payload={"error_type": error_type, "attempt": attempt},
        trace_id=trace_id,
    )
    await _emit(
        session,
        workspace_id=workspace_id,
        event_type="agent.task_dead_letter",
        entity_type="agent_task",
        entity_id=str(task.id),
        payload={"error_type": error_type, "attempt": attempt},
        trace_id=trace_id,
    )
    await _emit(
        session,
        workspace_id=workspace_id,
        event_type="agent.queue.dead_lettered",
        entity_type="agent_task",
        entity_id=str(task.id),
        payload={
            "error_type": error_type,
            "attempt": attempt,
            "execution_id": str(execution.id),
        },
        trace_id=trace_id,
    )
    await backend.ack(task_queue.task_stream(), get_settings().task_queue_group, message_id)
    return "dead_letter"


async def process_message(
    backend: task_queue.TaskQueueBackend,
    session_factory: async_sessionmaker,
    message: task_queue.StreamMessage,
    *,
    executor: ExecutorFn | None = None,
    worker_id: str | None = None,
    gate: ConcurrencyGate | None = None,
    trace_id: str | None = None,
) -> str:
    """Process one queue message end-to-end; always acks terminal outcomes.

    Returns one of: ``completed`` / ``retried`` / ``dead_letter`` /
    ``budget_blocked`` / ``deferred`` / ``skipped`` / ``skipped_concurrent`` /
    ``malformed`` / ``failed``.
    """
    settings = get_settings()
    worker_id = worker_id or settings.worker_id
    trace_id = trace_id or new_trace_id()
    stream = task_queue.task_stream()
    group = settings.task_queue_group

    try:
        data = task_queue.parse_message(message.fields)
    except Exception:  # noqa: BLE001 - malformed messages are acked and logged
        logger.warning("malformed queue message %s (trace=%s)", message.message_id, trace_id)
        await backend.ack(stream, group, message.message_id)
        return "malformed"

    workspace_id: UUID = data["workspace_id"]
    task_id: UUID = data["task_id"]
    attempt: int = data["attempt"]

    # M5.3 message-level dedup: stable identity per (task, attempt) - never a
    # random UUID. The Redis token is an optimization; the DB task row stays
    # the business source of truth (idempotent redeliveries).
    dedup_key = data.get("dedup_key") or task_queue.build_dedup_key(
        workspace_id=workspace_id, task_id=task_id, attempt=attempt
    )
    dedup_claimed = await backend.dedup_claim(
        dedup_key,
        ttl_seconds=settings.task_queue_dedup_ttl_seconds,
        stale_after_seconds=settings.task_queue_reclaim_idle_ms / 1000.0,
    )
    if not dedup_claimed:
        # A live duplicate delivery (concurrent worker / duplicate XADD):
        # only one worker may hold the token - ack and never execute.
        async with session_factory() as session:
            await _emit(
                session,
                workspace_id=workspace_id,
                event_type="agent.queue.message_skipped",
                entity_type="agent_task",
                entity_id=str(task_id),
                payload={"attempt": attempt, "reason": "dedup_token_busy"},
                trace_id=trace_id,
            )
        await backend.ack(stream, group, message.message_id)
        return "skipped_concurrent"

    async with session_factory() as session:
        task = await session.get(AgentTask, task_id)
        if task is not None and task.workspace_id == workspace_id and task.trace_id:
            # Continue the creation-time trace id through the whole chain
            # (task -> execution -> LLM -> decision -> events).
            trace_id = task.trace_id
        if task is None or task.workspace_id != workspace_id:
            # Unknown or cross-workspace delivery: idempotent skip.
            await backend.ack(stream, group, message.message_id)
            return "skipped"
        if task.status != "pending":
            # Already handled (completed/failed/running): the DB guard
            # deduplicates the redelivery - ack, do not re-execute.
            await _emit(
                session,
                workspace_id=workspace_id,
                event_type="agent.queue.message_deduplicated",
                entity_type="agent_task",
                entity_id=str(task_id),
                payload={"attempt": attempt, "task_status": task.status},
                trace_id=trace_id,
            )
            await backend.ack(stream, group, message.message_id)
            return "skipped"

        agent = await session.get(AgentRegistry, task.agent_id) if task.agent_id else None
        if agent is None or agent.workspace_id != workspace_id or agent.status != "active":
            task.status = "failed"
            task.error_message = "agent not found or not active"
            task.completed_at = _now()
            await _emit(
                session,
                workspace_id=workspace_id,
                event_type="agent.task_failed",
                entity_type="agent_task",
                entity_id=str(task.id),
                payload={"error_type": "unknown", "reason": "agent unavailable"},
                trace_id=trace_id,
            )
            await backend.ack(stream, group, message.message_id)
            return "failed"

        policy = await agent_policies.get_execution_policy(
            session, workspace_id=workspace_id, agent_id=agent.id, trace_id=trace_id
        )
        if not policy.enabled:
            task.status = "failed"
            task.error_message = "execution policy disabled"
            task.completed_at = _now()
            await _emit(
                session,
                workspace_id=workspace_id,
                event_type="agent.task_failed",
                entity_type="agent_task",
                entity_id=str(task.id),
                payload={"error_type": "policy_disabled"},
                trace_id=trace_id,
            )
            await backend.ack(stream, group, message.message_id)
            return "failed"

        # Per-agent concurrency gate (defer without consuming an attempt).
        if gate is not None and not gate.try_acquire(str(agent.id), policy.max_concurrent):
            # The deferred message carries the SAME dedup key (same attempt):
            # release our token so the re-enqueued message can be claimed.
            await backend.dedup_release(dedup_key)
            await task_queue.enqueue_delayed_retry(
                backend,
                workspace_id=workspace_id,
                task_id=task.id,
                attempt=attempt,
                delay_seconds=settings.task_queue_defer_delay,
                idempotency_key=task.idempotency_key,
            )
            await _emit(
                session,
                workspace_id=workspace_id,
                event_type="agent.task_deferred",
                entity_type="agent_task",
                entity_id=str(task.id),
                payload={"reason": "concurrency_limit", "attempt": attempt},
                trace_id=trace_id,
            )
            await backend.ack(stream, group, message.message_id)
            return "deferred"

        try:
            resolved_executor = executor or resolve_executor(agent)
            return await _run_attempt(
                session=session,
                backend=backend,
                workspace_id=workspace_id,
                task=task,
                agent=agent,
                policy=policy,
                attempt=attempt,
                executor=resolved_executor,
                worker_id=worker_id,
                trace_id=trace_id,
                message_id=message.message_id,
            )
        finally:
            if gate is not None:
                gate.release(str(agent.id))


async def _run_attempt(
    *,
    session: Any,
    backend: task_queue.TaskQueueBackend,
    workspace_id: UUID,
    task: AgentTask,
    agent: AgentRegistry,
    policy: Any,
    attempt: int,
    executor: ExecutorFn,
    worker_id: str,
    trace_id: str,
    message_id: str,
) -> str:
    """One attempt: budget gate -> execution -> completion or failure path."""
    settings = get_settings()
    stream = task_queue.task_stream()
    group = settings.task_queue_group

    budget_policy = await agent_policies.get_budget_policy(
        session, workspace_id=workspace_id, agent_id=agent.id, trace_id=trace_id
    )
    decision = await agent_budget.check_budget(
        session,
        workspace_id=workspace_id,
        agent=agent,
        policy=budget_policy,
        projected_cost=budget_policy.max_cost_per_execution,
        trace_id=trace_id,
    )
    if not decision.allowed:
        await retry_engine.record_attempt(
            session,
            workspace_id=workspace_id,
            task_id=task.id,
            attempt_number=attempt,
            status=retry_engine.ATTEMPT_BUDGET_BLOCKED,
            error_type="budget",
            error_message=decision.reason,
            worker_id=worker_id,
            trace_id=trace_id,
        )
        task.status = "failed"
        task.error_message = decision.reason
        task.completed_at = _now()
        await _emit(
            session,
            workspace_id=workspace_id,
            event_type="agent.execution_budget_blocked",
            entity_type="agent_execution",
            entity_id=str(task.id),
            payload={
                "monthly_usage": str(decision.monthly_usage),
                "monthly_budget": str(decision.monthly_budget),
                "reason": decision.reason,
            },
            trace_id=trace_id,
        )
        await _emit(
            session,
            workspace_id=workspace_id,
            event_type="agent.task_failed",
            entity_type="agent_task",
            entity_id=str(task.id),
            payload={"error_type": "budget", "reason": decision.reason},
            trace_id=trace_id,
        )
        await backend.ack(stream, group, message_id)
        return "budget_blocked"

    await retry_engine.record_attempt(
        session,
        workspace_id=workspace_id,
        task_id=task.id,
        attempt_number=attempt,
        status=retry_engine.ATTEMPT_RUNNING,
        worker_id=worker_id,
        trace_id=trace_id,
    )
    execution = await agent_runtime.start_execution(
        session, workspace_id=workspace_id, task_id=task.id, trace_id=trace_id
    )
    execution.worker_id = worker_id
    execution.attempt_number = attempt
    await session.flush()
    await _emit(
        session,
        workspace_id=workspace_id,
        event_type="agent.task_attempt_started",
        entity_type="agent_task",
        entity_id=str(task.id),
        payload={"attempt": attempt, "execution_id": str(execution.id)},
        trace_id=trace_id,
    )

    try:
        result = await asyncio.wait_for(
            executor(
                session,
                workspace_id=workspace_id,
                agent=agent,
                task=task,
                policy=policy,
                trace_id=trace_id,
            ),
            timeout=policy.execution_timeout_seconds,
        )
    except TimeoutError:
        return await _handle_failure(
            session=session,
            backend=backend,
            workspace_id=workspace_id,
            task=task,
            agent=agent,
            policy=policy,
            execution=execution,
            attempt=attempt,
            error_type="timeout",
            error_message=f"execution timed out after {policy.execution_timeout_seconds}s",
            worker_id=worker_id,
            trace_id=trace_id,
            message_id=message_id,
        )
    except Exception as exc:  # noqa: BLE001 - classify and retry/dead-letter
        error_type = retry_engine.classify_error(exc)
        logger.warning(
            "execution failed (task=%s, error=%s, trace=%s): %s", task.id, error_type, trace_id, exc
        )
        return await _handle_failure(
            session=session,
            backend=backend,
            workspace_id=workspace_id,
            task=task,
            agent=agent,
            policy=policy,
            execution=execution,
            attempt=attempt,
            error_type=error_type,
            error_message=str(exc)[:900],
            worker_id=worker_id,
            trace_id=trace_id,
            message_id=message_id,
        )

    await agent_runtime.complete_execution(
        session,
        workspace_id=workspace_id,
        execution_id=execution.id,
        output=result.output,
        provider=result.provider,
        model=result.model,
        tokens=result.tokens,
        cost=result.cost,
        latency_ms=result.latency_ms,
        trace_id=trace_id,
    )
    await retry_engine.record_attempt(
        session,
        workspace_id=workspace_id,
        task_id=task.id,
        attempt_number=attempt,
        status=retry_engine.ATTEMPT_SUCCEEDED,
        execution_id=execution.id,
        latency_ms=result.latency_ms,
        worker_id=worker_id,
        trace_id=trace_id,
    )
    await _emit(
        session,
        workspace_id=workspace_id,
        event_type="agent.task_attempt_succeeded",
        entity_type="agent_task",
        entity_id=str(task.id),
        payload={"attempt": attempt, "execution_id": str(execution.id)},
        trace_id=trace_id,
    )
    await backend.ack(stream, group, message_id)
    return "completed"


async def _process_with_runtime(
    backend: task_queue.TaskQueueBackend,
    session_factory: async_sessionmaker,
    message: task_queue.StreamMessage,
    *,
    executor: ExecutorFn | None,
    worker_id: str,
    gate: ConcurrencyGate | None,
    runtime: agent_workers.WorkerRuntime | None,
) -> str:
    """Run one message with worker heartbeat (busy -> idle/processed/failed)."""
    current_task_id = message.fields.get(task_queue.FIELD_TASK_ID)
    if runtime is not None:
        async with session_factory() as session:
            await runtime.beat(
                status=agent_workers.WORKER_BUSY,
                current_task_id=current_task_id,
                session=session,
            )
    try:
        outcome = await process_message(
            backend,
            session_factory,
            message,
            executor=executor,
            worker_id=worker_id,
            gate=gate,
        )
    except Exception:
        if runtime is not None:
            async with session_factory() as session:
                await runtime.mark_failed(session=session)
        raise
    if runtime is not None:
        async with session_factory() as session:
            if outcome in ("failed", "dead_letter", "budget_blocked", "malformed"):
                await runtime.mark_failed(session=session)
            elif outcome == "completed":
                await runtime.mark_processed(session=session)
            else:
                await runtime.beat(
                    status=agent_workers.WORKER_IDLE,
                    current_task_id="",
                    current_execution_id="",
                    session=session,
                )
    return outcome


async def run_worker_once(
    backend: task_queue.TaskQueueBackend,
    session_factory: async_sessionmaker,
    *,
    executor: ExecutorFn | None = None,
    worker_id: str | None = None,
    gate: ConcurrencyGate | None = None,
    runtime: agent_workers.WorkerRuntime | None = None,
    max_messages: int = 10,
) -> int:
    """Drain up to ``max_messages`` messages (flush delayed first).

    When ``runtime`` is provided the worker heartbeats through the registry
    (``starting`` -> ``busy`` -> ``idle``) and keeps processed/failed
    counters; ``None`` keeps the call side-effect free for unit tests.
    """
    settings = get_settings()
    worker_id = worker_id or settings.worker_id
    stream = task_queue.task_stream()
    group = settings.task_queue_group
    await backend.ensure_group(stream, group)
    await task_queue.flush_delayed(backend)
    # Reclaim deliveries left in the PEL by crashed workers (idempotent via
    # the DB task row) before consuming new messages.
    reclaimed = await backend.reclaim_orphaned(
        stream,
        group,
        worker_id,
        min_idle_ms=settings.task_queue_reclaim_idle_ms,
        count=settings.task_queue_reclaim_batch,
    )
    messages = reclaimed + await backend.read_group(
        stream,
        group,
        worker_id,
        count=max_messages,
        block_ms=0,
    )
    if runtime is not None:
        async with session_factory() as session:
            await runtime.start(session=session)
    processed = 0
    for message in messages:
        await _process_with_runtime(
            backend,
            session_factory,
            message,
            executor=executor,
            worker_id=worker_id,
            gate=gate,
            runtime=runtime,
        )
        processed += 1
    return processed


async def run_worker(
    backend: task_queue.TaskQueueBackend | None = None,
    session_factory: async_sessionmaker | None = None,
    *,
    executor: ExecutorFn | None = None,
    worker_id: str | None = None,
    stop_event: asyncio.Event | None = None,
    runtime: agent_workers.WorkerRuntime | None = None,
) -> None:
    """Resident worker loop (blocking); start it in its own process/task.

    The worker registers itself and heartbeats through
    :class:`~app.services.agent_workers.WorkerRuntime`; state changes are
    mirrored to ``event_log`` (``agent.queue.worker_*``).
    """
    from app.core.database import async_session_factory

    settings = get_settings()
    backend = backend or task_queue.get_queue_backend()
    session_factory = session_factory or async_session_factory
    worker_id = worker_id or settings.worker_id
    # executor=None -> per-agent dispatch inside process_message (M5.2).
    gate = ConcurrencyGate()
    stream = task_queue.task_stream()
    group = settings.task_queue_group

    await backend.ensure_group(stream, group)
    runtime = runtime or agent_workers.WorkerRuntime(backend=backend, worker_id=worker_id)
    async with session_factory() as session:
        await runtime.start(session=session)
    logger.info("agent worker %s started (concurrency=%s)", worker_id, settings.worker_concurrency)
    try:
        while stop_event is None or not stop_event.is_set():
            try:
                async with session_factory() as session:
                    await runtime.beat(status=agent_workers.WORKER_IDLE, session=session)
                await task_queue.flush_delayed(backend)
                reclaimed = await backend.reclaim_orphaned(
                    stream,
                    group,
                    worker_id,
                    min_idle_ms=settings.task_queue_reclaim_idle_ms,
                    count=settings.task_queue_reclaim_batch,
                )
                messages = reclaimed + await backend.read_group(
                    stream,
                    group,
                    worker_id,
                    count=settings.worker_concurrency,
                    block_ms=settings.task_queue_poll_ms,
                )
                for message in messages:
                    try:
                        await _process_with_runtime(
                            backend,
                            session_factory,
                            message,
                            executor=executor,
                            worker_id=worker_id,
                            gate=gate,
                            runtime=runtime,
                        )
                    except Exception:  # noqa: BLE001 - never kill the loop
                        logger.exception(
                            "worker message error (message=%s, worker=%s)",
                            message.message_id,
                            worker_id,
                        )
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - keep the worker alive
                logger.exception("worker loop error (worker=%s)", worker_id)
                await asyncio.sleep(1)
    finally:
        async with session_factory() as session:
            await runtime.stop(session=session)
