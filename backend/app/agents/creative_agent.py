"""Creative Agent v1.

AI creative production capability for Nuotao AI OS. Analyzes products
and autonomously creates creative briefs, generates assets, and queues
them for human review.

Permissions
-----------
- READ:  product data, creative templates, existing briefs/assets
- WRITE: creative_briefs, creative_studio_assets (via services)
- FORBIDDEN: direct DB writes, delete operations, pricing changes

Flow
----
Product Context -> Prompt (registry) -> LLM Gateway -> Structured Output
-> Validation (schema + business gates) -> Creative Brief creation -> audit rows.

v1 changes
----------
- Product analysis: determine required creative assets based on product category
- Brief creation: automatically create CreativeBrief with required_assets
- Template matching: find appropriate prompt templates for each asset type
- Batch generation: optionally trigger batch generation after brief creation
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.generic_agent import GenericAgentResult, run_generic_agent
from app.models.agent import AiAgentRun
from app.models.creative import CreativeReview

logger = logging.getLogger(__name__)

AGENT_ID = "creative_agent"
AGENT_NAME = "Creative Agent"
PROMPT_NAME = "AGENT_CREATIVE_AGENT"
PROMPT_VERSION = "v1"
TRIGGER = "api:creative:analyze"

TRUTHFULNESS_RULES = """\
## Truthfulness Rules (MANDATORY)
1. EVERY asset recommendation must be based on product data in the Context.
   Never invent product features, materials, or use cases.
2. ASSET COUNT MUST BE REALISTIC. For a standard product listing, recommend
   5-11 total assets (hero + detail images). Never recommend 50+ assets.
3. ASSET TYPES MUST MATCH THE LIBRARY. Use only asset_types defined in the
   prompt template library (hero_image, detail_image, lifestyle, etc.).
4. PROMPT TEXT MUST BE USABLE. Each asset's prompt must be specific enough
   to generate a useful image. Never use vague prompts like "nice product".
5. COST ESTIMATES MUST BE HONEST. If cost data is unavailable, write "unknown"
   instead of guessing. Never present estimated costs as facts.
6. OUTPUT MUST BE COMPLETE. Return the full JSON object. If you cannot finish,
   return {"error": "..."} instead of truncating.
7. All recommendations are audited (ai_agent_runs); fabricating data is a
   blocking failure.
