"""Image to WooCommerce auto pipeline.

Downloads generated images from URLs, uploads to WC Media Library,
updates the product images array, and verifies WC GET=200.

Flow:
1. Download image from URL → local bytes
2. Upload to WC Media Library (wp/v2/media) → media_id
3. Update product images array (wc/v3/products/{id}) → verified
4. WC GET=200 verification

Design:
- All httpx.AsyncClient calls use trust_env=False (proxy workaround)
- WC REST API v3 requires object array for images: [{id, src, alt, name, position}]
- Upload timeout: 120s (11 images can be large)
- Does NOT block the pipeline on individual image failures (AGENTS.md §1.2)

Usage:
    from app.services.image_wc_pipeline import upload_images_to_wc

    result = await upload_images_to_wc(
        image_urls=["https://.../img1.png", "https://.../img2.png"],
        wc_product_id=2230,
        alt_texts=["Main image", "Detail image"],
    )
    if result.success:
        print(f"Uploaded {result.uploaded}/{result.total} images")
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# WC configuration (same as woocommerce_sync_service)
# ---------------------------------------------------------------------------

try:
    from app.core.config import settings as _wc_settings

    WC_URL = (
        (_wc_settings.woocommerce_base_url or "")
        .strip()
        .rstrip("/")
        or os.getenv("WOOCOMMERCE_BASE_URL", "").strip().rstrip("/")
        or os.getenv("WOOCOMMERCE_URL", "https://nuotaooutdoor.com").strip().rstrip("/")
    )
    WC_CONSUMER_KEY = (
        (_wc_settings.woocommerce_consumer_key or "")
        .strip()
        or os.getenv("WOOCOMMERCE_CONSUMER_KEY", "").strip()
    )
    WC_CONSUMER_SECRET = (
        (_wc_settings.woocommerce_consumer_secret or "")
        .strip()
        or os.getenv("WOOCOMMERCE_CONSUMER_SECRET", "").strip()
    )
except Exception:
    WC_URL = os.getenv("WOOCOMMERCE_BASE_URL", "https://nuotaooutdoor.com").strip().rstrip("/")
    WC_CONSUMER_KEY = os.getenv("WOOCOMMERCE_CONSUMER_KEY", "").strip()
    WC_CONSUMER_SECRET = os.getenv("WOOCOMMERCE_CONSUMER_SECRET", "").strip()


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ImageUploadResult:
    """Result of uploading a single image to WC."""

    url: str
    media_id: int | None
    media_url: str | None
    success: bool
    error: str = ""
    latency_ms: int = 0


@dataclass(frozen=True)
class PipelineResult:
    """Result of the full image-to-WC pipeline."""

    success: bool
    total: int
    uploaded: int
    failed: int
    results: list[ImageUploadResult] = field(default_factory=list)
    wc_product_id: int | None = None
    verified: bool = False
    verification_url: str = ""
    error: str = ""


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


async def download_image(url: str, *, timeout: float = 30.0) -> tuple[bytes, str] | None:
    """Download an image from a URL.

    Args:
        url: Image URL to download.
        timeout: HTTP timeout in seconds.

    Returns:
        Tuple of (bytes, filename) or None if download fails.
    """
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            trust_env=False,
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            content = resp.content

            # Extract filename from URL or Content-Disposition
            filename = ""
            content_disposition = resp.headers.get("content-disposition", "")
            if "filename=" in content_disposition:
                filename = content_disposition.split("filename=")[1].strip('"\'')
            if not filename:
                # Extract from URL path
                url_path = url.split("?")[0]  # Remove query string
                filename = os.path.basename(url_path) or f"image_{uuid.uuid4().hex[:8]}.png"

            return content, filename

    except Exception as exc:
        logger.warning("Image download failed: %s - %s", url, exc)
        return None


async def upload_to_wc_media(
    image_bytes: bytes,
    filename: str,
    *,
    alt_text: str = "",
    timeout: float = 120.0,
) -> tuple[int | None, str | None]:
    """Upload an image to WooCommerce Media Library.

    Uses the WordPress REST API v2 media endpoint.

    Args:
        image_bytes: Image content as bytes.
        filename: Original filename.
        alt_text: Alt text for the image.
        timeout: HTTP timeout in seconds.

    Returns:
        Tuple of (media_id, media_url) or (None, None) on failure.
    """
    if not WC_CONSUMER_KEY or not WC_CONSUMER_SECRET:
        logger.warning("WC credentials not configured")
        return None, None

    endpoint = f"{WC_URL}/wp-json/wp/v2/media"

    # Determine content type
    if filename.lower().endswith(".png"):
        content_type = "image/png"
    elif filename.lower().endswith((".jpg", ".jpeg")):
        content_type = "image/jpeg"
    elif filename.lower().endswith(".webp"):
        content_type = "image/webp"
    else:
        content_type = "image/png"

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            trust_env=False,
        ) as client:
            response = await client.post(
                endpoint,
                auth=(WC_CONSUMER_KEY, WC_CONSUMER_SECRET),
                files={"file": (filename, image_bytes, content_type)},
                data={
                    "alt": alt_text,
                },
            )

        if response.status_code == 201:
            data = response.json()
            return data.get("id"), data.get("source_url") or data.get("url")
        else:
            logger.warning(
                "WC media upload failed: status=%d body=%s",
                response.status_code,
                response.text[:500],
            )
            return None, None

    except Exception as exc:
        logger.warning("WC media upload error: %s", exc)
        return None, None


async def update_product_images(
    wc_product_id: int,
    media_ids: list[dict[str, Any]],
    *,
    timeout: float = 60.0,
) -> bool:
    """Update a WooCommerce product's images array.

    Args:
        wc_product_id: WC product ID.
        media_ids: List of image entries [{id, src, alt, name, position}].
        timeout: HTTP timeout in seconds.

    Returns:
        True if update succeeded, False otherwise.
    """
    if not WC_CONSUMER_KEY or not WC_CONSUMER_SECRET:
        logger.warning("WC credentials not configured")
        return False

    endpoint = f"{WC_URL}/wp-json/wc/v3/products/{wc_product_id}"

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            trust_env=False,
        ) as client:
            # Get current product data
            get_resp = await client.get(
                endpoint,
                auth=(WC_CONSUMER_KEY, WC_CONSUMER_SECRET),
            )

            if get_resp.status_code != 200:
                logger.warning(
                    "WC get product failed: status=%d",
                    get_resp.status_code,
                )
                return False

            product_data = get_resp.json()
            existing_images = product_data.get("images", [])

            # Normalize existing images to object format
            normalized_existing = []
            for img in existing_images:
                if isinstance(img, dict):
                    normalized_existing.append(img)
                elif isinstance(img, int):
                    normalized_existing.append({"id": img})
                # Skip strings or other types

            # Merge: new images first (as featured/gallery start)
            merged_images = media_ids + normalized_existing

            # Update product
            put_resp = await client.put(
                endpoint,
                auth=(WC_CONSUMER_KEY, WC_CONSUMER_SECRET),
                json={"images": merged_images},
            )

            if put_resp.status_code == 200:
                return True
            else:
                logger.warning(
                    "WC update product images failed: status=%d body=%s",
                    put_resp.status_code,
                    put_resp.text[:500],
                )
                return False

    except Exception as exc:
        logger.warning("WC update product images error: %s", exc)
        return False


async def verify_wc_product(wc_product_id: int) -> tuple[bool, str]:
    """Verify a WC product exists and returns HTTP 200.

    Args:
        wc_product_id: WC product ID.

    Returns:
        Tuple of (verified, permalink).
    """
    if not WC_CONSUMER_KEY or not WC_CONSUMER_SECRET:
        return False, ""

    endpoint = f"{WC_URL}/wp-json/wc/v3/products/{wc_product_id}"

    try:
        async with httpx.AsyncClient(
            timeout=30.0,
            trust_env=False,
        ) as client:
            resp = await client.get(
                endpoint,
                auth=(WC_CONSUMER_KEY, WC_CONSUMER_SECRET),
            )
            if resp.status_code == 200:
                data = resp.json()
                return True, data.get("permalink", "")
            else:
                logger.warning("WC verify product failed: status=%d", resp.status_code)
                return False, ""
    except Exception as exc:
        logger.warning("WC verify product error: %s", exc)
        return False, ""


async def upload_images_to_wc(
    image_urls: list[str],
    *,
    wc_product_id: int,
    alt_texts: list[str] | None = None,
    product_name: str = "",
    max_concurrent: int = 3,
) -> PipelineResult:
    """Upload multiple images to WC and update product images array.

    Args:
        image_urls: List of image URLs to download and upload.
        wc_product_id: WC product ID to update.
        alt_texts: Optional list of alt texts (same order as image_urls).
        product_name: Product name for alt text generation.
        max_concurrent: Max concurrent downloads/uploads.

    Returns:
        PipelineResult with upload status and verification.
    """
    started = time.perf_counter()
    results: list[ImageUploadResult] = []
    uploaded_media: list[dict[str, Any]] = []
    uploaded_count = 0
    failed_count = 0

    for idx, url in enumerate(image_urls):
        alt_text = ""
        if alt_texts and idx < len(alt_texts):
            alt_text = alt_texts[idx]
        elif product_name:
            alt_text = f"{product_name} image {idx + 1}"

        # Download image
        dl_result = await download_image(url)
        if not dl_result:
            results.append(ImageUploadResult(
                url=url,
                media_id=None,
                media_url=None,
                success=False,
                error="Download failed",
            ))
            failed_count += 1
            continue

        image_bytes, filename = dl_result

        # Upload to WC media
        media_id, media_url = await upload_to_wc_media(
            image_bytes,
            filename,
            alt_text=alt_text,
        )

        if media_id is None:
            results.append(ImageUploadResult(
                url=url,
                media_id=None,
                media_url=None,
                success=False,
                error="Upload failed",
            ))
            failed_count += 1
            continue

        # Add to uploaded media list
        uploaded_media.append({
            "id": media_id,
            "src": media_url or "",
            "alt": alt_text,
            "name": filename,
            "position": idx,
        })

        results.append(ImageUploadResult(
            url=url,
            media_id=media_id,
            media_url=media_url,
            success=True,
        ))
        uploaded_count += 1

        logger.info(
            "Uploaded image %d/%d: %s → media_id=%d",
            idx + 1, len(image_urls), url[:60], media_id,
        )

    # Update product images if any were uploaded
    if uploaded_media:
        updated = await update_product_images(wc_product_id, uploaded_media)
        if updated:
            logger.info("Updated WC product %d with %d images", wc_product_id, len(uploaded_media))
        else:
            logger.warning("Failed to update WC product %d images", wc_product_id)
            # Mark as failed
            results.append(ImageUploadResult(
                url=f"update_product:{wc_product_id}",
                media_id=None,
                media_url=None,
                success=False,
                error="Product images update failed",
            ))
            failed_count += 1
    else:
        logger.warning("No images uploaded, skipping product update")

    # Verify product exists
    verified, permalink = await verify_wc_product(wc_product_id)
    if not verified:
        logger.warning("WC product %d verification failed", wc_product_id)

    latency_ms = int((time.perf_counter() - started) * 1000)

    # Overall success: at least 1 image uploaded AND product updated
    success = uploaded_count > 0 and failed_count == 0

    return PipelineResult(
        success=success,
        total=len(image_urls),
        uploaded=uploaded_count,
        failed=failed_count,
        results=results,
        wc_product_id=wc_product_id,
        verified=verified,
        verification_url=permalink,
        error="" if success else "See results for details",
    )


def format_pipeline_report(result: PipelineResult) -> str:
    """Format a pipeline result as a human-readable report."""
    status = "✅ SUCCESS" if result.success else "❌ FAILED"
    lines = [
        f"Image → WC Pipeline: {status}",
        f"  Product ID: {result.wc_product_id}",
        f"  Verified: {'Yes' if result.verified else 'No'}",
        f"  URL: {result.verification_url}",
        f"  Total: {result.total}",
        f"  Uploaded: {result.uploaded}",
        f"  Failed: {result.failed}",
    ]

    if result.results:
        lines.append("")
        lines.append("Image Results:")
        for r in result.results:
            icon = "✅" if r.success else "❌"
            if r.success:
                lines.append(f"  {icon} media_id={r.media_id} {r.url[:60]}")
            else:
                lines.append(f"  {icon} {r.url[:60]} - {r.error}")

    return "\n".join(lines)
