"""BUG #20: Object Storage upload service for generated images.

Provides a pluggable OSS (S3-compatible) upload layer. When OSS_ENABLED is
true, images are uploaded to the configured bucket and the public CDN URL is
returned. When disabled, the local file path is used as fallback.

Supports: AWS S3, Alibaba Cloud OSS, Tencent Cloud COS, MinIO, and any
S3-compatible endpoint.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def is_oss_enabled() -> bool:
    """Return True when object storage is configured and enabled."""
    s = get_settings()
    return (
        s.OSS_ENABLED
        and bool(s.OSS_ACCESS_KEY)
        and bool(s.OSS_SECRET_KEY)
        and bool(s.OSS_BUCKET)
    )


def upload_image_to_oss(local_path: str | Path) -> str | None:
    """Upload a local image file to object storage.

    Args:
        local_path: Path to the local image file.

    Returns:
        Public CDN URL on success, None on failure (caller falls back to
        local path / API download endpoint).
    """
    local_path = Path(local_path)
    if not local_path.exists():
        logger.warning("Cannot upload: file not found at %s", local_path)
        return None

    s = get_settings()
    if not is_oss_enabled():
        logger.debug("OSS not enabled; skipping upload for %s", local_path.name)
        return None

    try:
        import boto3
        from botocore.config import Config as BotoConfig
    except ImportError:
        logger.warning("boto3 not installed; skipping OSS upload")
        return None

    try:
        client = boto3.client(
            "s3",
            endpoint_url=s.OSS_ENDPOINT or None,
            aws_access_key_id=s.OSS_ACCESS_KEY,
            aws_secret_access_key=s.OSS_SECRET_KEY,
            config=BotoConfig(
                s3={"addressing_style": "path"},
                retries={"max_attempts": 2},
            ),
        )

        # Build the S3 key with a date-based prefix for bucket organization
        today = local_path.stat().st_mtime
        import datetime as _dt
        date_str = _dt.datetime.fromtimestamp(today, tz=_dt.timezone.utc).strftime("%Y/%m/%d")
        object_key = f"{s.OSS_IMAGE_PREFIX}/{date_str}/{local_path.name}"

        # Detect content type
        suffix = local_path.suffix.lower()
        content_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".svg": "image/svg+xml",
            ".gif": "image/gif",
        }.get(suffix, "application/octet-stream")

        client.put_object(
            Bucket=s.OSS_BUCKET,
            Key=object_key,
            Body=local_path.read_bytes(),
            ContentType=content_type,
            CacheControl="public, max-age=31536000",  # 1 year
        )

        # Build public URL
        if s.OSS_PUBLIC_BASE_URL:
            url = f"{s.OSS_PUBLIC_BASE_URL.rstrip('/')}/{object_key}"
        else:
            # Default: <endpoint>/<bucket>/<key>
            base = s.OSS_ENDPOINT.replace("https://", "").replace("http://", "").rstrip("/")
            url = f"https://{base}/{s.OSS_BUCKET}/{object_key}"

        logger.info("Uploaded image to OSS: %s -> %s", local_path.name, url)
        return url

    except Exception:
        logger.exception("Failed to upload image to OSS: %s", local_path.name)
        return None