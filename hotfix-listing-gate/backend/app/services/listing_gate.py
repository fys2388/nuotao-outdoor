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
3. Build a WooCommerce payload from the *approved English copy* rather than the
   raw Chinese source title/description.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Reasons that can never be force-overridden (hard block -> 422).
HARD_BLOCK: set[str] = {"missing_sku"}
# Reasons that require human review but are overridable (-> 409).
REVIEW_REQUIRED: set[str] = {"missing_price", "unapproved_copy"}

_COPY_STATUSES_PASSING = {"approved", "approved_en"}


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
    status = str(en_copy.get("status") or "").strip().lower()
    return status in _COPY_STATUSES_PASSING


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
    # WooCommerce hard-rejects sale_price >= regular_price; drop the sale price
    # in that case rather than shipping a payload that can never create.
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

    copy_status = str(en_copy.get("status") or "缺失")
    if not copy_is_approved(en_copy):
        reasons.append({
            "code": "unapproved_copy",
            "message": f"英文文案未批准，当前状态：{copy_status}",
        })

    if any(reason["code"] in HARD_BLOCK for reason in reasons):
        return {"status": "blocked", "reasons": reasons}
    if reasons:
        return {"status": "needs_review", "reasons": reasons}
    return {"status": "passed", "reasons": []}


def build_wc_payload(product: Any, prices: dict, en_copy: dict) -> dict:
    """Build a WooCommerce product payload from the approved English copy.

    Uses the localized title/description/bullet points/SEO keywords so the
    storefront never receives a Chinese or empty listing.
    """
    title = str(en_copy.get("title") or getattr(product, "name", "") or "").strip()
    description = str(en_copy.get("description") or getattr(product, "description", "") or "").strip()
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
        "status": "publish" if getattr(product, "status", None) == "active" else "draft",
        "regular_price": str(round(regular, 2)) if regular else "0",
        "description": description,
        "short_description": short,
    }
    if prices.get("sale_price"):
        payload["sale_price"] = str(round(prices["sale_price"], 2))

    category = getattr(product, "category", None)
    if category:
        payload["categories"] = [{"name": str(category)}]

    tags = [str(k).strip() for k in keywords if str(k).strip()]
    if not tags:
        raw_tags = getattr(product, "tags", None)
        if isinstance(raw_tags, list):
            tags = [str(t).strip() for t in raw_tags if str(t).strip()]
    if tags:
        payload["tags"] = [{"name": t} for t in tags[:12]]

    return payload