"""

PROMPT_TEMPLATE = (
    "You are the Creative Agent for Nuotao Outdoor, an outdoor gear DTC brand "
    "targeting European and American customers. Analyze the provided product context "
    "and respond with ONLY a JSON object matching the output schema.\n\n"
    + TRUTHFULNESS_RULES
    + "\n\nContext: {context_json}\n\n"
    "Output schema: {output_schema}\n\n"
    "Focus on: product creative strategy, asset requirements, visual style guidelines, "
    "and cost estimates. All recommendations must be practical and based on product data."
)

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "Brief summary of creative strategy for this product",
        },
        "product_analysis": {
            "type": "object",
            "description": "Analysis of the product for creative purposes",
            "properties": {
                "category": {"type": "string"},
                "key_features": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Top 3-5 key features for visual emphasis",
                },
                "target_audience": {"type": "string"},
                "visual_style": {
                    "type": "string",
                    "description": "Recommended visual style (e.g., 'outdoor adventure', 'minimalist')",
                },
                "color_palette": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Recommended color palette for creatives",
                },
            },
            "required": ["category", "visual_style"],
        },
        "required_assets": {
            "type": "array",
            "description": "List of required creative assets for this product",
            "items": {
                "type": "object",
                "properties": {
                    "asset_type": {
                        "type": "string",
                        "description": "Asset type (hero_image, detail_image, lifestyle, etc.)",
                    },
                    "count": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 5,
                        "description": "Number of images needed for this asset type",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                    },
                    "prompt_hint": {
                        "type": "string",
                        "description": "Brief prompt hint for this asset type",
                    },
                    "aspect_ratio": {
                        "type": "string",
                        "description": "Recommended aspect ratio (1:1, 3:4, etc.)",
                    },
                },
                "required": ["asset_type", "count", "priority"],
            },
            "minItems": 3,
            "maxItems": 15,
        },
        "visual_guidelines": {
            "type": "object",
            "properties": {
                "background_style": {"type": "string"},
                "lighting": {"type": "string"},
                "mood": {"type": "string"},
                "composition": {"type": "string"},
            },
        },
        "cost_estimate": {
            "type": "object",
            "properties": {
                "total_assets": {"type": "integer"},
                "estimated_cost_cny": {"type": ["number", "string"]},
                "cost_breakdown": {
                    "type": "object",
                    "description": "Cost breakdown by asset type",
                },
                "currency": {"type": "string"},
            },
        },
        "action_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                    "action": {"type": "string"},
                    "expected_impact": {"type": "string"},
                    "timeline": {"type": "string"},
                },
                "required": ["priority", "action"],
            },
        },
        "confidence_score": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": [
        "summary",
        "product_analysis",
        "required_assets",
        "action_items",
        "confidence_score",
    ],
}


@dataclass
class CreativeAnalysisResult:
    """Outcome of one creative agent run."""

    agent_run: AiAgentRun | None
    output: dict[str, Any] | None
    brief_id: str | None = None
    error: str | None = None
    dry_run: bool = False


async def analyze_product_for_creative(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    context: dict[str, Any] | None = None,
    trace_id: str | None = None,
    persist: bool = True,
) -> CreativeAnalysisResult:
    """Analyze a product for creative requirements.

    Args:
        session: database session
        workspace_id: workspace identifier
        product_id: product identifier
        context: optional additional context data
        trace_id: optional trace identifier
        persist: when False, skip audit persistence (dry-run)

    Returns:
        CreativeAnalysisResult with structured output or error.
    """
    from app.models.product import Product

    # Get product data
    stmt = await session.execute(
        select(Product).where(
            Product.id == product_id,
            Product.workspace_id == workspace_id,
        )
    )
    product = stmt.scalar_one_or_none()
    if not product:
        return CreativeAnalysisResult(
            agent_run=None,
            output=None,
            error=f"Product not found: {product_id}",
            dry_run=not persist,
        )

    # Build context for the agent
    agent_context = {
        "product_id": str(product.id),
        "product_name": product.name,
        "product_sku": product.sku,
        "product_category": product.category,
        "product_brand": product.brand,
        "product_description": product.description,
        "target_market": product.target_market,
        "weight_kg": str(product.weight_kg) if product.weight_kg else None,
        "tags": product.tags or [],
        "attributes": product.attributes or {},
    }

    # Merge with any additional context
    if context:
        agent_context.update(context)

    result: GenericAgentResult = await run_generic_agent(
        session,
        workspace_id=workspace_id,
        agent_id=AGENT_ID,
        agent_name=AGENT_NAME,
        trigger=TRIGGER,
        context=agent_context,
        prompt_name=PROMPT_NAME,
        output_schema=OUTPUT_SCHEMA,
        system_instruction=(
            "You are a senior creative strategist for an outdoor gear DTC brand. "
            "Analyze the product and recommend creative assets. "
            "Respond ONLY with a valid JSON object matching the schema. "
            "Obey the Truthfulness Rules: no invented features, realistic asset counts, "
            "usable prompts, honest cost estimates."
        ),
        temperature=0.4,
        task_type="creative_analysis",
        trace_id=trace_id,
        persist=persist,
    )

    return CreativeAnalysisResult(
        agent_run=result.agent_run,
        output=result.output,
        error=result.error,
        dry_run=not persist,
    )


async def create_brief_from_analysis(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    analysis_output: dict[str, Any],
    trace_id: str | None = None,
) -> str:
    """Create a CreativeBrief from agent analysis output.

    Args:
        session: database session
        workspace_id: workspace identifier
        product_id: product identifier
        analysis_output: output from analyze_product_for_creative
        trace_id: optional trace identifier

    Returns:
        UUID string of the created brief.
    """
    from app.services import creative_service

    # Extract required assets from analysis
    required_assets = analysis_output.get("required_assets", [])

    # Convert agent's asset format to brief's required_assets format
    brief_assets = []
    for asset in required_assets:
        brief_asset = {
            "asset_type": asset.get("asset_type", "hero_image"),
            "count": asset.get("count", 1),
            "priority": asset.get("priority", "medium"),
            "prompt_hint": asset.get("prompt_hint", ""),
            "aspect_ratio": asset.get("aspect_ratio", "1:1"),
        }
        brief_assets.append(brief_asset)

    # Create the brief
    brief = await creative_service.create_brief(
        session,
        workspace_id=workspace_id,
        product_id=product_id,
        brief_type="ai_generated",
        required_assets=brief_assets,
        visual_style=analysis_output.get("product_analysis", {}).get("visual_style"),
        trace_id=trace_id,
    )

    return str(brief.id)


async def run_creative_pipeline(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    execute_immediately: bool = False,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Run the full creative pipeline: analyze -> create brief -> generate.

    Args:
        session: database session
        workspace_id: workspace identifier
        product_id: product identifier
        execute_immediately: if True, batch generate assets after brief creation
        trace_id: optional trace identifier

    Returns:
        Dict with brief_id, analysis_summary, and optional generation results.
    """
    from app.services import creative_service

    # Step 1: Analyze the product
    analysis = await analyze_product_for_creative(
        session,
        workspace_id=workspace_id,
        product_id=product_id,
        trace_id=trace_id,
    )

    if analysis.error:
        return {
            "error": analysis.error,
            "brief_id": None,
            "analysis_summary": None,
            "generation_results": None,
        }

    if not analysis.output:
        return {
            "error": "Agent returned no output",
            "brief_id": None,
            "analysis_summary": None,
            "generation_results": None,
        }

    # Step 2: Create a brief from the analysis
    brief_id = await create_brief_from_analysis(
        session,
        workspace_id=workspace_id,
        product_id=product_id,
        analysis_output=analysis.output,
        trace_id=trace_id,
    )

    result = {
        "brief_id": brief_id,
        "analysis_summary": analysis.output.get("summary"),
        "product_analysis": analysis.output.get("product_analysis"),
        "required_assets": analysis.output.get("required_assets"),
        "generation_results": None,
    }

    # Step 3: Optionally batch generate assets
    if execute_immediately:
        try:
            generation_results = await creative_service.generate_brief_assets(
                session,
                brief_id=UUID(brief_id),
                workspace_id=workspace_id,
                execute_immediately=True,
                trace_id=trace_id,
            )
            result["generation_results"] = generation_results
        except Exception as exc:
            logger.warning("[creative_agent] batch generation failed: %s", exc)
            result["generation_error"] = str(exc)

    await session.flush()
    return result


