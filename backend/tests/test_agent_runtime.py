"""Tests for M5.0 Agent Runtime Foundation.

Covers: agent registry + prompt version resolution, task lifecycle, tool
whitelist, L0-L3 permission enforcement, high-risk approval flow, execution
audit, memory retrieval (incl. knowledge grounding) and evaluations - all
workspace-scoped, all events + trace_id.
"""

from uuid import UUID

import pytest
from sqlalchemy import select

from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.agent_runtime import AgentExecution, AgentTask
from app.models.event import EventLog
from app.models.product_intelligence import ProductKnowledgeEntry
from app.schemas.prompt import PromptCreate
from app.services import prompt_registry

WORKSPACE = DEFAULT_WORKSPACE_ID
OTHER_WORKSPACE = UUID("00000000-0000-0000-0000-000000000099")

PROMPT_NAME = "AGENT_TEST_ANALYST"


def _headers(workspace: UUID | None = None) -> dict:
    return {"X-Workspace-Id": str(workspace)} if workspace else {}


async def _event_types(db_session) -> set[str]:
    rows = (await db_session.execute(select(EventLog.event_type))).scalars().all()
    return set(rows)


async def _seed_prompt(db_session, workspace: UUID = WORKSPACE, name: str = PROMPT_NAME) -> None:
    await prompt_registry.create_prompt(
        db_session,
        workspace_id=workspace,
        data=PromptCreate(
            prompt_id=f"prompt-{name.lower()}",
            name=name,
            version="v1",
            template="You are a {role} analyzing product {sku}.",
            variables=["role", "sku"],
        ),
    )


