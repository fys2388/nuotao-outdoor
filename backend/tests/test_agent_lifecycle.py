"""Tests for the M5.5 Agent Lifecycle Management.

Covers version publishing (append-only), activation (one active version),
pause/resume (paused blocks new tasks, running work untouched), and the
approval-gated retire/rollback transitions. Rollback creates a NEW active
version and never mutates history. Every transition is audited with
``agent.lifecycle.*`` events and is workspace-scoped.
"""

from uuid import UUID

import pytest
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.agent_platform import AgentVersion
from app.models.agent_runtime import AgentRegistry
from app.models.event import EventLog
from app.schemas.agent_runtime import AgentRegisterRequest, TaskCreate
from app.schemas.prompt import PromptCreate
from app.services import (
    agent_lifecycle,
    agent_runtime,
    approval_service,
    prompt_registry,
    task_queue,
)
from sqlalchemy import select

WORKSPACE = DEFAULT_WORKSPACE_ID
OTHER_WORKSPACE = UUID("00000000-0000-0000-0000-000000000099")


async def _seed_agent(
    db_session, *, workspace_id: UUID = WORKSPACE, agent_code: str = "LIFE_TEST"
) -> AgentRegistry:
    await prompt_registry.create_prompt(
        db_session,
        workspace_id=workspace_id,
        data=PromptCreate(
            prompt_id=f"prompt-{agent_code.lower()}",
            name=f"AGENT_{agent_code.upper()}",
            version="v1",
            template="Analyze {sku}.",
            variables=["sku"],
        ),
    )
    return await agent_runtime.register_agent(
        db_session,
        workspace_id=workspace_id,
        data=AgentRegisterRequest(
            agent_id=agent_code,
            name="Lifecycle Test Agent",
            domain="operations",
            version="v1",
            status="active",
            model_provider="openai",
            model_name="gpt-4o-mini",
            prompt_version="v1",
            permission_level="L2",
        ),
    )


async def _publish(
    db_session, agent: AgentRegistry, version: str, *, workspace_id: UUID = WORKSPACE
) -> AgentVersion:
    return await agent_lifecycle.publish_version(
        db_session,
        workspace_id=workspace_id,
        agent_uuid=agent.id,
        version=version,
        prompt_version="v1",
        model_config={"model_provider": "openai", "model_name": "gpt-4o-mini"},
        created_by="tester",
        trace_id="test",
    )


@pytest.mark.asyncio
async def test_publish_version_creates_draft(db_session) -> None:
    agent = await _seed_agent(db_session)
    version = await _publish(db_session, agent, "v2")
    assert version.status == "draft"
    assert version.agent_id == agent.id
    assert agent.current_version is None  # publishing never activates


@pytest.mark.asyncio
async def test_publish_duplicate_version_rejected(db_session) -> None:
    agent = await _seed_agent(db_session)
    await _publish(db_session, agent, "v2")
    with pytest.raises(agent_lifecycle.AgentLifecycleError, match="already exists"):
        await _publish(db_session, agent, "v2")


@pytest.mark.asyncio
async def test_list_versions_newest_first(db_session) -> None:
    agent = await _seed_agent(db_session)
    await _publish(db_session, agent, "v1")
    await _publish(db_session, agent, "v2")
    await _publish(db_session, agent, "v3")
    rows = await agent_lifecycle.list_versions(
        db_session, workspace_id=WORKSPACE, agent_uuid=agent.id
    )
    assert [r.version for r in rows] == ["v3", "v2", "v1"]


@pytest.mark.asyncio
async def test_activate_version_promotes_and_retires_old(db_session) -> None:
    agent = await _seed_agent(db_session)
    await _publish(db_session, agent, "v1")
    await _publish(db_session, agent, "v2")
    await agent_lifecycle.activate_version(
        db_session, workspace_id=WORKSPACE, agent_uuid=agent.id, version="v1", actor="tester"
    )
    await agent_lifecycle.activate_version(
        db_session, workspace_id=WORKSPACE, agent_uuid=agent.id, version="v2", actor="tester"
    )
    rows = (
        (
            await db_session.execute(
                select(AgentVersion).where(
                    AgentVersion.workspace_id == WORKSPACE,
                    AgentVersion.agent_id == agent.id,
                )
            )
        )
        .scalars()
        .all()
    )
    statuses = {r.version: r.status for r in rows}
    assert statuses["v1"] == "retired"
    assert statuses["v2"] == "active"
    await db_session.refresh(agent)
    assert agent.status == "active"
    assert agent.current_version == "v2"


