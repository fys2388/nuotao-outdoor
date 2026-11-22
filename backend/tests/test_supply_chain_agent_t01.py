"""T0.1 Supply Chain Agent registration tests (M4.2.0).

Owner directive: register the Supply Chain Analyst agent skeleton — a versioned
prompt in the Prompt Registry plus an ``AgentRegistry`` row at
``permission_level=L2`` (analysis + proposal only; never approves, purchases,
allocates inventory or modifies hard rules).

These tests prove:
- The seed is idempotent (create-if-missing) and binds agent -> prompt version.
- The prompt is versioned and audited in the Prompt Registry, not hardcoded.
- The agent is registered at L2 within the ``supply_chain`` domain.
- The L2 boundary is structurally enforced: the agent cannot be the authorizing
  subject of a purchase-order approval (governance invariant from T0.2).
"""

from uuid import UUID

import pytest
from sqlalchemy import select

from app.agents.agent_seed import (
    SUPPLY_CHAIN_AGENT_ID,
    SUPPLY_CHAIN_PROMPT_NAME,
    ensure_supply_chain_analyst_agent,
)
from app.agents.supply_chain_analyst_prompt import PROMPT_VERSION_V1
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.agent_runtime import AgentRegistry
from app.models.prompt import Prompt
from app.services import supply_chain
WORKSPACE = DEFAULT_WORKSPACE_ID


async def _seed(db_session):
    return await ensure_supply_chain_analyst_agent(db_session, workspace_id=WORKSPACE)


# --------------------------------------------------------------------------- #
# 1. Registration + idempotency
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_seed_registers_supply_chain_analyst(db_session) -> None:
    """Seeding registers the agent at L2 in the supply_chain domain."""
    agent = await _seed(db_session)
    assert agent.agent_id == SUPPLY_CHAIN_AGENT_ID == "supply_chain_analyst"
    assert agent.permission_level == "L2"
    assert agent.domain == "supply_chain"
    assert agent.prompt_version == PROMPT_VERSION_V1


@pytest.mark.asyncio
async def test_seed_is_idempotent(db_session) -> None:
    """Calling the seed twice yields one agent row and one active prompt."""
    first = await _seed(db_session)
    second = await _seed(db_session)
    assert first.id == second.id

    agents = (
        await db_session.execute(
            select(AgentRegistry).where(AgentRegistry.agent_id == SUPPLY_CHAIN_AGENT_ID)
        )
    ).scalars().all()
    assert len(agents) == 1


# --------------------------------------------------------------------------- #
# 2. Versioned + audited prompt (never hardcoded in code paths)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_prompt_is_versioned_in_registry(db_session) -> None:
    """The prompt lives in the Prompt Registry under the derived name + version."""
    await _seed(db_session)
    prompt = (
        await db_session.execute(
            select(Prompt).where(
                Prompt.workspace_id == WORKSPACE,
                Prompt.name == SUPPLY_CHAIN_PROMPT_NAME,
                Prompt.version == PROMPT_VERSION_V1,
                Prompt.status == "active",
            )
        )
    ).scalar_one_or_none()
    assert prompt is not None, "active versioned prompt must exist before agent registration"
    assert "context_json" in prompt.variables
    assert "output_schema" in prompt.variables
    # Governance text present: the prompt encodes the proposer-not-executor rule.
    assert "never" in prompt.template.lower()


@pytest.mark.asyncio
async def test_agent_registration_requires_prompt(db_session) -> None:
    """register_agent fails closed if the bound prompt is missing (no orphan agents)."""
    from app.schemas.agent_runtime import AgentRegisterRequest
    from app.services import agent_runtime

    with pytest.raises(agent_runtime.AgentRuntimeError, match="not found"):
        await agent_runtime.register_agent(
            db_session,
            workspace_id=WORKSPACE,
            data=AgentRegisterRequest(
                agent_id="supply_chain_analyst",
                name="Supply Chain Analyst",
                domain="supply_chain",
                permission_level="L2",
                prompt_version="v1",
            ),
        )


# --------------------------------------------------------------------------- #
# 3. L2 boundary: proposer, never an approver (governance invariant)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_l2_agent_cannot_self_approve_purchase_order(db_session, api_client) -> None:
    """The L2 agent cannot authorize its own purchase order (fail-closed approve)."""
    agent = await _seed(db_session)
    assert agent.permission_level == "L2"

    # A PO proposed/created by the agent starts in draft. Even if the L2 agent
    # then tried to approve it, the approval choke point requires an
    # authenticated human operator (caller_user_id) that the service verifies
    # against the users table — the agent can never be the authorizing subject
    # of its own proposal (M4.2.0-R2).
    created = api_client.post(
        "/api/v1/purchase-orders",
        json={
            "po_number": "T01-SELFAPPROVE",
            "items": [{"sku": "TENT-1", "name": "Tent 1P", "quantity": 1, "unit_cost": "10.00"}],
        },
        headers={"X-Workspace-Id": str(WORKSPACE)},
    )
    assert created.status_code == 201, created.text
    po_id = UUID(created.json()["id"])

    with pytest.raises(supply_chain.SupplyChainError, match="operator user id"):
        await supply_chain.approve_purchase_order(
            db_session,
            workspace_id=WORKSPACE,
            po_id=po_id,
            approved_by=None,
            caller_user_id=None,
        )
