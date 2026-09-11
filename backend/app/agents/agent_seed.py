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

from app.models.agent_runtime import AgentRegistry
from app.schemas.agent_runtime import AgentRegisterRequest
from app.schemas.prompt import PromptCreate
from app.services import agent_runtime, prompt_registry

AGENT_ID = "product_analyst"
PROMPT_NAME = "AGENT_PRODUCT_ANALYST"
PROMPT_VERSION = "v1"
PROMPT_TEMPLATE = (
    "You are the Nuotao Outdoor Product Analyst. Analyze the provided product "
    "context and respond with ONLY a JSON object matching the output schema.\n"
    "Context: {context_json}\nOutput schema: {output_schema}"
)
PROMPT_VARIABLES = ["context_json", "output_schema"]


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
                description="Product Analyst agent runtime prompt v1 (M5.2)",
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
