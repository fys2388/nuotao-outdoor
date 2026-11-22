"""Product Analyst agent seed (M5.2).

Idempotently bootstraps the first real business agent on top of the M5.0/M5.1
runtime:

- ``AGENT_PRODUCT_ANALYST`` v1 prompt in the Prompt Registry (versioned,
  never hardcoded in code paths);
- ``product_analyst`` agent registration bound to that prompt version with
  ``permission_level=L2`` (analysis + proposal only; never approves,
  publishes, purchases or allocates inventory).

The seed is safe to call repeatedly (create-if-missing semantics). The worker
runtime itself never auto-registers anything; operations/bootstrap scripts
call this helper or use the documented API calls.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.product_analyst_prompt import (
    PRODUCT_ANALYST_TEMPLATE_V3,
    PROMPT_VERSION_V3,
)
from app.agents.supply_chain_analyst_prompt import (
    PROMPT_VERSION_V1 as SC_PROMPT_VERSION_V1,
    SUPPLY_CHAIN_ANALYST_TEMPLATE_V1,
)
from app.models.agent_runtime import AgentRegistry
from app.schemas.agent_runtime import AgentRegisterRequest
from app.schemas.prompt import PromptCreate
from app.services import agent_runtime, prompt_registry

AGENT_ID = "product_analyst"
PROMPT_NAME = "AGENT_PRODUCT_ANALYST"
PROMPT_VERSION = PROMPT_VERSION_V3
PROMPT_TEMPLATE = PRODUCT_ANALYST_TEMPLATE_V3
PROMPT_VARIABLES = ["context_json", "output_schema"]

# --- Supply Chain Analyst (M4.2.0 T0.1) ---
SUPPLY_CHAIN_AGENT_ID = "supply_chain_analyst"
SUPPLY_CHAIN_PROMPT_NAME = "AGENT_SUPPLY_CHAIN_ANALYST"


async def ensure_product_analyst_agent(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    trace_id: str | None = None,
) -> AgentRegistry:
    """Create (if missing) the AGENT_PRODUCT_ANALYST v1 prompt + agent row.

    Returns the registered agent; safe to call multiple times.
    """
    try:
        await prompt_registry.create_prompt(
            session,
            workspace_id=workspace_id,
            data=PromptCreate(
                prompt_id=PROMPT_NAME,
                name=PROMPT_NAME,
                version=PROMPT_VERSION,
                template=PROMPT_TEMPLATE,
                variables=PROMPT_VARIABLES,
                status="active",
                description="Product Analyst agent runtime prompt v3 (Nuotao Score V3.0)",
            ),
            trace_id=trace_id,
        )
    except prompt_registry.PromptConflictError:
        pass  # already seeded

    existing = (
        await session.execute(
            select(AgentRegistry).where(
                AgentRegistry.workspace_id == workspace_id,
                AgentRegistry.agent_id == AGENT_ID,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    return await agent_runtime.register_agent(
        session,
        workspace_id=workspace_id,
        data=AgentRegisterRequest(
            agent_id=AGENT_ID,
            name="Product Analyst",
            domain="product",
            version="v1",
            status="active",
            model_provider="openai",
            model_name="gpt-4o-mini",
            prompt_version=PROMPT_VERSION,
            permission_level="L2",
            description="AI product analyst: analysis + decision proposals only (M5.2)",
        ),
        trace_id=trace_id,
    )


async def ensure_supply_chain_analyst_agent(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    trace_id: str | None = None,
) -> AgentRegistry:
    """Create (if missing) the AGENT_SUPPLY_CHAIN_ANALYST prompt + agent row.

    The Supply Chain Analyst is an L2 PROPOSER: it analyses suppliers, costs,
    inventory and demand and proposes procurement actions, but it can never
    approve, purchase, allocate inventory or modify hard rules (mirrors the
    Product Analyst's L2 boundary). Safe to call repeatedly (create-if-missing).
    """
    try:
        await prompt_registry.create_prompt(
            session,
            workspace_id=workspace_id,
            data=PromptCreate(
                prompt_id=SUPPLY_CHAIN_PROMPT_NAME,
                name=SUPPLY_CHAIN_PROMPT_NAME,
                version=SC_PROMPT_VERSION_V1,
                template=SUPPLY_CHAIN_ANALYST_TEMPLATE_V1,
                variables=["context_json", "output_schema"],
                status="active",
                description=(
                    "Supply Chain Analyst agent prompt v1: supplier/cost/inventory "
                    "analysis + procurement proposals only (L2 proposer, never executes)"
                ),
            ),
            trace_id=trace_id,
        )
    except prompt_registry.PromptConflictError:
        pass  # already seeded

    existing = (
        await session.execute(
            select(AgentRegistry).where(
                AgentRegistry.workspace_id == workspace_id,
                AgentRegistry.agent_id == SUPPLY_CHAIN_AGENT_ID,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    return await agent_runtime.register_agent(
        session,
        workspace_id=workspace_id,
        data=AgentRegisterRequest(
            agent_id=SUPPLY_CHAIN_AGENT_ID,
            name="Supply Chain Analyst",
            domain="supply_chain",
            version="v1",
            status="active",
            model_provider="sensenova",
            model_name="sensenova-6.8-flash-lite",
            prompt_version=SC_PROMPT_VERSION_V1,
            permission_level="L2",
            description=(
                "AI supply chain analyst: supplier risk, landed-cost and procurement "
                "proposals only; never approves or purchases (M4.2.0 T0.1)"
            ),
        ),
        trace_id=trace_id,
    )