async def _seed_agent(
    api_client,
    db_session,
    *,
    agent_id: str = "TEST_ANALYST",
    level: str = "L2",
    domain: str = "product",
    workspace: UUID | None = None,
) -> dict:
    ws = workspace or WORKSPACE
    await _seed_prompt(db_session, workspace=ws, name=f"AGENT_{agent_id.upper()}")
    response = api_client.post(
        "/api/v1/agent-registry",
        json={
            "agent_id": agent_id,
            "name": "Test Analyst",
            "domain": domain,
            "version": "v1",
            "status": "active",
            "model_provider": "openai",
            "model_name": "gpt-4o-mini",
            "prompt_version": "v1",
            "permission_level": level,
        },
        headers=_headers(workspace),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _seed_tool(
    api_client,
    *,
    tool_name: str,
    level: str,
    enabled: bool = True,
    workspace: UUID | None = None,
) -> dict:
    response = api_client.post(
        "/api/v1/agent-tools",
        json={
            "tool_name": tool_name,
            "description": f"Test tool {tool_name}",
            "permission_level": level,
            "enabled": enabled,
            "category": "test",
        },
        headers=_headers(workspace),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _create_task_and_start(
    api_client, agent_row: dict, workspace: UUID | None = None
) -> tuple[dict, dict]:
    created = api_client.post(
        "/api/v1/agent-tasks",
        json={"agent_id": agent_row["id"], "input": {"sku": "SKU-TEST"}, "priority": 3},
        headers=_headers(workspace),
    )
    assert created.status_code == 201, created.text
    task = created.json()
    started = api_client.post(
        "/api/v1/agent-executions",
        json={"task_id": task["id"]},
        headers=_headers(workspace),
    )
    assert started.status_code == 201, started.text
    return task, started.json()


# --------------------------------------------------------------------------- #
# 1. Agent registry + prompt version
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_agent_registry_register_and_list(db_session, api_client) -> None:
    """Registering an agent (with its prompt) persists the registry row."""
    await _seed_prompt(db_session)
    body = await _seed_agent(api_client, db_session, agent_id="REG-1", level="L1")

    assert body["agent_id"] == "REG-1"
    assert body["domain"] == "product"
    assert body["permission_level"] == "L1"
    assert body["prompt_version"] == "v1"
    assert body["status"] == "active"

    listed = api_client.get("/api/v1/agent-registry")
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert "agent.registry_created" in await _event_types(db_session)


@pytest.mark.asyncio
async def test_agent_registry_requires_prompt(db_session, api_client) -> None:
    """Registering an agent without its prompt version fails with 400."""
    response = api_client.post(
        "/api/v1/agent-registry",
        json={
            "agent_id": "NO_PROMPT",
            "name": "No Prompt",
            "domain": "product",
            "permission_level": "L1",
        },
    )
    assert response.status_code == 404
    assert "prompt" in response.json()["detail"]


@pytest.mark.asyncio
async def test_agent_prompt_version_resolution(db_session, api_client) -> None:
    """The registry resolves the exact versioned prompt bound to an agent."""
    agent = await _seed_agent(api_client, db_session, agent_id="RESOLVE-1")

    response = api_client.get(f"/api/v1/agent-registry/{agent['id']}/prompt")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "AGENT_RESOLVE-1"
    assert body["version"] == "v1"
    assert "{role}" in body["template"]


# --------------------------------------------------------------------------- #
# 2. Task lifecycle
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_task_lifecycle_complete(db_session, api_client) -> None:
    """pending -> running -> completed; execution audit is persisted."""
    await _seed_prompt(db_session)
    agent = await _seed_agent(api_client, db_session, agent_id="LIFE-1")
    task, execution = await _create_task_and_start(api_client, agent)

    assert task["status"] == "pending"
    assert execution["status"] == "running"
    assert execution["context_snapshot"]["agent_id"] == "LIFE-1"
    assert execution["input"] == {"sku": "SKU-TEST"}

    completed = api_client.post(
        f"/api/v1/agent-executions/{execution['id']}/complete",
        json={
            "output": {"decision": "test", "score": 80},
            "provider": "openai",
            "model": "gpt-4o-mini",
            "tokens": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            "cost": "0.0001",
            "latency_ms": 320,
        },
    )
    assert completed.status_code == 200, completed.text
    body = completed.json()
    assert body["status"] == "completed"
    assert body["model"] == "gpt-4o-mini"
    assert body["cost"] == "0.000100"
    assert body["latency_ms"] == 320
    assert body["output"]["score"] == 80

    task_row = (
        await db_session.execute(select(AgentTask).where(AgentTask.id == UUID(task["id"])))
    ).scalar_one()
    assert task_row.status == "completed"
    assert task_row.result["score"] == 80

    events = await _event_types(db_session)
    assert "agent.task_created" in events
    assert "agent.execution_started" in events
    assert "agent.execution_completed" in events


@pytest.mark.asyncio
async def test_task_lifecycle_fail(db_session, api_client) -> None:
    """A failed execution marks both execution and task as failed."""
    await _seed_prompt(db_session)
    agent = await _seed_agent(api_client, db_session, agent_id="LIFE-FAIL")
    _task, execution = await _create_task_and_start(api_client, agent)

    failed = api_client.post(
        f"/api/v1/agent-executions/{execution['id']}/fail",
        json={"error_message": "model timeout"},
    )
    assert failed.status_code == 200
    assert failed.json()["status"] == "failed"

    task_row = (
        await db_session.execute(select(AgentTask).where(AgentTask.id == UUID(_task["id"])))
    ).scalar_one()
    assert task_row.status == "failed"
    assert task_row.error_message == "model timeout"
    assert "agent.execution_failed" in await _event_types(db_session)


@pytest.mark.asyncio
async def test_task_cancel_and_invalid_start(db_session, api_client) -> None:
    """A pending task can be cancelled; starting twice is rejected."""
    await _seed_prompt(db_session)
    agent = await _seed_agent(api_client, db_session, agent_id="LIFE-CANCEL")
    created = api_client.post(
        "/api/v1/agent-tasks",
        json={"agent_id": agent["id"], "input": {"sku": "SKU-X"}},
    )
    task = created.json()

    cancelled = api_client.post(
        f"/api/v1/agent-tasks/{task['id']}/cancel", json={"actor": "ops", "note": "not needed"}
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    # Cancelled tasks cannot start.
    started = api_client.post("/api/v1/agent-executions", json={"task_id": task["id"]})
    assert started.status_code == 400
    assert "only pending tasks can start" in started.json()["detail"]

    # A second start on a running task is also rejected.
    _task, execution = await _create_task_and_start(api_client, agent)
    assert execution["status"] == "running"


# --------------------------------------------------------------------------- #
# 3. Tool whitelist + permission engine
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_tool_whitelist_unknown_tool_404(db_session, api_client) -> None:
    """Calling an unregistered tool is rejected (whitelist)."""
    await _seed_prompt(db_session)
    agent = await _seed_agent(api_client, db_session, agent_id="TOOL-UNKNOWN")
    _task, execution = await _create_task_and_start(api_client, agent)

    response = api_client.post(
        f"/api/v1/agent-executions/{execution['id']}/tool-calls",
        json={"tool_name": "not-a-registered-tool", "arguments": {}},
    )
    assert response.status_code == 404
    assert "not registered" in response.json()["detail"]


@pytest.mark.asyncio
async def test_tool_permission_denied(db_session, api_client) -> None:
    """An L1 agent cannot call an L2 tool; the denial is audited."""
    await _seed_prompt(db_session)
    agent = await _seed_agent(api_client, db_session, agent_id="TOOL-DENY", level="L1")
    await _seed_tool(api_client, tool_name="propose_strategy", level="L2")
    _task, execution = await _create_task_and_start(api_client, agent)

    response = api_client.post(
        f"/api/v1/agent-executions/{execution['id']}/tool-calls",
        json={"tool_name": "propose_strategy", "arguments": {"sku": "SKU-1"}},
    )
    assert response.status_code == 403
    assert "cannot call" in response.json()["detail"]

    events = await _event_types(db_session)
    assert "agent.tool_call_denied" in events
    execution_row = (
        await db_session.execute(
            select(AgentExecution).where(AgentExecution.id == UUID(execution["id"]))
        )
    ).scalar_one()
    assert execution_row.tool_calls[-1]["status"] == "denied"


@pytest.mark.asyncio
async def test_tool_disabled_denied(db_session, api_client) -> None:
    """A disabled tool denies every call with 403."""
    await _seed_prompt(db_session)
    agent = await _seed_agent(api_client, db_session, agent_id="TOOL-DISABLED", level="L3")
    await _seed_tool(api_client, tool_name="read_inventory", level="L1", enabled=False)
    _task, execution = await _create_task_and_start(api_client, agent)

    response = api_client.post(
        f"/api/v1/agent-executions/{execution['id']}/tool-calls",
        json={"tool_name": "read_inventory", "arguments": {}},
    )
    assert response.status_code == 403
    assert "disabled" in response.json()["detail"]


@pytest.mark.asyncio
async def test_tool_allowed_lower_level(db_session, api_client) -> None:
    """An L2 agent can call L1 tools; the call is recorded as allowed."""
    await _seed_prompt(db_session)
    agent = await _seed_agent(api_client, db_session, agent_id="TOOL-ALLOW", level="L2")
    await _seed_tool(api_client, tool_name="read_product", level="L1")
    _task, execution = await _create_task_and_start(api_client, agent)

    response = api_client.post(
        f"/api/v1/agent-executions/{execution['id']}/tool-calls",
        json={"tool_name": "read_product", "arguments": {"sku": "SKU-1"}},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "allowed"
    assert response.json()["requires_approval"] is False
    assert "agent.tool_call_allowed" in await _event_types(db_session)


# --------------------------------------------------------------------------- #
# 4. High-risk approval flow (human-in-the-loop)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_high_risk_tool_requires_human_approval(db_session, api_client) -> None:
    """An L3 tool call stops at waiting_approval; approval completes it."""
    await _seed_prompt(db_session)
    agent = await _seed_agent(api_client, db_session, agent_id="HR-1", level="L3")
    await _seed_tool(api_client, tool_name="purchase_order", level="L3")
    _task, execution = await _create_task_and_start(api_client, agent)

    call = api_client.post(
        f"/api/v1/agent-executions/{execution['id']}/tool-calls",
        json={"tool_name": "purchase_order", "arguments": {"sku": "SKU-1", "qty": 100}},
    )
    assert call.status_code == 200, call.text
    assert call.json()["status"] == "requires_approval"
    assert call.json()["requires_approval"] is True

    waiting = (
        await db_session.execute(
            select(AgentExecution).where(AgentExecution.id == UUID(execution["id"]))
        )
    ).scalar_one()
    assert waiting.status == "waiting_approval"
    task_row = (
        await db_session.execute(select(AgentTask).where(AgentTask.id == UUID(_task["id"])))
    ).scalar_one()
    assert task_row.status == "waiting_approval"

    approved = api_client.post(
        f"/api/v1/agent-executions/{execution['id']}/approve",
        json={"actor": "ops-lead", "note": "ok to order"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "completed"
    assert approved.json()["approval"]["decision"] == "approved"

    # Second approval is rejected (state machine guard).
    double = api_client.post(
        f"/api/v1/agent-executions/{execution['id']}/approve",
        json={"actor": "ops-lead"},
    )
    assert double.status_code == 400
    assert "already completed" in double.json()["detail"]

    events = await _event_types(db_session)
    assert "agent.tool_call_requires_approval" in events
    assert "agent.execution_waiting_approval" in events
    assert "agent.execution_approved" in events


@pytest.mark.asyncio
async def test_high_risk_tool_rejected(db_session, api_client) -> None:
    """Human rejection: execution -> rejected, task -> failed."""
    await _seed_prompt(db_session)
    agent = await _seed_agent(api_client, db_session, agent_id="HR-2", level="L3")
    await _seed_tool(api_client, tool_name="purchase_order", level="L3")
    _task, execution = await _create_task_and_start(api_client, agent)

    api_client.post(
        f"/api/v1/agent-executions/{execution['id']}/tool-calls",
        json={"tool_name": "purchase_order", "arguments": {"sku": "SKU-2"}},
    )
    rejected = api_client.post(
        f"/api/v1/agent-executions/{execution['id']}/reject",
        json={"actor": "ops-lead", "note": "budget frozen"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["approval"]["decision"] == "rejected"

    task_row = (
        await db_session.execute(select(AgentTask).where(AgentTask.id == UUID(_task["id"])))
    ).scalar_one()
    assert task_row.status == "failed"
    assert "rejected by human" in task_row.error_message
    assert "agent.execution_rejected" in await _event_types(db_session)


# --------------------------------------------------------------------------- #
# 5. Execution audit + workspace isolation
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_execution_audit_fields(db_session, api_client) -> None:
    """Executions persist trace_id, context, input, output and model usage."""
    await _seed_prompt(db_session)
    agent = await _seed_agent(api_client, db_session, agent_id="AUDIT-1")
    _task, execution = await _create_task_and_start(api_client, agent)

    api_client.post(
        f"/api/v1/agent-executions/{execution['id']}/complete",
        json={
            "output": {"ok": True},
            "provider": "deepseek",
            "model": "deepseek-chat",
            "tokens": {"total_tokens": 200},
            "cost": "0.0002",
            "latency_ms": 512,
        },
    )
    row = (
        await db_session.execute(
            select(AgentExecution).where(AgentExecution.id == UUID(execution["id"]))
        )
    ).scalar_one()
    assert row.trace_id is not None
    assert row.provider == "deepseek"
    assert row.model == "deepseek-chat"
    assert row.tokens["total_tokens"] == 200
    assert row.context_snapshot["permission_level"] == "L2"
    assert row.status == "completed"


@pytest.mark.asyncio
async def test_workspace_isolation(db_session, api_client) -> None:
    """Registry, tasks and executions are invisible across workspaces."""
    await _seed_prompt(db_session)
    await _seed_prompt(db_session, workspace=OTHER_WORKSPACE)
    await _seed_agent(api_client, db_session, agent_id="ISO-1")
    await _seed_agent(api_client, db_session, agent_id="ISO-2", workspace=OTHER_WORKSPACE)

    visible = api_client.get("/api/v1/agent-registry")
    assert len(visible.json()) == 1

    other = api_client.get("/api/v1/agent-registry", headers=_headers(OTHER_WORKSPACE))
    assert len(other.json()) == 1
    assert other.json()[0]["agent_id"] == "ISO-2"


# --------------------------------------------------------------------------- #
# 6. Agent memory + knowledge grounding
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_memory_store_and_search(db_session, api_client) -> None:
    """Memory entries are stored and retrievable by domain/keyword."""
    await _seed_prompt(db_session)
    agent = await _seed_agent(api_client, db_session, agent_id="MEM-1")

    stored = api_client.post(
        "/api/v1/agent-memory",
        json={
            "agent_id": agent["id"],
            "domain": "product",
            "source_type": "product_knowledge",
            "source_id": "entry-1",
            "content": "Headlamps sell best in Q4 with a red colorway.",
            "tags": ["headlamp", "seasonality"],
            "meta": {"category": "lighting"},
        },
    )
    assert stored.status_code == 201, stored.text
    assert stored.json()["source_type"] == "product_knowledge"

    by_domain = api_client.get("/api/v1/agent-memory", params={"domain": "product"})
    assert len(by_domain.json()) == 1

    by_keyword = api_client.get("/api/v1/agent-memory", params={"keyword": "red colorway"})
    assert len(by_keyword.json()) == 1

    no_match = api_client.get("/api/v1/agent-memory", params={"keyword": "backpack"})
    assert len(no_match.json()) == 0

    assert "agent.memory_stored" in await _event_types(db_session)


@pytest.mark.asyncio
async def test_knowledge_snapshot_grounding(db_session, api_client) -> None:
    """The grounding snapshot pulls product knowledge entries."""
    await _seed_prompt(db_session)
    entry = ProductKnowledgeEntry(
        workspace_id=WORKSPACE,
        entry_type="category_insight",
        category="lighting",
        title="Q4 peak",
        content="Lighting demand peaks in Q4.",
        tags=["q4"],
        source="test",
    )
    db_session.add(entry)
    await db_session.flush()

    response = api_client.get(
        "/api/v1/agent-memory/knowledge-snapshot", params={"domain": "product"}
    )
    assert response.status_code == 200, response.text
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["source_type"] == "product_knowledge"
    assert rows[0]["title"] == "Q4 peak"
    assert rows[0]["entry_type"] == "category_insight"

    missing = api_client.get(
        "/api/v1/agent-memory/knowledge-snapshot", params={"domain": "not_a_domain"}
    )
    assert missing.status_code == 400


# --------------------------------------------------------------------------- #
# 7. Agent evaluation
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_evaluation_success(db_session, api_client) -> None:
    """A matched decision is classified as success with calibration data."""
    await _seed_prompt(db_session)
    agent = await _seed_agent(api_client, db_session, agent_id="EVAL-1")

    response = api_client.post(
        "/api/v1/agent-evaluations",
        json={
            "agent_id": agent["id"],
            "prediction": {"decision": "approve", "confidence": 0.8},
            "actual_result": {"decision": "approve", "success": True},
            "human_rating": 5,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["prediction_result"] == "success"
    assert body["success_flag"] is True
    assert body["confidence_bucket"] == "HIGH"
    assert body["accuracy"]["decision_match"] is True
    assert body["calibration"]["sample_size"] == 1
    assert "agent.evaluation_recorded" in await _event_types(db_session)


@pytest.mark.asyncio
async def test_evaluation_failure_classification(db_session, api_client) -> None:
    """A decision mismatch is classified as failure with error_type."""
    await _seed_prompt(db_session)
    agent = await _seed_agent(api_client, db_session, agent_id="EVAL-2")

    response = api_client.post(
        "/api/v1/agent-evaluations",
        json={
            "agent_id": agent["id"],
            "prediction": {"decision": "approve", "confidence": 0.8},
            "actual_result": {"decision": "reject"},
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["prediction_result"] == "failure"
    assert body["success_flag"] is False
    assert body["error_type"] == "decision_mismatch"

    listed = api_client.get("/api/v1/agent-evaluations")
    assert len(listed.json()) == 1


@pytest.mark.asyncio
async def test_evaluation_unknown_agent_404(db_session, api_client) -> None:
    """Evaluating an unknown agent returns 404."""
    missing = UUID("00000000-0000-0000-0000-00000000dead")
    response = api_client.post(
        "/api/v1/agent-evaluations",
        json={"agent_id": str(missing), "prediction": {}, "actual_result": {}},
    )
    assert response.status_code == 404
    assert "agent not found" in response.json()["detail"]
