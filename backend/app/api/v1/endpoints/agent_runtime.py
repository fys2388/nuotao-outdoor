"""Agent Runtime Foundation endpoints (M5.0).

Registry / tasks / executions / tool whitelist / memory / evaluations. The
runtime is generic infrastructure - no concrete business agent is exposed.
High-risk (L3) tool calls stop at ``waiting_approval`` for a human decision;
the API never auto-executes business actions.
"""

import logging
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import resolve_actor
from app.core.database import get_db
from app.core.tracing import get_trace_id
from app.core.workspace import get_workspace_id
from app.schemas.agent_runtime import (
    AgentEvaluationCreate,
    AgentEvaluationOut,
    AgentOut,
    AgentRegisterRequest,
    ExecutionApproveRequest,
    ExecutionCompleteRequest,
    ExecutionFailRequest,
    ExecutionOut,
    ExecutionStartRequest,
    MemoryCreate,
    MemoryOut,
    TaskCreate,
    TaskOut,
    ToolCallOut,
    ToolCallRequest,
    ToolOut,
    ToolRegisterRequest,
    ToolUpdateRequest,
)
from app.services import agent_runtime, event_service, task_queue

router = APIRouter(tags=["agent-runtime"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
WorkspaceId = Annotated[UUID, Depends(get_workspace_id)]


def _http_error(exc: agent_runtime.AgentRuntimeError) -> HTTPException:
    """Map runtime errors: missing resources -> 404, state/validation -> 400."""
    if "not found" in str(exc):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _tool_error(exc: Exception) -> HTTPException:
    """Map tool-call errors: unknown tool -> 404, permission -> 403."""
    if isinstance(exc, agent_runtime.ToolNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, agent_runtime.ToolPermissionError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    return _http_error(exc)


# --------------------------------------------------------------------------- #
# Agent registry + prompt resolution
# --------------------------------------------------------------------------- #


@router.post(
    "/agent-registry",
    response_model=AgentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register (or update) an agent in the runtime registry",
)
async def register_agent(
    body: AgentRegisterRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> AgentOut:
    """Register an agent; its versioned prompt must exist in the registry."""
    try:
        agent = await agent_runtime.register_agent(
            db, workspace_id=workspace_id, data=body, trace_id=get_trace_id()
        )
    except agent_runtime.AgentRuntimeError as exc:
        raise _http_error(exc) from exc
    return AgentOut.model_validate(agent)


@router.get(
    "/agent-registry",
    response_model=list[AgentOut],
    summary="List registered agents",
)
async def list_agents(
    db: DbSession,
    workspace_id: WorkspaceId,
    domain: Annotated[str | None, Query()] = None,
    agent_status: Annotated[str | None, Query(alias="status")] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[AgentOut]:
    """Return registered agents, newest first, workspace-scoped."""
    agents, _total = await agent_runtime.list_agents(
        db,
        workspace_id=workspace_id,
        domain=domain,
        status=agent_status,
        limit=min(limit, 200),
        offset=max(offset, 0),
    )
    return [AgentOut.model_validate(agent) for agent in agents]


@router.get(
    "/agent-registry/{agent_uuid}",
    response_model=AgentOut,
    summary="Get one registered agent",
)
async def get_agent(
    agent_uuid: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> AgentOut:
    """Return one registered agent by its registry row id."""
    agent = await agent_runtime.get_agent(db, workspace_id=workspace_id, agent_uuid=agent_uuid)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="agent not found")
    return AgentOut.model_validate(agent)


@router.get(
    "/agent-registry/{agent_uuid}/prompt",
    response_model=dict,
    summary="Resolve the versioned prompt bound to an agent",
)
async def resolve_agent_prompt(
    agent_uuid: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> dict:
    """Return the agent's exact active prompt (name/version/template)."""
    try:
        prompt = await agent_runtime.resolve_agent_prompt(
            db, workspace_id=workspace_id, agent_uuid=agent_uuid
        )
    except agent_runtime.AgentRuntimeError as exc:
        raise _http_error(exc) from exc
    return {
        "prompt_id": prompt.prompt_id,
        "name": prompt.name,
        "version": prompt.version,
        "status": prompt.status,
        "template": prompt.template,
        "variables": prompt.variables,
    }


# --------------------------------------------------------------------------- #
# Agent tasks
# --------------------------------------------------------------------------- #


@router.post(
    "/agent-tasks",
    response_model=TaskOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create an agent task (status=pending)",
)
async def create_task(
    body: TaskCreate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> TaskOut:
    """Create a pending task and enqueue it on the Redis-Stream queue.

    The DB row is the source of truth; if enqueueing fails the task stays
    ``pending`` and the reconciliation sweeper re-enqueues it later.
    """
    try:
        task = await agent_runtime.create_task(
            db, workspace_id=workspace_id, data=body, trace_id=get_trace_id()
        )
    except agent_runtime.AgentRuntimeError as exc:
        raise _http_error(exc) from exc
    try:
        backend = task_queue.get_queue_backend()
        # A reused idempotency-key task was already enqueued by its first
        # POST; never double-enqueue the same work.
        if task.enqueued_at is None:
            await task_queue.enqueue_task(
                backend,
                workspace_id=workspace_id,
                task_id=task.id,
                attempt=1,
                idempotency_key=task.idempotency_key,
            )
            task.enqueued_at = datetime.now(UTC)
            await db.flush()
        await event_service.create_event(
            db,
            workspace_id=workspace_id,
            event_type="agent.task_enqueued",
            entity_type="agent_task",
            entity_id=str(task.id),
            payload={"attempt": 1},
            trace_id=get_trace_id(),
        )
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "task %s enqueue failed (%s) trace=%s; reconciliation will retry",
            task.id,
            exc,
            get_trace_id(),
        )
        await event_service.create_event(
            db,
            workspace_id=workspace_id,
            event_type="agent.task_enqueue_failed",
            entity_type="agent_task",
            entity_id=str(task.id),
            payload={"error": str(exc)[:300]},
            trace_id=get_trace_id(),
        )
    await db.refresh(task)
    return TaskOut.model_validate(task)


@router.get(
    "/agent-tasks",
    response_model=list[TaskOut],
    summary="List agent tasks",
)
async def list_tasks(
    db: DbSession,
    workspace_id: WorkspaceId,
    task_status: Annotated[str | None, Query(alias="status")] = None,
    agent_id: Annotated[UUID | None, Query()] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TaskOut]:
    """Return tasks, newest first by priority, workspace-scoped."""
    tasks, _total = await agent_runtime.list_tasks(
        db,
        workspace_id=workspace_id,
        status=task_status,
        agent_id=agent_id,
        limit=min(limit, 200),
        offset=max(offset, 0),
    )
    return [TaskOut.model_validate(task) for task in tasks]


@router.get(
    "/agent-tasks/{task_id}",
    response_model=TaskOut,
    summary="Get one agent task",
)
async def get_task(
    task_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> TaskOut:
    """Return one task (workspace-scoped)."""
    task = await agent_runtime.get_task(db, workspace_id=workspace_id, task_id=task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    return TaskOut.model_validate(task)


@router.post(
    "/agent-tasks/{task_id}/cancel",
    response_model=TaskOut,
    summary="Cancel a pending/running/waiting_approval task",
)
async def cancel_task(
    task_id: UUID,
    body: ExecutionApproveRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> TaskOut:
    """Cancel the task; the reason is recorded as its error_message."""
    try:
        task = await agent_runtime.cancel_task(
            db,
            workspace_id=workspace_id,
            task_id=task_id,
            reason=body.note,
            trace_id=get_trace_id(),
        )
    except agent_runtime.AgentRuntimeError as exc:
        raise _http_error(exc) from exc
    return TaskOut.model_validate(task)


# --------------------------------------------------------------------------- #
# Agent executions (audit + human-in-the-loop)
# --------------------------------------------------------------------------- #


@router.post(
    "/agent-executions",
    response_model=ExecutionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Start an execution for a pending task",
)
async def start_execution(
    body: ExecutionStartRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ExecutionOut:
    """Start the task: status running + execution audit row created."""
    try:
        execution = await agent_runtime.start_execution(
            db, workspace_id=workspace_id, task_id=body.task_id, trace_id=get_trace_id()
        )
    except agent_runtime.AgentRuntimeError as exc:
        raise _http_error(exc) from exc
    return ExecutionOut.model_validate(execution)


@router.get(
    "/agent-executions",
    response_model=list[ExecutionOut],
    summary="List execution audit rows",
)
async def list_executions(
    db: DbSession,
    workspace_id: WorkspaceId,
    task_id: Annotated[UUID | None, Query()] = None,
    agent_id: Annotated[UUID | None, Query()] = None,
    execution_status: Annotated[str | None, Query(alias="status")] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[ExecutionOut]:
    """Return execution audit rows, newest first, workspace-scoped."""
    executions, _total = await agent_runtime.list_executions(
        db,
        workspace_id=workspace_id,
        task_id=task_id,
        agent_id=agent_id,
        status=execution_status,
        limit=min(limit, 200),
        offset=max(offset, 0),
    )
    return [ExecutionOut.model_validate(execution) for execution in executions]


@router.post(
    "/agent-executions/{execution_id}/complete",
    response_model=ExecutionOut,
    summary="Complete a running execution with model usage metrics",
)
async def complete_execution(
    execution_id: UUID,
    body: ExecutionCompleteRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ExecutionOut:
    """Persist output + provider/model/tokens/cost/latency; task -> completed."""
    try:
        execution = await agent_runtime.complete_execution(
            db,
            workspace_id=workspace_id,
            execution_id=execution_id,
            output=body.output,
            provider=body.provider,
            model=body.model,
            tokens=body.tokens,
            cost=body.cost,
            latency_ms=body.latency_ms,
            trace_id=get_trace_id(),
        )
    except agent_runtime.AgentRuntimeError as exc:
        raise _http_error(exc) from exc
    return ExecutionOut.model_validate(execution)


@router.post(
    "/agent-executions/{execution_id}/fail",
    response_model=ExecutionOut,
    summary="Fail a running execution",
)
async def fail_execution(
    execution_id: UUID,
    body: ExecutionFailRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ExecutionOut:
    """Mark the execution + task failed with the error message."""
    try:
        execution = await agent_runtime.fail_execution(
            db,
            workspace_id=workspace_id,
            execution_id=execution_id,
            error_message=body.error_message,
            trace_id=get_trace_id(),
        )
    except agent_runtime.AgentRuntimeError as exc:
        raise _http_error(exc) from exc
    return ExecutionOut.model_validate(execution)


@router.post(
    "/agent-executions/{execution_id}/approve",
    response_model=ExecutionOut,
    summary="Approve a waiting_approval execution (human-in-the-loop)",
)
async def approve_execution(
    execution_id: UUID,
    body: ExecutionApproveRequest,
    request: Request,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ExecutionOut:
    """Human approval: waiting_approval -> completed (audited)."""
    try:
        execution = await agent_runtime.approve_execution(
            db,
            workspace_id=workspace_id,
            execution_id=execution_id,
            actor=resolve_actor(request, body.actor),
            note=body.note,
            trace_id=get_trace_id(),
        )
    except agent_runtime.AgentRuntimeError as exc:
        raise _http_error(exc) from exc
    return ExecutionOut.model_validate(execution)


@router.post(
    "/agent-executions/{execution_id}/reject",
    response_model=ExecutionOut,
    summary="Reject a waiting_approval execution (human-in-the-loop)",
)
async def reject_execution(
    execution_id: UUID,
    body: ExecutionApproveRequest,
    request: Request,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ExecutionOut:
    """Human rejection: waiting_approval -> rejected; task -> failed."""
    try:
        execution = await agent_runtime.reject_execution(
            db,
            workspace_id=workspace_id,
            execution_id=execution_id,
            actor=resolve_actor(request, body.actor),
            note=body.note,
            trace_id=get_trace_id(),
        )
    except agent_runtime.AgentRuntimeError as exc:
        raise _http_error(exc) from exc
    return ExecutionOut.model_validate(execution)


@router.post(
    "/agent-executions/{execution_id}/tool-calls",
    response_model=ToolCallOut,
    summary="Gate one tool call (whitelist + L0-L3 permission check)",
)
async def execute_tool_call(
    execution_id: UUID,
    body: ToolCallRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ToolCallOut:
    """Run one tool call through the gate; every outcome is audited."""
    try:
        result = await agent_runtime.execute_tool_call(
            db,
            workspace_id=workspace_id,
            execution_id=execution_id,
            tool_name=body.tool_name,
            arguments=body.arguments,
            trace_id=get_trace_id(),
        )
    except Exception as exc:
        raise _tool_error(exc) from exc
    return ToolCallOut(**result)


# --------------------------------------------------------------------------- #
# Tool registry (whitelist)
# --------------------------------------------------------------------------- #


@router.post(
    "/agent-tools",
    response_model=ToolOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register (or update) a tool in the whitelist",
)
async def register_tool(
    body: ToolRegisterRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ToolOut:
    """Register a tool with its permission level and enabled state."""
    try:
        tool = await agent_runtime.register_tool(
            db,
            workspace_id=workspace_id,
            tool_name=body.tool_name,
            description=body.description,
            permission_level=body.permission_level,
            enabled=body.enabled,
            category=body.category,
            handler_name=body.handler_name,
            args_schema=body.args_schema,
            trace_id=get_trace_id(),
        )
    except agent_runtime.AgentRuntimeError as exc:
        raise _http_error(exc) from exc
    return ToolOut.model_validate(tool)


@router.get(
    "/agent-tools",
    response_model=list[ToolOut],
    summary="List the tool registry whitelist",
)
async def list_tools(
    db: DbSession,
    workspace_id: WorkspaceId,
    enabled: Annotated[bool | None, Query()] = None,
) -> list[ToolOut]:
    """Return the whitelist, optionally filtered by enabled state."""
    tools = await agent_runtime.list_tools(
        db, workspace_id=workspace_id, enabled=enabled, limit=200
    )
    return [ToolOut.model_validate(tool) for tool in tools]


@router.patch(
    "/agent-tools/{tool_name}",
    response_model=ToolOut,
    summary="Enable/disable a registered tool",
)
async def update_tool(
    tool_name: str,
    body: ToolUpdateRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ToolOut:
    """Toggle a tool; disabled tools deny every call with 403."""
    try:
        tool = await agent_runtime.update_tool_enabled(
            db,
            workspace_id=workspace_id,
            tool_name=tool_name,
            enabled=body.enabled,
            description=body.description,
            handler_name=body.handler_name,
            args_schema=body.args_schema,
            trace_id=get_trace_id(),
        )
    except agent_runtime.AgentRuntimeError as exc:
        raise _http_error(exc) from exc
    return ToolOut.model_validate(tool)


# --------------------------------------------------------------------------- #
# Agent memory (grounded in the four knowledge domains)
# --------------------------------------------------------------------------- #


@router.post(
    "/agent-memory",
    response_model=MemoryOut,
    status_code=status.HTTP_201_CREATED,
    summary="Store one agent memory entry",
)
async def store_memory(
    body: MemoryCreate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> MemoryOut:
    """Store an agent memory entry linked to a knowledge domain."""
    try:
        memory = await agent_runtime.store_memory(
            db, workspace_id=workspace_id, data=body, trace_id=get_trace_id()
        )
    except agent_runtime.AgentRuntimeError as exc:
        raise _http_error(exc) from exc
    return MemoryOut.model_validate(memory)


@router.get(
    "/agent-memory",
    response_model=list[MemoryOut],
    summary="Search agent memory",
)
async def search_memory(
    db: DbSession,
    workspace_id: WorkspaceId,
    domain: Annotated[str | None, Query()] = None,
    agent_id: Annotated[UUID | None, Query()] = None,
    source_type: Annotated[str | None, Query()] = None,
    keyword: Annotated[str | None, Query()] = None,
    limit: int = 50,
) -> list[MemoryOut]:
    """Return memory entries filtered by domain/agent/source/keyword."""
    rows = await agent_runtime.search_memory(
        db,
        workspace_id=workspace_id,
        domain=domain,
        agent_id=agent_id,
        source_type=source_type,
        keyword=keyword,
        limit=min(limit, 200),
    )
    return [MemoryOut.model_validate(row) for row in rows]


@router.get(
    "/agent-memory/knowledge-snapshot",
    response_model=list[dict],
    summary="Pull knowledge entries for a domain (agent grounding context)",
)
async def knowledge_snapshot(
    db: DbSession,
    workspace_id: WorkspaceId,
    domain: str,
    limit: int = 20,
) -> list[dict]:
    """Return recent product/marketing/customer/supply_chain knowledge."""
    try:
        rows = await agent_runtime.knowledge_snapshot(
            db, workspace_id=workspace_id, domain=domain, limit=min(limit, 100)
        )
    except agent_runtime.AgentRuntimeError as exc:
        raise _http_error(exc) from exc
    return rows


# --------------------------------------------------------------------------- #
# Agent evaluation
# --------------------------------------------------------------------------- #


@router.post(
    "/agent-evaluations",
    response_model=AgentEvaluationOut,
    status_code=status.HTTP_201_CREATED,
    summary="Record an agent prediction evaluation",
)
async def record_evaluation(
    body: AgentEvaluationCreate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> AgentEvaluationOut:
    """Record prediction vs actual with deterministic accuracy/calibration."""
    try:
        evaluation = await agent_runtime.record_evaluation(
            db, workspace_id=workspace_id, data=body, trace_id=get_trace_id()
        )
    except agent_runtime.AgentRuntimeError as exc:
        raise _http_error(exc) from exc
    return AgentEvaluationOut.model_validate(evaluation)


@router.get(
    "/agent-evaluations",
    response_model=list[AgentEvaluationOut],
    summary="List agent evaluations",
)
async def list_evaluations(
    db: DbSession,
    workspace_id: WorkspaceId,
    agent_id: Annotated[UUID | None, Query()] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[AgentEvaluationOut]:
    """Return evaluations, newest first, workspace-scoped."""
    evaluations, _total = await agent_runtime.list_evaluations(
        db,
        workspace_id=workspace_id,
        agent_id=agent_id,
        limit=min(limit, 200),
        offset=max(offset, 0),
    )
    return [AgentEvaluationOut.model_validate(item) for item in evaluations]
