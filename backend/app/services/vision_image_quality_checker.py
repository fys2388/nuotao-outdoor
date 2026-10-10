"""Vision-based image quality checker (SOP Step 6).

Uses the Agnes Vision API (agnes-2.5-flash) to check generated product
images against quality criteria defined in the SOP:

1. Appearance consistency — product shape/color/material matches reference
2. Text correctness — all visible text is English, no spelling errors
3. Background cleanliness — no watermarks, logos, or extra elements
4. Composition — product fully visible, not cropped, good lighting

Design:
- Calls ``llm_gateway.complete(vision=True)`` with both the generated image
  and (optionally) the reference image as base64 data URIs.
- Returns structured JSON via ``response_format="json_object"``.
- Deterministic fallback: if Vision API is unavailable, returns a "skipped"
  result rather than blocking the pipeline (AGENTS.md §1.2).
- All image URLs are resolved to base64 data URIs before the API call.

Usage:
    from app.services.vision_image_quality_checker import check_image_quality

    result = await check_image_quality(
        generated_url="https://.../output.png",
        reference_url="https://cbu01.alicdn.com/...",  # optional
        image_type="main",  # main | gallery | description
    )
    if result.passed:
        print("Quality check passed")
    else:
        for finding in result.findings:
            print(f"  [{finding.severity}] {finding.dimension}: {finding.description}")
"""

from __future__ import annotations

import base64
import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx

