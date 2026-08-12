"""Tests for the M5.5 Approval Center RBAC.

Covers server-side permission checks (actor -> workspace -> role ->
permission -> approval type), the legacy open mode when no roles are
configured, role CRUD, workspace isolation and the lifecycle permission.
The API layer maps ``ApprovalRBACError`` to 403 - the frontend never decides.
"""

from uuid import UUID

import pytest
from app.core.config import get_settings
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.agent_operations import AgentApproval
from app.models.agent_platform import AgentApprovalRole
from app.services import approval_rbac, approval_service, task_queue
from sqlalchemy import select

WORKSPACE = DEFAULT_WORKSPACE_ID
OTHER_WORKSPACE = UUID("00000000-0000-0000-0000-000000000099")


async def _seed_role(
    db_session, *, workspace_id: UUID, role_name: str = "ops-admin"
) -> AgentApprovalRole:
    return await approval_rbac.create_role(
        db_session,
        workspace_id=workspace_id,
        role_name=role_name,
        permissions=[
            "tool.approve",
            "tool.reject",
            "dlq_replay.approve",
            "agent.lifecycle.approve",
        ],
        actors=["alice", "bob"],
        enabled=True,
        trace_id="test",
    )


async def _seed_approval(
    db_session, *, workspace_id: UUID, approval_type: str = "L3_TOOL"
) -> AgentApproval:
    return await approval_service.ensure_approval(
        db_session,
        workspace_id=workspace_id,
        approval_type=approval_type,
        entity_type="agent_execution",
        entity_id="00000000-0000-0000-0000-00000000aa01",
        trace_id="test",
    )


@pytest.mark.asyncio
async def test_permission_mapping_tool(db_session) -> None:
    assert approval_rbac.permission_name("L3_TOOL", "approve") == "tool.approve"
    assert approval_rbac.permission_name("L3_TOOL", "reject") == "tool.reject"


@pytest.mark.asyncio
async def test_permission_mapping_all_types(db_session) -> None:
    assert approval_rbac.permission_name("RECOMMENDATION", "approve") == "recommendation.approve"
    assert approval_rbac.permission_name("CALIBRATION", "reject") == "calibration.reject"
    assert approval_rbac.permission_name("DLQ_REPLAY", "approve") == "dlq_replay.approve"
    assert approval_rbac.permission_name("AGENT_LIFECYCLE", "approve") == "agent.lifecycle.approve"


@pytest.mark.asyncio
async def test_actor_with_permission_allowed(db_session) -> None:
    await _seed_role(db_session, workspace_id=WORKSPACE)
    allowed = await approval_rbac.check_approval_permission(
        db_session,
        workspace_id=WORKSPACE,
        actor="alice",
        approval_type="L3_TOOL",
        action="approve",
    )
    assert allowed is True


@pytest.mark.asyncio
async def test_actor_without_permission_denied(db_session) -> None:
    await _seed_role(
        db_session,
        workspace_id=WORKSPACE,
        role_name="reviewer",
    )
    # Replace permissions: reviewer cannot approve tools.
    role = (
        await db_session.execute(
            select(AgentApprovalRole).where(
                AgentApprovalRole.workspace_id == WORKSPACE,
                AgentApprovalRole.role_name == "reviewer",
            )
        )
    ).scalar_one()
    role.permissions = ["dlq_replay.reject"]
    await db_session.flush()
    with pytest.raises(approval_rbac.ApprovalRBACError):
        await approval_rbac.check_approval_permission(
            db_session,
            workspace_id=WORKSPACE,
            actor="alice",
            approval_type="L3_TOOL",
            action="approve",
        )


@pytest.mark.asyncio
async def test_unknown_actor_denied(db_session) -> None:
    await _seed_role(db_session, workspace_id=WORKSPACE)
    with pytest.raises(approval_rbac.ApprovalRBACError):
        await approval_rbac.check_approval_permission(
            db_session,
            workspace_id=WORKSPACE,
            actor="mallory",
            approval_type="L3_TOOL",
            action="approve",
        )


@pytest.mark.asyncio
async def test_no_roles_legacy_open_mode(db_session) -> None:
    """A workspace without enabled roles stays open (backwards compatible)."""
    assert (
        await approval_rbac.check_approval_permission(
            db_session,
            workspace_id=WORKSPACE,
            actor="anyone",
            approval_type="DLQ_REPLAY",
            action="approve",
        )
        is True
    )


@pytest.mark.asyncio
async def test_rbac_disabled_global_allow(db_session) -> None:
    await _seed_role(db_session, workspace_id=WORKSPACE)
    settings = get_settings()
    original = settings.approval_rbac_enabled
    settings.approval_rbac_enabled = False
    try:
        assert (
            await approval_rbac.check_approval_permission(
                db_session,
                workspace_id=WORKSPACE,
                actor="mallory",
                approval_type="L3_TOOL",
                action="approve",
            )
            is True
        )
    finally:
        settings.approval_rbac_enabled = original


@pytest.mark.asyncio
async def test_disabled_role_ignored(db_session) -> None:
    await _seed_role(db_session, workspace_id=WORKSPACE)
    role = (
        await db_session.execute(
            select(AgentApprovalRole).where(
                AgentApprovalRole.workspace_id == WORKSPACE,
                AgentApprovalRole.role_name == "ops-admin",
            )
        )
    ).scalar_one()
    role.enabled = False
    await db_session.flush()
    # No enabled roles left -> legacy open mode.
    assert (
        await approval_rbac.check_approval_permission(
            db_session,
            workspace_id=WORKSPACE,
            actor="alice",
            approval_type="L3_TOOL",
            action="approve",
        )
        is True
    )


