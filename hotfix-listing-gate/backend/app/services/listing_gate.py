"""V3.0 listing publish gate: pre-publish validation + WooCommerce payload builder.

This module is intentionally self-contained. It does NOT modify
``woocommerce_sync_service`` or ``products.py`` — the production checkout may
carry uncommitted routes that a full-file rsync would destroy.

Responsibilities
----------------
1. Repair the price field-name fracture (pipeline writes ``meta.sale_price``
   while consumers read ``meta.price`` / ``meta.regular_price``).
2. Enforce a real pre-publish gate (409 needs-review / 422 hard-block) instead
   of the current unconditional HTTP 200.
3. Respect the candidate lifecycle: only ``approved`` candidates may publish;
   rows with ``candidate_status IS NULL`` are downstream commerce products.
4. Intercept Chinese copy: a CJK title/description with no approved English
   localization is a hard block, never a forceable warning.
5. Build a WooCommerce payload from the *approved English copy* plus the full
   physical/inventory/attribute shape, so the storefront page is complete.
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Reasons that can never be force-overridden (hard block -> 422).
HARD_BLOCK: set[str] = {"missing_sku", "cjk_without_localization"}
# Reasons that require human review but are overridable (-> 409).
REVIEW_REQUIRED: set[str] = {
    "missing_price",
    "unapproved_copy",
    "unapproved_candidate",
    "thin_copy",
}

_COPY_STATUSES_PASSING = {"approved"}
_CANDIDATE_STATUSES_PASSING = {"approved"}

# WooCommerce rejects sale_price >= regular_price.
_CJK_RE = re.compile(r"[\u3400-\u9fff\uf900-\ufaff\u3000-\u303f\uff00-\uffef]")
# Front-page completeness floor for a purchasable product description.
_MIN_DESCRIPTION_CHARS = 600

# Chinese category labels commonly produced by 1688 sourcing would otherwise be
# created by WooCommerce as "Uncategorized" (or a Chinese-named term).
_CATEGORY_MAP: dict[str, str] = {
    "户外": "Outdoor",
    "户外用品": "Outdoor",
    "露营": "Camping",
    "露营装备": "Camping",
    "座椅": "Furniture",
    "椅子": "Furniture",
    "照明": "Lighting",
    "背包": "Bags",
    "炊具": "Cookware",
    "工具": "Tools",
    "服装": "Apparel",
    "鞋靴": "Footwear",
    "运动": "Sports",
    "家具": "Furniture",
    "收纳": "Storage",
    "睡眠": "Sleep",
    "厨房": "Kitchen",
}


def _num(value: Any) -> float | None:
    """Coerce a messy price value to a positive float, else None."""
    if value is None or value == "":
        return None
    try:
        cleaned = str(value).replace(",", "").replace("$", "").replace("¥", "").strip()
        parsed = float(cleaned)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def get_english_copy(meta: dict | None) -> dict:
    """Return ``meta.localizations.en`` as a dict (never raises)."""
    meta = meta or {}
    localizations = meta.get("localizations")
    if not isinstance(localizations, dict):
        return {}
    english = localizations.get("en")
    return english if isinstance(english, dict) else {}


def copy_is_approved(en_copy: dict) -> bool:
    return str(en_copy.get("status") or "").strip().lower() in _COPY_STATUSES_PASSING


def has_cjk(text: Any) -> bool:
    return bool(_CJK_RE.search(str(text or "")))


def resolve_prices(meta: dict | None) -> dict:
    """Resolve regular/sale price for WooCommerce.

    Repairs the fracture where the sourcing pipeline persists only
    ``meta.sale_price`` (plus ``meta.source_price`` as the 1688 cost). Without
    this the WooCommerce payload carried a sale price but no regular price,
    which WooCommerce rejects.
    """
    meta = meta or {}
    en_copy = get_english_copy(meta)

    regular: float | None = None
    for source in (
        en_copy.get("price"),
        en_copy.get("regular_price"),
        meta.get("regular_price"),
        meta.get("price"),
        meta.get("retail_price"),
        meta.get("sale_price"),
    ):
        regular = _num(source)
        if regular:
            break

    sale = _num(en_copy.get("sale_price") or meta.get("wc_sale_price"))
    if regular and sale and sale >= regular:
        sale = None

    return {"regular_price": regular, "sale_price": sale}


def evaluate_gate(product: Any, prices: dict, en_copy: dict) -> dict:
    """Evaluate the pre-publish gate.

    Returns ``{"status": "passed" | "needs_review" | "blocked", "reasons": [...]}``.
    """
    reasons: list[dict] = []

    sku = str(getattr(product, "sku", "") or "").strip()
    if not sku:
        reasons.append({
            "code": "missing_sku",
            "message": "缺少 SKU，无法建立 WooCommerce 渠道映射",
        })

    if not prices.get("regular_price"):
        reasons.append({
            "code": "missing_price",
            "message": "缺少有效零售价（meta 中 regular_price/price/sale_price 均无正值）",
        })

    # Candidate lifecycle (M5.13): NULL means the row is already a downstream
    # commerce product, so it is not gated by the candidate state machine.
    candidate_status = getattr(product, "candidate_status", None)
    if candidate_status and str(candidate_status).strip() not in _CANDIDATE_STATUSES_PASSING:
        reasons.append({
            "code": "unapproved_candidate",
            "message": f"候选状态为 {candidate_status}，需先完成候选评审至 approved",
        })

    title = str(en_copy.get("title") or getattr(product, "name", "") or "")
    description = str(en_copy.get("description") or getattr(product, "description", "") or "")
    if has_cjk(title) or has_cjk(description):
        if not copy_is_approved(en_copy):
            reasons.append({
                "code": "cjk_without_localization",
                "message": "商品仍为中文文案且无已批准的英文本地化，禁止推送中文商品",
            })
        else:
            reasons.append({
                "code": "cjk_in_approved_copy",
                "message": "已批准英文文案中仍含中文字符，请人工确认",
            })

    copy_status = str(en_copy.get("status") or "缺失")
    if not copy_is_approved(en_copy):
        reasons.append({
            "code": "unapproved_copy",
            "message": f"英文文案未批准，当前状态：{copy_status}",
        })
    elif len(description.strip()) < _MIN_DESCRIPTION_CHARS:
        reasons.append({
            "code": "thin_copy",
            "message": f"英文描述仅 {len(description.strip())} 字符（建议 ≥{_MIN_DESCRIPTION_CHARS}），"
                       "WC 前台内容完整度不足",
        })

    if any(reason["code"] in HARD_BLOCK for reason in reasons):
        return {"status": "blocked", "reasons": reasons}
    if reasons:
        return {"status": "needs_review", "reasons": reasons}
    return {"status": "passed", "reasons": []}


def _map_category(category: str | None) -> str | None:
    raw = str(category or "").strip()
    if not raw:
        return None
    if not _CJK_RE.search(raw):
        return raw
    for chinese, english in _CATEGORY_MAP.items():
        if chinese in raw or raw in chinese:
            return english
    return None


def build_wc_payload(product: Any, prices: dict, en_copy: dict) -> dict:
    """Build a WooCommerce product payload from the approved English copy.

    Covers the fields the WooCommerce storefront page needs to be complete:
    identity, price, description, short description, category, brand, images,
    shipping (weight + dimensions), inventory, tags and attributes.
    """
    meta = getattr(product, "meta", None)
    meta = meta if isinstance(meta, dict) else {}

    title = str(en_copy.get("title") or getattr(product, "name", "") or "").strip()
    description = str(
        en_copy.get("description") or getattr(product, "description", "") or ""
    ).strip()
    bullets = en_copy.get("bullet_points") or en_copy.get("bullets") or []
    keywords = en_copy.get("seo_keywords") or []
    if not isinstance(bullets, list):
        bullets = []
    if not isinstance(keywords, list):
        keywords = []

    regular = prices.get("regular_price")
    short = str(en_copy.get("short_description") or "").strip()
    if not short:
        short = "<br>".join(f"• {str(b).strip()}" for b in bullets if str(b).strip())[:200]
    if not short:
        short = description[:200]

    payload: dict[str, Any] = {
        "name": title,
        "sku": str(getattr(product, "sku", "") or ""),
        "type": "simple",
        "status": "publish" if getattr(product, "status", None) == "active" else "draft",
        "regular_price": str(round(regular, 2)) if regular else "0",
        "description": description,
        "short_description": short,
    }

    if prices.get("sale_price"):
        payload["sale_price"] = str(round(prices["sale_price"], 2))

    wc_category = _map_category(getattr(product, "category", None))
    if wc_category:
        payload["categories"] = [{"name": wc_category}]

    brand = str(getattr(product, "brand", "") or "").strip()
    if brand and not _CJK_RE.search(brand):
        payload["brand"] = brand

    raw_images = meta.get("images")
    if isinstance(raw_images, str):
        raw_images = [raw_images]
    if isinstance(raw_images, list):
        images: list[dict[str, str]] = []
        for item in raw_images:
            if isinstance(item, str) and item.strip():
                images.append({"src": item.strip()})
            elif isinstance(item, dict):
                source = item.get("src") or item.get("url") or item.get("image_url")
                if source:
                    images.append({"src": str(source)})
        if images:
            payload["images"] = images

    weight_kg = getattr(product, "weight_kg", None)
    if weight_kg is not None:
        try:
            weight = float(str(weight_kg))
            if weight > 0:
                payload["weight"] = f"{weight:.3f}"
        except (TypeError, ValueError):
            pass

    dimensions = getattr(product, "dimensions", None)
    if isinstance(dimensions, dict):
        wc_dimensions: dict[str, str] = {}
        for key in ("length", "width", "height"):
            value = _num(dimensions.get(key))
            if value:
                wc_dimensions[key] = f"{value:g}"
        if wc_dimensions:
            payload["dimensions"] = wc_dimensions

    # Inventory: keep the storefront purchasable for freshly published products.
    manage_stock = meta.get("manage_stock", True)
    payload["manage_stock"] = bool(manage_stock)
    payload["stock_quantity"] = int(_num(meta.get("stock_quantity")) or 100)
    stock_status = str(meta.get("stock_status") or "instock").strip().lower()
    payload["stock_status"] = stock_status if stock_status in {
        "instock", "outofstock", "onbackorder", "pending",
    } else "instock"

    raw_attributes = getattr(product, "attributes", None)
    if isinstance(raw_attributes, dict):
        attributes: list[dict[str, Any]] = []
        for key, value in raw_attributes.items():
            if isinstance(value, list) and len(value) > 1:
                options = [str(v).strip() for v in value if str(v).strip()]
                if len(options) > 1:
                    attributes.append({
                        "name": str(key).strip(),
                        "options": options,
                        "visible": True,
                        "variation": False,
                    })
        if attributes:
            payload["attributes"] = attributes

    tags = [str(k).strip() for k in keywords if str(k).strip()]
    if not tags:
        product_tags = getattr(product, "tags", None)
        if isinstance(product_tags, list):
            tags = [str(t).strip() for t in product_tags if str(t).strip()]
    if tags:
        payload["tags"] = [{"name": t} for t in tags[:12]]

    return payload
