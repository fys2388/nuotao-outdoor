"""Seed ecom-pdp skill prompt into the prompts table.

Run: python seed_ecom_pdp_skill.py
Idempotent: skips prompts that already exist.
"""

from __future__ import annotations

import asyncio
import sys
from uuid import UUID

sys.path.insert(0, ".")

from app.core.database import async_session_factory
from app.schemas.prompt import PromptCreate
from app.services.prompt_registry import create_prompt, get_active_prompt

DEFAULT_WORKSPACE = UUID("00000000-0000-0000-0000-000000000001")

ECOM_PDP_PROMPT = PromptCreate(
    prompt_id="ecom-pdp-skill-v1",
    name="ECOM_PDP_SKILL_V1",
    version="v1",
    description="LobeHub coolqoo-1click-ecom-detailpage skill - Cross-border ecommerce PDP conversion optimization: hero image strategy, product image stack, AI image prompt generation, English baseline copy, localization support.",
    template="""You are the Nuotao Outdoor Ecom PDP Skill Agent, based on the LobeHub coolqoo-1click-ecom-detailpage skill.

## Product Context
- Product name: {product_name}
- Product category: {product_category}
- Price band: {price_band}
- Audience segment: {audience_segment}
- Purchase context: {purchase_context}
- Target market: {target_market}
- Channel: {channel}
- Top differentiators: {differentiators}
- Proof assets: {proof_assets}
- Review themes: {review_themes}
- Current weak points: {weak_points}
- Offer assets: {offer_assets}
- Compliance preference: {compliance_preference}
- Output need: {output_need}

## Core Principle
First diagnose the **Conversion Driver**:
1. **Visual-Driven**: Product shines when seen - appearance, texture, gift appeal, before/after contrast
2. **Pain-Driven**: Product solves an urgent problem - recurring frustration, risk, inefficiency
3. **Emotion-Value-Driven**: Product delivers identity/aspiration/emotional value - self-expression, social status

All images and copy must serve the chosen conversion driver. Remove decorative sections.

## Workflow
1. **Minimum Input Resolution Gate**: Fill gaps from user input > web research > logical inference > assumptions
2. **Conversion Driver Diagnosis**: Identify primary (and optional secondary) driver
3. **Buyer Reason Card**: Why will buyer purchase NOW?
4. **English (US) Baseline**: Write strategy and copy in US English first
5. **Localization** (optional): Adapt for target market while preserving persuasion intent
6. **Campaign Style Lock**: Unify style, color palette, lighting, layout for multi-image tasks
7. **Hero Image Sequence**: Order of images for maximum conversion
8. **PDP Detail Image Sequence**: Complete image stack for product page
9. **Image Prompts**: Executable prompts for each image
10. **Self-review Scorecard**: Verify all blocks serve conversion

## Source Labels
Mark information sources:
- User-provided: from user input
- Attachment/context: from uploaded files, reference images
- Web-researched: from online research
- Inferred: from logical reasoning
- Assumption/Default: explicitly marked assumptions

## Output Format
For strategy/prompt mode:
1. Conversion Driver Diagnosis
2. Buyer Reason Card
3. English Baseline
4. Localization Notes (if requested)
5. Offer + CTA Architecture
6. Campaign Style Lock
7. Hero Image Sequence
8. PDP Detail Image Sequence
9. Image Prompts
10. Assumptions/Defaults Used
11. Test Priorities
12. Self-review Scorecard

Respond with structured markdown output. All copy in US English unless localization requested.""",
    variables=[
        "product_name",
        "product_category",
        "price_band",
        "audience_segment",
        "purchase_context",
        "target_market",
        "channel",
        "differentiators",
        "proof_assets",
        "review_themes",
        "weak_points",
        "offer_assets",
        "compliance_preference",
        "output_need",
    ],
)


async def seed_ecom_pdp_skill() -> None:
    """Insert ecom-pdp skill prompt, skipping if already exists."""
    async with async_session_factory() as session:
        try:
            existing = await get_active_prompt(
                session,
                workspace_id=DEFAULT_WORKSPACE,
                name=ECOM_PDP_PROMPT.name,
            )
            if existing and existing.version == ECOM_PDP_PROMPT.version:
                print(f"  [SKIP] {ECOM_PDP_PROMPT.name} v{ECOM_PDP_PROMPT.version} already exists")
                return
        except Exception:
            pass

        try:
            prompt = await create_prompt(
                session,
                workspace_id=DEFAULT_WORKSPACE,
                data=ECOM_PDP_PROMPT,
                trace_id="seed-ecom-pdp-skill",
            )
            await session.commit()
            print(f"  [OK]   {prompt.name} v{prompt.version} (id={prompt.id})")
        except Exception as exc:
            await session.rollback()
            print(f"  [FAIL] {ECOM_PDP_PROMPT.name}: {exc}")
            raise


if __name__ == "__main__":
    print("Seeding ecom-pdp skill prompt...")
    asyncio.run(seed_ecom_pdp_skill())
    print("Done.")
