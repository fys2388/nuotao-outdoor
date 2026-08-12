"""Tests for the M5.5 platform APIs (lifecycle / RBAC / SLA / metrics /
console audit) and their security posture (workspace isolation, no sensitive
fields in responses, console header required for audit events).
"""

from uuid import UUID

import pytest
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.event import EventLog
from app.schemas.agent_runtime import AgentRegisterRequest
from app.schemas.prompt import PromptCreate
from app.services import agent_runtime, prompt_registry
from sqlalchemy import select

WORKSPACE = DEFAULT_WORKSPACE_ID
OTHER_WORKSPACE = UUID("00000000-0000-0000-0000-000000000099")

CONSOLE_HEADERS = {"X-Nuotao-Console": "runtime-console"}


async def _seed_agent(db_session, *, agent_code: str = "PLATFORM_TEST") -> None:
    await prompt_registry.create_prompt(
        db_session,
        workspace_id=WORKSPACE,
        data=PromptCreate(
            prompt_id="prompt-platform-test",
            name=f"AGENT_{agent_code}",
            version="v1",
            template="Analyze {sku}.",
            variables=["sku"],
        ),
    )
    await agent_runtime.register_agent(
        db_session,
        workspace_id=WORKSPACE,
        data=AgentRegisterRequest(
            agent_id=agent_code,
            name="Platform Test Agent",
            domain="operations",
            version="v1",
            status="active",
            model_provider="openai",
            model_name="gpt-4o-mini",
            prompt_version="v1",
            permission_level="L2",
        ),
    )


def _get_agent_id(api_client, agent_code: str = "PLATFORM_TEST") -> str:
    response = api_client.get("/api/v1/agent-registry")
    assert response.status_code == 200
    for agent in response.json():
        if agent["agent_id"] == agent_code:
            return agent["id"]
    raise AssertionError("agent not registered")


def test_metrics_api_shape(api_client):
    response = api_client.get("/api/v1/agent-runtime/metrics")
    assert response.status_code == 200
    body = response.json()
    for key in (
        "agent_tasks_created_total",
        "agent_tasks_completed_total",
        "agent_tasks_failed_total",
        "agent_execution_total",
        "agent_llm_tokens_total",
        "agent_llm_cost_total",
        "agent_retry_total",
        "agent_dlq_total",
        "agent_approval_pending",
        "agent_alert_open",
        "agent_worker_active",
        "agent_worker_dead",
        "queue",
    ):
        assert key in body


def test_metrics_never_leak_sensitive_fields(api_client):
    """Runtime metrics must never expose prompt text / keys / PII."""
    response = api_client.get("/api/v1/agent-runtime/metrics")
    assert response.status_code == 200
    serialized = str(response.json()).lower()
    for forbidden in ("api_key", "password", "secret", "authorization", "customer_email", "prompt"):
        assert forbidden not in serialized


