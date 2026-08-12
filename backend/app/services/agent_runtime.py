"""Agent Runtime (M5.0): registry, task lifecycle, execution audit, tool gate.

The runtime is generic infrastructure - no concrete business agent is
implemented here. Every execution is fully audited (context snapshot, input,
output, model usage, cost, latency, trace_id) and every tool call passes the
Tool Registry whitelist plus the Permission Engine (L0-L3). High-risk (L3)
tools never execute: the execution stops at ``waiting_approval`` for a human
decision (approve/reject), matching the OS-wide human-in-the-loop rule.
"""

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_runtime import (
    EXECUTION_STATUSES,
    MEMORY_SOURCE_TYPES,
    PERMISSION_LEVELS,
    TASK_STATUSES,
    AgentEvaluation,
    AgentExecution,
    AgentMemory,
    AgentRegistry,
    AgentTask,
    AgentTool,
)
from app.models.customer import CustomerKnowledgeEntry
from app.models.marketing_learning import MarketingKnowledgeEntry
from app.models.product_intelligence import ProductKnowledgeEntry
from app.models.prompt import Prompt
from app.models.supply_chain import SupplyChainKnowledgeEntry
from app.schemas.agent_runtime import (
    AgentEvaluationCreate,
    AgentRegisterRequest,
    MemoryCreate,
    TaskCreate,
)
from app.services import (
    agent_policies,
    ai_evaluation,  # shared classification (single source)
    event_service,
    permission_engine,
    tool_gateway,
)

logger = logging.getLogger(__name__)

# Agent registry prompt naming convention: AGENT_<AGENT_ID>.
PROMPT_NAME_PREFIX = "AGENT_"

# Knowledge-domain -> table mapping for the agent memory grounding query.
_KNOWLEDGE_MODELS: dict[str, type] = {
    "product": ProductKnowledgeEntry,
    "marketing": MarketingKnowledgeEntry,
    "customer": CustomerKnowledgeEntry,
    "supply_chain": SupplyChainKnowledgeEntry,
}


class AgentRuntimeError(Exception):
    """Raised when an agent runtime operation cannot complete."""


class ToolPermissionError(AgentRuntimeError):
    """Raised when a tool call fails the whitelist/permission gate."""


class ToolNotFoundError(AgentRuntimeError):
    """Raised when a tool is not in the registry whitelist."""


def agent_prompt_name(agent_id: str) -> str:
    """Registry name of the versioned prompt bound to an agent."""
    return f"{PROMPT_NAME_PREFIX}{agent_id.upper()}"


# --------------------------------------------------------------------------- #
# Agent registry
# --------------------------------------------------------------------------- #


async def _load_agent_prompt(
    session: AsyncSession, *, workspace_id: UUID, agent: AgentRegistry
) -> Prompt | None:
    """Return the exact versioned prompt bound to an agent, if registered."""
    return (
        await session.execute(
            select(Prompt).where(
                Prompt.workspace_id == workspace_id,
                Prompt.name == agent_prompt_name(agent.agent_id),
                Prompt.version == agent.prompt_version,
                Prompt.status == "active",
            )
        )
    ).scalar_one_or_none()


async def register_agent(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    data: AgentRegisterRequest,
    trace_id: str | None = None,
) -> AgentRegistry:
    """Register (or update) an agent; its prompt version must exist."""
    prompt_name = agent_prompt_name(data.agent_id)
    prompt = (
        await session.execute(
            select(Prompt.id).where(
                Prompt.workspace_id == workspace_id,
                Prompt.name == prompt_name,
                Prompt.version == data.prompt_version,
                Prompt.status == "active",
            )
        )
    ).scalar_one_or_none()
    if prompt is None:
        raise AgentRuntimeError(
            f"active prompt '{prompt_name}' version '{data.prompt_version}' not found "
            "(register the prompt first)"
        )

    agent = (
        await session.execute(
            select(AgentRegistry).where(
                AgentRegistry.workspace_id == workspace_id,
                AgentRegistry.agent_id == data.agent_id,
            )
        )
    ).scalar_one_or_none()
    if agent is None:
        agent = AgentRegistry(
            workspace_id=workspace_id,
            agent_id=data.agent_id,
            name=data.name,
            domain=data.domain,
            version=data.version,
            status=data.status,
            model_provider=data.model_provider,
            model_name=data.model_name,
            prompt_version=data.prompt_version,
            permission_level=data.permission_level,
            description=data.description,
            trace_id=trace_id,
        )
        session.add(agent)
        await session.flush()
        await event_service.create_event(
            session,
            workspace_id=workspace_id,
            event_type="agent.registry_created",
            entity_type="agent",
            entity_id=str(agent.id),
            payload={
                "agent_id": data.agent_id,
                "domain": data.domain,
                "permission_level": data.permission_level,
                "prompt_version": data.prompt_version,
            },
            trace_id=trace_id,
        )
        logger.info("agent %s registered trace=%s", data.agent_id, trace_id)
        await session.refresh(agent)
        return agent

    agent.name = data.name
    agent.domain = data.domain
    agent.version = data.version
    agent.status = data.status
    agent.model_provider = data.model_provider
    agent.model_name = data.model_name
    agent.prompt_version = data.prompt_version
    agent.permission_level = data.permission_level
    agent.description = data.description
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.registry_updated",
        entity_type="agent",
        entity_id=str(agent.id),
        payload={
            "agent_id": data.agent_id,
            "permission_level": data.permission_level,
            "prompt_version": data.prompt_version,
        },
        trace_id=trace_id,
    )
    logger.info("agent %s updated trace=%s", data.agent_id, trace_id)
    await session.refresh(agent)
    return agent


