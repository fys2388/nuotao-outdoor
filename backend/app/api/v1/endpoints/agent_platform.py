"""Agent platform productionization endpoints (M5.5).

Adds the M5.5 platform APIs on top of the existing runtime:

- Agent Lifecycle: publish/activate versions, pause/resume, and the
  approval-gated retire/rollback transitions (``agent.lifecycle.*`` events).
- Approval RBAC roles + Approval SLA configuration and the manual SLA scan.
- Runtime metrics (``GET /agent-runtime/metrics``) - the unified JSON view.
- Runtime Console audit (``POST /agent-runtime/console-audit``) - the console
  explicitly reports every operator action; the backend persists it as
  ``agent.console.<action>`` events.

Everything is workspace-scoped and audited through ``event_log`` with a
``trace_id``. No business agent and no auto-executed business action live
here; retire/rollback still require a human approval.
"""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.tracing import get_trace_id
from app.core.workspace import get_workspace_id
from app.schemas.agent_platform import (
    ApprovalRoleCreate,
    ApprovalRoleOut,
    ApprovalSlaOut,
    ApprovalSlaUpsert,
    ConsoleAuditRequest,
    LifecycleActionRequest,
    RollbackRequest,
    VersionOut,
    VersionPublishRequest,
)
from app.services import (
    agent_lifecycle,
    approval_rbac,
    approval_sla,
    event_service,
    runtime_metrics,
    task_queue,
)

router = APIRouter(tags=["agent-platform"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
WorkspaceId = Annotated[UUID, Depends(get_workspace_id)]
logger = logging.getLogger(__name__)


def _error(exc: Exception) -> HTTPException:
    """Map platform errors: missing resources -> 404, state -> 400."""
    message = str(exc)
    if "not found" in message:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)
    if "permission" in message.lower() and "lacks" in message.lower():
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=message)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


def _version_out(version: agent_lifecycle.AgentVersion) -> VersionOut:
    """Map an ORM version row to its API schema (model_config -> settings)."""
    return VersionOut(
        id=version.id,
        workspace_id=version.workspace_id,
        agent_id=version.agent_id,
        version=version.version,
        prompt_name=version.prompt_name,
        prompt_version=version.prompt_version,
        config_snapshot=version.config_snapshot,
        model_settings=version.model_config,
        execution_policy_version=version.execution_policy_version,
        retry_policy_version=version.retry_policy_version,
        budget_policy_version=version.budget_policy_version,
        status=version.status,
        created_by=version.created_by,
        trace_id=version.trace_id,
        created_at=version.created_at,
        updated_at=version.updated_at,
    )


# --------------------------------------------------------------------------- #
# Agent Lifecycle
# --------------------------------------------------------------------------- #