@pytest.mark.asyncio
async def test_only_one_active_version(db_session) -> None:
    agent = await _seed_agent(db_session)
    await _publish(db_session, agent, "v1")
    await _publish(db_session, agent, "v2")
    await agent_lifecycle.activate_version(
        db_session, workspace_id=WORKSPACE, agent_uuid=agent.id, version="v1", actor="tester"
    )
    await agent_lifecycle.activate_version(
        db_session, workspace_id=WORKSPACE, agent_uuid=agent.id, version="v2", actor="tester"
    )
    active = (
        (
            await db_session.execute(
                select(AgentVersion).where(
                    AgentVersion.workspace_id == WORKSPACE,
                    AgentVersion.agent_id == agent.id,
                    AgentVersion.status == "active",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(list(active)) == 1


@pytest.mark.asyncio
async def test_activate_retired_version_rejected(db_session) -> None:
    agent = await _seed_agent(db_session)
    await _publish(db_session, agent, "v1")
    await _publish(db_session, agent, "v2")
    await agent_lifecycle.activate_version(
        db_session, workspace_id=WORKSPACE, agent_uuid=agent.id, version="v1", actor="tester"
    )
    await agent_lifecycle.activate_version(
        db_session, workspace_id=WORKSPACE, agent_uuid=agent.id, version="v2", actor="tester"
    )
    with pytest.raises(agent_lifecycle.AgentLifecycleError, match="use rollback"):
        await agent_lifecycle.activate_version(
            db_session, workspace_id=WORKSPACE, agent_uuid=agent.id, version="v1", actor="tester"
        )


@pytest.mark.asyncio
async def test_pause_blocks_new_tasks(db_session) -> None:
    agent = await _seed_agent(db_session)
    await agent_lifecycle.pause_agent(
        db_session, workspace_id=WORKSPACE, agent_uuid=agent.id, actor="ops"
    )
    await db_session.refresh(agent)
    assert agent.status == "paused"
    with pytest.raises(agent_runtime.AgentRuntimeError, match="not active"):
        await agent_runtime.create_task(
            db_session,
            workspace_id=WORKSPACE,
            data=TaskCreate(agent_id=agent.id, input={"sku": "A"}, priority=3),
        )


@pytest.mark.asyncio
async def test_resume_restores_task_creation(db_session) -> None:
    agent = await _seed_agent(db_session)
    await agent_lifecycle.pause_agent(
        db_session, workspace_id=WORKSPACE, agent_uuid=agent.id, actor="ops"
    )
    await agent_lifecycle.resume_agent(
        db_session, workspace_id=WORKSPACE, agent_uuid=agent.id, actor="ops"
    )
    await db_session.refresh(agent)
    assert agent.status == "active"
    task = await agent_runtime.create_task(
        db_session,
        workspace_id=WORKSPACE,
        data=TaskCreate(agent_id=agent.id, input={"sku": "A"}, priority=3),
    )
    assert task.status == "pending"


@pytest.mark.asyncio
async def test_resume_non_paused_rejected(db_session) -> None:
    agent = await _seed_agent(db_session)
    with pytest.raises(agent_lifecycle.AgentLifecycleError, match="only paused"):
        await agent_lifecycle.resume_agent(
            db_session, workspace_id=WORKSPACE, agent_uuid=agent.id, actor="ops"
        )


@pytest.mark.asyncio
async def test_retire_creates_approval_proposal(db_session) -> None:
    agent = await _seed_agent(db_session)
    proposal = await agent_lifecycle.retire_agent(
        db_session,
        workspace_id=WORKSPACE,
        agent_uuid=agent.id,
        actor="ops",
        trace_id="test",
    )
    assert proposal.approval_type == "AGENT_LIFECYCLE"
    assert proposal.status == "pending"
    assert (proposal.metadata_ or {}).get("action") == "retire"
    await db_session.refresh(agent)
    assert agent.status == "active"  # not yet retired (approval pending)


@pytest.mark.asyncio
async def test_retire_after_approval_sets_retired(db_session) -> None:
    agent = await _seed_agent(db_session)
    proposal = await agent_lifecycle.retire_agent(
        db_session,
        workspace_id=WORKSPACE,
        agent_uuid=agent.id,
        actor="ops",
        trace_id="test",
    )
    backend = task_queue.get_queue_backend()
    await approval_service.approve_approval(
        db_session,
        backend,
        workspace_id=WORKSPACE,
        approval_id=proposal.id,
        actor="admin",
        trace_id="test",
    )
    await db_session.refresh(agent)
    assert agent.status == "retired"
    with pytest.raises(agent_runtime.AgentRuntimeError, match="not active"):
        await agent_runtime.create_task(
            db_session,
            workspace_id=WORKSPACE,
            data=TaskCreate(agent_id=agent.id, input={"sku": "A"}, priority=3),
        )


@pytest.mark.asyncio
async def test_retire_rejected_keeps_active(db_session) -> None:
    agent = await _seed_agent(db_session)
    proposal = await agent_lifecycle.retire_agent(
        db_session,
        workspace_id=WORKSPACE,
        agent_uuid=agent.id,
        actor="ops",
        trace_id="test",
    )
    backend = task_queue.get_queue_backend()
    await approval_service.reject_approval(
        db_session,
        backend,
        workspace_id=WORKSPACE,
        approval_id=proposal.id,
        actor="admin",
        trace_id="test",
    )
    await db_session.refresh(agent)
    assert agent.status == "active"


@pytest.mark.asyncio
async def test_rollback_creates_new_active_version(db_session) -> None:
    agent = await _seed_agent(db_session)
    await _publish(db_session, agent, "v1")
    await _publish(db_session, agent, "v2")
    await agent_lifecycle.activate_version(
        db_session, workspace_id=WORKSPACE, agent_uuid=agent.id, version="v2", actor="tester"
    )
    proposal = await agent_lifecycle.rollback_agent(
        db_session,
        workspace_id=WORKSPACE,
        agent_uuid=agent.id,
        target_version="v1",
        actor="ops",
        trace_id="test",
    )
    backend = task_queue.get_queue_backend()
    await approval_service.approve_approval(
        db_session,
        backend,
        workspace_id=WORKSPACE,
        approval_id=proposal.id,
        actor="admin",
        trace_id="test",
    )
    await db_session.refresh(agent)
    assert agent.current_version == "v3"  # NEW version, never a mutation of v1
    rows = (
        (
            await db_session.execute(
                select(AgentVersion).where(
                    AgentVersion.workspace_id == WORKSPACE,
                    AgentVersion.agent_id == agent.id,
                )
            )
        )
        .scalars()
        .all()
    )
    statuses = {r.version: r.status for r in rows}
    assert statuses["v1"] == "draft"  # never activated, still a draft
    assert statuses["v2"] == "retired"  # the previous active is retired
    assert statuses["v3"] == "active"


@pytest.mark.asyncio
async def test_rollback_history_immutable(db_session) -> None:
    """The historical target version row keeps its own status/config."""
    agent = await _seed_agent(db_session)
    v1 = await _publish(db_session, agent, "v1")
    await _publish(db_session, agent, "v2")
    await agent_lifecycle.activate_version(
        db_session, workspace_id=WORKSPACE, agent_uuid=agent.id, version="v1", actor="tester"
    )
    await agent_lifecycle.activate_version(
        db_session, workspace_id=WORKSPACE, agent_uuid=agent.id, version="v2", actor="tester"
    )
    # v1 is now retired; rolling back to it copies its config into a NEW
    # version and never resurrects v1 itself.
    proposal = await agent_lifecycle.rollback_agent(
        db_session,
        workspace_id=WORKSPACE,
        agent_uuid=agent.id,
        target_version="v1",
        actor="ops",
        trace_id="test",
    )
    backend = task_queue.get_queue_backend()
    await approval_service.approve_approval(
        db_session,
        backend,
        workspace_id=WORKSPACE,
        approval_id=proposal.id,
        actor="admin",
        trace_id="test",
    )
    await db_session.refresh(v1)
    assert v1.status == "retired"  # still retired - never mutated back
    assert v1.prompt_version == "v1"
    assert v1.created_by == "tester"
    await db_session.refresh(agent)
    assert agent.current_version == "v3"


@pytest.mark.asyncio
async def test_lifecycle_events_audited(db_session) -> None:
    agent = await _seed_agent(db_session)
    await _publish(db_session, agent, "v1")
    await agent_lifecycle.activate_version(
        db_session, workspace_id=WORKSPACE, agent_uuid=agent.id, version="v1", actor="tester"
    )
    await agent_lifecycle.pause_agent(
        db_session, workspace_id=WORKSPACE, agent_uuid=agent.id, actor="ops"
    )
    rows = (
        (
            await db_session.execute(
                select(EventLog).where(
                    EventLog.workspace_id == WORKSPACE,
                    EventLog.event_type.like("agent.lifecycle.%"),
                )
            )
        )
        .scalars()
        .all()
    )
    types = {r.event_type for r in rows}
    assert "agent.lifecycle.created" in types
    assert "agent.lifecycle.activated" in types
    assert "agent.lifecycle.paused" in types


@pytest.mark.asyncio
async def test_workspace_isolation(db_session) -> None:
    agent = await _seed_agent(db_session, workspace_id=WORKSPACE)
    with pytest.raises(agent_lifecycle.AgentLifecycleError, match="not found"):
        await agent_lifecycle.pause_agent(
            db_session, workspace_id=OTHER_WORKSPACE, agent_uuid=agent.id, actor="ops"
        )
