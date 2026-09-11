"""
AI Product Copy Generation Service
Generates English titles, descriptions, SEO keywords, and bullet points
from raw product information using the LLM Gateway.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.services.llm_gateway import LLMRequest, complete

logger = logging.getLogger(__name__)


PRODUCT_COPY_SYSTEM_PROMPT = """You are an expert e-commerce copywriter for outdoor gear products sold on WooCommerce.
Your task is to generate high-converting English product copy from raw Chinese/English product information.

Rules:
1. Title: 60-80 characters, include key product type, main feature, and use case
2. Description: 150-250 words, 3-4 paragraphs, highlight benefits not just features
3. Bullet points: 5-6 short bullet points (each < 80 chars), focus on key selling points
4. SEO keywords: 8-12 relevant keywords/phrases for search optimization
5. All output must be in English
6. Do not make up specifications not provided; if info is missing, use generic but accurate language
7. Output must be valid JSON with the exact structure specified"""


PRODUCT_COPY_USER_TEMPLATE = """Generate product copy for the following product:

Product Name (original): {name}
Category: {category}
Description (original): {description}
Source URL: {source_url}
Weight: {weight_kg} kg
Target Market: {target_market}

Return ONLY a JSON object with this exact structure:
{{
  "title": "English product title",
  "description": "Full English product description (150-250 words)",
  "bullet_points": ["bullet 1", "bullet 2", "bullet 3", "bullet 4", "bullet 5"],
  "seo_keywords": ["keyword1", "keyword2", "keyword3"],
  "short_description": "Short description for product card (50-80 chars)"
}}"""


async def generate_product_copy(
    *,
    name: str,
    category: str | None = None,
    description: str | None = None,
    source_url: str | None = None,
    weight_kg: float | None = None,
    target_market: str = "US",
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Generate English product copy using LLM.

    Args:
        name: Original product name (Chinese or English)
        category: Product category
        description: Original product description
        source_url: Source product URL
        weight_kg: Product weight in kg
        target_market: Target market (US, EU, etc.)
        trace_id: Correlation ID

    Returns:
        Dict with title, description, bullet_points, seo_keywords, short_description
    """
    user_prompt = PRODUCT_COPY_USER_TEMPLATE.format(
        name=name or "Unknown product",
        category=category or "General",
        description=description or "No detailed description provided",
        source_url=source_url or "N/A",
        weight_kg=weight_kg if weight_kg is not None else "N/A",
        target_market=target_market,
    )

    request = LLMRequest(
        messages=[
            {"role": "system", "content": PRODUCT_COPY_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        task_type="product_copy",
        temperature=0.7,
        max_tokens=2000,
        response_format="json_object",
    )

    try:
        response = await complete(request, trace_id=trace_id)
        content = response.content.strip()

        # Parse JSON response
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code block
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
                result = json.loads(content)
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
                result = json.loads(content)
            else:
                raise

        # Validate required fields
        required_fields = ["title", "description", "bullet_points", "seo_keywords", "short_description"]
        for field in required_fields:
            if field not in result:
                logger.warning("Missing field %s in LLM response, using default", field)
                if field == "bullet_points":
                    result[field] = []
                elif field == "seo_keywords":
                    result[field] = []
                else:
                    result[field] = ""

        # Add metadata
        result["_meta"] = {
            "provider": response.provider,
            "model": response.model,
            "tokens": response.tokens,
            "cost": str(response.cost),
            "latency_ms": response.latency_ms,
            "trace_id": response.trace_id,
        }

        logger.info(
            "Generated product copy for '%s': provider=%s model=%s tokens=%s cost=$%s",
            name[:30],
            response.provider,
            response.model,
            response.tokens.get("total_tokens", "?"),
            response.cost,
        )

        return result

    except Exception as exc:
        logger.error("Failed to generate product copy: %s", exc, exc_info=True)
        # Return fallback with original info
        return {
            "title": name,
            "description": description or "",
            "bullet_points": [],
            "seo_keywords": [],
            "short_description": name[:80] if name else "",
            "_meta": {
                "error": str(exc),
                "fallback": True,
            },
        }
