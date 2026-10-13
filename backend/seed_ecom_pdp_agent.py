"""Register the ecom_pdp_skill agent in the AgentRegistry table.

Run: python seed_ecom_pdp_agent.py
Idempotent: skips if already exists.
"""

from __future__ import annotations

import asyncio
import sys
from uuid import UUID

sys.path.insert(0, ".")

from app.core.database import async_session_factory
from app.models.agent_runtime import AgentRegistry
from app.schemas.agent_runtime import AgentRegisterRequest
from app.services import agent_runtime

DEFAULT_WORKSPACE = UUID("00000000-0000-0000-0000-000000000001")


async def seed_ecom_pdp_agent() -> None:
    async with async_session_factory() as session:
        existing = (
            await session.execute(
                select(AgentRegistry).where(
                    AgentRegistry.workspace_id == DEFAULT_WORKSPACE,
                    AgentRegistry.agent_id == "ecom_pdp_skill",
                )
            )
        ).scalar_one_or_none()
        if existing:
            print(f"  [SKIP] ecom_pdp_skill already registered (id={existing.id})")
            return

        data = AgentRegisterRequest(
            agent_id="ecom_pdp_skill",
            name="Ecom PDP Skill",
            domain="marketing",
            version="v1",
            status="active",
            model_provider="sensenova",
            model_name="sensenova-6.8-flash-lite",
            prompt_version="v1",
            permission_level="L2",
            business_scope="SHARED",
            description="Cross-border ecommerce PDP conversion optimization - hero images, image stack, AI image prompts",
        )
        agent = await agent_runtime.register_agent(
            session,
            workspace_id=DEFAULT_WORKSPACE,
            data=data,
            trace_id="seed-ecom-pdp-agent",
        )
        await session.commit()
        print(f"  [OK]   ecom_pdp_skill registered (id={agent.id})")


if __name__ == "__main__":
    print("Registering ecom_pdp_skill agent...")
    asyncio.run(seed_ecom_pdp_agent())
    print("Done.")