async def get_agent(
    session: AsyncSession, *, workspace_id: UUID, agent_uuid: UUID
) -> AgentRegistry | None:
    """Return one registered agent by its registry row id."""
    return (
        await session.execute(
            select(AgentRegistry).where(
                AgentRegistry.workspace_id == workspace_id,
                AgentRegistry.id == agent_uuid,
            )
        )
    ).scalar_one_or_none()


async def get_agent_by_code(
    session: AsyncSession, *, workspace_id: UUID, agent_id: str
) -> AgentRegistry | None:
    """Return one registered agent by its logical agent_id."""
    return (
        await session.execute(
            select(AgentRegistry).where(
                AgentRegistry.workspace_id == workspace_id,
                AgentRegistry.agent_id == agent_id,
            )
        )
    ).scalar_one_or_none()


async def list_agents(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    domain: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[AgentRegistry], int]:
    """Query registered agents (workspace-scoped)."""
    filters = [AgentRegistry.workspace_id == workspace_id]
    if domain:
        filters.append(AgentRegistry.domain == domain)
    if status:
        filters.append(AgentRegistry.status == status)
    total = (
        await session.execute(select(func.count()).select_from(AgentRegistry).where(*filters))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                select(AgentRegistry)
                .where(*filters)
                .order_by(AgentRegistry.created_at.desc(), AgentRegistry.id)
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return list(rows), total


async def resolve_agent_prompt(
    session: AsyncSession, *, workspace_id: UUID, agent_uuid: UUID
) -> Prompt:
    """Resolve the exact versioned prompt bound to a registered agent."""
    agent = await get_agent(session, workspace_id=workspace_id, agent_uuid=agent_uuid)
    if agent is None:
        raise AgentRuntimeError("agent not found")
    prompt = await _load_agent_prompt(session, workspace_id=workspace_id, agent=agent)
    if prompt is None:
        raise AgentRuntimeError(
            f"active prompt '{agent_prompt_name(agent.agent_id)}' version "
            f"'{agent.prompt_version}' not found"
        )
    return prompt


# --------------------------------------------------------------------------- #
# Agent tasks
# --------------------------------------------------------------------------- #


async def create_task(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    data: TaskCreate,
    trace_id: str | None = None,
) -> AgentTask:
    """Create a task in ``pending`` for a registered, active agent.

    When ``idempotency_key`` is set, an existing task with the same
    (workspace, agent, key) is returned instead of creating a duplicate - the
    producer may safely retry, and the same work is never enqueued twice.
    """
    agent = await get_agent(session, workspace_id=workspace_id, agent_uuid=data.agent_id)
    if agent is None:
        raise AgentRuntimeError("agent not found")
    if agent.status != "active":
        raise AgentRuntimeError(f"agent '{agent.agent_id}' is not active")

    if data.idempotency_key:
        existing = (
            (
                await session.execute(
                    select(AgentTask).where(
                        AgentTask.workspace_id == workspace_id,
                        AgentTask.agent_id == data.agent_id,
                        AgentTask.idempotency_key == data.idempotency_key,
                    )
                )
            )
            .scalars()
            .first()
        )
        if existing is not None:
            await event_service.create_event(
                session,
                workspace_id=workspace_id,
                event_type="agent.task_idempotent_reused",
                entity_type="agent_task",
                entity_id=str(existing.id),
                payload={
                    "agent_id": agent.agent_id,
                    "idempotency_key": data.idempotency_key,
                },
                trace_id=trace_id,
            )
            logger.info(
                "task %s reused for idempotency_key=%s trace=%s",
                existing.id,
                data.idempotency_key,
                trace_id,
            )
            return existing

    task = AgentTask(
        workspace_id=workspace_id,
        agent_id=data.agent_id,
        input=data.input,
        status="pending",
        priority=data.priority,
        idempotency_key=data.idempotency_key,
        trace_id=trace_id,
    )
    session.add(task)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.task_created",
        entity_type="agent_task",
        entity_id=str(task.id),
        payload={"agent_id": agent.agent_id, "priority": data.priority},
        trace_id=trace_id,
    )
    logger.info("task %s created for agent %s trace=%s", task.id, agent.agent_id, trace_id)
    await session.refresh(task)
    return task


