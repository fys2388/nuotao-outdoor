"""Pluggable image generation gateway (M6).

Encapsulates all external image generation API calls. Supports multiple
backends via a simple adapter pattern; the service layer never talks to a
specific provider directly.

Backends (Phase 1):
- ``wan2.7-image`` (default): Alibaba Cloud DashScope / Bailian, ¥0.08/img
- ``qwen-image-3.0``: Alibaba Cloud, ¥0.18/img (high quality)
- ``seedream-4.0``: Volcengine Ark, ¥0.22/img
- ``mock``: returns a placeholder for development / tests (no API call)

Costs are recorded in CNY for budget tracking. The gateway enforces timeout,
retry (idempotent generation), and fallback to a cheaper model on failure.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class ImageGenError(Exception):
    """Raised when an image generation backend cannot produce an image."""


@dataclass(frozen=True)
class ImageGenResult:
    """Result of one image generation call (JSON-safe)."""

    image_url: str | None
    image_b64: str | None
    model: str
    cost_cny: float
    raw_response: dict[str, Any]


# Backend pricing table (CNY per image, 1024x1024 baseline).
# Sourced from public pricing pages (2026-09); update when providers change.
# Note: qwen-image models currently have free quota (100/10 images) — cost
# shown is the normal paid rate after free quota is exhausted.
BACKEND_PRICING: dict[str, dict[str, Any]] = {
    # --- Volcengine Seedream (default, free quota available) ---
    "doubao-seedream-4-0-250828": {
        "cost_cny": 0.20,
        "provider": "volcengine",
        "quality": "high",
        "default": True,
        "free_quota": "200 images (new user)",
        "api_style": "openai_images",
    },
    "doubao-seedream-5-0-pro-260628": {
        "cost_cny": 0.30,
        "provider": "volcengine",
        "quality": "very_high",
        "default": False,
        "free_quota": "input image first free",
        "api_style": "openai_images",
    },
    "doubao-seedream-4-5-251128": {
        "cost_cny": 0.25,
        "provider": "volcengine",
        "quality": "very_high",
        "default": False,
        "free_quota": "200 images (new user)",
        "api_style": "openai_images",
    },
    # --- Alibaba qwen-image (free quota, but account may be arreared) ---
    "qwen-image-2.0-pro-2026-06-22": {
        "cost_cny": 0.5,
        "provider": "alibaba",
        "quality": "high",
        "default": False,
        "free_quota": "100 images (expires 2026-09-23)",
        "api_style": "sync_multimodal",
    },
    "qwen-image-3.0": {
        "cost_cny": 0.18,
        "provider": "alibaba",
        "quality": "very_high",
        "default": False,
        "free_quota": "10 images (expires 2026-11-03)",
        "api_style": "sync_multimodal",
    },
    "qwen-image-3.0-pro": {
        "cost_cny": 0.22,
        "provider": "alibaba",
        "quality": "very_high",
        "default": False,
        "free_quota": "10 images (expires 2026-11-03)",
        "api_style": "sync_multimodal",
    },
    "wan2.7-image": {
        "cost_cny": 0.08,
        "provider": "alibaba",
        "quality": "high",
        "default": False,
        "api_style": "async_text2image",
    },
    "seedream-4.0": {
        "cost_cny": 0.22,
        "provider": "volcengine",
        "quality": "high",
        "default": False,
    },
    "mock": {
        "cost_cny": 0.0,
        "provider": "mock",
        "quality": "placeholder",
        "default": False,
    },
}

# Fallback chain: Seedream 4.0 (default, 200 free) -> 4.5 (200 free) -> 5.0 pro -> qwen-image -> mock.
FALLBACK_CHAIN: list[str] = [
    "doubao-seedream-4-0-250828",
    "doubao-seedream-4-5-251128",
    "doubao-seedream-5-0-pro-260628",
    "qwen-image-3.0",
    "mock",
]

DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_MAX_RETRIES = 2


def list_available_models() -> list[dict[str, Any]]:
    """Return the list of supported models with pricing (for API discovery)."""
    return [
        {
            "model": name,
            "cost_cny": info["cost_cny"],
            "provider": info["provider"],
            "quality": info["quality"],
            "is_default": info.get("default", False),
        }
        for name, info in BACKEND_PRICING.items()
    ]


def get_model_cost(model: str) -> float:
    """Return the per-image cost in CNY for a model (0.0 if unknown)."""
    info = BACKEND_PRICING.get(model)
    return info["cost_cny"] if info else 0.0


async def generate_image(
    *,
    prompt: str,
    model: str = "doubao-seedream-4-0-250828",
    width: int = 1024,
    height: int = 1024,
    negative_prompt: str | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> ImageGenResult:
    """Generate an image through the pluggable gateway with fallback.

    Args:
        prompt: text prompt for image generation
        model: requested backend model (falls back on failure)
        width: image width in pixels
        height: image height in pixels
        negative_prompt: optional negative prompt
        timeout_seconds: per-request timeout
        max_retries: retry count per backend before fallback

    Returns:
        ImageGenResult with image URL / base64, actual model used, and cost.

    Raises:
        ImageGenError: if all backends in the fallback chain fail.
    """
    # Build the attempt list: requested model first, then fallback chain
    # (deduped, excluding the requested model if already first).
    attempt_models = [model]
    for fb in FALLBACK_CHAIN:
        if fb not in attempt_models:
            attempt_models.append(fb)

    last_error: str | None = None

    for attempt_model in attempt_models:
        for retry in range(max_retries + 1):
            try:
                logger.info(
                    "[image_gen] generating model=%s attempt=%d/%d width=%d height=%d",
                    attempt_model, retry + 1, max_retries + 1, width, height,
                )
                result = await _dispatch_to_backend(
                    model=attempt_model,
                    prompt=prompt,
                    width=width,
                    height=height,
                    negative_prompt=negative_prompt,
                    timeout_seconds=timeout_seconds,
                )
                logger.info(
                    "[image_gen] success model=%s cost=%.4f CNY",
                    result.model, result.cost_cny,
                )
                return result
            except ImageGenError as exc:
                last_error = str(exc)
                logger.warning(
                    "[image_gen] backend=%s failed (retry %d/%d): %s",
                    attempt_model, retry + 1, max_retries + 1, exc,
                )
                continue
            except Exception as exc:
                last_error = f"unexpected error: {exc}"
                logger.exception("[image_gen] backend=%s unexpected error", attempt_model)
                continue

    raise ImageGenError(f"all backends failed. last error: {last_error}")


async def _dispatch_to_backend(
    *,
    model: str,
    prompt: str,
    width: int,
    height: int,
    negative_prompt: str | None,
    timeout_seconds: float,
) -> ImageGenResult:
    """Dispatch to the appropriate backend adapter."""
    if model == "mock":
        return _generate_mock(prompt=prompt, width=width, height=height)

    provider = BACKEND_PRICING.get(model, {}).get("provider", "unknown")

    if provider == "alibaba":
        return await _generate_alibaba(
            model=model,
            prompt=prompt,
            width=width,
            height=height,
            negative_prompt=negative_prompt,
            timeout_seconds=timeout_seconds,
        )

    if provider == "volcengine":
        return await _generate_volcengine(
            model=model,
            prompt=prompt,
            width=width,
            height=height,
            negative_prompt=negative_prompt,
            timeout_seconds=timeout_seconds,
        )

    raise ImageGenError(f"unsupported model: {model}")


# ---------------------------------------------------------------------------
# Backend adapters
# ---------------------------------------------------------------------------


def _generate_mock(*, prompt: str, width: int, height: int) -> ImageGenResult:
    """Mock backend: returns an SVG placeholder as base64 (no API call)."""
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
        f'<rect width="100%" height="100%" fill="#e8e8e8"/>'
        f'<text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" '
        f'font-family="sans-serif" font-size="14" fill="#999">MOCK: {prompt[:60]}</text>'
        f'</svg>'
    )
    b64 = base64.b64encode(svg.encode("utf-8")).decode("utf-8")
    return ImageGenResult(
        image_url=None,
        image_b64=b64,
        model="mock",
        cost_cny=0.0,
        raw_response={"mock": True, "prompt": prompt},
    )


async def _generate_alibaba(
    *,
    model: str,
    prompt: str,
    width: int,
    height: int,
    negative_prompt: str | None,
    timeout_seconds: float,
) -> ImageGenResult:
    """Alibaba Cloud DashScope / Bailian image generation adapter.

    Supports two API styles:
    - sync_multimodal: qwen-image-2.0-pro / qwen-image-3.0 / qwen-image-3.0-pro
      Uses the synchronous multimodal-generation API (one request, no polling).
    - async_text2image: wan2.7-image / wanx models
      Uses the async text2image API (submit task, then poll for result).

    Requires ``DASHSCOPE_API_KEY`` and ``DASHSCOPE_WORKSPACE_ID`` (via Settings).
    """
    settings = get_settings()
    api_key = settings.dashscope_api_key
    workspace_id = settings.dashscope_workspace_id
    if not api_key:
        raise ImageGenError("DASHSCOPE_API_KEY not configured")

    api_style = BACKEND_PRICING.get(model, {}).get("api_style", "sync_multimodal")

    if api_style == "sync_multimodal":
        return await _generate_alibaba_sync(
            model=model,
            prompt=prompt,
            width=width,
            height=height,
            negative_prompt=negative_prompt,
            timeout_seconds=timeout_seconds,
            api_key=api_key,
            workspace_id=workspace_id,
        )
    else:
        return await _generate_alibaba_async(
            model=model,
            prompt=prompt,
            width=width,
            height=height,
            negative_prompt=negative_prompt,
            timeout_seconds=timeout_seconds,
            api_key=api_key,
        )


async def _generate_alibaba_sync(
    *,
    model: str,
    prompt: str,
    width: int,
    height: int,
    negative_prompt: str | None,
    timeout_seconds: float,
    api_key: str,
    workspace_id: str,
) -> ImageGenResult:
    """Synchronous multimodal-generation API for qwen-image series.

    One POST request returns the image directly (no task polling).
    Uses workspace-specific domain for better performance and stability.
    """
    if not workspace_id:
        raise ImageGenError("DASHSCOPE_WORKSPACE_ID not configured (required for sync API)")

    base_url = (
        f"https://{workspace_id}.cn-beijing.maas.aliyuncs.com"
        f"/api/v1/services/aigc/multimodal-generation/generation"
    )
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # qwen-image-2.0 series supports 512*512 to 2048*2048; clamp to valid range
    clamped_w = max(512, min(width, 2048))
    clamped_h = max(512, min(height, 2048))

    payload: dict[str, Any] = {
        "model": model,
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [{"text": prompt}],
                }
            ]
        },
        "parameters": {
            "size": f"{clamped_w}*{clamped_h}",
            "n": 1,
            "prompt_extend": True,
            "watermark": False,
        },
    }
    if negative_prompt:
        payload["parameters"]["negative_prompt"] = negative_prompt

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            resp = await client.post(base_url, headers=headers, json=payload)
            if resp.status_code != 200:
                raise ImageGenError(
                    f"qwen-image sync failed: {resp.status_code} {resp.text[:500]}"
                )
            data = resp.json()

            # Extract image URL from the multimodal response
            choices = data.get("output", {}).get("choices", [])
            if not choices:
                raise ImageGenError(f"qwen-image no choices in response: {data}")

            content = choices[0].get("message", {}).get("content", [])
            image_url = None
            for item in content:
                if isinstance(item, dict) and item.get("image"):
                    image_url = item["image"]
                    break

            if not image_url:
                raise ImageGenError(f"qwen-image succeeded but no image URL: {data}")

            return ImageGenResult(
                image_url=image_url,
                image_b64=None,
                model=model,
                cost_cny=get_model_cost(model),
                raw_response=data,
            )
    except httpx.TimeoutException:
        raise ImageGenError("qwen-image request timed out") from None
    except httpx.HTTPError as exc:
        raise ImageGenError(f"qwen-image HTTP error: {exc}") from None


async def _generate_alibaba_async(
    *,
    model: str,
    prompt: str,
    width: int,
    height: int,
    negative_prompt: str | None,
    timeout_seconds: float,
    api_key: str,
) -> ImageGenResult:
    """Async text2image API for wanx / wan2.7-image series (task polling)."""
    base_url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable",
    }

    # Map our model names to DashScope model IDs
    dashscope_model = {
        "wan2.7-image": "wanx2.1-t2i-turbo",
    }.get(model, "wanx2.1-t2i-turbo")

    payload: dict[str, Any] = {
        "model": dashscope_model,
        "input": {"prompt": prompt},
        "parameters": {"size": f"{width}*{height}", "n": 1},
    }
    if negative_prompt:
        payload["input"]["negative_prompt"] = negative_prompt

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            # 1. Submit async task
            resp = await client.post(base_url, headers=headers, json=payload)
            if resp.status_code != 200:
                raise ImageGenError(f"DashScope submit failed: {resp.status_code} {resp.text[:500]}")
            task_data = resp.json()
            task_id = task_data.get("output", {}).get("task_id")
            if not task_id:
                raise ImageGenError(f"DashScope no task_id in response: {task_data}")

            # 2. Poll for result (up to ~50s)
            poll_url = f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
            for _ in range(25):
                await _async_sleep(2.0)
                poll_resp = await client.get(poll_url, headers=headers)
                if poll_resp.status_code != 200:
                    continue
                poll_data = poll_resp.json()
                status = poll_data.get("output", {}).get("task_status", "")
                if status == "SUCCEEDED":
                    results = poll_data.get("output", {}).get("results", [])
                    if results and results[0].get("url"):
                        return ImageGenResult(
                            image_url=results[0]["url"],
                            image_b64=None,
                            model=model,
                            cost_cny=get_model_cost(model),
                            raw_response=poll_data,
                        )
                    raise ImageGenError("DashScope succeeded but no image URL")
                if status == "FAILED":
                    raise ImageGenError(f"DashScope task failed: {poll_data.get('output', {}).get('message', '')}")
            raise ImageGenError("DashScope task timed out after polling")
    except httpx.TimeoutException:
        raise ImageGenError("DashScope request timed out") from None
    except httpx.HTTPError as exc:
        raise ImageGenError(f"DashScope HTTP error: {exc}") from None


async def _generate_volcengine(
    *,
    model: str,
    prompt: str,
    width: int,
    height: int,
    negative_prompt: str | None,
    timeout_seconds: float,
) -> ImageGenResult:
    """Volcengine Ark image generation adapter (Seedream models).

    Supports two calling modes:
    1. Direct model name (e.g. doubao-seedream-4.0) — no endpoint setup needed.
    2. Inference endpoint ID (VOLCENGINE_ARK_ENDPOINT) — for custom deployments.

    Requires ``VOLCENGINE_API_KEY`` env var (via Settings).
    """
    settings = get_settings()
    api_key = settings.volcengine_api_key
    endpoint = settings.volcengine_ark_endpoint
    if not api_key:
        raise ImageGenError("VOLCENGINE_API_KEY not configured")

    # Use endpoint ID if configured, otherwise use the model name directly
    model_param = endpoint if endpoint else model

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": model_param,
        "prompt": prompt,
        "size": f"{width}x{height}",
        "n": 1,
    }
    if negative_prompt:
        payload["negative_prompt"] = negative_prompt

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            resp = await client.post(
                "https://ark.cn-beijing.volces.com/api/v3/images/generations",
                headers=headers,
                json=payload,
            )
            if resp.status_code != 200:
                raise ImageGenError(f"Volcengine failed: {resp.status_code} {resp.text[:500]}")
            data = resp.json()
            images = data.get("data", [])
            if images and (images[0].get("url") or images[0].get("b64_json")):
                return ImageGenResult(
                    image_url=images[0].get("url"),
                    image_b64=images[0].get("b64_json"),
                    model=model,
                    cost_cny=get_model_cost(model),
                    raw_response=data,
                )
            raise ImageGenError("Volcengine no image in response")
    except httpx.TimeoutException:
        raise ImageGenError("Volcengine request timed out") from None
    except httpx.HTTPError as exc:
        raise ImageGenError(f"Volcengine HTTP error: {exc}") from None


async def _async_sleep(seconds: float) -> None:
    """Small async sleep helper (avoids importing asyncio at module top)."""
    import asyncio
    await asyncio.sleep(seconds)
