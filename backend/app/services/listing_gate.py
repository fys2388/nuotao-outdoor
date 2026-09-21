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
# missing_price and unapproved_candidate were previously REVIEW_REQUIRED, which
# made "zero retail price" and "never reviewed" one-click overrideable - a hard
# business precondition that should not sit behind a force flag.
HARD_BLOCK: set[str] = {
    "missing_sku",
    "missing_price",
    "unapproved_candidate",
    "cjk_without_localization",
}
# Reasons that require human review but are overridable (-> 409).
REVIEW_REQUIRED: set[str] = {
    "unapproved_copy",
    "thin_copy",
}

_COPY_STATUSES_PASSING = {"approved"}
# Candidate lifecycle is candidate -> approved -> testing -> winner (see
# product_intelligence._CANDIDATE_TRANSITIONS). Only ``approved`` used to pass,
# so testing/winner - strictly further along the review - were refused with
# "请先完成候选评审至 approved", and winner (the terminal best outcome) could
# never be published at all.
_CANDIDATE_STATUSES_PASSING = {"approved", "testing", "winner"}

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


def evaluate_gate_from_dict(listing_data: dict[str, Any]) -> dict[str, Any]:
    """Gate the raw dict handed to ``list_to_woocommerce``.

    ``evaluate_gate`` needs a ``Product`` row (``candidate_status``, approved
    English copy in ``meta.localizations.en``), but the two pipeline call sites
    and the legacy listing endpoint hand ``list_to_woocommerce`` a plain dict
    built from ``_generate_listing_data`` - and none of them run a gate at all.
    That left an ungated exit: the same product could be blocked on the
    storefront route while sailing straight into WooCommerce from the pipeline.

    This checks only what a dict can tell us, and makes each of them a hard
    block so the ungated path cannot be weaker than the gated one:

      missing_sku                  no channel mapping key
      missing_price                zero/absent retail price
      cjk_without_localization     Chinese copy into an overseas store

    If the dict happens to carry a ``candidate_status`` (some callers forward
    the Product attributes) it is checked with the same passing set as
    ``evaluate_gate``. Approval status of English copy is intentionally NOT
    asserted here: the pipeline localizes the copy itself, and a dict has no
    approval signal to read, so requiring it would block legitimate output.
    """
    data = listing_data or {}
    reasons: list[dict[str, str]] = []

    sku = str(data.get("sku") or "").strip()
    if not sku:
        reasons.append({
            "code": "missing_sku",
            "message": "缺少 SKU，无法建立 WooCommerce 渠道映射",
        })

    price = _num(
        data.get("regular_price", data.get("price", data.get("sale_price", "")))
    )
    if price is None:
        reasons.append({
            "code": "missing_price",
            "message": "缺少有效零售价（regular_price/price/sale_price 均无正值）",
        })

    title = str(data.get("name") or data.get("title") or "").strip()
    description = str(
        data.get("description") or data.get("long_description") or ""
    ).strip()
    if has_cjk(title) or has_cjk(description):
        reasons.append({
            "code": "cjk_without_localization",
            "message": "商品文案仍含中文字符，海外店铺禁止推送中文商品",
        })

    candidate_status = data.get("candidate_status")
    if candidate_status and str(candidate_status).strip() not in _CANDIDATE_STATUSES_PASSING:
        reasons.append({
            "code": "unapproved_candidate",
            "message": f"候选状态为 {candidate_status}，需先完成候选评审",
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


# When the sourcing pipeline did not persist a category, WooCommerce would file
# the product under "Uncategorized" - a 10-point completeness loss. These rules are
# matched against the already-approved English title, so the assignment is derived
# from reviewed copy rather than from the raw Chinese product name.
# Each entry is a list of regex fragments matched with word boundaries against the
# approved English title. "light" carries a negative lookahead: both the token
# "lightweight" and the prose "light weight" describe product weight, not lighting.
_TITLE_CATEGORY_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("lamp", r"light(?!weight|\s+weight)", "lantern", "torch", "headlamp"), "Lighting"),
    (("tent", r"sleeping\s+bag", "pillow", "mattress", "hammock", "cot"), "Sleep"),
    (("cook", "pot", "pan", "stove", "kettle", "bottle", "cup"), "Cookware"),
    (("backpack", "raincoat", "bag"), "Bags"),
    (("knife", "multitool", "axe", "tool"), "Tools"),
    (("jacket", "shirt", "pants", "sock", "hat"), "Apparel"),
    (("shoe", "boot", "sandal"), "Footwear"),
)
# Storefront default for this outdoor DTC store when no rule applies.
_DEFAULT_CATEGORY = "Camping"


def category_for_product(product: Any, title: str) -> str | None:
    """Resolve a WooCommerce category name for ``product``.

    Prefers the source category, then an approved-title match, then the store
    default. Never returns ``None`` for a product with a title, because a product
    without a category lands in "Uncategorized".
    """
    mapped = _map_category(getattr(product, "category", None))
    if mapped:
        return mapped
    haystack = str(title or "").lower()
    if not haystack:
        return None
    # Word boundaries are mandatory: "Lightweight" contains "light" but is not a
    # lighting product, and a naive substring test sends every moon chair to the
    # Lighting category.
    for keywords, category in _TITLE_CATEGORY_RULES:
        pattern = r"\b(" + "|".join(keywords) + r")\b"
        if re.search(pattern, haystack):
            return category
    return _DEFAULT_CATEGORY