async def get_task(session: AsyncSession, *, workspace_id: UUID, task_id: UUID) -> AgentTask | None:
    """Return one task (workspace-scoped)."""
    return (
        await session.execute(
            select(AgentTask).where(
                AgentTask.workspace_id == workspace_id,
                AgentTask.id == task_id,
            )
        )
    ).scalar_one_or_none()


async def list_tasks(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    status: str | None = None,
    agent_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[AgentTask], int]:
    """Query tasks (workspace-scoped), newest first by priority."""
    filters = [AgentTask.workspace_id == workspace_id]
    if status:
        if status not in TASK_STATUSES:
            raise AgentRuntimeError(f"invalid task status '{status}'")
        filters.append(AgentTask.status == status)
    if agent_id is not None:
        filters.append(AgentTask.agent_id == agent_id)
    total = (
        await session.execute(select(func.count()).select_from(AgentTask).where(*filters))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                select(AgentTask)
                .where(*filters)
                .order_by(AgentTask.priority.desc(), AgentTask.created_at.desc(), AgentTask.id)
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return list(rows), total


async def cancel_task(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    task_id: UUID,
    reason: str | None = None,
    trace_id: str | None = None,
) -> AgentTask:
    """Cancel a pending/running/waiting_approval task (audited)."""
    task = await get_task(session, workspace_id=workspace_id, task_id=task_id)
    if task is None:
        raise AgentRuntimeError("task not found")
    if task.status not in ("pending", "running", "waiting_approval"):
        raise AgentRuntimeError(f"task already {task.status}; cannot cancel")
    task.status = "cancelled"
    task.error_message = reason or "cancelled"
    task.completed_at = datetime.now(UTC)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.task_cancelled",
        entity_type="agent_task",
        entity_id=str(task.id),
        payload={"reason": reason},
        trace_id=trace_id,
    )
    await session.refresh(task)
    return task


# --------------------------------------------------------------------------- #
# Agent executions
# --------------------------------------------------------------------------- #


async def _load_execution(
    session: AsyncSession, *, workspace_id: UUID, execution_id: UUID
) -> AgentExecution | None:
    return (
        await session.execute(
            select(AgentExecution).where(
                AgentExecution.workspace_id == workspace_id,
                AgentExecution.id == execution_id,
            )
        )
    ).scalar_one_or_none()


async def _set_task_status(
    session: AsyncSession,
    *,
    task_id: UUID,
    status: str,
    result: dict | None = None,
    error_message: str | None = None,
) -> None:
    task = await session.get(AgentTask, task_id)
    if task is None:
        return
    task.status = status
    if result is not None:
        task.result = result
    if error_message is not None:
        task.error_message = error_message
    if status in ("completed", "failed", "cancelled"):
        task.completed_at = datetime.now(UTC)
    if status == "running":
        task.started_at = datetime.now(UTC)


async def start_execution(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    task_id: UUID,
    trace_id: str | None = None,
) -> AgentExecution:
    """Start a pending task: task -> running, execution row created."""
    task = await get_task(session, workspace_id=workspace_id, task_id=task_id)
    if task is None:
        raise AgentRuntimeError("task not found")
    if task.status != "pending":
        raise AgentRuntimeError(f"task already {task.status}; only pending tasks can start")
    agent = await get_agent(session, workspace_id=workspace_id, agent_uuid=task.agent_id)
    if agent is None or agent.status != "active":
        raise AgentRuntimeError("agent not found or not active")

    context_snapshot = {
        "agent_id": agent.agent_id,
        "agent_name": agent.name,
        "domain": agent.domain,
        "version": agent.version,
        "prompt_version": agent.prompt_version,
        "model_provider": agent.model_provider,
        "model_name": agent.model_name,
        "permission_level": agent.permission_level,
    }
    execution = AgentExecution(
        workspace_id=workspace_id,
        agent_id=agent.id,
        task_id=task.id,
        context_snapshot=context_snapshot,
        input=task.input,
        status="running",
        started_at=datetime.now(UTC),
        trace_id=trace_id,
    )
    session.add(execution)
    await session.flush()
    await _set_task_status(session, task_id=task.id, status="running")
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.execution_started",
        entity_type="agent_execution",
        entity_id=str(execution.id),
        payload={
            "agent_id": agent.agent_id,
            "task_id": str(task.id),
            "permission_level": agent.permission_level,
        },
        trace_id=trace_id,
    )
    logger.info("execution %s started for task %s trace=%s", execution.id, task.id, trace_id)
    await session.refresh(execution)
    return execution


