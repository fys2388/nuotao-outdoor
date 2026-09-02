"""Initialize all 5 AI agents for Nuotao Outdoor AI OS.

Registers prompts and agents for:
1. Product Analyst (product_analyst) - already exists
2. Marketing Manager (marketing_manager)
3. Supply Chain Manager (supply_chain_manager)
4. Customer Service Manager (customer_service_manager)
5. Business Analyst (business_analyst)
"""
from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.models.agent_runtime import AgentRegistry
from app.schemas.agent_runtime import AgentRegisterRequest
from app.schemas.prompt import PromptCreate
from app.services import agent_runtime, prompt_registry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000001")

# Agent definitions: (agent_id, name, domain, description, prompt_template, permission_level)
AGENTS = [
    (
        "marketing_manager",
        "Marketing Manager",
        "marketing",
        "AI marketing manager: campaign planning, content creation, SEO/SEM optimization",
        (
            "You are the Nuotao Outdoor Marketing Manager. Analyze the provided marketing "
            "context and respond with ONLY a JSON object matching the output schema.\n"
            "Context: {context_json}\nOutput schema: {output_schema}"
        ),
        "L2",
    ),
    (
        "supply_chain_manager",
        "Supply Chain Manager",
        "supply_chain",
        "AI supply chain manager: supplier selection, cost optimization, inventory planning",
        (
            "You are the Nuotao Outdoor Supply Chain Manager. Analyze the provided supply "
            "chain context and respond with ONLY a JSON object matching the output schema.\n"
            "Context: {context_json}\nOutput schema: {output_schema}"
        ),
        "L2",
    ),
    (
        "customer_service_manager",
        "Customer Service Manager",
        "customer",
        "AI customer service manager: ticket handling, response generation, satisfaction analysis",
        (
            "You are the Nuotao Outdoor Customer Service Manager. Analyze the provided customer "
            "service context and respond with ONLY a JSON object matching the output schema.\n"
            "Context: {context_json}\nOutput schema: {output_schema}"
        ),
        "L2",
    ),
    (
        "business_analyst",
        "Business Analyst",
        "operations",
        "AI business analyst: financial analysis, KPI tracking, business intelligence reporting",
        (
            "You are the Nuotao Outdoor Business Analyst. Analyze the provided business "
            "context and respond with ONLY a JSON object matching the output schema.\n"
            "Context: {context_json}\nOutput schema: {output_schema}"
        ),
        "L1",
    ),
]


async def register_agent(
    session: AsyncSession,
    *,
    agent_id: str,
    name: str,
    domain: str,
    description: str,
    prompt_template: str,
    permission_level: str,
) -> AgentRegistry:
    """Register a prompt and agent if not exists."""
    prompt_name = f"AGENT_{agent_id.upper()}"
    prompt_version = "v1"

    # Create prompt
    try:
        await prompt_registry.create_prompt(
            session,
            workspace_id=WORKSPACE_ID,
            data=PromptCreate(
                prompt_id=prompt_name,
                name=prompt_name,
                version=prompt_version,
                template=prompt_template,
                variables=["context_json", "output_schema"],
                status="active",
                description=f"{name} agent runtime prompt v1",
            ),
            trace_id="init-all-agents",
        )
        logger.info(f"  ✅ Prompt created: {prompt_name} v1")
    except prompt_registry.PromptConflictError:
        logger.info(f"  ⏭️  Prompt already exists: {prompt_name} v1")

    # Check if agent already exists
    existing = (
        await session.execute(
            select(AgentRegistry).where(
                AgentRegistry.workspace_id == WORKSPACE_ID,
                AgentRegistry.agent_id == agent_id,
            )
        )
    ).scalar_one_or_none()

    if existing is not None:
        logger.info(f"  ⏭️  Agent already exists: {agent_id} ({existing.status})")
        return existing

    # Register agent
    agent = await agent_runtime.register_agent(
        session,
        workspace_id=WORKSPACE_ID,
        data=AgentRegisterRequest(
            agent_id=agent_id,
            name=name,
            domain=domain,
            version="v1",
            status="active",
            model_provider="deepseek",
            model_name="deepseek-chat",
            prompt_version=prompt_version,
            permission_level=permission_level,
            description=description,
        ),
        trace_id="init-all-agents",
    )
    logger.info(f"  ✅ Agent registered: {agent_id} (model=deepseek/deepseek-chat)")
    return agent


async def main() -> None:
    """Initialize all agents."""
    logger.info("=" * 60)
    logger.info("初始化所有 AI Agent")
    logger.info("=" * 60)

    async with async_session_factory() as session:
        for agent_id, name, domain, description, prompt_template, permission_level in AGENTS:
            logger.info(f"\n【{name}】({agent_id})")
            await register_agent(
                session,
                agent_id=agent_id,
                name=name,
                domain=domain,
                description=description,
                prompt_template=prompt_template,
                permission_level=permission_level,
            )

        # Verify all agents
        logger.info("\n" + "=" * 60)
        logger.info("验证所有 Agent")
        logger.info("=" * 60)
        all_agents = (
            await session.execute(
                select(AgentRegistry).where(AgentRegistry.workspace_id == WORKSPACE_ID)
            )
        ).scalars().all()

        for agent in all_agents:
            logger.info(f"  ✅ {agent.agent_id}: {agent.name} ({agent.status}, model={agent.model_provider}/{agent.model_name})")

        logger.info(f"\n总计: {len(all_agents)} 个 Agent 已注册")


if __name__ == "__main__":
    asyncio.run(main())
