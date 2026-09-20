"""Agent platform B2C/B2B/SHARED scope isolation tests."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select

from app.core.agent_scope import scope_compatible
from app.core.config import get_settings
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.agent_operations import AgentApproval
from app.models.agent_runtime import AgentExecution
from app.models.event import EventLog
from app.schemas.agent_runtime import AgentRegisterRequest, TaskCreate
from app.schemas.prompt import PromptCreate
from app.services import (
    agent_budget,
    agent_lifecycle,
    agent_policies,
    agent_runtime,
    approval_rbac,
    approval_service,
    prompt_registry,
)

WORKSPACE = DEFAULT_WORKSPACE_ID


async def _seed_agent(session, *, agent_id: str, business_scope: str):
    prompt_name = f"AGENT_{agent_id.upper()}"
    await prompt_registry.create_prompt(
        session,
        workspace_id=WORKSPACE,
        data=PromptCreate(
            prompt_id=f"prompt-{agent_id.lower()}",
            name=prompt_name,
            version="v1",
            template="Analyze {sku}.",
            variables=["sku"],
        ),
    )
    return await agent_runtime.register_agent(
        session,
        workspace_id=WORKSPACE,
        data=AgentRegisterRequest(
            agent_id=agent_id,
            name=f"{business_scope} agent",
            domain="product",
            prompt_version="v1",
            permission_level="L2",
            business_scope=business_scope,
        ),
    )


def test_scope_compatibility_matrix() -> None:
    assert scope_compatible("B2C", "B2C") is True
    assert scope_compatible("B2C", "SHARED") is True
    assert scope_compatible("B2C", "B2B") is False
    assert scope_compatible("B2B", "B2B") is True
    assert scope_compatible("B2B", "SHARED") is True
    assert scope_compatible("B2B", "B2C") is False
    assert scope_compatible("SHARED", "B2C") is True
    assert scope_compatible("SHARED", "B2B") is True
    assert scope_compatible("SHARED", "SHARED") is True
    assert scope_compatible(None, "B2C") is False


@pytest.mark.asyncio
async def test_task_scope_inherits_and_never_widens_agent(db_session) -> None:
    b2c_agent = await _seed_agent(
        db_session,
        agent_id="SCOPE_B2C_TASK",
        business_scope="B2C",
    )
    inherited = await agent_runtime.create_task(
        db_session,
        workspace_id=WORKSPACE,
        data=TaskCreate(agent_id=b2c_agent.id, input={"sku": "A"}),
    )
    assert inherited.business_scope == "B2C"

    with pytest.raises(agent_runtime.AgentRuntimeError, match="not allowed"):
        await agent_runtime.create_task(
            db_session,
            workspace_id=WORKSPACE,
            data=TaskCreate(
                agent_id=b2c_agent.id,
                input={"sku": "A"},
                business_scope="B2B",
            ),
        )
    with pytest.raises(agent_runtime.AgentRuntimeError, match="cannot be changed"):
        await agent_runtime.register_agent(
            db_session,
            workspace_id=WORKSPACE,
            data=AgentRegisterRequest(
                agent_id=b2c_agent.agent_id,
                name=b2c_agent.name,
                domain=b2c_agent.domain,
                prompt_version=b2c_agent.prompt_version,
                permission_level=b2c_agent.permission_level,
                business_scope="SHARED",
            ),
        )
    with pytest.raises(agent_lifecycle.AgentLifecycleError, match="cannot activate"):
        await agent_lifecycle.publish_version(
            db_session,
            workspace_id=WORKSPACE,
            agent_uuid=b2c_agent.id,
            version="v2",
            prompt_version="v1",
            business_scope="SHARED",
        )

    shared_agent = await _seed_agent(
        db_session,
        agent_id="SCOPE_SHARED_TASK",
        business_scope="SHARED",
    )
    legacy_default = await agent_runtime.create_task(
        db_session,
        workspace_id=WORKSPACE,
        data=TaskCreate(agent_id=shared_agent.id, input={"sku": "S"}),
    )
    explicit_b2b = await agent_runtime.create_task(
        db_session,
        workspace_id=WORKSPACE,
        data=TaskCreate(
            agent_id=shared_agent.id,
            input={"sku": "S"},
            business_scope="B2B",
        ),
    )
    assert legacy_default.business_scope == "B2C"
    assert explicit_b2b.business_scope == "B2B"


@pytest.mark.asyncio
async def test_tool_calls_reject_cross_scope_access(db_session) -> None:
    b2c_agent = await _seed_agent(
        db_session,
        agent_id="SCOPE_B2C_TOOL",
        business_scope="B2C",
    )
    task = await agent_runtime.create_task(
        db_session,
        workspace_id=WORKSPACE,
        data=TaskCreate(agent_id=b2c_agent.id, input={"sku": "A"}),
    )
    execution = await agent_runtime.start_execution(
        db_session,
        workspace_id=WORKSPACE,
        task_id=task.id,
    )
    await agent_runtime.register_tool(
        db_session,
        workspace_id=WORKSPACE,
        tool_name="create_b2b_quote",
        description="B2B only",
        permission_level="L1",
        enabled=True,
        business_scope="B2B",
    )

    with pytest.raises(agent_runtime.ToolPermissionError, match="not compatible"):
        await agent_runtime.execute_tool_call(
            db_session,
            workspace_id=WORKSPACE,
            execution_id=execution.id,
            tool_name="create_b2b_quote",
            arguments={},
        )

    denied = (
        await db_session.execute(
            select(EventLog).where(EventLog.event_type == "agent.tool_call_denied")
        )
    ).scalars().all()
    assert denied
    assert denied[-1].payload["execution_business_scope"] == "B2C"
    assert denied[-1].payload["tool_business_scope"] == "B2B"

    await agent_runtime.register_tool(
        db_session,
        workspace_id=WORKSPACE,
        tool_name="read_product",
        description="Shared",
        permission_level="L1",
        enabled=True,
        business_scope="SHARED",
    )
    result = await agent_runtime.execute_tool_call(
        db_session,
        workspace_id=WORKSPACE,
        execution_id=execution.id,
        tool_name="read_product",
        arguments={},
    )
    assert result["status"] == "allowed"

    b2b_agent = await _seed_agent(
        db_session,
        agent_id="SCOPE_B2B_TOOL",
        business_scope="B2B",
    )
    b2b_task = await agent_runtime.create_task(
        db_session,
        workspace_id=WORKSPACE,
        data=TaskCreate(
            agent_id=b2b_agent.id,
            input={"sku": "B"},
            business_scope="B2B",
        ),
    )
    b2b_execution = await agent_runtime.start_execution(
        db_session,
        workspace_id=WORKSPACE,
        task_id=b2b_task.id,
    )
    await agent_runtime.register_tool(
        db_session,
        workspace_id=WORKSPACE,
        tool_name="read_b2c_customer",
        description="B2C only",
        permission_level="L1",
        enabled=True,
        business_scope="B2C",
    )
    with pytest.raises(agent_runtime.ToolPermissionError, match="not compatible"):
        await agent_runtime.execute_tool_call(
            db_session,
            workspace_id=WORKSPACE,
            execution_id=b2b_execution.id,
            tool_name="read_b2c_customer",
            arguments={},
        )


@pytest.mark.asyncio
async def test_policy_scope_is_separate_and_agent_bounded(db_session) -> None:
    shared_agent = await _seed_agent(
        db_session,
        agent_id="SCOPE_POLICY_SHARED",
        business_scope="SHARED",
    )
    b2c_policy = await agent_policies.set_budget_policy(
        db_session,
        workspace_id=WORKSPACE,
        agent_id=shared_agent.id,
        monthly_budget=Decimal("25"),
        max_cost_per_execution=Decimal("1"),
        alert_threshold=Decimal("0.8"),
        business_scope="B2C",
    )
    assert b2c_policy.business_scope == "B2C"
    assert (
        await agent_policies.get_budget_policy(
            db_session,
            workspace_id=WORKSPACE,
            agent_id=shared_agent.id,
            business_scope="B2C",
        )
    ).id == b2c_policy.id
    assert (
        await agent_policies.get_budget_policy(
            db_session,
            workspace_id=WORKSPACE,
            agent_id=shared_agent.id,
            business_scope="B2B",
        )
    ).id != b2c_policy.id

    b2c_agent = await _seed_agent(
        db_session,
        agent_id="SCOPE_POLICY_B2C",
        business_scope="B2C",
    )
    with pytest.raises(agent_policies.AgentPolicyError, match="not compatible"):
        await agent_policies.set_execution_policy(
            db_session,
            workspace_id=WORKSPACE,
            agent_id=b2c_agent.id,
            max_concurrent=2,
            execution_timeout_seconds=60,
            approval_timeout_seconds=300,
            max_context_size=2000,
            retry_policy_id="standard",
            business_scope="B2B",
        )


@pytest.mark.asyncio
async def test_monthly_budget_usage_is_channel_scoped(db_session) -> None:
    agent = await _seed_agent(
        db_session,
        agent_id="SCOPE_BUDGET",
        business_scope="SHARED",
    )
    now = datetime.now(UTC)
    for scope, cost in (("B2C", "1.25"), ("B2B", "4.50")):
        db_session.add(
            AgentExecution(
                workspace_id=WORKSPACE,
                agent_id=agent.id,
                business_scope=scope,
                status="completed",
                cost=Decimal(cost),
                started_at=now,
                completed_at=now,
            )
        )
    await db_session.flush()

    assert await agent_budget.monthly_usage(
        db_session,
        workspace_id=WORKSPACE,
        agent_id=agent.id,
        business_scope="B2C",
    ) == Decimal("1.250000")
    assert await agent_budget.monthly_usage(
        db_session,
        workspace_id=WORKSPACE,
        agent_id=agent.id,
        business_scope="B2B",
    ) == Decimal("4.500000")
    assert await agent_budget.monthly_usage(
        db_session,
        workspace_id=WORKSPACE,
        agent_id=agent.id,
    ) == Decimal("5.750000")


@pytest.mark.asyncio
async def test_approval_scope_is_derived_and_rbac_isolated(
    db_session,
    monkeypatch,
) -> None:
    agent = await _seed_agent(
        db_session,
        agent_id="SCOPE_APPROVAL",
        business_scope="B2C",
    )
    approval = await approval_service.ensure_approval(
        db_session,
        workspace_id=WORKSPACE,
        approval_type="RECOMMENDATION",
        entity_type="recommendation",
        entity_id=str(UUID(int=123)),
        agent_id=agent.id,
    )
    assert isinstance(approval, AgentApproval)
    assert approval.business_scope == "B2C"

    monkeypatch.setattr(get_settings(), "approval_rbac_enabled", True)
    await approval_rbac.create_role(
        db_session,
        workspace_id=WORKSPACE,
        role_name="b2c-reviewer",
        permissions=["recommendation.approve"],
        actors=["b2c-actor"],
        business_scope="B2C",
    )
    assert await approval_rbac.check_approval_permission(
        db_session,
        workspace_id=WORKSPACE,
        actor="b2c-actor",
        approval_type="RECOMMENDATION",
        action="approve",
        business_scope="B2C",
    )
    with pytest.raises(approval_rbac.ApprovalRBACError):
        await approval_rbac.check_approval_permission(
            db_session,
            workspace_id=WORKSPACE,
            actor="b2c-actor",
            approval_type="RECOMMENDATION",
            action="approve",
            business_scope="B2B",
        )
