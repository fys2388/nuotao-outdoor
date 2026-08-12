"""Agent runtime sweepers (M5.1): keep the system self-healing.

- ``expire_stale_approvals``: L3 executions waiting for a human decision
  past their policy deadline are auto-REJECTED (never auto-approved) and the
  task fails with ``approval timed out``.
- ``fail_stale_executions``: executions stuck in ``running`` beyond the
  execution timeout (crashed worker) are failed; the task is retried through
  the retry engine when policy allows.
- ``reconcile_pending_tasks``: enqueue pending tasks that never made it into
  the queue (crash between DB commit and XADD), making the DB the source of
  truth and the queue an accelerator.

Everything is workspace-scoped, event-logged and trace-consistent.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_runtime import AgentExecution, AgentRegistry, AgentTask
from app.services import agent_policies, event_service, retry_engine, task_queue


@dataclass(frozen=True)
class SweeperResult:
    """Counts of rows touched by one sweeper pass."""

    approvals_expired: int = 0
    stale_executions_failed: int = 0
    tasks_requeued: int = 0
    pending_tasks_enqueued: int = 0


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    """Normalize a (possibly naive) DB datetime to UTC-aware for comparison."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


async def expire_stale_approvals(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    trace_id: str | None = None,
) -> int:
    """Auto-reject waiting_approval executions past their deadline."""
    now = _now()
    rows = (
        (
            await session.execute(
                select(AgentExecution).where(
                    AgentExecution.workspace_id == workspace_id,
                    AgentExecution.status == "waiting_approval",
                    AgentExecution.approval_deadline.is_not(None),
                    AgentExecution.approval_deadline < now,
                )
            )
        )
        .scalars()
        .all()
    )
    for execution in rows:
        execution.status = "rejected"
        execution.approval = {
            "decision": "expired",
            "actor": "system-sweeper",
            "note": "approval deadline exceeded; auto-rejected (never auto-approved)",
            "decided_at": now.isoformat(),
        }
        execution.completed_at = now
        await session.flush()
        task = await session.get(AgentTask, execution.task_id) if execution.task_id else None
        if task is not None and task.workspace_id == workspace_id:
            task.status = "failed"
            task.error_message = "approval timed out; execution auto-rejected"
            task.completed_at = now
        await event_service.create_event(
            session,
            workspace_id=workspace_id,
            event_type="agent.approval_expired",
            entity_type="agent_execution",
            entity_id=str(execution.id),
            payload={"task_id": str(execution.task_id), "decision": "rejected"},
            trace_id=trace_id,
        )
        # M5.4: keep the unified Approval Center row in sync (auto-reject is
        # never an approval - the decision is always "rejected").
        from app.services.approval_service import sync_approval

        await sync_approval(
            session,
            workspace_id=workspace_id,
            approval_type="L3_TOOL",
            entity_id=str(execution.id),
            decision="rejected",
            actor="system-sweeper",
            note="approval deadline exceeded; auto-rejected",
            trace_id=trace_id,
        )
    return len(rows)


async def fail_stale_executions(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    backend: task_queue.TaskQueueBackend,
    trace_id: str | None = None,
) -> tuple[int, int]:
    """Fail running executions past the policy timeout; retry their tasks.

    Returns ``(failed_executions, requeued_tasks)``.
    """
    now = _now()
    running = (
        (
            await session.execute(
                select(AgentExecution).where(
                    AgentExecution.workspace_id == workspace_id,
                    AgentExecution.status == "running",
                    AgentExecution.started_at.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    failed = 0
    requeued = 0
    for execution in running:
        agent = await session.get(AgentRegistry, execution.agent_id) if execution.agent_id else None
        if agent is None or agent.workspace_id != workspace_id:
            continue
        policy = await agent_policies.get_execution_policy(
            session, workspace_id=workspace_id, agent_id=agent.id, trace_id=trace_id
        )
        started_at = _aware(execution.started_at)
        if started_at is None:
            continue
        deadline = started_at + timedelta(seconds=policy.execution_timeout_seconds)
        if now <= deadline:
            continue
        execution.status = "failed"
        execution.error_message = "stale execution exceeded timeout (worker lost)"
        execution.error_type = "timeout"
        execution.completed_at = now
        await session.flush()
        await event_service.create_event(
            session,
            workspace_id=workspace_id,
            event_type="agent.execution_timed_out",
            entity_type="agent_execution",
            entity_id=str(execution.id),
            payload={"task_id": str(execution.task_id), "source": "sweeper"},
            trace_id=trace_id,
        )
        failed += 1
        task = await session.get(AgentTask, execution.task_id) if execution.task_id else None
        if task is None or task.workspace_id != workspace_id:
            continue
        attempt = execution.attempt_number or 1
        await retry_engine.record_attempt(
            session,
            workspace_id=workspace_id,
            task_id=task.id,
            attempt_number=attempt,
            status=retry_engine.ATTEMPT_TIMED_OUT,
            execution_id=execution.id,
            error_type="timeout",
            error_message="stale execution exceeded timeout (worker lost)",
            worker_id="sweeper",
            trace_id=trace_id,
        )
        retry_policy = await agent_policies.get_retry_policy(
            session, workspace_id=workspace_id, retry_policy_id=policy.retry_policy_id
        )
        if retry_engine.should_retry(retry_policy, error_type="timeout", attempts_used=attempt):
            task.status = "pending"
            task.error_message = None
            task.started_at = None
            await session.flush()
            delay = retry_engine.backoff_seconds(retry_policy, attempts_used=attempt)
            await task_queue.enqueue_delayed_retry(
                backend,
                workspace_id=workspace_id,
                task_id=task.id,
                attempt=attempt + 1,
                delay_seconds=delay,
                idempotency_key=task.idempotency_key,
            )
            await event_service.create_event(
                session,
                workspace_id=workspace_id,
                event_type="agent.task_requeued",
                entity_type="agent_task",
                entity_id=str(task.id),
                payload={"attempt": attempt + 1, "delay_seconds": delay, "source": "sweeper"},
                trace_id=trace_id,
            )
            requeued += 1
        else:
            task.status = "failed"
            task.error_message = f"stale execution exceeded timeout (attempt {attempt})"
            task.completed_at = _now()
            await event_service.create_event(
                session,
                workspace_id=workspace_id,
                event_type="agent.task_dead_letter",
                entity_type="agent_task",
                entity_id=str(task.id),
                payload={"error_type": "timeout", "attempt": attempt, "source": "sweeper"},
                trace_id=trace_id,
            )
    return failed, requeued


async def reconcile_pending_tasks(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    backend: task_queue.TaskQueueBackend,
    trace_id: str | None = None,
) -> int:
    """Enqueue pending tasks that have no queue record (crash recovery)."""
    pending = (
        (
            await session.execute(
                select(AgentTask).where(
                    AgentTask.workspace_id == workspace_id,
                    AgentTask.status == "pending",
                    AgentTask.enqueued_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    enqueued = 0
    for task in pending:
        await task_queue.enqueue_task(
            backend,
            workspace_id=workspace_id,
            task_id=task.id,
            attempt=max(task.attempt_count, 1),
            idempotency_key=task.idempotency_key,
        )
        task.enqueued_at = _now()
        await event_service.create_event(
            session,
            workspace_id=workspace_id,
            event_type="agent.task_enqueued",
            entity_type="agent_task",
            entity_id=str(task.id),
            payload={"attempt": max(task.attempt_count, 1), "source": "reconcile"},
            trace_id=trace_id,
        )
        enqueued += 1
    if enqueued:
        await session.flush()
    return enqueued
