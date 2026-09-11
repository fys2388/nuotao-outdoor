"""Retry engine (M5.1): durable attempt audit + retry/backoff decisions.

Every attempt writes an immutable ``agent_task_attempts`` row (attempt
number, status, error classification, latency, worker, trace_id) and bumps
the task's ``attempt_count``. Retry decisions come from the versioned retry
policy - nothing is hardcoded in the worker or prompts.

Error classes: ``llm`` / ``network`` / ``timeout`` / ``transient`` are
retryable by default; ``auth`` / ``invalid`` / ``budget`` / ``unknown`` are
terminal (no silent retry of poisoned work).
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_runtime import AgentTask
from app.models.agent_runtime_hardening import AgentRetryPolicy, AgentTaskAttempt

# Attempt statuses (immutable audit rows).
ATTEMPT_RUNNING = "running"
ATTEMPT_SUCCEEDED = "succeeded"
ATTEMPT_FAILED = "failed"
ATTEMPT_TIMED_OUT = "timed_out"
ATTEMPT_BUDGET_BLOCKED = "budget_blocked"

# Error classes that are terminal regardless of policy.
TERMINAL_ERROR_TYPES = frozenset({"auth", "invalid", "budget", "unknown"})


class RetryError(Exception):
    """Raised when the retry engine cannot record an attempt."""


def classify_error(error: BaseException | None) -> str:
    """Map an exception to a retryable/terminal error class."""
    if error is None:
        return "unknown"
    name = type(error).__name__.lower()
    if name == "timeouterror":
        return "timeout"
    # LLM gateway errors expose a ``kind`` attribute (llm/auth/network/...).
    kind = getattr(error, "kind", None)
    if kind:
        return "llm" if kind == "provider" else kind
    if name in ("connectionerror", "timeout"):
        return "network"
    if name in ("llmerror",):
        return "llm"
    return "unknown"


def should_retry(policy: AgentRetryPolicy, *, error_type: str, attempts_used: int) -> bool:
    """Decide whether another attempt is allowed for this error class."""
    if not policy.enabled:
        return False
    if attempts_used >= policy.max_attempts:
        return False
    if error_type in TERMINAL_ERROR_TYPES:
        return False
    return error_type in (policy.retry_on_error_types or [])


def backoff_seconds(policy: AgentRetryPolicy, *, attempts_used: int) -> int:
    """Exponential backoff: base * multiplier^(attempts_used-1), capped."""
    if policy.backoff_base_seconds <= 0:
        return 0
    exponent = max(attempts_used - 1, 0)
    multiplier = policy.backoff_multiplier if policy.backoff_multiplier else Decimal("1")
    seconds = policy.backoff_base_seconds * (multiplier**exponent)
    return min(int(seconds), policy.max_backoff_seconds)


async def record_attempt(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    task_id: UUID,
    attempt_number: int,
    status: str,
    execution_id: UUID | None = None,
    error_type: str | None = None,
    error_message: str | None = None,
    latency_ms: int | None = None,
    worker_id: str | None = None,
    trace_id: str | None = None,
) -> AgentTaskAttempt:
    """Persist one attempt row and bump the task's attempt counter."""
    attempt = AgentTaskAttempt(
        workspace_id=workspace_id,
        task_id=task_id,
        execution_id=execution_id,
        attempt_number=attempt_number,
        status=status,
        error_type=error_type,
        error_message=(error_message or "")[:1000],
        latency_ms=latency_ms,
        worker_id=worker_id,
        trace_id=trace_id,
    )
    session.add(attempt)
    task = await session.get(AgentTask, task_id)
    if task is not None and task.workspace_id == workspace_id:
        task.attempt_count = max(task.attempt_count or 0, attempt_number)
    await session.flush()
    return attempt