# ===================================================================
# AI Quality Check (C6)
# ===================================================================

QC_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "Brief summary of image quality assessment",
        },
        "overall_score": {
            "type": "number",
            "minimum": 0,
            "maximum": 5,
            "description": "Overall quality score (0-5, where 5 is excellent)",
        },
        "image_integrity": {
            "type": "object",
            "properties": {
                "passed": {"type": "boolean"},
                "score": {"type": "number", "minimum": 0, "maximum": 5},
                "issues": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Integrity issues (corruption, truncation, etc.)",
                },
            },
            "required": ["passed", "score"],
        },
        "product_presence": {
            "type": "object",
            "properties": {
                "passed": {"type": "boolean"},
                "score": {"type": "number", "minimum": 0, "maximum": 5},
                "notes": {"type": "string", "description": "Notes on product presence and fidelity"},
            },
            "required": ["passed", "score"],
        },
        "visual_quality": {
            "type": "object",
            "properties": {
                "passed": {"type": "boolean"},
                "score": {"type": "number", "minimum": 0, "maximum": 5},
                "issues": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Visual issues (blur, noise, artifacts, distortion)",
                },
            },
            "required": ["passed", "score"],
        },
        "composition": {
            "type": "object",
            "properties": {
                "passed": {"type": "boolean"},
                "score": {"type": "number", "minimum": 0, "maximum": 5},
                "notes": {"type": "string", "description": "Composition and framing assessment"},
            },
            "required": ["passed", "score"],
        },
        "color_consistency": {
            "type": "object",
            "properties": {
                "passed": {"type": "boolean"},
                "score": {"type": "number", "minimum": 0, "maximum": 5},
                "notes": {"type": "string", "description": "Color accuracy and consistency"},
            },
            "required": ["passed", "score"],
        },
        "background_quality": {
            "type": "object",
            "properties": {
                "passed": {"type": "boolean"},
                "score": {"type": "number", "minimum": 0, "maximum": 5},
                "notes": {"type": "string", "description": "Background quality assessment"},
            },
            "required": ["passed", "score"],
        },
        "text_artifact": {
            "type": "object",
            "properties": {
                "passed": {"type": "boolean"},
                "score": {"type": "number", "minimum": 0, "maximum": 5},
                "issues": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Text artifacts, watermarks, or overlays detected",
                },
            },
            "required": ["passed", "score"],
        },
        "brand_consistency": {
            "type": "object",
            "properties": {
                "passed": {"type": "boolean"},
                "score": {"type": "number", "minimum": 0, "maximum": 5},
                "notes": {"type": "string", "description": "Brand consistency assessment"},
            },
            "required": ["passed", "score"],
        },
        "policy_flags": {
            "type": "object",
            "properties": {
                "passed": {"type": "boolean"},
                "flags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Policy violations (copyright, PII, inappropriate content)",
                },
            },
            "required": ["passed"],
        },
        "confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
            "description": "Confidence level of the QC assessment",
        },
        "recommendation": {
            "type": "string",
            "enum": ["approve", "approve_with_notes", "regenerate", "reject"],
            "description": "Final recommendation for this image",
        },
        "vision_analysis_performed": {
            "type": "boolean",
            "description": "Whether actual vision analysis was performed (false = text-only metadata analysis)",
        },
    },
    "required": [
        "summary",
        "overall_score",
        "image_integrity",
        "product_presence",
        "visual_quality",
        "composition",
        "color_consistency",
        "background_quality",
        "text_artifact",
        "brand_consistency",
        "policy_flags",
        "confidence",
        "recommendation",
        "vision_analysis_performed",
    ],
}

