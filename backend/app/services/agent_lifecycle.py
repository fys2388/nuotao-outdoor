"""Agent Lifecycle Management (M5.5): draft -> active -> paused -> retired
with append-only configuration versions and human-approved rollback.

Model:

- ``agent_versions`` is append-only: publishing creates a ``draft`` version,
  activating promotes it to ``active`` (the previous active version becomes
  ``retired``). At most ONE active version exists per agent.
- ``pause`` / ``resume`` toggle the registry status; ``paused`` agents reject
  new tasks (``create_task`` already requires ``active``) while running
  executions are left alone.
- ``retire`` and ``rollback`` are HIGH-RISK lifecycle actions: they only
  create an ``AGENT_LIFECYCLE`` approval proposal (permission
  ``agent.lifecycle.approve``). The real transition runs after a human
  approval through the Approval Center dispatch.
- ``rollback`` never mutates history: it copies the target version's
  configuration into a NEW version and activates it.

Every transition writes ``event_log`` with a ``trace_id`` and is
workspace-scoped. No business agent and no auto-executed business action
live here.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_platform import AgentVersion
from app.models.agent_runtime import AgentRegistry
from app.services import approval_service, event_service

logger = logging.getLogger(__name__)

LIFECYCLE_ACTIVE = "active"
LIFECYCLE_PAUSED = "paused"
LIFECYCLE_RETIRED = "retired"
VERSION_DRAFT = "draft"
VERSION_ACTIVE = "active"
VERSION_RETIRED = "retired"

# Actions executed only after a human approval (AGENT_LIFECYCLE proposals).
LIFECYCLE_APPROVED_ACTIONS: tuple[str, ...] = ("retire", "rollback")


class AgentLifecycleError(Exception):
    """Raised when a lifecycle transition cannot complete."""


def _version_key(version: str) -> tuple[int, ...]:
    """Sortable numeric key for version strings (``v1`` < ``v2`` < ``v10``)."""
    return tuple(int(part) for part in re.findall(r"\d+", version) or [0])


async def _load_agent(
    session: AsyncSession, *, workspace_id: UUID, agent_uuid: UUID
) -> AgentRegistry:
    agent = (
        await session.execute(
            select(AgentRegistry).where(
                AgentRegistry.workspace_id == workspace_id,
                AgentRegistry.id == agent_uuid,
            )
        )
    ).scalar_one_or_none()
    if agent is None:
        raise AgentLifecycleError("agent not found")
    return agent


# --------------------------------------------------------------------------- #
# Version publishing / listing / activation
# --------------------------------------------------------------------------- #


async def publish_version(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    agent_uuid: UUID,
    version: str,
    prompt_name: str | None = None,
    prompt_version: str = "v1",
    config_snapshot: dict[str, Any] | None = None,
    model_config: dict[str, Any] | None = None,
    execution_policy_version: str = "1",
    retry_policy_version: str = "1",
    budget_policy_version: str = "1",
    created_by: str | None = None,
    trace_id: str | None = None,
) -> AgentVersion:
    """Create a new ``draft`` configuration version (append-only)."""
    await _load_agent(session, workspace_id=workspace_id, agent_uuid=agent_uuid)
    existing = (
        await session.execute(
            select(AgentVersion).where(
                AgentVersion.workspace_id == workspace_id,
                AgentVersion.agent_id == agent_uuid,
                AgentVersion.version == version,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise AgentLifecycleError(f"version '{version}' already exists for this agent")
    row = AgentVersion(
        workspace_id=workspace_id,
        agent_id=agent_uuid,
        version=version,
        prompt_name=prompt_name,
        prompt_version=prompt_version,
        config_snapshot=config_snapshot or {},
        model_config=model_config or {},
        execution_policy_version=execution_policy_version,
        retry_policy_version=retry_policy_version,
        budget_policy_version=budget_policy_version,
        status=VERSION_DRAFT,
        created_by=created_by,
        trace_id=trace_id,
    )
    session.add(row)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.lifecycle.created",
        entity_type="agent_version",
        entity_id=str(row.id),
        payload={"agent_uuid": str(agent_uuid), "version": version},
        trace_id=trace_id,
    )
    await session.refresh(row)
    return row


async def list_versions(
    session: AsyncSession, *, workspace_id: UUID, agent_uuid: UUID
) -> list[AgentVersion]:
    """List the append-only versions of one agent, newest first.

    Version numbers are monotonic (append-only), so a numeric tie-break keeps
    the order deterministic even when rows share the same timestamp (SQLite
    only stores second precision and a batch publish can collide).
    """
    rows = (
        (
            await session.execute(
                select(AgentVersion).where(
                    AgentVersion.workspace_id == workspace_id,
                    AgentVersion.agent_id == agent_uuid,
                )
            )
        )
        .scalars()
        .all()
    )
    return sorted(
        rows,
        key=lambda row: (row.created_at or datetime.min, _version_key(row.version)),
        reverse=True,
    )


async def _load_version(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    agent_uuid: UUID,
    version: str,
) -> AgentVersion:
    row = (
        await session.execute(
            select(AgentVersion).where(
                AgentVersion.workspace_id == workspace_id,
                AgentVersion.agent_id == agent_uuid,
                AgentVersion.version == version,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise AgentLifecycleError(f"version '{version}' not found for this agent")
    return row


async def activate_version(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    agent_uuid: UUID,
    version: str,
    actor: str,
    trace_id: str | None = None,
) -> AgentVersion:
    """Promote one version to ``active`` (old active version -> retired)."""
    agent = await _load_agent(session, workspace_id=workspace_id, agent_uuid=agent_uuid)
    target = await _load_version(
        session, workspace_id=workspace_id, agent_uuid=agent_uuid, version=version
    )
    if target.status == VERSION_RETIRED:
        raise AgentLifecycleError("retired versions cannot be re-activated; use rollback")
    # Retire the currently active version first so the partial unique index
    # (one active version per agent) is never violated.
    active_rows = (
        (
            await session.execute(
                select(AgentVersion).where(
                    AgentVersion.workspace_id == workspace_id,
                    AgentVersion.agent_id == agent_uuid,
                    AgentVersion.status == VERSION_ACTIVE,
                )
            )
        )
        .scalars()
        .all()
    )
    for row in active_rows:
        row.status = VERSION_RETIRED
    if active_rows:
        # Flush the retirement FIRST: the partial unique index (one active
        # version per agent) must never see two active rows, even transiently
        # (SQLite checks partial indexes row-by-row during a batch update).
        await session.flush()
    target.status = VERSION_ACTIVE
    # Keep the registry in sync: active version + active lifecycle status.
    agent.status = LIFECYCLE_ACTIVE
    agent.current_version = version
    if target.model_config:
        agent.model_provider = target.model_config.get("model_provider", agent.model_provider)
        agent.model_name = target.model_config.get("model_name", agent.model_name)
    if target.prompt_version:
        agent.prompt_version = target.prompt_version
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.lifecycle.activated",
        entity_type="agent_version",
        entity_id=str(target.id),
        payload={"agent_uuid": str(agent_uuid), "version": version, "actor": actor},
        trace_id=trace_id,
    )
    await session.refresh(target)
    return target


# --------------------------------------------------------------------------- #
# Pause / resume (operator action, no approval required)
# --------------------------------------------------------------------------- #


async def pause_agent(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    agent_uuid: UUID,
    actor: str,
    trace_id: str | None = None,
) -> AgentRegistry:
    """Pause an active agent (blocks new tasks; running work continues)."""
    agent = await _load_agent(session, workspace_id=workspace_id, agent_uuid=agent_uuid)
    if agent.status == LIFECYCLE_PAUSED:
        raise AgentLifecycleError("agent is already paused")
    if agent.status == LIFECYCLE_RETIRED:
        raise AgentLifecycleError("retired agents cannot be paused; use resume of a version")
    agent.status = LIFECYCLE_PAUSED
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.lifecycle.paused",
        entity_type="agent_registry",
        entity_id=str(agent.id),
        payload={"agent_id": agent.agent_id, "actor": actor},
        trace_id=trace_id,
    )
    await session.refresh(agent)
    return agent


async def resume_agent(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    agent_uuid: UUID,
    actor: str,
    trace_id: str | None = None,
) -> AgentRegistry:
    """Resume a paused agent (back to ``active``; tasks accepted again)."""
    agent = await _load_agent(session, workspace_id=workspace_id, agent_uuid=agent_uuid)
    if agent.status != LIFECYCLE_PAUSED:
        raise AgentLifecycleError("only paused agents can be resumed")
    agent.status = LIFECYCLE_ACTIVE
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.lifecycle.resumed",
        entity_type="agent_registry",
        entity_id=str(agent.id),
        payload={"agent_id": agent.agent_id, "actor": actor},
        trace_id=trace_id,
    )
    await session.refresh(agent)
    return agent


# --------------------------------------------------------------------------- #
# Retire / rollback (HIGH-RISK: approval required, never auto-executed)
# --------------------------------------------------------------------------- #


async def retire_agent(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    agent_uuid: UUID,
    actor: str,
    note: str | None = None,
    trace_id: str | None = None,
) -> Any:
    """Propose to retire an agent; the transition waits for a human approval.

    Returns the created ``AgentApproval`` proposal. The actual status change
    runs only after ``approve`` through the Approval Center.
    """
    agent = await _load_agent(session, workspace_id=workspace_id, agent_uuid=agent_uuid)
    if agent.status == LIFECYCLE_RETIRED:
        raise AgentLifecycleError("agent is already retired")
    return await approval_service.ensure_approval(
        session,
        workspace_id=workspace_id,
        approval_type="AGENT_LIFECYCLE",
        entity_type="agent_registry",
        entity_id=str(agent.id),
        agent_id=agent.id,
        metadata_={"action": "retire", "proposed_by": actor, "note": note},
        trace_id=trace_id,
    )


async def _execute_retire(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    agent_uuid: UUID,
    actor: str,
    trace_id: str | None = None,
) -> AgentRegistry:
    """The approved retire transition (called by the Approval dispatch)."""
    agent = await _load_agent(session, workspace_id=workspace_id, agent_uuid=agent_uuid)
    if agent.status == LIFECYCLE_RETIRED:
        raise AgentLifecycleError("agent is already retired")
    agent.status = LIFECYCLE_RETIRED
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.lifecycle.retired",
        entity_type="agent_registry",
        entity_id=str(agent.id),
        payload={"agent_id": agent.agent_id, "actor": actor},
        trace_id=trace_id,
    )
    await session.refresh(agent)
    return agent


async def rollback_agent(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    agent_uuid: UUID,
    target_version: str,
    actor: str,
    note: str | None = None,
    trace_id: str | None = None,
) -> Any:
    """Propose to roll back to a historical version (approval required).

    Returns the created ``AgentApproval`` proposal; after approval a NEW
    active version is created from the target's configuration (the target
    row itself is never modified).
    """
    agent = await _load_agent(session, workspace_id=workspace_id, agent_uuid=agent_uuid)
    target = await _load_version(
        session, workspace_id=workspace_id, agent_uuid=agent_uuid, version=target_version
    )
    if target.status == VERSION_ACTIVE:
        raise AgentLifecycleError("target version is already active")
    return await approval_service.ensure_approval(
        session,
        workspace_id=workspace_id,
        approval_type="AGENT_LIFECYCLE",
        entity_type="agent_registry",
        entity_id=str(agent.id),
        agent_id=agent.id,
        metadata_={
            "action": "rollback",
            "target_version": target_version,
            "proposed_by": actor,
            "note": note,
        },
        trace_id=trace_id,
    )


async def _execute_rollback(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    agent_uuid: UUID,
    target_version: str,
    actor: str,
    trace_id: str | None = None,
) -> AgentVersion:
    """The approved rollback: create a NEW active version from the target."""
    await _load_agent(session, workspace_id=workspace_id, agent_uuid=agent_uuid)
    target = await _load_version(
        session, workspace_id=workspace_id, agent_uuid=agent_uuid, version=target_version
    )
    existing = await list_versions(session, workspace_id=workspace_id, agent_uuid=agent_uuid)
    next_number = max((_version_key(row.version)[0] for row in existing), default=0) + 1
    new_version = f"v{next_number}"
    row = AgentVersion(
        workspace_id=workspace_id,
        agent_id=agent_uuid,
        version=new_version,
        prompt_name=target.prompt_name,
        prompt_version=target.prompt_version,
        config_snapshot=target.config_snapshot,
        model_config=target.model_config,
        execution_policy_version=target.execution_policy_version,
        retry_policy_version=target.retry_policy_version,
        budget_policy_version=target.budget_policy_version,
        status=VERSION_DRAFT,
        created_by=actor,
        trace_id=trace_id,
    )
    session.add(row)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.lifecycle.rollback",
        entity_type="agent_version",
        entity_id=str(row.id),
        payload={
            "agent_uuid": str(agent_uuid),
            "from_version": target_version,
            "to_version": new_version,
            "actor": actor,
        },
        trace_id=trace_id,
    )
    # Activate the new version (registry -> active, old active -> retired).
    return await activate_version(
        session,
        workspace_id=workspace_id,
        agent_uuid=agent_uuid,
        version=new_version,
        actor=actor,
        trace_id=trace_id,
    )