def test_console_audit_requires_header(api_client):
    response = api_client.post(
        "/api/v1/agent-runtime/console-audit",
        json={"action": "viewed", "actor": "ops"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_console_audit_records_event(api_client, db_session):
    response = api_client.post(
        "/api/v1/agent-runtime/console-audit",
        json={
            "action": "approved",
            "entity_type": "agent_approval",
            "entity_id": "abc",
            "actor": "ops",
        },
        headers=CONSOLE_HEADERS,
    )
    assert response.status_code == 200
    rows = (
        (
            await db_session.execute(
                select(EventLog).where(
                    EventLog.event_type == "agent.console.approved",
                    EventLog.entity_type == "agent_approval",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(list(rows)) == 1


@pytest.mark.asyncio
async def test_lifecycle_pause_resume_api(api_client, db_session):
    await _seed_agent(db_session)
    agent_uuid = _get_agent_id(api_client)
    response = api_client.post(f"/api/v1/agent-registry/{agent_uuid}/pause", json={"actor": "ops"})
    assert response.status_code == 200
    assert response.json()["status"] == "paused"
    response = api_client.post(f"/api/v1/agent-registry/{agent_uuid}/resume", json={"actor": "ops"})
    assert response.status_code == 200
    assert response.json()["status"] == "active"


@pytest.mark.asyncio
async def test_lifecycle_versions_api(api_client, db_session):
    await _seed_agent(db_session)
    agent_uuid = _get_agent_id(api_client)
    response = api_client.post(
        f"/api/v1/agent-registry/{agent_uuid}/versions",
        json={"version": "v2", "prompt_version": "v1", "created_by": "ops"},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "draft"
    response = api_client.post(
        f"/api/v1/agent-registry/{agent_uuid}/versions/v2/activate",
        json={"actor": "ops"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "active"
    listing = api_client.get(f"/api/v1/agent-registry/{agent_uuid}/versions")
    assert listing.status_code == 200
    assert any(v["version"] == "v2" for v in listing.json())


@pytest.mark.asyncio
async def test_retire_requires_approval(api_client, db_session):
    await _seed_agent(db_session)
    agent_uuid = _get_agent_id(api_client)
    response = api_client.post(f"/api/v1/agent-registry/{agent_uuid}/retire", json={"actor": "ops"})
    assert response.status_code == 202
    assert response.json()["action"] == "retire"
    # Agent is not retired until a human approval.
    registry = api_client.get("/api/v1/agent-registry").json()
    agent = next(a for a in registry if a["id"] == agent_uuid)
    assert agent["status"] == "active"


@pytest.mark.asyncio
async def test_rollback_requires_approval(api_client, db_session):
    """Rollback to a *historical* version needs a human approval (202)."""
    await _seed_agent(db_session)
    agent_uuid = _get_agent_id(api_client)
    for version in ("v1", "v2"):
        published = api_client.post(
            f"/api/v1/agent-registry/{agent_uuid}/versions",
            json={"version": version, "prompt_version": "v1", "created_by": "ops"},
        )
        assert published.status_code == 201
        activated = api_client.post(
            f"/api/v1/agent-registry/{agent_uuid}/versions/{version}/activate",
            json={"actor": "ops"},
        )
        assert activated.status_code == 200
    # Rolling back to the current active version is a no-op -> 400.
    noop = api_client.post(
        f"/api/v1/agent-registry/{agent_uuid}/rollback",
        json={"target_version": "v2", "actor": "ops"},
    )
    assert noop.status_code == 400
    # Rolling back to the historical v1 -> approval proposal (202).
    response = api_client.post(
        f"/api/v1/agent-registry/{agent_uuid}/rollback",
        json={"target_version": "v1", "actor": "ops"},
    )
    assert response.status_code == 202
    assert response.json()["action"] == "rollback"


def test_roles_api_crud(api_client):
    response = api_client.post(
        "/api/v1/approval-roles",
        json={
            "role_name": "ops-admin",
            "permissions": ["tool.approve", "dlq_replay.approve"],
            "actors": ["alice"],
            "enabled": True,
        },
    )
    assert response.status_code == 200
    listing = api_client.get("/api/v1/approval-roles")
    assert listing.status_code == 200
    assert any(r["role_name"] == "ops-admin" for r in listing.json())
    response = api_client.delete("/api/v1/approval-roles/ops-admin")
    assert response.status_code == 204
    listing = api_client.get("/api/v1/approval-roles")
    assert not any(r["role_name"] == "ops-admin" for r in listing.json())


def test_sla_api_upsert_and_list(api_client):
    response = api_client.post(
        "/api/v1/approval-slas",
        json={
            "approval_type": "DLQ_REPLAY",
            "warning_after_seconds": 60,
            "expire_after_seconds": 600,
        },
    )
    assert response.status_code == 200
    assert response.json()["warning_after_seconds"] == 60
    listing = api_client.get("/api/v1/approval-slas")
    assert listing.status_code == 200
    assert any(s["approval_type"] == "DLQ_REPLAY" for s in listing.json())


def test_sla_scan_api(api_client):
    response = api_client.post("/api/v1/approvals/sla-scan")
    assert response.status_code == 200
    assert "warned" in response.json()
    assert "expired" in response.json()


@pytest.mark.asyncio
async def test_console_audit_workspace_isolation(api_client, db_session):
    response = api_client.post(
        "/api/v1/agent-runtime/console-audit",
        json={"action": "viewed", "actor": "ops"},
        headers=CONSOLE_HEADERS,
    )
    assert response.status_code == 200
    rows = (
        (
            await db_session.execute(
                select(EventLog).where(
                    EventLog.event_type == "agent.console.viewed",
                    EventLog.workspace_id == WORKSPACE,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(list(rows)) == 1
    other = (
        (
            await db_session.execute(
                select(EventLog).where(
                    EventLog.event_type == "agent.console.viewed",
                    EventLog.workspace_id == OTHER_WORKSPACE,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(list(other)) == 0