QC_PROMPT_TEMPLATE = (
    "You are the Creative Quality Check Agent for Nuotao Outdoor, an outdoor gear DTC brand. "
    "Analyze the provided image context and product information, and assess the image quality "
    "for e-commerce use. Respond with ONLY a JSON object matching the output schema.\n\n"
    "## Truthfulness Rules (MANDATORY)\n"
    "1. ALL assessments must be based on the provided image context and product context.\n"
    "2. NEVER invent image details that are not described.\n"
    "3. SCORES MUST BE HONEST. If you cannot assess something, use a middle score and explain.\n"
    "4. COMPLIANCE ISSUES MUST BE FLAGGED. If there's any copyright or PII risk, mark it clearly.\n"
    "5. REGENERATION SUGGESTIONS MUST BE ACTIONABLE. Be specific about what to change.\n"
    "6. VISION ANALYSIS: If vision_analysis_performed is false, you are analyzing based on "
    "metadata only (prompt, dimensions, product context). This is NOT a visual inspection. "
    "Set vision_analysis_performed to false in your output.\n\n"
    "Context: {context_json}\n\n"
    "Output schema: {output_schema}"
)

QC_AGENT_ID = "creative_qc_agent"
QC_AGENT_NAME = "Creative QC Agent"
QC_PROMPT_NAME = "AGENT_CREATIVE_QC"
QC_TRIGGER = "api:creative:qc"


