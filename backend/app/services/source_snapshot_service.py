"""Source snapshot service for capturing 1688 product page data.

This service captures a snapshot of the 1688 source page when a product is
selected, storing original images and description text for later use by:
- AI copy generation (as reference data)
- 1688 vs WC comparison analysis
- Data quality tracking

The snapshot is stored in the ``products.source_snapshot`` JSON column.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product

logger = logging.getLogger(__name__)

# Maximum number of images to capture from the 1688 page
MAX_IMAGES = 15

# Timeout for fetching the 1688 page (seconds)
FETCH_TIMEOUT = 30


async def capture_source_snapshot(
    db: AsyncSession,
    product_id: str,
    source_url: str,
) -> dict[str, Any] | None:
    """Capture a snapshot of the 1688 source page.

    Args:
        db: Database session.
        product_id: The product UUID.
        source_url: The 1688 product URL.

    Returns:
        The captured snapshot dict, or None if capture failed.
    """
    from app.core.config import settings

    # Check if scraping is enabled
    if not settings.scraping_enabled:
        logger.warning(
            "Scraping is disabled; cannot capture source snapshot for product %s",
            product_id,
        )
        return None

    # Check if domain is allowlisted
    domain = _extract_domain(source_url)
    if domain not in settings.scraping_allowed_domains:
        logger.warning(
            "Domain %s not in scraping allowlist; cannot capture source snapshot",
            domain,
        )
        return None

    try:
        # Fetch the 1688 page
        snapshot = await _fetch_1688_page(source_url)

        # Store the snapshot in the product record
        product = await db.get(Product, product_id)
        if product is None:
            logger.error("Product %s not found for source snapshot", product_id)
            return None

        product.source_snapshot = snapshot
        product.source_url = source_url

        await db.commit()
        await db.refresh(product)

        logger.info(
            "Source snapshot captured for product %s: %d images, %d chars description",
            product_id,
            len(snapshot.get("images", [])),
            len(snapshot.get("description", "")),
        )

        return snapshot

    except Exception as e:
        logger.error("Failed to capture source snapshot for product %s: %s", product_id, e)
        return None


async def _fetch_1688_page(url: str) -> dict[str, Any]:
    """Fetch and parse the 1688 product page.

    Args:
        url: The 1688 product URL.

    Returns:
        A dict with captured page data.
    """
    import httpx

    async with httpx.AsyncClient(timeout=FETCH_TIMEOUT, follow_redirects=True) as client:
        response = await client.get(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })

    if response.status_code != 200:
        raise ValueError(f"Failed to fetch 1688 page: HTTP {response.status_code}")

    html = response.text

    # Parse the HTML to extract images and description
    images = _extract_images(html)
    description = _extract_description(html)
    title = _extract_title(html)
    attributes = _extract_attributes(html)

    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "source_url": url,
        "title": title,
        "images": images[:MAX_IMAGES],
        "description": description,
        "attributes": attributes,
    }


def _extract_images(html: str) -> list[str]:
    """Extract product image URLs from HTML.

    Args:
        html: The HTML content.

    Returns:
        List of image URLs.
    """
    import re

    # Pattern for 1688 product images (from their CDN)
    pattern = r'(https?://[^\s"\']*\.(?:jpg|jpeg|png|webp))'
    matches = re.findall(pattern, html, re.IGNORECASE)

    # Filter out non-product images (logos, icons, etc.)
    product_images = [
        url for url in matches
        if any(keyword in url.lower() for keyword in ["product", "item", "detail", "offer"])
    ]

    # If no product images found, return all matches
    return product_images if product_images else matches


def _extract_description(html: str) -> str:
    """Extract product description from HTML.

    Args:
        html: The HTML content.

    Returns:
        The extracted description text.
    """
    import re

    # Remove script and style tags
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)

    # Extract text content
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text).strip()

    # Truncate to reasonable length
    return text[:5000]


def _extract_title(html: str) -> str:
    """Extract product title from HTML.

    Args:
        html: The HTML content.

    Returns:
        The extracted title.
    """
    import re

    match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _extract_attributes(html: str) -> dict[str, str]:
    """Extract product attributes from HTML.

    Args:
        html: The HTML content.

    Returns:
        Dict of attribute key-value pairs.
    """
    import re

    attributes = {}

    # Pattern for 1688 attribute tables
    pattern = r'<td[^>]*>([^<]+)</td>\s*<td[^>]*>([^<]+)</td>'
    for match in re.finditer(pattern, html, re.IGNORECASE):
        key = match.group(1).strip()
        value = match.group(2).strip()
        if key and value and len(key) < 100 and len(value) < 500:
            attributes[key] = value

    return attributes


def _extract_domain(url: str) -> str:
    """Extract domain from URL.

    Args:
        url: The URL.

    Returns:
        The domain name.
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return parsed.netloc.lower()


async def get_source_snapshot(db: AsyncSession, product_id: str) -> dict[str, Any] | None:
    """Get the stored source snapshot for a product.

    Args:
        db: Database session.
        product_id: The product UUID.

    Returns:
        The source snapshot dict, or None if not available.
    """
    result = await db.execute(
        select(Product.source_snapshot).where(Product.id == product_id)
    )
    return result.scalar_one_or_none()


async def compare_with_wc(db: AsyncSession, product_id: str) -> dict[str, Any]:
    """Compare the source snapshot with the current WC listing.

    This function analyzes gaps between the 1688 source data and the WC listing,
    providing actionable recommendations for improvement.

    Args:
        db: Database session.
        product_id: The product UUID.

    Returns:
        A comparison report with gaps and recommendations.
    """
    snapshot = await get_source_snapshot(db, product_id)
    if not snapshot:
        return {
            "status": "no_snapshot",
            "message": "No source snapshot available for comparison",
        }

    product = await db.get(Product, product_id)
    if not product:
        return {
            "status": "not_found",
            "message": f"Product {product_id} not found",
        }

    comparison = {
        "status": "ok",
        "source_url": product.source_url,
        "source_images_count": len(snapshot.get("images", [])),
        "source_description_length": len(snapshot.get("description", "")),
        "wc_description_length": len(product.description or ""),
        "gaps": [],
        "recommendations": [],
    }

    # Check description length
    if len(snapshot.get("description", "")) > len(product.description or "") * 2:
        comparison["gaps"].append({
            "type": "description_length",
            "severity": "medium",
            "detail": "1688 description is significantly longer than WC description",
        })
        comparison["recommendations"].append({
            "priority": "P0",
            "action": "Expand WC description to match 1688 content depth",
            "target_words": 600,
        })

    # Check images
    if len(snapshot.get("images", [])) > 5:
        comparison["gaps"].append({
            "type": "image_count",
            "severity": "high",
            "detail": f"1688 has {len(snapshot['images'])} images, WC has fewer",
        })
        comparison["recommendations"].append({
            "priority": "P0",
            "action": "Generate additional product images (back, interior, details, scene)",
            "target_count": 8,
        })

    return comparison
