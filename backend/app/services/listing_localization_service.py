"""Listing localization service (M6): multi-language product listing generation.

Generates and optimizes product listings for multiple target markets
(English, German, French, Spanish, Italian). Not a literal translation —
the LLM adapts copy to local consumer preferences, SEO keywords, and
cultural norms.

Agent access: Product Analyst uses ``localize_listing`` via the whitelist
tool; agents never mutate product rows directly.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from uuid import UUID

from app.agents.generic_agent import run_generic_agent

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

DEFAULT_WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000001")

AGENT_ID = "listing_localizer"
AGENT_NAME = "Listing Localizer"
PROMPT_NAME = "LISTING_LOCALIZATION_V1"
TRIGGER = "api:listing:localize"

# Supported target languages (Phase 1: major European markets + English).
SUPPORTED_LANGUAGES: tuple[str, ...] = (
    "en",  # English (default / source)
    "de",  # German
    "fr",  # French
    "es",  # Spanish
    "it",  # Italian
)

LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
}

# Output schema for localized listing.
LOCALIZED_LISTING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "Localized product title (max 120 chars)"},
        "short_description": {"type": "string", "description": "Localized short description (max 300 chars)"},
        "long_description": {"type": "string", "description": "Localized long description with HTML formatting"},
        "bullet_points": {
            "type": "array",
            "items": {"type": "string"},
            "description": "5-7 localized bullet points highlighting key features",
        },
        "seo_keywords": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Target SEO keywords for this language/market",
        },
        "meta_title": {"type": "string", "description": "SEO meta title (max 60 chars)"},
        "meta_description": {"type": "string", "description": "SEO meta description (max 160 chars)"},
        "localization_notes": {
            "type": "string",
            "description": "Notes on cultural adaptation, local preferences, or market-specific changes",
        },
        "confidence_score": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["title", "short_description", "bullet_points", "seo_keywords", "confidence_score"],
}


class ListingLocalizationError(Exception):
    """Raised when listing localization fails."""


def get_listing_localization_status() -> dict[str, Any]:
    """Return service status and supported languages."""
    return {
        "service": "listing_localization",
        "status": "operational",
        "supported_languages": list(SUPPORTED_LANGUAGES),
        "language_names": LANGUAGE_NAMES,
        "agent_id": AGENT_ID,
        "prompt_name": PROMPT_NAME,
    }


async def localize_listing(
    session: AsyncSession,
    *,
    workspace_id: UUID | None = None,
    product_name: str,
    source_listing: dict[str, Any],
    target_language: str = "en",
    target_market: str | None = None,
    product_category: str | None = None,
    additional_context: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Generate a localized product listing for a target language/market.

    Args:
        session: database session
        workspace_id: workspace identifier
        product_name: source product name
        source_listing: source listing dict (title, description, bullets, etc.)
        target_language: target language code (en/de/fr/es/it)
        target_market: optional target market (e.g. "DE", "FR", "US")
        product_category: optional product category for context
        additional_context: optional additional context
        trace_id: optional trace identifier

    Returns:
        Localized listing dict with all fields from the output schema.
    """
    if target_language not in SUPPORTED_LANGUAGES:
        raise ListingLocalizationError(
            f"unsupported language: {target_language}; must be one of {SUPPORTED_LANGUAGES}"
        )

    ws = workspace_id or DEFAULT_WORKSPACE_ID

    context: dict[str, Any] = {
        "product_name": product_name,
        "source_listing": source_listing,
        "target_language": target_language,
        "target_language_name": LANGUAGE_NAMES.get(target_language, target_language),
        "target_market": target_market,
        "product_category": product_category,
        "brand": "Nuotao Outdoor",
        "market": "outdoor gear DTC",
    }
    if additional_context:
        context["additional_context"] = additional_context

    result = await run_generic_agent(
        session,
        workspace_id=ws,
        agent_id=AGENT_ID,
        agent_name=AGENT_NAME,
        trigger=TRIGGER,
        context=context,
        prompt_name=PROMPT_NAME,
        output_schema=LOCALIZED_LISTING_SCHEMA,
        system_instruction=(
            f"You are a professional e-commerce copywriter and localization expert. "
            f"Localize the product listing for {LANGUAGE_NAMES.get(target_language, target_language)} "
            f"speaking customers. Do NOT translate literally — adapt the copy to local consumer "
            f"preferences, cultural norms, and SEO keywords. All output must be in the target language. "
            f"Respond ONLY with a valid JSON object matching the schema."
        ),
        temperature=0.5,
        task_type="listing_localization",
        trace_id=trace_id,
    )

    if result.error or not result.output:
        raise ListingLocalizationError(f"localization failed: {result.error or 'no output'}")

    return {
        "product_name": product_name,
        "target_language": target_language,
        "target_market": target_market,
        "localized_listing": result.output,
        "agent_run_id": str(result.agent_run.id) if result.agent_run else None,
    }


async def localize_listing_batch(
    session: AsyncSession,
    *,
    workspace_id: UUID | None = None,
    product_name: str,
    source_listing: dict[str, Any],
    target_languages: list[str],
    product_category: str | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Generate localized listings for multiple target languages in one call.

    Returns a dict keyed by language code. Failures for individual languages
    are captured as error entries rather than failing the whole batch.
    """
    results: dict[str, Any] = {}
    for lang in target_languages:
        try:
            result = await localize_listing(
                session,
                workspace_id=workspace_id,
                product_name=product_name,
                source_listing=source_listing,
                target_language=lang,
                product_category=product_category,
                trace_id=trace_id,
            )
            results[lang] = result
        except ListingLocalizationError as exc:
            results[lang] = {"error": str(exc), "target_language": lang}

    return {
        "product_name": product_name,
        "target_languages": target_languages,
        "results": results,
        "success_count": sum(1 for r in results.values() if "error" not in r),
        "failure_count": sum(1 for r in results.values() if "error" in r),
    }
