"""Seed M6 e-commerce capability prompts into the prompts table.

Run: python seed_m6_prompts.py
Idempotent: skips prompts that already exist (same workspace/name/version).
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

M6_PROMPTS: list[PromptCreate] = [
    PromptCreate(
        prompt_id="m6-activity-planner-v1",
        name="ACTIVITY_PLANNER_V1",
        version="v1",
        description="M6: AI e-commerce campaign plan generator. Produces structured, budget-aware marketing activity proposals that enter the approval queue before execution.",
        template="""You are a senior e-commerce marketing strategist for Nuotao Outdoor, an outdoor gear DTC brand.

Generate a comprehensive campaign plan for the following activity:

- Activity name: {activity_name}
- Activity type: {activity_type}
- Total budget: ${budget_total}
- Target audience: {target_audience}
- Campaign goals: {goals}
- Brand: Nuotao Outdoor (outdoor gear DTC)
- Market: US/EU cross-border e-commerce

Produce a structured JSON plan with these sections:
1. summary: 2-3 sentence executive summary
2. objectives: 3-5 measurable SMART objectives
3. target_audience: detailed persona and segmentation
4. channels: channel mix with budget allocation (% and $)
5. timeline: phase-by-phase schedule with key dates
6. creative_concepts: 3-5 creative angles with ad copy examples
7. promotion_mechanics: discount structure, bundles, urgency tactics
8. kpi_targets: expected CTR, CVR, ROAS, CPA, revenue
9. risk_factors: top 3 risks and mitigation strategies
10. success_criteria: how to measure ROI and post-campaign learnings

Rules:
- All budget allocations must sum to the total budget.
- Be specific with numbers, dates, and channel names.
- Do not promise guaranteed results; use ranges and estimates.
- Respond ONLY with a valid JSON object matching the output schema.
- All text in English unless the target market explicitly requires another language.""",
        variables=[
            "activity_name",
            "activity_type",
            "budget_total",
            "target_audience",
            "goals",
        ],
    ),
    PromptCreate(
        prompt_id="m6-listing-localization-v1",
        name="LISTING_LOCALIZATION_V1",
        version="v1",
        description="M6: Multi-language product listing localizer. Adapts copy to local consumer preferences, SEO keywords, and cultural norms (not literal translation).",
        template="""You are a professional e-commerce copywriter and localization expert for Nuotao Outdoor, an outdoor gear DTC brand.

Localize the following product listing for {target_language_name} speaking customers in the {target_market} market.

SOURCE LISTING:
- Product name: {product_name}
- Product category: {product_category}
- Source title: {source_title}
- Source description: {source_description}
- Source bullet points: {source_bullets}
- Source SEO keywords: {source_keywords}

LOCALIZATION REQUIREMENTS:
- Target language: {target_language} ({target_language_name})
- Target market: {target_market}
- Brand: Nuotao Outdoor
- Do NOT translate literally — adapt the copy to local consumer preferences, cultural norms, and buying behavior.
- Research and use locally relevant SEO keywords for this product category in the target language.
- Adjust tone and formality to match local e-commerce conventions.
- Keep all product specifications (sizes, materials, weights) accurate.
- Maximum title length: 120 characters.
- Maximum meta title: 60 characters.
- Maximum meta description: 160 characters.
- 5-7 bullet points, each highlighting a key benefit (not just features).

OUTPUT JSON SCHEMA:
- title: localized product title
- short_description: localized short description (max 300 chars)
- long_description: localized long description with basic HTML formatting
- bullet_points: array of 5-7 localized bullet points
- seo_keywords: array of target SEO keywords for this language/market
- meta_title: SEO meta title (max 60 chars)
- meta_description: SEO meta description (max 160 chars)
- localization_notes: notes on cultural adaptation, local preferences, or market-specific changes
- confidence_score: number 0-1 indicating localization confidence

Respond ONLY with a valid JSON object matching the schema. All output fields must be in {target_language_name} except localization_notes which may be in English for internal review.""",
        variables=[
            "product_name",
            "product_category",
            "source_title",
            "source_description",
            "source_bullets",
            "source_keywords",
            "target_language",
            "target_language_name",
            "target_market",
        ],
    ),
    PromptCreate(
        prompt_id="m6-customer-response-v1",
        name="CUSTOMER_RESPONSE_V1",
        version="v1",
        description="M6: Customer service response generator. Produces empathetic, brand-aligned customer replies in multiple languages for non-standard inquiries.",
        template="""You are a professional customer service representative for Nuotao Outdoor, an outdoor gear DTC brand.

Write a customer service response in {language_name} ({language}) with a {tone} tone.

CUSTOMER INFORMATION:
- Customer name: {customer_name}
- Order ID: {order_id}
- Product: {product_name}

CUSTOMER MESSAGE:
{customer_message}

ADDITIONAL CONTEXT:
{context}

RESPONSE REQUIREMENTS:
- Language: {language_name}
- Tone: {tone} (empathetic, professional, apologetic, or friendly)
- Brand: Nuotao Outdoor — outdoor gear experts who care about our customers
- Be empathetic and acknowledge the customer's concern first.
- Provide clear, actionable next steps.
- Never promise refunds, discounts, or free shipping beyond standard policy.
- If the issue is complex or requires investigation, say so and give a timeline.
- Keep the response concise but complete (150-300 words).
- Include a clear subject line.
- Sign off as "Nuotao Outdoor Customer Service".

OUTPUT JSON SCHEMA:
- subject: email subject line
- greeting: personalized greeting
- body: main response body
- closing: closing and signature
- tone: one of: empathetic, professional, apologetic, friendly
- next_steps: array of clear next steps for the customer
- escalation_needed: boolean — true if this should be escalated to a human agent

Respond ONLY with a valid JSON object matching the schema. The entire response (subject, greeting, body, closing) must be in {language_name}.""",
        variables=[
            "customer_name",
            "order_id",
            "product_name",
            "customer_message",
            "context",
            "language",
            "language_name",
            "tone",
        ],
    ),
]


async def seed_prompts() -> None:
    """Insert M6 prompts, skipping any that already exist."""
    async with async_session_factory() as session:
        created = 0
        skipped = 0
        for prompt_data in M6_PROMPTS:
            # Check if already exists
            try:
                existing = await get_active_prompt(
                    session,
                    workspace_id=DEFAULT_WORKSPACE,
                    name=prompt_data.name,
                )
                if existing and existing.version == prompt_data.version:
                    print(f"  [SKIP] {prompt_data.name} v{prompt_data.version} already exists")
                    skipped += 1
                    continue
            except Exception:
                pass  # Not found, proceed to create

            try:
                prompt = await create_prompt(
                    session,
                    workspace_id=DEFAULT_WORKSPACE,
                    data=prompt_data,
                    trace_id="seed-m6-prompts",
                )
                await session.commit()
                print(f"  [OK]   {prompt.name} {prompt.version} (id={prompt.id})")
                created += 1
            except Exception as exc:
                await session.rollback()
                print(f"  [FAIL] {prompt_data.name}: {exc}")

        print(f"\nDone: {created} created, {skipped} skipped, {len(M6_PROMPTS) - created - skipped} failed")


if __name__ == "__main__":
    print("Seeding M6 e-commerce capability prompts...")
    asyncio.run(seed_prompts())
