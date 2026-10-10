"""Product listing readiness gate.

Validates that a product has all critical fields needed for accurate
WooCommerce listing and image generation, BEFORE any marketing content is
produced. This prevents the "guessing parameters" problem where weight,
dimensions, material, and charging port are fabricated or left blank.

Design:
- Deterministic, side-effect free (like data_integrity_gate)
- Called after product data is imported/analyzed but BEFORE image generation
- Returns a structured result with missing fields and recommendations
- Does NOT block — the caller decides whether to proceed with incomplete data

Usage:
    from app.services.product_readiness_gate import check_readiness
    result = check_readiness(product)
    if not result.ready:
        log.warning("Product missing: %s", result.missing_fields)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Field specification — reviewed, configurable, never hidden.
# ---------------------------------------------------------------------------

# Fields that MUST be present for WooCommerce listing accuracy.
# These are P0 — missing values cause incorrect shipping, returns, or claims.
LISTING_CRITICAL_FIELDS: dict[str, dict[str, Any]] = {
    "weight_kg": {
        "label": "Weight (kg)",
        "priority": "P0",
        "reason": "Required for shipping cost calculation. Estimating wrong weight causes 30-60% shipping loss.",
        "source": "1688 product detail page (product parameters section)",
        "example": "0.29",
    },
    "dimensions": {
        "label": "Dimensions (cm)",
        "priority": "P0",
        "reason": "Required for shipping volume weight calculation. 25x4x4 vs 30x20x15 changes cost by 10x.",
        "source": "1688 product detail page (product parameters section)",
        "example": "{'length': '25', 'width': '4', 'height': '4'}",
    },
    "material": {
        "label": "Material",
        "priority": "P1",
        "reason": "Used in product description and attributes. Must be accurate to avoid returns.",
        "source": "1688 product detail page (product parameters section)",
        "example": "ABS + PC",
    },
    "charging_port": {
        "label": "Charging Port",
        "priority": "P1",
        "reason": "Critical for electronics products. USB-C vs Micro-USB affects accessory compatibility.",
        "source": "1688 product detail page (seller description)",
        "example": "Type-C",
    },
    "waterproof_rating": {
        "label": "Waterproof Rating",
        "priority": "P1",
        "reason": "Outdoor products. IP65 vs non-waterproof changes use cases and returns.",
        "source": "1688 product detail page (product parameters section)",
        "example": "IP65",
    },
    "certification": {
        "label": "Certification",
        "priority": "P2",
        "reason": "May be required for target market compliance (CE, FCC, etc.).",
        "source": "1688 product detail page or supplier inquiry",
        "example": "CE, FCC",
    },
    "power_supply": {
        "label": "Power Supply",
        "priority": "P2",
        "reason": "Electronics products. Voltage and wattage affect usage instructions.",
        "source": "1688 product detail page (product parameters section)",
        "example": "5V / 2W",
    },
}

# Fields that SHOULD be present for good marketing content.
# These are P1/P2 — missing values reduce content quality but don't block.
MARKETING_FIELDS: dict[str, dict[str, Any]] = {
    "product_images": {
        "label": "Product Images (1688 originals)",
        "priority": "P0",
        "reason": "I2I generation requires reference images. Without them, all images are T2I (less accurate).",
        "source": "1688 product detail page (image gallery)",
        "min_count": 1,
    },
    "description_zh": {
        "label": "Chinese Description",
        "priority": "P1",
        "reason": "Source for accurate English translation. Missing description means AI has to guess features.",
        "source": "1688 product detail page (seller description)",
    },
    "supplier_name": {
        "label": "Supplier Name",
        "priority": "P2",
        "reason": "Needed for sourcing traceability and supplier evaluation.",
        "source": "1688 product detail page",
    },
}

# Fields that are OPTIONAL but nice to have.
NICE_TO_HAVE_FIELDS: dict[str, dict[str, Any]] = {
    "color_options": {
        "label": "Color Options",
        "priority": "P3",
        "reason": "Needed for variant listing. Missing = single-color listing.",
        "source": "1688 product detail page",
    },
    "size_options": {
        "label": "Size Options",
        "priority": "P3",
        "reason": "Needed for size variant listing.",
        "source": "1688 product detail page",
    },
    "weight_per_unit": {
        "label": "Weight Per Unit",
        "priority": "P3",
        "reason": "Needed for multi-pack shipping calculation.",
        "source": "1688 product detail page",
    },
}

# All fields combined for easy access.
ALL_READINESS_FIELDS = {
    **LISTING_CRITICAL_FIELDS,
    **MARKETING_FIELDS,
    **NICE_TO_HAVE_FIELDS,
}


@dataclass(frozen=True)
class ReadinessResult:
    """Outcome of one product readiness check."""

    ready: bool  # True if all P0 fields are present
    score: Decimal  # 0-100 readiness score
    status: str  # "ready" | "partial" | "missing"
    missing_fields: list[str]  # Field names that are absent
    present_fields: list[str]  # Field names that are present
    recommendations: list[str]  # Human-readable recommendations
    field_details: dict[str, dict[str, Any]]  # Per-field detail (label, priority, reason)
    version: str


def _get_attr(product: Any, name: str, default: Any = None) -> Any:
    """Get attribute from either a dict or an object."""
    if isinstance(product, dict):
        return product.get(name, default)
    return getattr(product, name, default)


def _extract_field(product: Any, field_name: str) -> Any:
    """Extract a field value from a product object or dict.

    Handles:
    - SQLAlchemy Product model (weight_kg, dimensions, attributes, meta)
    - Dict-like objects (from Newton, JSON, etc.)
    - Dot-notation fields (e.g. 'attributes.material')
    """
    if field_name in ("weight_kg", "weight"):
        val = _get_attr(product, "weight_kg") or _get_attr(product, "weight")
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                return None
        meta = _get_attr(product, "meta") or {}
        if isinstance(meta, dict) and meta.get("weight_kg"):
            try:
                return float(meta["weight_kg"])
            except (ValueError, TypeError):
                pass
        attributes = _get_attr(product, "attributes") or {}
        if isinstance(attributes, dict):
            for key in ("weight_kg", "weight", "Weight"):
                if attributes.get(key):
                    try:
                        return float(attributes[key])
                    except (ValueError, TypeError):
                        pass
        return None

    if field_name == "dimensions":
        dims = _get_attr(product, "dimensions")
        if dims and isinstance(dims, dict):
            keys = {k.lower() for k in dims.keys()}
            if {"length", "width", "height"}.intersection(keys) or {"l", "w", "h"}.intersection(keys):
                return dims
        return None

    if field_name == "material":
        attributes = _get_attr(product, "attributes") or {}
        if isinstance(attributes, dict):
            for key in ("material", "Material", "材质", "外壳材质"):
                if attributes.get(key):
                    return attributes[key]
        meta = _get_attr(product, "meta") or {}
        if isinstance(meta, dict) and meta.get("material"):
            return meta["material"]
        return None

    if field_name == "charging_port":
        attributes = _get_attr(product, "attributes") or {}
        if isinstance(attributes, dict):
            for key in ("charging_port", "Charging Port", "充电口", "接口"):
                if attributes.get(key):
                    return attributes[key]
        return None

    if field_name == "waterproof_rating":
        attributes = _get_attr(product, "attributes") or {}
        if isinstance(attributes, dict):
            for key in ("waterproof_rating", "Waterproof", "防水等级", "IP"):
                if attributes.get(key):
                    return attributes[key]
        return None

    if field_name == "certification":
        attributes = _get_attr(product, "attributes") or {}
        if isinstance(attributes, dict):
            for key in ("certification", "Certification", "认证"):
                if attributes.get(key):
                    return attributes[key]
        return None

    if field_name == "power_supply":
        attributes = _get_attr(product, "attributes") or {}
        if isinstance(attributes, dict):
            for key in ("power_supply", "Power Supply", "电源", "电压"):
                if attributes.get(key):
                    return attributes[key]
        voltage = None
        wattage = None
        if isinstance(attributes, dict):
            for key in ("voltage", "Voltage", "电压"):
                if attributes.get(key):
                    voltage = attributes[key]
            for key in ("wattage", "Wattage", "功率"):
                if attributes.get(key):
                    wattage = attributes[key]
        if voltage and wattage:
            return f"{voltage} / {wattage}"
        return None

    if field_name == "product_images":
        meta = _get_attr(product, "meta") or {}
        if isinstance(meta, dict):
            images = meta.get("images") or meta.get("reference_images") or []
            if isinstance(images, list) and len(images) > 0:
                return images
        attributes = _get_attr(product, "attributes") or {}
        if isinstance(attributes, dict):
            images = attributes.get("images") or []
            if isinstance(images, list) and len(images) > 0:
                return images
        source_url = _get_attr(product, "source_url")
        if source_url:
            return [source_url]
        return None

    if field_name == "description_zh":
        description = _get_attr(product, "description")
        if description and len(str(description)) > 20:
            import re
            if re.search(r"[\u4e00-\u9fff]", str(description)):
                return description
        return None

    if field_name == "supplier_name":
        meta = _get_attr(product, "meta") or {}
        if isinstance(meta, dict) and meta.get("supplier_name"):
            return meta["supplier_name"]
        return None

    if field_name == "color_options":
        attributes = _get_attr(product, "attributes") or {}
        if isinstance(attributes, dict):
            for key in ("color", "colors", "Color", "颜色"):
                if attributes.get(key):
                    return attributes[key]
        return None

    if field_name == "size_options":
        attributes = _get_attr(product, "attributes") or {}
        if isinstance(attributes, dict):
            for key in ("size", "sizes", "Size", "尺寸"):
                if attributes.get(key):
                    return attributes[key]
        return None

    if field_name == "weight_per_unit":
        meta = _get_attr(product, "meta") or {}
        if isinstance(meta, dict) and meta.get("weight_per_unit"):
            return meta["weight_per_unit"]
        return None

    # Fallback: check attributes dict with the exact field name
    attributes = _get_attr(product, "attributes") or {}
    if isinstance(attributes, dict) and attributes.get(field_name):
        return attributes[field_name]

    meta = _get_attr(product, "meta") or {}
    if isinstance(meta, dict) and meta.get(field_name):
        return meta[field_name]

    return None


def check_readiness(product: Any, *, trace_id: str = "") -> ReadinessResult:
    """Check product readiness for WooCommerce listing and image generation.

    Args:
        product: A SQLAlchemy Product model or dict-like object with product data.
        trace_id: Optional trace ID for audit.

    Returns:
        ReadinessResult with score, missing fields, and recommendations.
    """
    missing: list[str] = []
    present: list[str] = []
    recommendations: list[str] = []
    field_details: dict[str, dict[str, Any]] = {}

    total_weight = Decimal("100")
    passed_weight = Decimal("0")

    # Weight each priority level. Weights must sum to 100 across all fields.
    # P0 (3 fields x 20) = 60, P1 (4 fields x 8) = 32, P2 (3 fields x 2) = 6, P3 (3 fields x 0.67) ≈ 2
    PRIORITY_WEIGHTS: dict[str, Decimal] = {
        "P0": Decimal("20"),
        "P1": Decimal("8"),
        "P2": Decimal("2"),
        "P3": Decimal("1"),
    }

    for field_name, spec in ALL_READINESS_FIELDS.items():
        priority = spec.get("priority", "P3")
        weight = PRIORITY_WEIGHTS.get(priority, Decimal("2"))
        spec_copy = {
            "label": spec.get("label", field_name),
            "priority": priority,
            "reason": spec.get("reason", ""),
            "source": spec.get("source", ""),
            "example": spec.get("example", ""),
        }
        field_details[field_name] = spec_copy

        value = _extract_field(product, field_name)
        is_present = value is not None and value != "" and value != [] and value != {}

        if is_present:
            present.append(field_name)
            passed_weight += weight
        else:
            missing.append(field_name)
            # Add specific recommendation based on priority
            if priority == "P0":
                recommendations.append(
                    f"[BLOCKING] {spec.get('label', field_name)} is missing. "
                    f"{spec.get('reason', '')} Source: {spec.get('source', '1688 detail page')}"
                )
            elif priority == "P1":
                recommendations.append(
                    f"[IMPORTANT] {spec.get('label', field_name)} is missing. "
                    f"{spec.get('reason', '')} Source: {spec.get('source', '1688 detail page')}"
                )
            elif priority == "P2":
                recommendations.append(
                    f"[RECOMMENDED] {spec.get('label', field_name)} is missing. "
                    f"Source: {spec.get('source', '1688 detail page')}"
                )
            # P3 fields are optional, no recommendation needed

    score = (passed_weight / total_weight * 100).quantize(Decimal("0.01"))
    # Clamp to 0-100
    if score > 100:
        score = Decimal("100.00")
    if score < 0:
        score = Decimal("0.00")

    # Determine status
    has_p0_missing = any(
        ALL_READINESS_FIELDS[f].get("priority") == "P0" for f in missing
    )
    has_p1_missing = any(
        ALL_READINESS_FIELDS[f].get("priority") == "P1" for f in missing
    )

    if has_p0_missing:
        ready = False
        status = "missing"
    elif has_p1_missing:
        ready = False
        status = "partial"
    else:
        ready = True
        status = "ready"

    # Sort recommendations by priority
    priority_order = {"BLOCKING": 0, "IMPORTANT": 1, "RECOMMENDED": 2}
    recommendations.sort(key=lambda r: priority_order.get(
        next((tag for tag in priority_order if r.startswith(f"[{tag}]")), "RECOMMENDED"),
        3,
    ))

    result = ReadinessResult(
        ready=ready,
        score=score,
        status=status,
        missing_fields=missing,
        present_fields=present,
        recommendations=recommendations,
        field_details=field_details,
        version="v1",
    )

    logger.info(
        "readiness_check trace_id=%s ready=%s score=%.1f missing=%s present=%s",
        trace_id, ready, float(score), missing, present,
    )

    return result


def format_readiness_report(result: ReadinessResult) -> str:
    """Format a readiness result as a human-readable report."""
    lines = [
        f"Product Readiness Report (v{result.version})",
        f"Status: {result.status.upper()} | Score: {result.score}/100",
        f"Ready for listing: {'YES' if result.ready else 'NO'}",
        "",
        f"Present ({len(result.present_fields)}): {', '.join(result.present_fields)}",
        f"Missing ({len(result.missing_fields)}): {', '.join(result.missing_fields)}",
    ]
    if result.recommendations:
        lines.append("")
        lines.append("Recommendations:")
        for rec in result.recommendations:
            lines.append(f"  - {rec}")
    return "\n".join(lines)