# WooCommerce attribute limits kept small on purpose: attributes are a
# completeness signal, not a data dump.
_MAX_ATTRIBUTES = 8
_MAX_ATTRIBUTE_OPTIONS = 10
_MAX_IMAGES = 10


def normalise_listing_images(raw: Any) -> list[dict[str, str]]:
    """Normalise pipeline image shapes into WooCommerce ``[{"src": url}]``.

    Accepts strings, ``{"src": ...}``, ``{"url": ...}`` and ``{"image_url": ...}``.
    Returns an empty list rather than guessing: an unparsable image entry is
    dropped instead of being replaced with a placeholder.
    """
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    images: list[dict[str, str]] = []
    for item in raw:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = str(
                item.get("src") or item.get("url") or item.get("image_url") or ""
            ).strip()
        else:
            continue
        if text:
            images.append({"src": text})
    return images


def normalise_listing_tags(raw: Any) -> list[str]:
    """Normalise pipeline tags (``[{"name": ...}]`` or ``["..."]``) to strings."""
    if not isinstance(raw, list):
        return []
    tags: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            text = str(item.get("name") or item.get("slug") or "").strip()
        else:
            text = str(item or "").strip()
        if text and text not in tags:
            tags.append(text)
    return tags


def parse_dimensions(raw: Any) -> dict[str, float] | None:
    """Turn a 1688 dimension string such as ``60*40*115`` into WC mm values.

    Returns ``None`` when the input has fewer than three numeric parts. Numbers
    are never invented: a dimension that cannot be parsed is omitted rather than
    guessed, because a wrong dimension ships a wrong freight estimate.
    """
    if isinstance(raw, dict):
        parsed: dict[str, float] = {}
        for key in ("length", "width", "height"):
            value = _num(raw.get(key))
            if value:
                parsed[key] = value
        return parsed or None
    if raw is None:
        return None
    parts = re.split(r"[*/x×,，\s]+", str(raw).strip())
    numbers: list[float] = []
    for part in parts:
        cleaned = re.sub(r"[^0-9.]", "", part)
        if not cleaned:
            continue
        try:
            numbers.append(float(cleaned))
        except ValueError:
            continue
    if len(numbers) >= 3:
        return {"length": numbers[0], "width": numbers[1], "height": numbers[2]}
    return None


def collect_attributes(product_info: dict[str, Any]) -> dict[str, list[str]]:
    """Collect real attribute pairs from pipeline ``product_info``.

    Reads the raw 1688 ``attributes`` list and the fields the pipeline already
    derived from it (materials / dimensions / weight). Returns ``{}`` when the
    source had none - never synthesised.
    """
    collected: dict[str, list[str]] = {}

    def _add(label: Any, value: Any) -> None:
        text = str(label or "").strip()
        if not text:
            return
        bucket = collected.setdefault(text, [])
        if value not in bucket:
            bucket.append(value)

    raw_attributes = product_info.get("attributes")
    has_raw = isinstance(raw_attributes, list) and bool(raw_attributes)
    if has_raw:
        for attr in raw_attributes:
            if not isinstance(attr, dict):
                continue
            key = str(attr.get("name") or attr.get("attributeName") or "").strip()
            value = str(attr.get("value") or "").strip()
            if key and value:
                _add(key, value)

    # Fall back to the fields the pipeline derived from those same attributes.
    # Only used when the raw list is absent, so a real attribute is never
    # shadowed by its own derived restatement.
    if not has_raw:
        materials = product_info.get("materials")
        if isinstance(materials, list):
            for item in materials:
                _add("Material", str(item).strip())
        elif isinstance(materials, str) and materials.strip():
            _add("Material", materials.strip())

        dimensions = product_info.get("dimensions")
        if isinstance(dimensions, str) and dimensions.strip():
            _add("Dimensions", dimensions.strip())
        weight = product_info.get("weight")
        if isinstance(weight, str) and weight.strip():
            _add("Weight", weight.strip())

    return {k: v for k, v in collected.items() if v}


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

    wc_category = category_for_product(product, title)
    if wc_category:
        payload["categories"] = [{"name": wc_category}]

    brand = str(getattr(product, "brand", "") or "").strip()
    if brand and not _CJK_RE.search(brand):
        payload["brand"] = brand

    # ``main_images`` is the pipeline's curated first five; ``images`` is the
    # flat backwards-compatible array. Prefer the curated set when both exist.
    images = normalise_listing_images(meta.get("main_images") or meta.get("images"))
    if images:
        payload["images"] = images[:_MAX_IMAGES]

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
            name = str(key).strip()
            if not name:
                continue
            if isinstance(value, list):
                options = [str(v).strip() for v in value if str(v).strip()]
            else:
                options = [str(value).strip()] if str(value or "").strip() else []
            # Single-value attributes are valid WooCommerce global attributes.
            # The previous ``len(value) > 1`` test dropped every non-variant
            # attribute, costing the 5 attribute completeness points on all
            # products even when the source data existed.
            if 1 <= len(options) <= _MAX_ATTRIBUTE_OPTIONS:
                attributes.append({
                    "name": name,
                    "options": options,
                    "visible": True,
                    "variation": False,
                })
        if attributes:
            payload["attributes"] = attributes[:_MAX_ATTRIBUTES]

    tags = [str(k).strip() for k in keywords if str(k).strip()]
    if not tags:
        tags = normalise_listing_tags(getattr(product, "tags", None))
    if tags:
        payload["tags"] = [{"name": t} for t in tags[:12]]

    return payload
