"""M6 tool handler registry: registers all e-commerce capability tool handlers.

Called from ``app.main.lifespan`` at startup. Each handler is a thin
adapter that translates the generic ``(arguments, context)`` tool-gateway
signature into the typed service-layer call. Handlers never touch the DB
directly — they delegate to services (AGENTS.md §2.3).
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.services.customer_template_service import (
    CustomerTemplateError,
    get_customer_template,
)
from app.services.image_generation_service import (
    ImageGenServiceError,
    generate_image_and_save,
)
from app.services.influencer_service import InfluencerServiceError, match_influencers
from app.services.listing_localization_service import (
    ListingLocalizationError,
    localize_listing,
)
from app.services.tool_gateway import ToolContext, register_handler

logger = logging.getLogger(__name__)

DEFAULT_WORKSPACE = UUID("00000000-0000-0000-0000-000000000001")


# ============================================
# Handlers
# ============================================


async def _handle_generate_product_image(
    arguments: dict[str, Any],
    context: ToolContext,
) -> dict[str, Any]:
    """Generate a product image and persist the task (L2: auto-execute, cost-guarded)."""
    prompt = arguments.get("prompt")
    if not prompt:
        return {"error": "prompt is required"}
    use_case = arguments.get("use_case", "main_image")
    model = arguments.get("model")  # None = service default (wan2.7-image)
    try:
        task = await generate_image_and_save(
            context.session,
            workspace_id=context.workspace_id,
            prompt=prompt,
            use_case=use_case,
            model=model,
            trace_id=context.trace_id,
        )
        return {
            "task_id": str(task.id),
            "status": task.status,
            "model": task.actual_model,
            "cost_cny": float(task.cost_cny) if task.cost_cny else 0,
            "image_path": task.image_path,
            "image_url": task.image_url,
            "approval_required": task.approval_required,
        }
    except ImageGenServiceError as exc:
        return {"error": str(exc)}


async def _handle_generate_activity_plan(
    arguments: dict[str, Any],
    context: ToolContext,
) -> dict[str, Any]:
    """Generate an activity plan proposal (L2: proposal only, enters approval queue)."""
    activity_type = arguments.get("activity_type", "seasonal")
    name = arguments.get("name")
    if not name:
        return {"error": "name is required"}
    budget = arguments.get("budget_total")
    target_audience = arguments.get("target_audience")
    goals = arguments.get("goals")
    try:
        from app.services.activity_planner_service import generate_plan
        plan = await generate_plan(
            context.session,
            workspace_id=context.workspace_id,
            name=name,
            activity_type=activity_type,
            budget_total=budget,
            target_audience=target_audience,
            goals=goals,
            trace_id=context.trace_id,
        )
        return {
            "plan_id": str(plan.id),
            "name": plan.name,
            "activity_type": plan.activity_type,
            "approval_status": plan.approval_status,
            "version": plan.version,
            "summary": plan.plan_json.get("summary", "") if plan.plan_json else "",
        }
    except Exception as exc:
        logger.exception("activity plan generation failed")
        return {"error": str(exc)}


async def _handle_match_influencers(
    arguments: dict[str, Any],
    context: ToolContext,
) -> dict[str, Any]:
    """Match influencers for a product/campaign (L1: read-only recommendation)."""
    product_category = arguments.get("product_category", "")
    target_region = arguments.get("target_region")
    min_followers = arguments.get("min_followers")
    max_followers = arguments.get("max_followers")
    limit = arguments.get("limit", 5)
    try:
        result = await match_influencers(
            context.session,
            workspace_id=context.workspace_id,
            product_category=product_category,
            target_region=target_region,
            min_followers=min_followers,
            max_followers=max_followers,
            limit=limit,
        )
        return {
            "candidates_evaluated": result["candidates_evaluated"],
            "matches": [
                {
                    "influencer_id": str(m["id"]),
                    "name": m["name"],
                    "platform": m["platform"],
                    "followers": m["followers"],
                    "match_score": m["match_score"],
                    "match_reasons": m["match_reasons"],
                }
                for m in result["matches"]
            ],
        }
    except InfluencerServiceError as exc:
        return {"error": str(exc)}


async def _handle_localize_listing(
    arguments: dict[str, Any],
    context: ToolContext,
) -> dict[str, Any]:
    """Localize a product listing for a target language/market (L2: proposal)."""
    product_name = arguments.get("product_name")
    source_listing = arguments.get("source_listing")
    target_language = arguments.get("target_language", "en")
    if not product_name or not source_listing:
        return {"error": "product_name and source_listing are required"}
    try:
        result = await localize_listing(
            context.session,
            workspace_id=context.workspace_id,
            product_name=product_name,
            source_listing=source_listing,
            target_language=target_language,
            target_market=arguments.get("target_market"),
            product_category=arguments.get("product_category"),
            trace_id=context.trace_id,
        )
        return {
            "product_name": result["product_name"],
            "target_language": result["target_language"],
            "localized_listing": result["localized_listing"],
        }
    except ListingLocalizationError as exc:
        return {"error": str(exc)}


async def _handle_get_customer_template(
    arguments: dict[str, Any],
    context: ToolContext,
) -> dict[str, Any]:
    """Retrieve a deterministic customer service template (L0: read-only, zero cost)."""
    category = arguments.get("category")
    language = arguments.get("language", "en")
    variables = arguments.get("variables", {})
    if not category:
        return {"error": "category is required"}
    try:
        template = get_customer_template(
            category=category,
            language=language,
            variables=variables,
        )
        return {
            "category": template["category"],
            "language": template["language"],
            "subject": template["subject"],
            "body": template["body"],
            "is_fallback": template["is_fallback"],
        }
    except CustomerTemplateError as exc:
        return {"error": str(exc)}


# ============================================
# Registry
# ============================================

# Handler name -> (handler_fn, description, permission_level)
M6_TOOL_HANDLERS: dict[str, tuple[Any, str, str]] = {
    "generate_product_image": (
        _handle_generate_product_image,
        "Generate a product image via the cost-guarded image gateway (default: wan2.7-image, ¥0.08/img)",
        "L2",
    ),
    "generate_activity_plan": (
        _handle_generate_activity_plan,
        "Generate an e-commerce campaign plan proposal (enters approval queue before execution)",
        "L2",
    ),
    "match_influencers": (
        _handle_match_influencers,
        "Match influencers/KOLs for a product or campaign based on category, region, and engagement",
        "L1",
    ),
    "localize_listing": (
        _handle_localize_listing,
        "Localize a product listing for a target language/market (en/de/fr/es/it)",
        "L2",
    ),
    "get_customer_template": (
        _handle_get_customer_template,
        "Retrieve a pre-built customer service response template (15 scenarios x 6 languages, zero LLM cost)",
        "L0",
    ),
}


def register_m6_tool_handlers() -> None:
    """Register all M6 e-commerce capability tool handlers in the tool gateway."""
    for name, (handler, _desc, _level) in M6_TOOL_HANDLERS.items():
        register_handler(name, handler)
        logger.info("registered M6 tool handler: %s", name)


def get_m6_tool_registry() -> list[dict[str, Any]]:
    """Return the M6 tool registry as a list of dicts (for API/seed use)."""
    return [
        {
            "handler_name": name,
            "description": desc,
            "permission_level": level,
        }
        for name, (_handler, desc, level) in M6_TOOL_HANDLERS.items()
    ]
