"""1688 product data extractor.

Extracts product parameters (weight, dimensions, material, etc.) from
1688 API responses and normalizes them into the format expected by
``product_readiness_gate``.

Data sources:
1. 1688 Open API (``alibaba.product.get``) — primary, if configured
2. HTTP scraping with browser-like headers — fallback

Design:
- Deterministic: no LLM, pure rule-based parsing
- Non-blocking: returns whatever data is available, never raises
- Fields mapped to ``product_readiness_gate`` spec

Usage:
    from app.services.product_data_extractor import extract_from_1688

    result = extract_from_1688("966534719581")
    if result.success:
        data = result.data
        print(data.get("weight_kg"))  # 0.29
        print(data.get("dimensions"))  # {"length": "25", "width": "4", "height": "4"}
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns for extracting values from attribute text
# ---------------------------------------------------------------------------

# Weight patterns: "0.29kg", "290g", "0.29 千克", "290 克"
_WEIGHT_PATTERN = re.compile(
    r"(\d+\.?\d*)\s*(kg|千克|g|克|gram|grams|公斤)",
    re.IGNORECASE,
)

# Dimensions patterns: "25x4x4cm", "25*4*4", "长25宽4高4"
_DIMENSION_PATTERN = re.compile(
    r"(\d+\.?\d*)\s*(?:x|X|×|\*|/)\s*(\d+\.?\d*)\s*(?:x|X|×|\*|/)\s*(\d+\.?\d*)",
)
# 2-number fallback: "高25cm×直径4cm", "25x4cm", "L25 W4"
_DIMENSION_2_PATTERN = re.compile(
    r"(?:高|长|H|L|height|length)?\s*(\d+\.?\d*)\s*(?:cm|CM|mm|MM)?\s*(?:x|X|×|\*|/)\s*(?:直径|宽|直径|W|D|width|diameter)?\s*(\d+\.?\d*)\s*(?:cm|CM|mm|MM)?",
)

# Material patterns: "ABS+PC", "纯钛", "304不锈钢", "食品级PP"
_MATERIAL_PATTERN = re.compile(
    r"^(ABS|PC|PP|PE|PET|PVC|TPU|TPE|硅胶|橡胶|塑料|不锈钢|钛|铝合金|锌合金|"
    r"纯棉|棉|涤纶|尼龙|帆布|皮革|PU|PU皮|真丝|亚麻|麻|玻璃|陶瓷|木|竹|"
    r"金属|塑料|abs|pc|pp|pe|pet|pvc)$",
    re.IGNORECASE,
)

# Charging port patterns: "Type-C", "USB-C", "Micro-USB", "Lightning"
_CHARGING_PORT_PATTERN = re.compile(
    r"(Type-?C|USB-?C|Micro-?USB|USB-?A|Lightning|无线充电|磁吸)",
    re.IGNORECASE,
)

# Waterproof rating patterns: "IP65", "IPX7", "IP68"
_WATERPROOF_PATTERN = re.compile(
    r"(IP[\dX]{2,4})",
    re.IGNORECASE,
)

# Power patterns: "5V", "2W", "5V/2W", "100-240V"
_POWER_PATTERN = re.compile(
    r"(\d+\.?\d*)\s*(V|W|Wh|mAh|毫安时)",
    re.IGNORECASE,
)

# Chinese character detection
_CJK_PATTERN = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExtractionResult:
    """Result of 1688 product data extraction."""

    success: bool
    product_id: str
    data: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    source: str = ""  # "1688_api" | "scrape" | "mock"


# ---------------------------------------------------------------------------
# Core extraction functions
# ---------------------------------------------------------------------------


def _extract_weight(text: str) -> float | None:
    """Extract weight in kg from text."""
    match = _WEIGHT_PATTERN.search(text)
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2).lower()
    if unit in ("g", "克", "gram", "grams"):
        return round(value / 1000, 4)
    # kg, 千克, 公斤
    return round(value, 4)


def _extract_dimensions(text: str) -> dict[str, str] | None:
    """Extract dimensions (length x width x height) from text."""
    match = _DIMENSION_PATTERN.search(text)
    if match:
        return {
            "length": match.group(1),
            "width": match.group(2),
            "height": match.group(3),
        }
    # Fallback: 2-number format (e.g. "高25cm×直径4cm")
    match2 = _DIMENSION_2_PATTERN.search(text)
    if match2:
        return {
            "length": match2.group(1),
            "width": match2.group(2),
            "height": "",
        }
    return None


def _extract_material(text: str) -> str | None:
    """Extract material from attribute value."""
    text = text.strip()
    # Check if the text contains a known material (search anywhere in text)
    for material in re.findall(
        r"(ABS|PC|PP|PE|PET|PVC|TPU|TPE|硅胶|橡胶|塑料|不锈钢|钛|铝合金|"
        r"锌合金|纯棉|棉|涤纶|尼龙|帆布|皮革|PU皮|真丝|亚麻|玻璃|陶瓷|木|竹|金属)",
        text,
        re.IGNORECASE,
    ):
        return material
    return None


def _extract_charging_port(text: str) -> str | None:
    """Extract charging port type from attribute value."""
    match = _CHARGING_PORT_PATTERN.search(text)
    return match.group(1) if match else None


def _extract_waterproof_rating(text: str) -> str | None:
    """Extract waterproof rating from attribute value."""
    match = _WATERPROOF_PATTERN.search(text)
    return match.group(1).upper() if match else None


def _extract_power_supply(text: str) -> str | None:
    """Extract power supply info from attribute value."""
    matches = re.findall(r"\d+\.?\d*\s*(?:V|W|Wh|mAh|毫安时)", text, re.IGNORECASE)
    if matches:
        return " / ".join(matches)
    return None


def _extract_supplier_name(supplier: dict[str, Any] | None) -> str | None:
    """Extract supplier name from supplier dict."""
    if not supplier:
        return None
    return (
        supplier.get("company_name")
        or supplier.get("companyName")
        or supplier.get("supplier_name")
        or None
    )


def _extract_product_images(product: dict[str, Any]) -> list[str] | None:
    """Extract product image URLs."""
    images = product.get("images") or []
    if isinstance(images, str):
        images = [images]
    normalized = []
    for img in images:
        if isinstance(img, str) and img.strip().startswith("http"):
            normalized.append(img.strip())
        elif isinstance(img, dict):
            url = img.get("url") or img.get("imageUrl") or ""
            if url.strip().startswith("http"):
                normalized.append(url.strip())
    return normalized if normalized else None


def _extract_description_zh(product: dict[str, Any]) -> str | None:
    """Extract Chinese description from product."""
    desc = product.get("description") or product.get("detail") or ""
    if desc and len(desc) > 20 and _CJK_PATTERN.search(desc):
        return desc[:500]  # Truncate to first 500 chars
    return None


def _extract_color_options(attributes: list[dict[str, Any]]) -> str | None:
    """Extract color options from attributes."""
    for attr in attributes:
        key = (attr.get("attrName") or attr.get("name") or "").lower()
        if key in ("颜色", "color", "颜色分类"):
            value = attr.get("attrValue") or attr.get("value") or ""
            if value:
                return value
    return None


def _extract_size_options(attributes: list[dict[str, Any]]) -> str | None:
    """Extract size options from attributes."""
    for attr in attributes:
        key = (attr.get("attrName") or attr.get("name") or "").lower()
        if key in ("尺寸", "size", "尺码", "规格"):
            value = attr.get("attrValue") or attr.get("value") or ""
            if value:
                return value
    return None


def parse_1688_attributes(
    attributes: list[dict[str, Any]] | None,
    product: dict[str, Any],
) -> dict[str, Any]:
    """Parse 1688 attributes into structured fields.

    Args:
        attributes: List of attribute dicts from 1688 API.
        product: Full product dict (for fallback extraction).

    Returns:
        Dict with extracted fields (weight_kg, dimensions, material, etc.)
    """
    result: dict[str, Any] = {}

    # Build a searchable text from all attributes
    attr_text = ""
    attr_map: dict[str, str] = {}
    if attributes:
        for attr in attributes:
            name = (attr.get("attrName") or attr.get("name") or "").strip()
            value = (attr.get("attrValue") or attr.get("value") or "").strip()
            if name and value:
                attr_map[name.lower()] = value
                attr_text += f"{name}:{value} "

    # Also include subject/description for fallback
    subject = product.get("subject") or ""
    description = product.get("description") or product.get("detail") or ""

    # --- Weight ---
    for name, value in attr_map.items():
        if any(k in name for k in ("重量", "weight", "净重", "毛重")):
            w = _extract_weight(value)
            if w is not None:
                result["weight_kg"] = w
                break
    if "weight_kg" not in result:
        w = _extract_weight(attr_text + " " + subject + " " + description[:200])
        if w is not None:
            result["weight_kg"] = w

    # --- Dimensions ---
    for name, value in attr_map.items():
        if any(k in name for k in ("尺寸", "规格", "size", "dimension", "长宽")):
            dims = _extract_dimensions(value)
            if dims is not None:
                result["dimensions"] = dims
                break
    if "dimensions" not in result:
        dims = _extract_dimensions(attr_text + " " + subject)
        if dims is not None:
            result["dimensions"] = dims

    # --- Material ---
    for name, value in attr_map.items():
        if any(k in name for k in ("材质", "material", "材料", "成分")):
            mat = _extract_material(value)
            if mat:
                result["material"] = mat
                break
    if "material" not in result:
        mat = _extract_material(attr_text + " " + subject)
        if mat:
            result["material"] = mat

    # --- Charging Port ---
    for name, value in attr_map.items():
        if any(k in name for k in ("充电", "接口", "charging", "port")):
            port = _extract_charging_port(value)
            if port:
                result["charging_port"] = port
                break
    if "charging_port" not in result:
        port = _extract_charging_port(attr_text + " " + subject)
        if port:
            result["charging_port"] = port

    # --- Waterproof Rating ---
    for name, value in attr_map.items():
        if any(k in name for k in ("防水", "防水等级", "waterproof", "ip")):
            ip = _extract_waterproof_rating(value)
            if ip:
                result["waterproof_rating"] = ip
                break
    if "waterproof_rating" not in result:
        ip = _extract_waterproof_rating(attr_text + " " + subject)
        if ip:
            result["waterproof_rating"] = ip

    # --- Power Supply ---
    for name, value in attr_map.items():
        if any(k in name for k in ("电压", "功率", "电源", "power", "voltage", "watt")):
            power = _extract_power_supply(value)
            if power:
                result["power_supply"] = power
                break
    if "power_supply" not in result:
        power = _extract_power_supply(attr_text + " " + subject)
        if power:
            result["power_supply"] = power

    # --- Certification ---
    for name, value in attr_map.items():
        if any(k in name for k in ("认证", "certification", "ce", "fcc")):
            if value:
                result["certification"] = value
                break

    # --- Supplier Name ---
    supplier = product.get("supplier")
    if isinstance(supplier, dict):
        supplier_name = _extract_supplier_name(supplier)
        if supplier_name:
            result["supplier_name"] = supplier_name
    elif product.get("company_name"):
        result["supplier_name"] = product["company_name"]

    # --- Product Images ---
    images = _extract_product_images(product)
    if images:
        result["product_images"] = images

    # --- Description (Chinese) ---
    desc = _extract_description_zh(product)
    if desc:
        result["description_zh"] = desc

    # --- Color Options ---
    if attributes:
        colors = _extract_color_options(attributes)
        if colors:
            result["color_options"] = colors

    # --- Size Options ---
    if attributes:
        sizes = _extract_size_options(attributes)
        if sizes:
            result["size_options"] = sizes

    # --- Weight Per Unit ---
    for name, value in attr_map.items():
        if any(k in name for k in ("单重", "单件重", "weight per")):
            w = _extract_weight(value)
            if w is not None:
                result["weight_per_unit"] = w
                break

    return result


def extract_from_1688(product_id: str) -> ExtractionResult:
    """Extract product data from 1688.

    Tries the 1688 Open API first. If not configured or fails,
    returns an empty result (the caller can fall back to other sources).

    Args:
        product_id: 1688 product ID (numeric string).

    Returns:
        ExtractionResult with parsed data or error.
    """
    # Try 1688 API
    try:
        from app.services.sourcing_1688_service import (
            get_product_detail,
            is_configured,
        )

        if is_configured():
            api_result = get_product_detail(product_id)
            if api_result.get("success") and api_result.get("product"):
                product = api_result["product"]
                attributes = product.get("attributes") or []
                data = parse_1688_attributes(attributes, product)

                # Add source info
                data["product_id"] = product_id
                data["source_url"] = f"https://detail.1688.com/offer/{product_id}.html"
                data["source"] = "1688_api"

                return ExtractionResult(
                    success=True,
                    product_id=product_id,
                    data=data,
                    source="1688_api",
                )
            else:
                error = api_result.get("error", "Unknown error")
                logger.warning("1688 API returned failure: %s", error)
        else:
            logger.info("1688 API not configured, skipping API extraction")

    except Exception as exc:
        logger.warning("1688 API extraction error: %s", exc)

    # Fallback: return empty result (caller can try other sources)
    return ExtractionResult(
        success=False,
        product_id=product_id,
        data={},
        error="1688 API not configured or failed",
        source="",
    )


def extract_from_product(product: dict[str, Any]) -> dict[str, Any]:
    """Extract data from a product dict (already fetched from some source).

    This is useful when the product data comes from Newton Agent,
    CSV import, or manual entry rather than the 1688 API.

    Args:
        product: Product dict with attributes, meta, etc.

    Returns:
        Dict with extracted fields.
    """
    attributes = product.get("attributes") or []
    if isinstance(attributes, str):
        # Try to parse JSON string
        import json

        try:
            attributes = json.loads(attributes)
        except (json.JSONDecodeError, ValueError):
            attributes = []

    return parse_1688_attributes(attributes, product)


def format_extraction_report(result: ExtractionResult) -> str:
    """Format an extraction result as a human-readable report."""
    if not result.success:
        return f"1688 Data Extraction: FAILED\n  Error: {result.error}"

    data = result.data
    lines = [
        f"1688 Data Extraction: SUCCESS",
        f"  Product ID: {result.product_id}",
        f"  Source: {result.source}",
        f"  Fields extracted: {len(data)}",
        "",
        "Fields:",
    ]

    field_order = [
        "weight_kg", "dimensions", "material", "charging_port",
        "waterproof_rating", "power_supply", "certification",
        "supplier_name", "product_images", "description_zh",
        "color_options", "size_options", "weight_per_unit",
    ]

    for field_name in field_order:
        value = data.get(field_name)
        if value is not None:
            if isinstance(value, list):
                value_str = f"[{len(value)} items]"
            elif isinstance(value, dict):
                value_str = str(value)
            elif isinstance(value, str) and len(value) > 100:
                value_str = value[:100] + "..."
            else:
                value_str = str(value)
            lines.append(f"  ✅ {field_name}: {value_str}")
        else:
            lines.append(f"  ❌ {field_name}: (missing)")

    return "\n".join(lines)