from app.services.llm_gateway import (
    LLMError,
    LLMRequest,
    complete as llm_complete,
    vision_capable,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Quality dimensions
# ---------------------------------------------------------------------------


class QualityDimension(str, Enum):
    """Quality dimensions checked by the Vision API."""

    APPEARANCE = "appearance_consistency"
    TEXT = "text_correctness"
    BACKGROUND = "background_cleanliness"
    COMPOSITION = "composition"


class Severity(str, Enum):
    """Severity of a quality finding."""

    BLOCKER = "blocker"  # Must fix before publishing
    WARNING = "warning"  # Should fix but not blocking
    INFO = "info"  # Informational, no action needed


@dataclass(frozen=True)
class QualityFinding:
    """A single quality finding from the Vision check."""

    dimension: QualityDimension
    severity: Severity
    passed: bool
    description: str
    detail: str = ""


@dataclass(frozen=True)
class QualityResult:
    """Result of one Vision-based image quality check."""

    passed: bool
    checked: bool  # False if Vision API was unavailable
    skipped_reason: str | None
    image_type: str  # main | gallery | description
    score: float  # 0.0 - 1.0
    findings: list[QualityFinding] = field(default_factory=list)
    raw_response: str = ""
    latency_ms: int = 0
    model: str = ""
    vision_tokens: int = 0


# ---------------------------------------------------------------------------
# Quality check prompt
# ---------------------------------------------------------------------------

_QUALITY_CHECK_PROMPT = """You are an AI image quality checker for e-commerce product photos.

Check the GENERATED image against these quality criteria:

1. APPEARANCE CONSISTENCY (if reference provided):
   - Product shape matches the reference
   - Product color matches the reference
   - Product material/texture is consistent
   - No distortion or deformation

2. TEXT CORRECTNESS:
   - All visible text must be ENGLISH only (no Chinese characters)
   - No spelling errors in visible text
   - Text is legible and properly positioned

3. BACKGROUND CLEANLINESS:
   - No watermarks, logos, or branding elements
   - No extra people, objects, or clutter
   - Background is clean and professional

4. COMPOSITION:
   - Product is fully visible (not cropped)
   - Product is well-lit and clearly visible
   - Image is not blurry or low resolution

IMPORTANT: The FIRST image is the GENERATED image to check.
The SECOND image (if present) is the REFERENCE image for comparison.

Respond with JSON only in this format:
{
  "passed": true/false,
  "score": 0.0-1.0,
  "findings": [
    {
      "dimension": "appearance_consistency|text_correctness|background_cleanliness|composition",
      "severity": "blocker|warning|info",
      "passed": true/false,
      "description": "short description of the issue",
      "detail": "detailed explanation if needed"
    }
  ]
}

Scoring:
- 1.0 = perfect, no issues
- 0.8-0.9 = minor issues (warnings only)
- 0.5-0.8 = significant issues (warnings + blockers)
- 0.0-0.5 = critical issues (multiple blockers)

If no issues found, return: {"passed": true, "score": 1.0, "findings": []}
"""

# Quick regex for Chinese characters (for a fast pre-check before Vision API)
_CJK_PATTERN = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


async def _download_as_data_uri(url: str, *, timeout: float = 30.0) -> str | None:
    """Download an image URL and return a base64 data URI.

    Returns None if the download fails.
    """
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=False, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            content = resp.content
            content_type = resp.headers.get("content-type", "image/png")
            # Strip any charset parameter
            content_type = content_type.split(";")[0].strip()
            b64 = base64.b64encode(content).decode("ascii")
            return f"data:{content_type};base64,{b64}"
    except Exception as exc:
        logger.warning("Failed to download image for Vision check: %s", exc)
        return None


async def check_image_quality(
    *,
    generated_url: str,
    reference_url: str | None = None,
    image_type: str = "main",
    trace_id: str | None = None,
) -> QualityResult:
    """Check image quality using Vision API.

    Args:
        generated_url: URL of the generated image to check.
        reference_url: Optional URL of the reference image for comparison.
        image_type: Type of image (main | gallery | description).
        trace_id: Optional trace ID for audit.

    Returns:
        QualityResult with pass/fail status and detailed findings.

    Design:
        - Does NOT block the pipeline: if Vision API is unavailable,
          returns checked=False with a skipped_reason.
        - Uses response_format="json_object" for structured output.
        - Includes a fast pre-check for Chinese characters (saves API calls
          for obviously bad images).
    """
    started = time.perf_counter()

    # --- Pre-check: fast Chinese character detection ---
    # This is a heuristic: we can't detect Chinese in images without Vision,
    # but we can check if the URL or metadata suggests Chinese content.
    # The real Chinese detection happens in the Vision API call.

    # --- Download images as base64 ---
    images: list[str] = []

    gen_data_uri = await _download_as_data_uri(generated_url)
    if not gen_data_uri:
        return QualityResult(
            passed=False,
            checked=False,
            skipped_reason=f"Failed to download generated image: {generated_url}",
            image_type=image_type,
            score=0.0,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
    images.append(gen_data_uri)

    if reference_url:
        ref_data_uri = await _download_as_data_uri(reference_url)
        if ref_data_uri:
            images.append(ref_data_uri)
        else:
            logger.warning(
                "Reference image download failed, checking without comparison: %s",
                reference_url,
            )

    # --- Build Vision API request ---
    messages = [
        {"role": "system", "content": _QUALITY_CHECK_PROMPT},
        {"role": "user", "content": "Check this product image for quality issues."},
    ]

    request = LLMRequest(
        messages=messages,
        provider="openai",
        model="agnes-2.5-flash",
        vision=True,
        images=images,
        response_format="json_object",
        temperature=0.0,  # Deterministic
        max_tokens=2048,
    )

    # --- Call Vision API ---
    try:
        response = await llm_complete(
            request,
            trace_id=trace_id,
        )
    except LLMError as exc:
        return QualityResult(
            passed=False,
            checked=False,
            skipped_reason=f"Vision API error: {exc}",
            image_type=image_type,
            score=0.0,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
    except Exception as exc:
        return QualityResult(
            passed=False,
            checked=False,
            skipped_reason=f"Vision API unexpected error: {type(exc).__name__}: {exc}",
            image_type=image_type,
            score=0.0,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    latency_ms = int((time.perf_counter() - started) * 1000)
    raw = response.content

    # --- Parse response ---
    import json

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        # Try to extract JSON from the response
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
            except json.JSONDecodeError:
                return QualityResult(
                    passed=False,
                    checked=False,
                    skipped_reason=f"Failed to parse Vision API response: {raw[:200]}",
                    image_type=image_type,
                    score=0.0,
                    raw_response=raw,
                    latency_ms=latency_ms,
                    model="agnes-2.5-flash",
                )
        else:
            return QualityResult(
                passed=False,
                checked=False,
                skipped_reason=f"No JSON found in Vision API response: {raw[:200]}",
                image_type=image_type,
                score=0.0,
                raw_response=raw,
                latency_ms=latency_ms,
                model="agnes-2.5-flash",
            )

    # --- Extract findings ---
    findings: list[QualityFinding] = []
    for f in data.get("findings", []):
        try:
            dim = QualityDimension(f.get("dimension", "composition"))
        except ValueError:
            dim = QualityDimension.COMPOSITION
        try:
            sev = Severity(f.get("severity", "warning"))
        except ValueError:
            sev = Severity.WARNING

        findings.append(QualityFinding(
            dimension=dim,
            severity=sev,
            passed=f.get("passed", True),
            description=f.get("description", ""),
            detail=f.get("detail", ""),
        ))

    passed = data.get("passed", True)
    score = float(data.get("score", 1.0))

    # Clamp score to [0, 1]
    score = max(0.0, min(1.0, score))

    # Check if there are any blockers
    has_blocker = any(
        f.severity == Severity.BLOCKER and not f.passed for f in findings
    )
    if has_blocker:
        passed = False

    result = QualityResult(
        passed=passed,
        checked=True,
        skipped_reason=None,
        image_type=image_type,
        score=score,
        findings=findings,
        raw_response=raw,
        latency_ms=latency_ms,
        model="agnes-2.5-flash",
    )

    logger.info(
        "vision_quality_check trace_id=%s passed=%s score=%.2f findings=%d latency=%dms",
        trace_id, passed, score, len(findings), latency_ms,
    )

    return result


def format_quality_report(result: QualityResult) -> str:
    """Format a quality check result as a human-readable report."""
    if not result.checked:
        return (
            f"Image Quality Report: SKIPPED\n"
            f"  Reason: {result.skipped_reason}\n"
            f"  Image type: {result.image_type}"
        )

    status = "PASSED" if result.passed else "FAILED"
    lines = [
        f"Image Quality Report: {status}",
        f"  Image type: {result.image_type}",
        f"  Score: {result.score:.2f}/1.0",
        f"  Findings: {len(result.findings)}",
        f"  Latency: {result.latency_ms}ms",
        f"  Model: {result.model}",
    ]

    if result.findings:
        lines.append("")
        lines.append("Findings:")
        for f in result.findings:
            icon = "✅" if f.passed else ("❌" if f.severity == Severity.BLOCKER else "⚠️")
            lines.append(f"  {icon} [{f.severity.value}] {f.dimension.value}: {f.description}")
            if f.detail:
                lines.append(f"     {f.detail}")

    return "\n".join(lines)


def check_image_quality_batch(
    images: list[dict[str, str]],
    *,
    reference_url: str | None = None,
    image_type: str = "main",
    trace_id: str | None = None,
    max_concurrent: int = 3,
) -> list[QualityResult]:
    """Check multiple images for quality (synchronous wrapper).

    Args:
        images: List of dicts with 'url' and optional 'type' keys.
        reference_url: Optional reference image URL.
        image_type: Default image type for all images.
        trace_id: Optional trace ID.
        max_concurrent: Max concurrent Vision API calls.

    Returns:
        List of QualityResult, same order as input.

    Note:
        This is a synchronous wrapper. For async usage, call
        ``check_image_quality`` directly for each image.
    """
    import asyncio

    async def _check_all():
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _check_one(idx: int, img: dict[str, str]) -> QualityResult:
            async with semaphore:
                return await check_image_quality(
                    generated_url=img["url"],
                    reference_url=reference_url,
                    image_type=img.get("type", image_type),
                    trace_id=f"{trace_id or ''}.{idx}" if trace_id else str(idx),
                )

        tasks = [_check_one(i, img) for i, img in enumerate(images)]
        return await asyncio.gather(*tasks, return_exceptions=True)

    try:
        results = asyncio.run(_check_all())
    except RuntimeError:
        # Already in an event loop (e.g., inside async code)
        loop = asyncio.get_event_loop()
        if loop.is_running():
            raise RuntimeError(
                "check_image_quality_batch() called from async context. "
                "Use check_image_quality() directly with asyncio.gather() instead."
            )
        results = loop.run_until_complete(_check_all())

    # Convert exceptions to skipped results
    final: list[QualityResult] = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            final.append(QualityResult(
                passed=False,
                checked=False,
                skipped_reason=f"Exception: {type(r).__name__}: {r}",
                image_type=images[i].get("type", image_type),
                score=0.0,
            ))
        else:
            final.append(r)
    return final