async def complete_execution(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    execution_id: UUID,
    output: dict,
    provider: str,
    model: str,
    tokens: dict,
    cost: Decimal,
    latency_ms: int,
    trace_id: str | None = None,
) -> AgentExecution:
    """Complete a running execution and persist the model usage audit."""
    execution = await _load_execution(session, workspace_id=workspace_id, execution_id=execution_id)
    if execution is None:
        raise AgentRuntimeError("execution not found")
    if execution.status != "running":
        raise AgentRuntimeError(f"execution already {execution.status}; cannot complete")
    execution.output = output
    execution.provider = provider
    execution.model = model
    execution.tokens = tokens
    execution.cost = cost
    execution.latency_ms = latency_ms
    execution.status = "completed"
    execution.completed_at = datetime.now(UTC)
    await session.flush()
    await _set_task_status(session, task_id=execution.task_id, status="completed", result=output)
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.execution_completed",
        entity_type="agent_execution",
        entity_id=str(execution.id),
        payload={
            "model": model,
            "tokens": tokens,
            "cost": str(cost),
            "latency_ms": latency_ms,
        },
        trace_id=trace_id,
    )
    logger.info("execution %s completed trace=%s", execution.id, trace_id)
    await session.refresh(execution)
    return execution


async def fail_execution(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    execution_id: UUID,
    error_message: str,
    error_type: str | None = None,
    fail_task: bool = True,
    trace_id: str | None = None,
) -> AgentExecution:
    """Fail a running execution and (by default) mark the task failed.

    ``fail_task=False`` lets the worker keep the task open for a retry while
    the failing attempt is fully audited (execution row + event).
    """
    execution = await _load_execution(session, workspace_id=workspace_id, execution_id=execution_id)
    if execution is None:
        raise AgentRuntimeError("execution not found")
    if execution.status != "running":
        raise AgentRuntimeError(f"execution already {execution.status}; cannot fail")
    execution.status = "failed"
    execution.error_message = error_message[:1000]
    execution.error_type = (error_type or "unknown")[:32]
    execution.completed_at = datetime.now(UTC)
    await session.flush()
    if fail_task:
        await _set_task_status(
            session, task_id=execution.task_id, status="failed", error_message=error_message[:1000]
        )
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.execution_failed",
        entity_type="agent_execution",
        entity_id=str(execution.id),
        payload={"error_message": error_message[:1000], "error_type": execution.error_type},
        trace_id=trace_id,
    )
    logger.warning("execution %s failed: %s trace=%s", execution.id, error_message, trace_id)
    await session.refresh(execution)
    return execution


async def _waiting_approval(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    execution: AgentExecution,
    reason: str,
    trace_id: str | None = None,
) -> AgentExecution:
    """Move an execution + its task to waiting_approval (audited)."""
    execution.status = "waiting_approval"
    execution.approval = {"reason": reason, "requested_at": datetime.now(UTC).isoformat()}
    await session.flush()
    await _set_task_status(session, task_id=execution.task_id, status="waiting_approval")
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.execution_waiting_approval",
        entity_type="agent_execution",
        entity_id=str(execution.id),
        payload={"reason": reason},
        trace_id=trace_id,
    )
    await session.refresh(execution)
    return execution


async def approve_execution(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    execution_id: UUID,
    actor: str,
    note: str | None = None,
    trace_id: str | None = None,
) -> AgentExecution:
    """Human approval: waiting_approval -> completed (approval audited)."""
    execution = await _load_execution(session, workspace_id=workspace_id, execution_id=execution_id)
    if execution is None:
        raise AgentRuntimeError("execution not found")
    if execution.status != "waiting_approval":
        raise AgentRuntimeError(
            f"execution already {execution.status}; "
            "only waiting_approval executions can be approved"
        )
    execution.status = "completed"
    execution.approval = {
        "decision": "approved",
        "actor": actor,
        "note": note,
        "decided_at": datetime.now(UTC).isoformat(),
    }
    execution.completed_at = datetime.now(UTC)
    await session.flush()
    await _set_task_status(session, task_id=execution.task_id, status="completed")
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.execution_approved",
        entity_type="agent_execution",
        entity_id=str(execution.id),
        payload={"actor": actor, "note": note},
        trace_id=trace_id,
    )
    logger.info("execution %s approved by %s trace=%s", execution.id, actor, trace_id)
    await session.refresh(execution)
    return execution


