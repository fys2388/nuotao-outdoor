"""Idempotent registration for the P2 B2B advisory agents."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models.agent_runtime import AgentRegistry
from app.models.prompt import Prompt
from app.schemas.agent_runtime import AgentRegisterRequest
from app.schemas.prompt import PromptCreate
from app.services import agent_runtime, prompt_registry

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class B2BAgentDefinition:
    agent_id: str
    name: str
    domain: str
    prompt_name: str
    template: str
    description: str


def _template(role: str, task: str, output: str) -> str:
    return (
        f"You are the Nuotao Outdoor {role}. {task} "
        "All recommendations must cite the provided structured evidence. "
        "Never execute writes or high-risk commercial actions; "
        "return recommendations for human approval only.\n"
        f"Context: {{context_json}}\nOutput schema: {output}"
    )


B2B_AGENT_DEFINITIONS: tuple[B2BAgentDefinition, ...] = (
    B2BAgentDefinition(
        agent_id="b2b_sales_agent",
        name="B2B Sales Agent",
        domain="sales",
        prompt_name="AGENT_B2B_SALES_AGENT",
        template=_template(
            "B2B Sales Agent",
            "Prioritize RFQs and recommend the next sales action from pipeline evidence.",
            "{output_schema}",
        ),
        description="Prioritizes B2B RFQs and recommends follow-up actions (advisory only)",
    ),
    B2BAgentDefinition(
        agent_id="b2b_quotation_agent",
        name="B2B Quotation Agent",
        domain="sales",
        prompt_name="AGENT_B2B_QUOTATION_AGENT",
        template=_template(
            "B2B Quotation Agent",
            "Recommend quote pricing from published price books, MOQ tiers, target prices, and landed costs.",
            "{output_schema}",
        ),
        description="Recommends B2B quote pricing and margin decisions (advisory only)",
    ),
    B2BAgentDefinition(
        agent_id="b2b_collection_agent",
        name="B2B Collection Agent",
        domain="finance",
        prompt_name="AGENT_B2B_COLLECTION_AGENT",
        template=_template(
            "B2B Collection Agent",
            "Prioritize receivables by aging, exposure, and customer risk, then recommend collection actions.",
            "{output_schema}",
        ),
        description="Prioritizes B2B receivables and recommends collection actions (advisory only)",
    ),
)


async def _ensure_definition(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    definition: B2BAgentDefinition,
    trace_id: str | None,
) -> AgentRegistry:
    prompt_exists = (
        await session.execute(
            select(Prompt.id).where(
                Prompt.workspace_id == workspace_id,
                Prompt.name == definition.prompt_name,
                Prompt.version == "v1",
            )
        )
    ).scalar_one_or_none()
    if prompt_exists is None:
        with suppress(prompt_registry.PromptConflictError):
            await prompt_registry.create_prompt(
                session,
                workspace_id=workspace_id,
                data=PromptCreate(
                    prompt_id=definition.prompt_name,
                    name=definition.prompt_name,
                    version="v1",
                    template=definition.template,
                    variables=["context_json", "output_schema"],
                    status="active",
                    description=f"{definition.name} runtime prompt v1 (P2)",
                ),
                trace_id=trace_id,
            )

    existing = (
        await session.execute(
            select(AgentRegistry).where(
                AgentRegistry.workspace_id == workspace_id,
                AgentRegistry.agent_id == definition.agent_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.business_scope != "B2B":
            raise agent_runtime.AgentRuntimeError(
                f"agent '{definition.agent_id}' already exists outside B2B scope"
            )
        return existing

    return await agent_runtime.register_agent(
        session,
        workspace_id=workspace_id,
        data=AgentRegisterRequest(
            agent_id=definition.agent_id,
            name=definition.name,
            domain=definition.domain,
            version="v1",
            status="active",
            model_provider="openai",
            model_name="gpt-4o-mini",
            prompt_version="v1",
            permission_level="L2",
            business_scope="B2B",
            description=definition.description,
        ),
        trace_id=trace_id,
    )


async def ensure_b2b_agents(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    trace_id: str | None = None,
) -> list[AgentRegistry]:
    """Create missing B2B agents and prompts; preserve existing registrations."""
    agents: list[AgentRegistry] = []
    for definition in B2B_AGENT_DEFINITIONS:
        agents.append(
            await _ensure_definition(
                session,
                workspace_id=workspace_id,
                definition=definition,
                trace_id=trace_id,
            )
        )
    return agents
