"""Product content and media helpers shared by intake and listing flows."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.image_gen import ImageGenerationTask
from app.models.product import Product

_MARKET_LANGUAGES: dict[str, str] = {
    "US": "en",
    "CA": "en",
    "GB": "en",
    "AU": "en",
    "DE": "de",
    "FR": "fr",
    "ES": "es",
    "IT": "it",
}


def target_language_for_market(target_market: str | None) -> str:
    """Map a target market to the default customer-facing language."""
    return _MARKET_LANGUAGES.get((target_market or "US").upper(), "en")


def normalize_image_urls(value: Any, *, limit: int = 30) -> list[str]:
    """Normalize image payloads to a deduplicated list of HTTP(S) URLs."""
    if isinstance(value, dict):
        value = (
            value.get("images")
            or value.get("gallery")
            or value.get("gallery_images")
            or value.get("detail_images")
            or []
        )
    if not isinstance(value, (list, tuple)):
        value = [value] if value else []

    urls: list[str] = []
    seen: set[str] = set()
    for item in value:
        if isinstance(item, dict):
            raw = item.get("src") or item.get("url") or item.get("image_url") or item.get("imageUrl")
        else:
            raw = item
        url = str(raw or "").strip()
        if not url.startswith(("http://", "https://")) or url in seen:
            continue
        seen.add(url)
        urls.append(url)
        if len(urls) >= limit:
            break
    return urls


def product_media_images(meta: dict[str, Any] | None) -> list[str]:
    """Read normalized media URLs from the product metadata contract."""
    if not isinstance(meta, dict):
        return []
    media = meta.get("media")
    if isinstance(media, dict):
        for key in ("images", "gallery", "main", "detail"):
            urls = normalize_image_urls(media.get(key))
            if urls:
                return urls
    return normalize_image_urls(meta.get("images"))


def get_localization(meta: dict[str, Any] | None, language: str) -> dict[str, Any] | None:
    """Return one persisted localization record."""
    if not isinstance(meta, dict):
        return None
    localizations = meta.get("localizations")
    if not isinstance(localizations, dict):
        return None
    value = localizations.get(language)
    return value if isinstance(value, dict) else None


def get_approved_localization(
    meta: dict[str, Any] | None,
    language: str,
) -> dict[str, Any] | None:
    """Return a localization only after explicit human approval."""
    localization = get_localization(meta, language)
    if not localization or localization.get("status") != "approved":
        return None
    return localization


def build_localization_record(
    result: dict[str, Any],
    *,
    language: str,
    target_market: str,
    source_trace_id: str | None = None,
) -> dict[str, Any]:
    """Build the persisted localization record from AI copy output."""
    meta = result.get("_meta") if isinstance(result.get("_meta"), dict) else {}
    return {
        "language": language,
        "target_market": target_market,
        "status": "generated",
        "title": str(result.get("title") or "").strip(),
        "description": str(result.get("description") or "").strip(),
        "short_description": str(result.get("short_description") or "").strip(),
        "bullet_points": [
            str(item).strip() for item in result.get("bullet_points", []) if str(item).strip()
        ],
        "seo_keywords": [
            str(item).strip() for item in result.get("seo_keywords", []) if str(item).strip()
        ],
        "generated_at": datetime.now(UTC).isoformat(),
        "generated_by": "product_copy_service",
        "source_trace_id": source_trace_id,
        "generation_meta": meta,
        "approved_by": None,
        "approved_at": None,
    }


def localization_values(
    localization: dict[str, Any] | None,
) -> tuple[str, str, str, list[str]]:
    """Return listing fields that are safe to hand to WooCommerce."""
    if not localization:
        return "", "", "", []
    title = str(localization.get("title") or "").strip()
    description = str(localization.get("description") or "").strip()
    short_description = str(localization.get("short_description") or "").strip()
    bullets = [
        str(item).strip()
        for item in localization.get("bullet_points", [])
        if str(item).strip()
    ]
    return title, description, short_description, bullets


def utc_now_iso() -> str:
    """Return an ISO timestamp for metadata updates."""
    return datetime.now(UTC).isoformat()


async def attach_approved_image(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    task_id: UUID,
    placement: str,
    actor: str,
) -> dict[str, Any]:
    """Attach an approved image task to the product media contract.

    Only an HTTP(S) artifact can enter the listing media list because the
    downstream WooCommerce importer needs a fetchable URL. Product and task
    ownership are checked together to prevent cross-workspace attachment.
    """
    product = (
        await session.execute(
            select(Product).where(
                Product.workspace_id == workspace_id,
                Product.id == product_id,
            )
        )
    ).scalar_one_or_none()
    if product is None:
        raise ValueError("product not found")

    task = (
        await session.execute(
            select(ImageGenerationTask).where(
                ImageGenerationTask.workspace_id == workspace_id,
                ImageGenerationTask.id == task_id,
                ImageGenerationTask.product_id == product_id,
            )
        )
    ).scalar_one_or_none()
    if task is None:
        raise ValueError("image task not found for this product")
    if task.status not in ("approved", "published"):
        raise ValueError("only an approved image can be attached to product media")

    image_url = str(task.image_url or "").strip()
    if not image_url.startswith(("http://", "https://")):
        raise ValueError("approved image has no fetchable HTTP(S) URL")

    meta = dict(product.meta or {})
    media = meta.get("media")
    media = dict(media) if isinstance(media, dict) else {}
    images = normalize_image_urls(media.get("images"))
    images = [url for url in images if url != image_url]
    if placement == "main":
        images.insert(0, image_url)
    else:
        images.append(image_url)

    approved_images = media.get("approved_images")
    approved_images = list(approved_images) if isinstance(approved_images, list) else []
    attachment = {
        "task_id": str(task.id),
        "url": image_url,
        "use_case": task.use_case,
        "placement": placement,
        "approved_by": task.approved_by or actor,
        "approved_at": task.approved_at.isoformat() if task.approved_at else None,
        "attached_by": actor,
        "attached_at": utc_now_iso(),
    }
    approved_images = [
        item
        for item in approved_images
        if not (isinstance(item, dict) and item.get("task_id") == str(task.id))
    ]
    approved_images.append(attachment)

    media["images"] = images
    media["main_image"] = images[0] if images else None
    media["gallery_images"] = images[1:]
    media["approved_images"] = approved_images
    meta["media"] = media
    meta["content_updated_at"] = utc_now_iso()
    product.meta = meta
    await session.flush()

    return {
        "product_id": str(product.id),
        "task_id": str(task.id),
        "placement": placement,
        "image_url": image_url,
        "images": images,
        "main_image": media["main_image"],
        "gallery_images": media["gallery_images"],
    }
