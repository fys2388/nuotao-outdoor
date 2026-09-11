"""Agent policy registry (M5.1): execution / budget / retry policies.

All policies are configuration- or database-driven - nothing is hardcoded in
prompts or business code. Every agent gets a *current* policy row on first
use; updating a policy creates a new versioned row (``is_current=True``) and
retires the previous one, so history is preserved for audit and rollback.

- Execution policy: per-agent concurrency, execution timeout, L3 approval
  timeout, context size, bound retry policy.
- Budget policy: monthly budget, max cost per execution, alert threshold.
- Retry policy: reusable by code (``standard`` by default), versioned.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.agent_runtime import AgentRegistry
from app.models.agent_runtime_hardening import (
    AgentBudgetPolicy,
    AgentExecutionPolicy,
    AgentRetryPolicy,
)
from app.services import event_service

DEFAULT_RETRY_POLICY_ID = "standard"

# Error classes the default retry policy considers retryable.
DEFAULT_RETRYABLE_ERROR_TYPES = ["llm", "network", "timeout", "transient"]


class AgentPolicyError(Exception):
    """Raised when a policy operation cannot complete."""


def _now() -> datetime:
    return datetime.now(UTC)


def _next_version(current: str) -> str:
    number = int(current.lstrip("v") or "0") + 1
    return f"v{number}"


# --------------------------------------------------------------------------- #
# Retry policies
# --------------------------------------------------------------------------- #


async def get_retry_policy(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    retry_policy_id: str = DEFAULT_RETRY_POLICY_ID,
    trace_id: str | None = None,
) -> AgentRetryPolicy:
    """Return the current retry policy; create the default one when missing."""
    policy = (
        await session.execute(
            select(AgentRetryPolicy).where(
                AgentRetryPolicy.workspace_id == workspace_id,
                AgentRetryPolicy.retry_policy_id == retry_policy_id,
                AgentRetryPolicy.is_current.is_(True),
            )
        )
    ).scalar_one_or_none()
    if policy is not None:
        return policy
    if retry_policy_id != DEFAULT_RETRY_POLICY_ID:
        raise AgentPolicyError(f"retry policy '{retry_policy_id}' not found (create it first)")
    settings = get_settings()
    policy = AgentRetryPolicy(
        workspace_id=workspace_id,
        retry_policy_id=DEFAULT_RETRY_POLICY_ID,
        name="Standard exponential backoff",
        version="v1",
        is_current=True,
        max_attempts=settings.retry_standard_max_attempts,
        backoff_base_seconds=settings.retry_standard_backoff_base,
        backoff_multiplier=settings.retry_standard_backoff_multiplier,
        max_backoff_seconds=settings.retry_standard_max_backoff,
        retry_on_error_types=list(DEFAULT_RETRYABLE_ERROR_TYPES),
        enabled=True,
        trace_id=trace_id,
    )
    session.add(policy)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.retry_policy_created",
        entity_type="agent_retry_policy",
        entity_id=retry_policy_id,
        payload={"version": policy.version, "max_attempts": policy.max_attempts},
        trace_id=trace_id,
    )
    return policy


async def set_retry_policy(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    retry_policy_id: str,
    name: str,
    max_attempts: int,
    backoff_base_seconds: int,
    backoff_multiplier: Decimal,
    max_backoff_seconds: int,
    retry_on_error_types: list[str],
    enabled: bool = True,
    trace_id: str | None = None,
) -> AgentRetryPolicy:
    """Create a new version of a retry policy (previous version retired)."""
    _validate_retry_args(
        max_attempts=max_attempts,
        backoff_base_seconds=backoff_base_seconds,
        backoff_multiplier=backoff_multiplier,
        max_backoff_seconds=max_backoff_seconds,
        retry_on_error_types=retry_on_error_types,
    )
    current = (
        await session.execute(
            select(AgentRetryPolicy).where(
                AgentRetryPolicy.workspace_id == workspace_id,
                AgentRetryPolicy.retry_policy_id == retry_policy_id,
                AgentRetryPolicy.is_current.is_(True),
            )
        )
    ).scalar_one_or_none()
    version = _next_version(current.version) if current else "v1"
    if current is not None:
        await session.execute(
            update(AgentRetryPolicy)
            .where(AgentRetryPolicy.id == current.id)
            .values(is_current=False, updated_at=_now())
        )
    policy = AgentRetryPolicy(
        workspace_id=workspace_id,
        retry_policy_id=retry_policy_id,
        name=name,
        version=version,
        is_current=True,
        max_attempts=max_attempts,
        backoff_base_seconds=backoff_base_seconds,
        backoff_multiplier=backoff_multiplier,
        max_backoff_seconds=max_backoff_seconds,
        retry_on_error_types=retry_on_error_types,
        enabled=enabled,
        trace_id=trace_id,
    )
    session.add(policy)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.retry_policy_updated",
        entity_type="agent_retry_policy",
        entity_id=retry_policy_id,
        payload={"version": version, "max_attempts": max_attempts},
        trace_id=trace_id,
    )
    return policy


def _validate_retry_args(
    *,
    max_attempts: int,
    backoff_base_seconds: int,
    backoff_multiplier: Decimal,
    max_backoff_seconds: int,
    retry_on_error_types: list[str],
) -> None:
    if not 1 <= max_attempts <= 10:
        raise AgentPolicyError("max_attempts must be between 1 and 10")
    if backoff_base_seconds < 0:
        raise AgentPolicyError("backoff_base_seconds must be >= 0")
    if backoff_multiplier < 1:
        raise AgentPolicyError("backoff_multiplier must be >= 1")
    if max_backoff_seconds < 1:
        raise AgentPolicyError("max_backoff_seconds must be >= 1")
    if not retry_on_error_types:
        raise AgentPolicyError("retry_on_error_types must not be empty")


# --------------------------------------------------------------------------- #
# Execution policies
# --------------------------------------------------------------------------- #


async def get_execution_policy(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    agent_id: UUID,
    trace_id: str | None = None,
) -> AgentExecutionPolicy:
    """Return the current execution policy; seed defaults on first use."""
    policy = (
        await session.execute(
            select(AgentExecutionPolicy).where(
                AgentExecutionPolicy.workspace_id == workspace_id,
                AgentExecutionPolicy.agent_id == agent_id,
                AgentExecutionPolicy.is_current.is_(True),
            )
        )
    ).scalar_one_or_none()
    if policy is not None:
        return policy
    settings = get_settings()
    policy = AgentExecutionPolicy(
        workspace_id=workspace_id,
        agent_id=agent_id,
        policy_version="v1",
        is_current=True,
        max_concurrent=settings.agent_default_max_concurrent,
        execution_timeout_seconds=settings.agent_default_execution_timeout,
        approval_timeout_seconds=settings.agent_default_approval_timeout,
        max_context_size=settings.agent_default_max_context_size,
        retry_policy_id=settings.agent_default_retry_policy,
        enabled=True,
        trace_id=trace_id,
    )
    session.add(policy)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.execution_policy_created",
        entity_type="agent_execution_policy",
        entity_id=str(agent_id),
        payload={"policy_version": policy.policy_version},
        trace_id=trace_id,
    )
    return policy


async def set_execution_policy(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    agent_id: UUID,
    max_concurrent: int,
    execution_timeout_seconds: int,
    approval_timeout_seconds: int,
    max_context_size: int,
    retry_policy_id: str,
    enabled: bool = True,
    trace_id: str | None = None,
) -> AgentExecutionPolicy:
    """Create a new version of an execution policy (previous version retired)."""
    _validate_execution_args(
        max_concurrent=max_concurrent,
        execution_timeout_seconds=execution_timeout_seconds,
        approval_timeout_seconds=approval_timeout_seconds,
        max_context_size=max_context_size,
    )
    agent = await session.get(AgentRegistry, agent_id)
    if agent is None or agent.workspace_id != workspace_id:
        raise AgentPolicyError("agent not found in workspace")
    current = (
        await session.execute(
            select(AgentExecutionPolicy).where(
                AgentExecutionPolicy.workspace_id == workspace_id,
                AgentExecutionPolicy.agent_id == agent_id,
                AgentExecutionPolicy.is_current.is_(True),
            )
        )
    ).scalar_one_or_none()
    version = _next_version(current.policy_version) if current else "v1"
    if current is not None:
        await session.execute(
            update(AgentExecutionPolicy)
            .where(AgentExecutionPolicy.id == current.id)
            .values(is_current=False, updated_at=_now())
        )
    policy = AgentExecutionPolicy(
        workspace_id=workspace_id,
        agent_id=agent_id,
        policy_version=version,
        is_current=True,
        max_concurrent=max_concurrent,
        execution_timeout_seconds=execution_timeout_seconds,
        approval_timeout_seconds=approval_timeout_seconds,
        max_context_size=max_context_size,
        retry_policy_id=retry_policy_id,
        enabled=enabled,
        trace_id=trace_id,
    )
    session.add(policy)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.execution_policy_updated",
        entity_type="agent_execution_policy",
        entity_id=str(agent_id),
        payload={
            "policy_version": version,
            "execution_timeout_seconds": execution_timeout_seconds,
            "max_concurrent": max_concurrent,
        },
        trace_id=trace_id,
    )
    return policy


def _validate_execution_args(
    *,
    max_concurrent: int,
    execution_timeout_seconds: int,
    approval_timeout_seconds: int,
    max_context_size: int,
) -> None:
    if not 1 <= max_concurrent <= 50:
        raise AgentPolicyError("max_concurrent must be between 1 and 50")
    if not 1 <= execution_timeout_seconds <= 86400:
        raise AgentPolicyError("execution_timeout_seconds must be between 1 and 86400")
    if not 60 <= approval_timeout_seconds <= 2_592_000:
        raise AgentPolicyError("approval_timeout_seconds must be between 60 and 2592000")
    if not 100 <= max_context_size <= 1_000_000:
        raise AgentPolicyError("max_context_size must be between 100 and 1000000")


# --------------------------------------------------------------------------- #
# Budget policies
# --------------------------------------------------------------------------- #


async def get_budget_policy(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    agent_id: UUID,
    trace_id: str | None = None,
) -> AgentBudgetPolicy:
    """Return the current budget policy; seed defaults on first use."""
    policy = (
        await session.execute(
            select(AgentBudgetPolicy).where(
                AgentBudgetPolicy.workspace_id == workspace_id,
                AgentBudgetPolicy.agent_id == agent_id,
                AgentBudgetPolicy.is_current.is_(True),
            )
        )
    ).scalar_one_or_none()
    if policy is not None:
        return policy
    settings = get_settings()
    policy = AgentBudgetPolicy(
        workspace_id=workspace_id,
        agent_id=agent_id,
        policy_version="v1",
        is_current=True,
        monthly_budget=settings.agent_default_monthly_budget,
        max_cost_per_execution=settings.agent_default_max_cost_per_execution,
        alert_threshold=settings.agent_default_budget_alert_threshold,
        currency="USD",
        enabled=True,
        trace_id=trace_id,
    )
    session.add(policy)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.budget_policy_created",
        entity_type="agent_budget_policy",
        entity_id=str(agent_id),
        payload={"policy_version": policy.policy_version},
        trace_id=trace_id,
    )
    return policy


async def set_budget_policy(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    agent_id: UUID,
    monthly_budget: Decimal,
    max_cost_per_execution: Decimal,
    alert_threshold: Decimal,
    currency: str = "USD",
    enabled: bool = True,
    trace_id: str | None = None,
) -> AgentBudgetPolicy:
    """Create a new version of a budget policy (previous version retired)."""
    if monthly_budget <= 0:
        raise AgentPolicyError("monthly_budget must be > 0")
    if max_cost_per_execution <= 0:
        raise AgentPolicyError("max_cost_per_execution must be > 0")
    if not Decimal("0") < alert_threshold <= 1:
        raise AgentPolicyError("alert_threshold must be between 0 and 1")
    agent = await session.get(AgentRegistry, agent_id)
    if agent is None or agent.workspace_id != workspace_id:
        raise AgentPolicyError("agent not found in workspace")
    current = (
        await session.execute(
            select(AgentBudgetPolicy).where(
                AgentBudgetPolicy.workspace_id == workspace_id,
                AgentBudgetPolicy.agent_id == agent_id,
                AgentBudgetPolicy.is_current.is_(True),
            )
        )
    ).scalar_one_or_none()
    version = _next_version(current.policy_version) if current else "v1"
    if current is not None:
        await session.execute(
            update(AgentBudgetPolicy)
            .where(AgentBudgetPolicy.id == current.id)
            .values(is_current=False, updated_at=_now())
        )
    policy = AgentBudgetPolicy(
        workspace_id=workspace_id,
        agent_id=agent_id,
        policy_version=version,
        is_current=True,
        monthly_budget=monthly_budget,
        max_cost_per_execution=max_cost_per_execution,
        alert_threshold=alert_threshold,
        currency=currency,
        enabled=enabled,
        trace_id=trace_id,
    )
    session.add(policy)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.budget_policy_updated",
        entity_type="agent_budget_policy",
        entity_id=str(agent_id),
        payload={
            "policy_version": version,
            "monthly_budget": str(monthly_budget),
            "max_cost_per_execution": str(max_cost_per_execution),
        },
        trace_id=trace_id,
    )
    return policy
