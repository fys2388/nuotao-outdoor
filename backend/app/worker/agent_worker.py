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
    event_service,
    retry_engine,
    task_queue,
)
from app.worker.executor import ExecutionResult, llm_executor

logger = logging.getLogger(__name__)

ExecutorFn = Callable[..., Awaitable[ExecutionResult]]


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
    ``budget_blocked`` / ``deferred`` / ``skipped`` / ``malformed`` /
    ``failed``.
    """
    executor = executor or llm_executor
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

    async with session_factory() as session:
        task = await session.get(AgentTask, task_id)
        if task is None or task.workspace_id != workspace_id or task.status != "pending":
            # Redelivery after crash / already handled: idempotent skip.
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
            await task_queue.enqueue_delayed_retry(
                backend,
                workspace_id=workspace_id,
                task_id=task.id,
                attempt=attempt,
                delay_seconds=settings.task_queue_defer_delay,
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
            return await _run_attempt(
                session=session,
                backend=backend,
                workspace_id=workspace_id,
                task=task,
                agent=agent,
                policy=policy,
                attempt=attempt,
                executor=executor,
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


async def run_worker_once(
    backend: task_queue.TaskQueueBackend,
    session_factory: async_sessionmaker,
    *,
    executor: ExecutorFn | None = None,
    worker_id: str | None = None,
    gate: ConcurrencyGate | None = None,
    max_messages: int = 10,
) -> int:
    """Drain up to ``max_messages`` messages (flush delayed first)."""
    settings = get_settings()
    worker_id = worker_id or settings.worker_id
    await backend.ensure_group(task_queue.task_stream(), settings.task_queue_group)
    await task_queue.flush_delayed(backend)
    messages = await backend.read_group(
        task_queue.task_stream(),
        settings.task_queue_group,
        worker_id,
        count=max_messages,
        block_ms=0,
    )
    processed = 0
    for message in messages:
        await process_message(
            backend,
            session_factory,
            message,
            executor=executor,
            worker_id=worker_id,
            gate=gate,
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
) -> None:
    """Resident worker loop (blocking); start it in its own process/task."""
    from app.core.database import async_session_factory

    settings = get_settings()
    backend = backend or task_queue.get_queue_backend()
    session_factory = session_factory or async_session_factory
    worker_id = worker_id or settings.worker_id
    executor = executor or llm_executor
    gate = ConcurrencyGate()
    stream = task_queue.task_stream()
    group = settings.task_queue_group

    await backend.ensure_group(stream, group)
    logger.info("agent worker %s started (concurrency=%s)", worker_id, settings.worker_concurrency)
    while stop_event is None or not stop_event.is_set():
        try:
            await task_queue.flush_delayed(backend)
            messages = await backend.read_group(
                stream,
                group,
                worker_id,
                count=settings.worker_concurrency,
                block_ms=settings.task_queue_poll_ms,
            )
            for message in messages:
                try:
                    await process_message(
                        backend,
                        session_factory,
                        message,
                        executor=executor,
                        worker_id=worker_id,
                        gate=gate,
                    )
                except Exception:  # noqa: BLE001 - never kill the loop
                    logger.exception(
                        "worker message error (message=%s, trace=%s)",
                        message.message_id,
                        worker_id,
                    )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - keep the worker alive
            logger.exception("worker loop error (worker=%s)", worker_id)
            await asyncio.sleep(1)