async def reject_execution(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    execution_id: UUID,
    actor: str,
    note: str | None = None,
    trace_id: str | None = None,
) -> AgentExecution:
    """Human rejection: waiting_approval -> rejected; task -> failed."""
    execution = await _load_execution(session, workspace_id=workspace_id, execution_id=execution_id)
    if execution is None:
        raise AgentRuntimeError("execution not found")
    if execution.status != "waiting_approval":
        raise AgentRuntimeError(
            f"execution already {execution.status}; "
            "only waiting_approval executions can be rejected"
        )
    execution.status = "rejected"
    execution.approval = {
        "decision": "rejected",
        "actor": actor,
        "note": note,
        "decided_at": datetime.now(UTC).isoformat(),
    }
    execution.completed_at = datetime.now(UTC)
    await session.flush()
    await _set_task_status(
        session,
        task_id=execution.task_id,
        status="failed",
        error_message=f"rejected by human: {note}" if note else "rejected by human",
    )
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.execution_rejected",
        entity_type="agent_execution",
        entity_id=str(execution.id),
        payload={"actor": actor, "note": note},
        trace_id=trace_id,
    )
    logger.info("execution %s rejected by %s trace=%s", execution.id, actor, trace_id)
    await session.refresh(execution)
    return execution


async def list_executions(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    task_id: UUID | None = None,
    agent_id: UUID | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[AgentExecution], int]:
    """Query execution audit rows (workspace-scoped), newest first."""
    filters = [AgentExecution.workspace_id == workspace_id]
    if task_id is not None:
        filters.append(AgentExecution.task_id == task_id)
    if agent_id is not None:
        filters.append(AgentExecution.agent_id == agent_id)
    if status:
        if status not in EXECUTION_STATUSES:
            raise AgentRuntimeError(f"invalid execution status '{status}'")
        filters.append(AgentExecution.status == status)
    total = (
        await session.execute(select(func.count()).select_from(AgentExecution).where(*filters))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                select(AgentExecution)
                .where(*filters)
                .order_by(AgentExecution.created_at.desc(), AgentExecution.id)
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return list(rows), total


# --------------------------------------------------------------------------- #
# Tool calls (whitelist + permission gate, fully audited)
# --------------------------------------------------------------------------- #


async def execute_tool_call(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    execution_id: UUID,
    tool_name: str,
    arguments: dict,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Gate one tool call through the registry + permission engine.

    Outcomes: ``allowed`` (recorded; handlers bind in a later milestone),
    ``requires_approval`` (L3 high-risk -> execution waits for a human), or
    ``denied`` (raises ToolPermissionError -> API 403). Every outcome is
    appended to the execution audit and emitted as an event.
    """
    execution = await _load_execution(session, workspace_id=workspace_id, execution_id=execution_id)
    if execution is None:
        raise AgentRuntimeError("execution not found")
    agent = await get_agent(session, workspace_id=workspace_id, agent_uuid=execution.agent_id)
    if agent is None:
        raise AgentRuntimeError("agent not found")
    tool = (
        await session.execute(
            select(AgentTool).where(
                AgentTool.workspace_id == workspace_id,
                AgentTool.tool_name == tool_name,
            )
        )
    ).scalar_one_or_none()
    if tool is None:
        raise ToolNotFoundError(f"tool '{tool_name}' is not registered (whitelist)")

    record: dict[str, Any] = {
        "tool_name": tool_name,
        "arguments": arguments,
        "tool_level": tool.permission_level,
        "called_at": datetime.now(UTC).isoformat(),
    }
    try:
        decision = permission_engine.check_tool(
            agent_level=agent.permission_level,
            tool_level=tool.permission_level,
            tool_name=tool_name,
            enabled=tool.enabled,
        )
    except permission_engine.PermissionError as exc:
        record["status"] = "denied"
        record["reason"] = str(exc)
        execution.tool_calls = [*execution.tool_calls, record]
        await session.flush()
        await event_service.create_event(
            session,
            workspace_id=workspace_id,
            event_type="agent.tool_call_denied",
            entity_type="agent_execution",
            entity_id=str(execution.id),
            payload={"tool_name": tool_name, "reason": str(exc)},
            trace_id=trace_id,
        )
        raise ToolPermissionError(str(exc)) from exc

    record["status"] = decision["status"]
    execution.tool_calls = [*execution.tool_calls, record]
    if decision["status"] == "requires_approval":
        # M5.1: L3 approval deadline comes from the versioned execution policy.
        policy = await agent_policies.get_execution_policy(
            session, workspace_id=workspace_id, agent_id=agent.id, trace_id=trace_id
        )
        execution.approval_deadline = datetime.now(UTC) + timedelta(
            seconds=policy.approval_timeout_seconds
        )
        await session.flush()
        await _waiting_approval(
            session,
            workspace_id=workspace_id,
            execution=execution,
            reason=f"high-risk tool '{tool_name}' requires human approval",
            trace_id=trace_id,
        )
        await event_service.create_event(
            session,
            workspace_id=workspace_id,
            event_type="agent.tool_call_requires_approval",
            entity_type="agent_execution",
            entity_id=str(execution.id),
            payload={
                "tool_name": tool_name,
                "tool_level": tool.permission_level,
                "approval_deadline": execution.approval_deadline.isoformat(),
            },
            trace_id=trace_id,
        )
        return {
            "status": "requires_approval",
            "requires_approval": True,
            "tool_name": tool_name,
            "execution_id": execution.id,
            "approval_deadline": execution.approval_deadline.isoformat(),
            "message": f"high-risk tool '{tool_name}' requires human approval",
        }

    # L0-L2: run the bound handler when present; keep M5.0 audit-only passthrough
    # for whitelist-only tools (no handler bound yet).
    if tool.handler_name:
        handler = tool_gateway.get_handler(tool.handler_name)
        if handler is None:
            record["status"] = "denied"
            record["reason"] = f"handler '{tool.handler_name}' is not registered"
            execution.tool_calls = [*execution.tool_calls, record]
            await session.flush()
            await event_service.create_event(
                session,
                workspace_id=workspace_id,
                event_type="agent.tool_call_denied",
                entity_type="agent_execution",
                entity_id=str(execution.id),
                payload={"tool_name": tool_name, "reason": record["reason"]},
                trace_id=trace_id,
            )
            raise ToolPermissionError(record["reason"])
        try:
            handler_output = await tool_gateway.execute_handler(
                session=session,
                workspace_id=workspace_id,
                agent=agent,
                execution=execution,
                tool=tool,
                arguments=arguments,
                trace_id=trace_id,
            )
        except Exception as exc:  # noqa: BLE001 - handler errors deny the call
            record["status"] = "denied"
            record["reason"] = str(exc)[:400]
            execution.tool_calls = [*execution.tool_calls, record]
            await session.flush()
            await event_service.create_event(
                session,
                workspace_id=workspace_id,
                event_type="agent.tool_call_denied",
                entity_type="agent_execution",
                entity_id=str(execution.id),
                payload={"tool_name": tool_name, "reason": record["reason"]},
                trace_id=trace_id,
            )
            raise ToolPermissionError(record["reason"]) from exc
        record["handler_name"] = tool.handler_name
        record["output"] = handler_output
        execution.tool_calls = [*execution.tool_calls, record]
        await event_service.create_event(
            session,
            workspace_id=workspace_id,
            event_type="agent.tool_call_executed",
            entity_type="agent_execution",
            entity_id=str(execution.id),
            payload={"tool_name": tool_name, "handler_name": tool.handler_name},
            trace_id=trace_id,
        )
        await session.refresh(execution)
        return {
            "status": "allowed",
            "requires_approval": False,
            "tool_name": tool_name,
            "execution_id": execution.id,
            "handler_name": tool.handler_name,
            "output": handler_output,
            "message": f"tool '{tool_name}' executed handler '{tool.handler_name}'",
        }

    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.tool_call_allowed",
        entity_type="agent_execution",
        entity_id=str(execution.id),
        payload={"tool_name": tool_name, "tool_level": tool.permission_level},
        trace_id=trace_id,
    )
    logger.info("tool call %s allowed on execution %s trace=%s", tool_name, execution.id, trace_id)
    await session.refresh(execution)
    return {
        "status": "allowed",
        "requires_approval": False,
        "tool_name": tool_name,
        "execution_id": execution.id,
        "message": f"tool '{tool_name}' passed the gate and was recorded (no handler bound)",
    }


# --------------------------------------------------------------------------- #
# Tool registry
# --------------------------------------------------------------------------- #


async def register_tool(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    tool_name: str,
    description: str | None,
    permission_level: str,
    enabled: bool,
    category: str | None = None,
    handler_name: str | None = None,
    args_schema: dict | None = None,
    trace_id: str | None = None,
) -> AgentTool:
    """Register (or update) one tool in the whitelist (M5.1 binds handlers)."""
    if permission_level not in PERMISSION_LEVELS:
        raise AgentRuntimeError(f"invalid permission level '{permission_level}'")
    tool = (
        await session.execute(
            select(AgentTool).where(
                AgentTool.workspace_id == workspace_id,
                AgentTool.tool_name == tool_name,
            )
        )
    ).scalar_one_or_none()
    if tool is None:
        tool = AgentTool(
            workspace_id=workspace_id,
            tool_name=tool_name,
            description=description,
            permission_level=permission_level,
            enabled=enabled,
            category=category,
            handler_name=handler_name,
            args_schema=args_schema or {},
            trace_id=trace_id,
        )
        session.add(tool)
        await session.flush()
        await event_service.create_event(
            session,
            workspace_id=workspace_id,
            event_type="agent.tool_registered",
            entity_type="agent_tool",
            entity_id=tool_name,
            payload={"tool_name": tool_name, "permission_level": permission_level},
            trace_id=trace_id,
        )
        logger.info("tool %s registered (level %s) trace=%s", tool_name, permission_level, trace_id)
        await session.refresh(tool)
        return tool

    tool.description = description
    tool.permission_level = permission_level
    tool.enabled = enabled
    tool.category = category
    tool.handler_name = handler_name
    if args_schema is not None:
        tool.args_schema = args_schema
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.tool_updated",
        entity_type="agent_tool",
        entity_id=tool_name,
        payload={"tool_name": tool_name, "permission_level": permission_level, "enabled": enabled},
        trace_id=trace_id,
    )
    await session.refresh(tool)
    return tool


async def update_tool_enabled(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    tool_name: str,
    enabled: bool,
    description: str | None = None,
    handler_name: str | None = None,
    args_schema: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> AgentTool:
    """Enable/disable a registered tool and (optionally) rebind its handler."""
    tool = (
        await session.execute(
            select(AgentTool).where(
                AgentTool.workspace_id == workspace_id,
                AgentTool.tool_name == tool_name,
            )
        )
    ).scalar_one_or_none()
    if tool is None:
        raise AgentRuntimeError("tool not found")
    tool.enabled = enabled
    if description is not None:
        tool.description = description
    if handler_name is not None:
        tool.handler_name = handler_name
    if args_schema is not None:
        tool.args_schema = args_schema
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.tool_updated",
        entity_type="agent_tool",
        entity_id=tool_name,
        payload={"tool_name": tool_name, "enabled": enabled},
        trace_id=trace_id,
    )
    await session.refresh(tool)
    return tool


async def list_tools(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    enabled: bool | None = None,
    limit: int = 100,
) -> list[AgentTool]:
    """List the tool registry whitelist."""
    stmt = select(AgentTool).where(AgentTool.workspace_id == workspace_id)
    if enabled is not None:
        stmt = stmt.where(AgentTool.enabled == enabled)
    stmt = stmt.order_by(AgentTool.tool_name).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


# --------------------------------------------------------------------------- #
# Agent memory (grounded in the four knowledge domains)
# --------------------------------------------------------------------------- #


async def store_memory(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    data: MemoryCreate,
    trace_id: str | None = None,
) -> AgentMemory:
    """Store one agent memory entry (optionally linked to an agent)."""
    if data.source_type not in MEMORY_SOURCE_TYPES:
        raise AgentRuntimeError(f"invalid source_type '{data.source_type}'")
    if data.agent_id is not None:
        agent = await get_agent(session, workspace_id=workspace_id, agent_uuid=data.agent_id)
        if agent is None:
            raise AgentRuntimeError("agent not found")
    memory = AgentMemory(
        workspace_id=workspace_id,
        agent_id=data.agent_id,
        domain=data.domain,
        source_type=data.source_type,
        source_id=data.source_id,
        content=data.content,
        tags=data.tags,
        meta=data.meta,
        trace_id=trace_id,
    )
    session.add(memory)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.memory_stored",
        entity_type="agent_memory",
        entity_id=str(memory.id),
        payload={"domain": data.domain, "source_type": data.source_type},
        trace_id=trace_id,
    )
    logger.info("memory %s stored (%s) trace=%s", memory.id, data.domain, trace_id)
    await session.refresh(memory)
    return memory


async def search_memory(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    domain: str | None = None,
    agent_id: UUID | None = None,
    source_type: str | None = None,
    keyword: str | None = None,
    limit: int = 50,
) -> list[AgentMemory]:
    """Query agent memory with domain/agent/source filters and keyword search."""
    filters = [AgentMemory.workspace_id == workspace_id]
    if domain:
        filters.append(AgentMemory.domain == domain)
    if agent_id is not None:
        filters.append(AgentMemory.agent_id == agent_id)
    if source_type:
        filters.append(AgentMemory.source_type == source_type)
    stmt = select(AgentMemory).where(*filters)
    if keyword:
        stmt = stmt.where(AgentMemory.content.ilike(f"%{keyword}%"))
    stmt = stmt.order_by(AgentMemory.created_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


async def knowledge_snapshot(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    domain: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Pull recent knowledge entries for a domain (agent grounding context).

    Connects agent memory to the product / marketing / customer / supply
    chain knowledge tables so future agents can be grounded in accumulated
    evidence without reading raw business tables.
    """
    model = _KNOWLEDGE_MODELS.get(domain)
    if model is None:
        raise AgentRuntimeError(f"no knowledge source for domain '{domain}'")
    rows = (
        (
            await session.execute(
                select(model)
                .where(model.workspace_id == workspace_id)  # type: ignore[attr-defined]
                .order_by(model.created_at.desc())  # type: ignore[attr-defined]
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    snapshot: list[dict[str, Any]] = []
    for row in rows:
        snapshot.append(
            {
                "source_type": f"{domain}_knowledge",
                "source_id": str(row.id),
                "entry_type": getattr(row, "entry_type", None),
                "category": getattr(row, "category", None),
                "title": getattr(row, "title", None),
                "content": getattr(row, "content", ""),
                "tags": getattr(row, "tags", []),
                "confidence": (
                    str(confidence)
                    if (confidence := getattr(row, "confidence", None)) is not None
                    else None
                ),
                "created_at": row.created_at.isoformat(),
            }
        )
    return snapshot


# --------------------------------------------------------------------------- #
# Agent evaluation (prediction vs actual, calibration)
# --------------------------------------------------------------------------- #


async def record_evaluation(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    data: AgentEvaluationCreate,
    trace_id: str | None = None,
) -> AgentEvaluation:
    """Record one agent evaluation with deterministic accuracy/calibration.

    Classification is delegated to the shared ``ai_evaluation`` module
    (confidence buckets, success flags, error types) so the M5 agent rows and
    the M2.3 product-domain rows never drift apart (single source of truth).
    """
    if data.agent_id is not None:
        agent = await get_agent(session, workspace_id=workspace_id, agent_uuid=data.agent_id)
        if agent is None:
            raise AgentRuntimeError("agent not found")

    accuracy = ai_evaluation.compute_accuracy(data.prediction, data.actual_result)
    confidence = ai_evaluation._prediction_confidence(data.prediction)
    decision_match = accuracy.get("decision_match")
    success_flag = ai_evaluation._determine_success(
        data.prediction, data.actual_result, decision_match
    )
    prediction_result = (
        "success" if success_flag is True else "failure" if success_flag is False else "unknown"
    )
    error_type = (
        ai_evaluation._error_type(data.prediction, data.actual_result, decision_match)
        if success_flag is False
        else None
    )

    calibration = {
        "confidence": str(confidence) if confidence is not None else None,
        "bucket": ai_evaluation._confidence_bucket(confidence),
        "prediction_result": prediction_result,
        "success_flag": success_flag,
        "sample_size": 1,
    }

    evaluation = AgentEvaluation(
        workspace_id=workspace_id,
        agent_id=data.agent_id,
        prediction=data.prediction,
        actual_result=data.actual_result,
        accuracy=accuracy,
        calibration=calibration,
        prediction_result=prediction_result,
        error_type=error_type,
        success_flag=success_flag,
        confidence=confidence,
        confidence_bucket=ai_evaluation._confidence_bucket(confidence),
        human_rating=data.human_rating,
        notes=data.notes,
        trace_id=trace_id,
    )
    session.add(evaluation)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.evaluation_recorded",
        entity_type="agent_evaluation",
        entity_id=str(evaluation.id),
        payload={
            "prediction_result": prediction_result,
            "error_type": error_type,
            "confidence_bucket": ai_evaluation._confidence_bucket(confidence),
        },
        trace_id=trace_id,
    )
    logger.info("evaluation %s recorded (%s) trace=%s", evaluation.id, prediction_result, trace_id)
    await session.refresh(evaluation)
    return evaluation


async def list_evaluations(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    agent_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[AgentEvaluation], int]:
    """Query agent evaluations (workspace-scoped), newest first."""
    filters = [AgentEvaluation.workspace_id == workspace_id]
    if agent_id is not None:
        filters.append(AgentEvaluation.agent_id == agent_id)
    total = (
        await session.execute(select(func.count()).select_from(AgentEvaluation).where(*filters))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                select(AgentEvaluation)
                .where(*filters)
                .order_by(AgentEvaluation.created_at.desc(), AgentEvaluation.id)
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return list(rows), total