@router.post(
    "/agent-registry/{agent_uuid}/pause",
    response_model=dict,
    summary="Pause an active agent (blocks new tasks; running work continues)",
)
async def pause_agent(
    agent_uuid: UUID,
    body: LifecycleActionRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> dict:
    """Pause the agent; the operator actor is audited."""
    try:
        agent = await agent_lifecycle.pause_agent(
            db,
            workspace_id=workspace_id,
            agent_uuid=agent_uuid,
            actor=body.actor,
            trace_id=get_trace_id(),
        )
    except agent_lifecycle.AgentLifecycleError as exc:
        raise _error(exc) from exc
    return {"agent_id": agent.agent_id, "status": agent.status}


@router.post(
    "/agent-registry/{agent_uuid}/resume",
    response_model=dict,
    summary="Resume a paused agent",
)
async def resume_agent(
    agent_uuid: UUID,
    body: LifecycleActionRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> dict:
    """Resume the agent (back to active; tasks accepted again)."""
    try:
        agent = await agent_lifecycle.resume_agent(
            db,
            workspace_id=workspace_id,
            agent_uuid=agent_uuid,
            actor=body.actor,
            trace_id=get_trace_id(),
        )
    except agent_lifecycle.AgentLifecycleError as exc:
        raise _error(exc) from exc
    return {"agent_id": agent.agent_id, "status": agent.status}


@router.post(
    "/agent-registry/{agent_uuid}/versions",
    response_model=VersionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Publish a new draft configuration version (append-only)",
)
async def publish_version(
    agent_uuid: UUID,
    body: VersionPublishRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> VersionOut:
    """Create a new draft version (does not change the active version)."""
    try:
        version = await agent_lifecycle.publish_version(
            db,
            workspace_id=workspace_id,
            agent_uuid=agent_uuid,
            version=body.version,
            prompt_name=body.prompt_name,
            prompt_version=body.prompt_version,
            config_snapshot=body.config_snapshot,
            model_config=body.model_settings,
            execution_policy_version=body.execution_policy_version,
            retry_policy_version=body.retry_policy_version,
            budget_policy_version=body.budget_policy_version,
            created_by=body.created_by,
            trace_id=get_trace_id(),
        )
    except agent_lifecycle.AgentLifecycleError as exc:
        raise _error(exc) from exc
    return _version_out(version)


@router.get(
    "/agent-registry/{agent_uuid}/versions",
    response_model=list[VersionOut],
    summary="List the append-only versions of one agent",
)
async def list_versions(
    agent_uuid: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> list[VersionOut]:
    """Return the version history (newest first)."""
    rows = await agent_lifecycle.list_versions(db, workspace_id=workspace_id, agent_uuid=agent_uuid)
    return [_version_out(row) for row in rows]


@router.post(
    "/agent-registry/{agent_uuid}/versions/{version}/activate",
    response_model=VersionOut,
    summary="Activate one version (old active version -> retired)",
)
async def activate_version(
    agent_uuid: UUID,
    version: str,
    body: LifecycleActionRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> VersionOut:
    """Promote the version to active and update the registry binding."""
    try:
        row = await agent_lifecycle.activate_version(
            db,
            workspace_id=workspace_id,
            agent_uuid=agent_uuid,
            version=version,
            actor=body.actor,
            trace_id=get_trace_id(),
        )
    except agent_lifecycle.AgentLifecycleError as exc:
        raise _error(exc) from exc
    return _version_out(row)


@router.post(
    "/agent-registry/{agent_uuid}/rollback",
    response_model=dict,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Propose a rollback to a historical version (human approval required)",
)
async def rollback_agent(
    agent_uuid: UUID,
    body: RollbackRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> dict:
    """Create an AGENT_LIFECYCLE approval proposal; the rollback runs only
    after a human approval (permission ``agent.lifecycle.approve``)."""
    try:
        proposal = await agent_lifecycle.rollback_agent(
            db,
            workspace_id=workspace_id,
            agent_uuid=agent_uuid,
            target_version=body.target_version,
            actor=body.actor,
            note=body.note,
            trace_id=get_trace_id(),
        )
    except agent_lifecycle.AgentLifecycleError as exc:
        raise _error(exc) from exc
    return {
        "proposal_id": str(proposal.id),
        "status": proposal.status,
        "action": "rollback",
        "target_version": body.target_version,
        "message": "rollback proposal created; a human approval is required to execute",
    }


@router.post(
    "/agent-registry/{agent_uuid}/retire",
    response_model=dict,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Propose to retire an agent (human approval required)",
)
async def retire_agent(
    agent_uuid: UUID,
    body: LifecycleActionRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> dict:
    """Create an AGENT_LIFECYCLE approval proposal; the retirement runs only
    after a human approval (permission ``agent.lifecycle.approve``)."""
    try:
        proposal = await agent_lifecycle.retire_agent(
            db,
            workspace_id=workspace_id,
            agent_uuid=agent_uuid,
            actor=body.actor,
            note=body.note,
            trace_id=get_trace_id(),
        )
    except agent_lifecycle.AgentLifecycleError as exc:
        raise _error(exc) from exc
    return {
        "proposal_id": str(proposal.id),
        "status": proposal.status,
        "action": "retire",
        "message": "retire proposal created; a human approval is required to execute",
    }


# --------------------------------------------------------------------------- #
# Approval RBAC roles
# --------------------------------------------------------------------------- #


@router.post(
    "/approval-roles",
    response_model=ApprovalRoleOut,
    summary="Create/replace an approval RBAC role (server-side permissions)",
)
async def create_role(
    body: ApprovalRoleCreate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ApprovalRoleOut:
    """Upsert one role; the API enforces permissions on every decision."""
    role = await approval_rbac.create_role(
        db,
        workspace_id=workspace_id,
        role_name=body.role_name,
        permissions=body.permissions,
        actors=body.actors,
        enabled=body.enabled,
        trace_id=get_trace_id(),
    )
    return ApprovalRoleOut.model_validate(role)


@router.get(
    "/approval-roles",
    response_model=list[ApprovalRoleOut],
    summary="List the approval roles of the workspace",
)
async def list_roles(db: DbSession, workspace_id: WorkspaceId) -> list[ApprovalRoleOut]:
    """Return the configured roles (used by the console RBAC panel)."""
    rows = await approval_rbac.list_roles(db, workspace_id=workspace_id)
    return [ApprovalRoleOut.model_validate(row) for row in rows]


@router.delete(
    "/approval-roles/{role_name}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete one approval role",
)
async def delete_role(
    role_name: str,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> None:
    """Remove the role; a 404 is returned when it did not exist."""
    deleted = await approval_rbac.delete_role(db, workspace_id=workspace_id, role_name=role_name)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="role not found")


# --------------------------------------------------------------------------- #
# Approval SLA
# --------------------------------------------------------------------------- #


@router.post(
    "/approval-slas",
    response_model=ApprovalSlaOut,
    summary="Upsert one approval-type SLA configuration",
)
async def upsert_sla(
    body: ApprovalSlaUpsert,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ApprovalSlaOut:
    """Create or replace the SLA row for one approval type."""
    from sqlalchemy import select

    from app.models.agent_platform import AgentApprovalSla

    row = (
        await db.execute(
            select(AgentApprovalSla).where(
                AgentApprovalSla.workspace_id == workspace_id,
                AgentApprovalSla.approval_type == body.approval_type,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = AgentApprovalSla(
            workspace_id=workspace_id,
            approval_type=body.approval_type,
            warning_after_seconds=body.warning_after_seconds,
            expire_after_seconds=body.expire_after_seconds,
            enabled=body.enabled,
            trace_id=get_trace_id(),
        )
        db.add(row)
    else:
        row.warning_after_seconds = body.warning_after_seconds
        row.expire_after_seconds = body.expire_after_seconds
        row.enabled = body.enabled
    await db.flush()
    await db.refresh(row)
    return ApprovalSlaOut.model_validate(row)


@router.get(
    "/approval-slas",
    response_model=list[ApprovalSlaOut],
    summary="List the approval SLA configuration of the workspace",
)
async def list_slas(db: DbSession, workspace_id: WorkspaceId) -> list[ApprovalSlaOut]:
    """Return the configured per-type SLAs."""
    from sqlalchemy import select

    from app.models.agent_platform import AgentApprovalSla

    rows = (
        (
            await db.execute(
                select(AgentApprovalSla).where(AgentApprovalSla.workspace_id == workspace_id)
            )
        )
        .scalars()
        .all()
    )
    return [ApprovalSlaOut.model_validate(row) for row in rows]


@router.post(
    "/approvals/sla-scan",
    response_model=dict,
    summary="Apply the approval SLA transitions (pending -> warning -> expired)",
)
async def sla_scan(db: DbSession, workspace_id: WorkspaceId) -> dict:
    """Run the SLA scan once; returns the number of warned/expired rows."""
    warned, expired = await approval_sla.apply_approval_slas(
        db, workspace_id=workspace_id, trace_id=get_trace_id()
    )
    return {"warned": warned, "expired": expired}


# --------------------------------------------------------------------------- #
# Runtime metrics + console audit
# --------------------------------------------------------------------------- #


@router.get(
    "/agent-runtime/metrics",
    response_model=dict,
    summary="Unified runtime metrics (JSON, Prometheus-ready later)",
)
async def get_runtime_metrics(db: DbSession, workspace_id: WorkspaceId) -> dict:
    """Return the unified operational metrics snapshot."""
    backend = task_queue.get_queue_backend()
    return await runtime_metrics.runtime_metrics(
        db, backend, workspace_id=workspace_id, trace_id=get_trace_id()
    )


@router.post(
    "/agent-runtime/console-audit",
    response_model=dict,
    summary="Record one Runtime Console operator action (agent.console.* event)",
)
async def console_audit(
    body: ConsoleAuditRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
    x_nuotao_console: Annotated[str | None, Header(alias="X-Nuotao-Console")] = None,
) -> dict:
    """Persist ``agent.console.<action>`` with workspace/actor/trace_id.

    The console must send the ``X-Nuotao-Console`` header so the backend can
    distinguish real console traffic from API automation.
    """
    if not x_nuotao_console:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="missing X-Nuotao-Console header (runtime console only)",
        )
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type=f"agent.console.{body.action}",
        entity_type=body.entity_type or "runtime_console",
        entity_id=body.entity_id or "console",
        payload={
            "actor": body.actor,
            "detail": body.detail,
            "console_source": x_nuotao_console,
        },
        trace_id=get_trace_id(),
    )
    await db.commit()
    return {"recorded": f"agent.console.{body.action}"}
