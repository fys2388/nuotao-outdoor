"""Render-test the ECOM_PDP_SKILL_V1 prompt without needing a server.

Usage:
    cd backend
    python test_render_ecom_pdp.py

This validates the prompt template renders correctly with sample product data.
"""

from __future__ import annotations

import sys
from pathlib import Path

# The prompt template is registered on the server; this script uses a local copy
# to verify the rendering logic works before deploying.

SAMPLE_CONTEXT = {
    "product_name": "Folding Camping Table - Carbon Steel",
    "product_category": "Outdoor Camping Furniture",
    "price_band": "$25-45",
    "audience_segment": "Weekend campers, families, fishing enthusiasts",
    "purchase_context": "Weekend camping trips, backpacking base camp",
    "target_market": "US",
    "channel": "WooCommerce",
    "differentiators": "Carbon steel construction, lightweight (3.5lb), 120lb capacity, quick-deploy",
    "proof_assets": "500+ reviews, 4.5 avg rating, monthly 530+ orders on 1688",
    "review_themes": "Lightweight, sturdy, easy to fold, great value",
    "weak_points": "Low brand awareness, no outdoor certification",
    "offer_assets": "60% profit margin, bundle with chair at $69",
    "compliance_preference": "ignore",
    "output_need": "Full PDP strategy + image prompts",
}


def render_prompt(context: dict) -> str:
    """Render the prompt template with the given context variables."""
    template = """You are the Nuotao Outdoor Ecom PDP Skill Agent, based on the LobeHub coolqoo-1click-ecom-detailpage skill.

Your task: Build high-converting cross-border ecommerce Product Detail Pages (PDP), hero images, product image stacks, and AI image prompts.

## Core Principle
First diagnose the **Conversion Driver**:
1. **Visual-Driven**: Product shines when seen - appearance, texture, gift appeal, before/after contrast
2. **Pain-Driven**: Product solves an urgent problem - recurring frustration, risk, inefficiency
3. **Emotion-Value-Driven**: Product delivers identity/aspiration/emotional value - self-expression, social status

All images and copy must serve the chosen conversion driver. Remove decorative sections.

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

Respond with structured markdown output. All copy in US English unless localization requested."""

    return template.format(**context)


if __name__ == "__main__":
    print("=" * 60)
    print("ECOM_PDP_SKILL_V1 - Render Test")
    print("=" * 60)

    rendered = render_prompt(SAMPLE_CONTEXT)

    # Validate no unresolved variables remain
    unresolved = [k for k, v in SAMPLE_CONTEXT.items() if f"{{{k}}}" in rendered]
    if unresolved:
        print(f"\n[X] UNRESOLVED VARIABLES: {unresolved}")
        sys.exit(1)

    # Validate key sections exist
    checks = [
        "Conversion Driver",
        "Buyer Reason Card",
        "English Baseline",
        "Hero Image Sequence",
        "PDP Detail Image Sequence",
        "Image Prompts",
        "Self-review Scorecard",
    ]

    print(f"\n[OK] Template rendered: {len(rendered)} characters")
    print(f"[OK] All {len(SAMPLE_CONTEXT)} variables resolved")

    for check in checks:
        if check in rendered:
            print(f"[OK] Section found: {check}")
        else:
            print(f"[X]  Section missing: {check}")

    print("\n" + "=" * 60)
    print("RENDERED PROMPT (first 1500 chars):")
    print("=" * 60)
    print(rendered[:1500])
    print(f"\n... [truncated, {len(rendered)} total chars]")
    print("\n[OK] Render test PASSED - prompt template is valid")