async def run_ai_quality_check(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    asset_id: UUID,
    trace_id: str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Run AI-based quality check on a creative asset.

    Uses LLM to analyze the image context and assess:
    - Image integrity (corruption, truncation)
    - Product presence (does the image show the product?)
    - Visual quality (resolution, artifacts, composition)
    - Color consistency (color accuracy)
    - Background quality (cleanliness, appropriateness)
    - Text artifacts (watermarks, overlays)
    - Brand consistency (brand alignment)
    - Policy flags (copyright, PII, inappropriate content)

    P0-4: Reads actual image file if available and passes to vision-capable model.
    If vision analysis is not possible, clearly indicates text-only analysis.

    Args:
        session: database session
        workspace_id: workspace identifier
        asset_id: asset identifier
        trace_id: optional trace identifier
        persist: when False, skip audit persistence (dry-run)

    Returns:
        Dict with QC results and updated asset status.
    """
    from pathlib import Path
    from app.services import creative_service
    from app.models.product import Product

    # Get the asset
    asset_data = await creative_service.get_asset(
        session, asset_id=asset_id, workspace_id=workspace_id
    )
    if not asset_data:
        return {"error": f"Asset not found: {asset_id}"}

    # Get product context
    product_context = {}
    if asset_data.get("product_id"):
        stmt = await session.execute(
            select(Product).where(
                Product.id == UUID(asset_data["product_id"]),
                Product.workspace_id == workspace_id,
            )
        )
        product = stmt.scalar_one_or_none()
        if product:
            product_context = {
                "product_name": product.name,
                "product_sku": product.sku,
                "product_category": product.category,
                "product_description": product.description,
                "product_attributes": product.attributes or {},
            }

    # P0-4: Try to read actual image file for vision analysis
    image_base64 = None
    image_data_url = None
    vision_analysis_performed = False
    vision_model_available = False
    image_source = asset_data.get("storage_key")

    if image_source:
        image_path = Path(image_source)
        if image_path.exists() and image_path.is_file():
            try:
                import base64
                with open(image_path, "rb") as f:
                    image_bytes = f.read()
                image_base64 = base64.b64encode(image_bytes).decode("utf-8")
                # Create data URL for OpenAI vision API
                mime_type = image_path.suffix.lstrip(".").upper()
                if mime_type == "JPG":
                    mime_type = "JPEG"
                if mime_type not in ("PNG", "JPEG", "WEBP", "GIF"):
                    mime_type = "PNG"  # default
                image_data_url = f"data:image/{mime_type.lower()};base64,{image_base64}"
                vision_analysis_performed = True
                vision_model_available = True
            except Exception as e:
                logger.warning(f"[QC] Failed to read image file: {e}")

    # Build QC context
    qc_context = {
        "asset_id": str(asset_id),
        "asset_type": asset_data.get("asset_type"),
        "asset_status": asset_data.get("status"),
        "image_url": asset_data.get("preview_url"),
        "image_dimensions": {
            "width": asset_data.get("width"),
            "height": asset_data.get("height"),
            "aspect_ratio": asset_data.get("ratio"),
        },
        "prompt_used": asset_data.get("prompt_text"),
        "product_context": product_context,
        "vision_analysis_performed": vision_analysis_performed,
        "vision_model_available": vision_model_available,
    }

    # P0-2 / P0-5: Run the QC agent with vision support if image is available.
    # The vision model must be a verified image-capable model, routed through an
    # explicit provider. The default provider chain (sensenova -> deepseek) does
    # NOT see images: deepseek returns HTTP 200 while silently ignoring the
    # picture, which would make a text-only guess look like a visual QC pass.
    # llm_gateway.VISION_CAPABLE enforces the whitelist and the response-level
    # image_tokens check makes a fake success impossible.
    from app.core.config import get_settings
    settings = get_settings()
    vision_model = settings.vision_model
    vision_provider = settings.vision_provider
    result: GenericAgentResult = await run_generic_agent(
        session,
        workspace_id=workspace_id,
        agent_id=QC_AGENT_ID,
        agent_name=QC_AGENT_NAME,
        trigger=QC_TRIGGER,
        context=qc_context,
        prompt_name=QC_PROMPT_NAME,
        output_schema=QC_OUTPUT_SCHEMA,
        system_instruction=(
            "You are a strict quality control agent for e-commerce images. "
            "Be thorough but fair. Flag real issues, don't invent problems. "
            "Recommend 'approve' only if the image is truly ready for production. "
            "If vision_analysis_performed is false, you are analyzing based on metadata only."
        ),
        temperature=0.2,
        task_type="creative_qc",
        trace_id=trace_id,
        persist=persist,
        # P0-2: Vision options
        vision=vision_model_available,
        images=[image_data_url] if image_data_url else None,
        model=vision_model if vision_model_available else None,
        provider=vision_provider if vision_model_available else None,
    )

    if result.error:
        return {"error": result.error, "asset_id": str(asset_id)}

    qc_output = result.output or {}

    # Update asset quality_result
    overall_score = qc_output.get("overall_score", 0)
    recommendation = qc_output.get("recommendation", "regenerate")
    vision_performed = qc_output.get("vision_analysis_performed", vision_analysis_performed)

    # Map recommendation to status
    if recommendation == "approve":
        new_status = "QC_PASSED"
    elif recommendation == "approve_with_notes":
        new_status = "QC_PASSED"  # Pass but with notes
    else:
        new_status = "REJECTED"

    # Update the asset
    await creative_service.update_asset(
        session,
        asset_id=asset_id,
        workspace_id=workspace_id,
        quality_result={
            "passed": new_status == "QC_PASSED",
            "score": overall_score / 5.0,  # Normalize to 0-1
            "ai_qc": qc_output,
            "checked_at": datetime.now(UTC).isoformat(),
            "checked_by": "qc_bot_v2_ai",
            "vision_analysis_performed": vision_performed,
        },
    )

    # Update asset status
    await creative_service.update_asset(
        session,
        asset_id=asset_id,
        workspace_id=workspace_id,
        status=new_status,
    )

    # Record review
    review = CreativeReview(
        id=uuid4(),
        workspace_id=workspace_id,
        asset_id=asset_id,
        review_type="quality_check",
        reviewer_type="AI",
        result="approved" if new_status == "QC_PASSED" else "rejected",
        reasons=qc_output,
        reviewer_id="qc_bot_v2_ai",
        trace_id=trace_id,
    )
    session.add(review)
    await session.flush()

    return {
        "asset_id": str(asset_id),
        "passed": new_status == "QC_PASSED",
        "status": new_status,
        "overall_score": overall_score,
        "recommendation": recommendation,
        "qc_details": qc_output,
        "vision_analysis_performed": vision_performed,
    }