@pytest.mark.asyncio
async def test_workspace_isolation(db_session) -> None:
    """Roles of workspace A never grant permissions in workspace B."""
    await _seed_role(db_session, workspace_id=WORKSPACE)
    # Workspace B configures its own role WITHOUT alice -> she is denied there.
    await approval_rbac.create_role(
        db_session,
        workspace_id=OTHER_WORKSPACE,
        role_name="ops-admin",
        permissions=["tool.approve"],
        actors=["charlie"],
        enabled=True,
        trace_id="test",
    )
    with pytest.raises(approval_rbac.ApprovalRBACError):
        await approval_rbac.check_approval_permission(
            db_session,
            workspace_id=OTHER_WORKSPACE,
            actor="alice",
            approval_type="L3_TOOL",
            action="approve",
        )


@pytest.mark.asyncio
async def test_approve_api_blocked_without_permission(db_session) -> None:
    """The real approve path raises ApprovalRBACError -> API 403."""
    await _seed_role(
        db_session,
        workspace_id=WORKSPACE,
        role_name="ops-admin",
    )
    role = (
        await db_session.execute(
            select(AgentApprovalRole).where(
                AgentApprovalRole.workspace_id == WORKSPACE,
                AgentApprovalRole.role_name == "ops-admin",
            )
        )
    ).scalar_one()
    role.permissions = ["calibration.approve"]  # NOT tool.approve
    await db_session.flush()
    approval = await _seed_approval(db_session, workspace_id=WORKSPACE)
    backend = task_queue.get_queue_backend()
    with pytest.raises(approval_rbac.ApprovalRBACError):
        await approval_service.approve_approval(
            db_session,
            backend,
            workspace_id=WORKSPACE,
            approval_id=approval.id,
            actor="alice",
            trace_id="test",
        )


@pytest.mark.asyncio
async def test_approve_api_succeeds_with_permission(db_session, monkeypatch) -> None:
    await _seed_role(db_session, workspace_id=WORKSPACE)
    approval = await _seed_approval(db_session, workspace_id=WORKSPACE)
    backend = task_queue.get_queue_backend()
    dispatched: list[str] = []

    async def fake_dispatch(session, backend, *, approval, decision, actor, note, trace_id):
        dispatched.append(decision)

    monkeypatch.setattr(approval_service, "_dispatch", fake_dispatch)
    decided = await approval_service.approve_approval(
        db_session,
        backend,
        workspace_id=WORKSPACE,
        approval_id=approval.id,
        actor="alice",
        trace_id="test",
    )
    assert decided.status == "approved"
    assert decided.actor == "alice"
    assert dispatched == ["approved"]


@pytest.mark.asyncio
async def test_role_delete(db_session) -> None:
    await _seed_role(db_session, workspace_id=WORKSPACE)
    assert (
        await approval_rbac.delete_role(db_session, workspace_id=WORKSPACE, role_name="ops-admin")
        is True
    )
    assert (
        await approval_rbac.delete_role(db_session, workspace_id=WORKSPACE, role_name="ops-admin")
        is False
    )
    roles = await approval_rbac.list_roles(db_session, workspace_id=WORKSPACE)
    assert roles == []


# --------------------------------------------------------------------------- #
# API-level enforcement: Approval Center endpoints must return 403, never a
# 500 or a silent allow, when the actor lacks the permission.
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_approve_api_403_without_permission(api_client, db_session) -> None:
    """RBAC denial surfaces as HTTP 403 through the unified Approval API."""
    await _seed_role(db_session, workspace_id=WORKSPACE)
    role = (
        await db_session.execute(
            select(AgentApprovalRole).where(
                AgentApprovalRole.workspace_id == WORKSPACE,
                AgentApprovalRole.role_name == "ops-admin",
            )
        )
    ).scalar_one()
    role.permissions = ["calibration.approve"]  # alice cannot approve tools
    await db_session.flush()
    approval = await _seed_approval(db_session, workspace_id=WORKSPACE)
    response = api_client.post(
        f"/api/v1/approvals/{approval.id}/approve",
        json={"actor": "alice"},
    )
    assert response.status_code == 403, response.text
    assert "lacks permission" in response.json()["detail"]


@pytest.mark.asyncio
async def test_approve_api_allowed_with_permission(api_client, db_session, monkeypatch) -> None:
    """An actor holding the permission may decide through the API (200)."""
    await _seed_role(db_session, workspace_id=WORKSPACE)
    approval = await _seed_approval(db_session, workspace_id=WORKSPACE)

    async def fake_dispatch(session, backend, *, approval, decision, actor, note, trace_id):
        return None

    monkeypatch.setattr(approval_service, "_dispatch", fake_dispatch)
    response = api_client.post(
        f"/api/v1/approvals/{approval.id}/approve",
        json={"actor": "alice"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "approved"
    assert response.json()["actor"] == "alice"


@pytest.mark.asyncio
async def test_reject_api_403_without_permission(api_client, db_session) -> None:
    """Reject is permission-gated the same way as approve."""
    await _seed_role(db_session, workspace_id=WORKSPACE)
    role = (
        await db_session.execute(
            select(AgentApprovalRole).where(
                AgentApprovalRole.workspace_id == WORKSPACE,
                AgentApprovalRole.role_name == "ops-admin",
            )
        )
    ).scalar_one()
    role.permissions = ["dlq_replay.approve"]  # no tool.reject
    await db_session.flush()
    approval = await _seed_approval(db_session, workspace_id=WORKSPACE)
    response = api_client.post(
        f"/api/v1/approvals/{approval.id}/reject",
        json={"actor": "alice"},
    )
    assert response.status_code == 403, response.text
