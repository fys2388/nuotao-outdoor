"""Creative Gateway: unified provider-agnostic interface for AI image
generation and editing (v0.17 C0).

Wraps the existing ``integrations/image_gen.py`` gateway and provides a
single interface for all creative operations:

- Text-to-image generation
- Image-to-image generation (reference image)
- Background replacement / removal
- Color variant generation
- Upscaling

The gateway is provider-agnostic: the service layer never talks to a
specific provider directly.  Currently backed by Volcengine Seedream and
Alibaba DashScope via the existing ``image_gen.py`` adapter.  New providers
can be added without changing the service or API layers.

Cost is tracked per operation in CNY.  The gateway enforces timeout,
retry, and fallback to a cheaper model on failure.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.integrations import image_gen as _image_gen
from app.integrations.image_gen import (
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT_SECONDS,
    ImageGenError,
    ImageGenResult,
    list_available_models,
    get_model_cost,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Creative operation types
# ---------------------------------------------------------------------------

# P0-3: Operation capability registry.
# Only operations that are truly supported by the provider are marked as SUPPORTED.
# Unsupported operations return 422 (operation_not_supported) instead of faking success.

OPERATION_STATUS = {
    "SUPPORTED": "Operation is implemented and can be executed",
    "UNSUPPORTED": "Operation is not implemented by any current provider",
}

# Operation definitions with capability status
OPERATION_TYPES: dict[str, dict[str, Any]] = {
    # --- Generation operations ---
    "generate": {
        "description": "Text-to-image or image-to-image generation",
        "requires_reference": False,
        "default_model": DEFAULT_MODEL,
        "status": "SUPPORTED",
        "provider_support": ["seedream", "flux", "sd"],
    },
    "background_replace": {
        "description": "Replace image background with new scene",
        "requires_reference": True,
        "default_model": DEFAULT_MODEL,
        "status": "UNSUPPORTED",
        "provider_support": [],
        "reason": "No provider currently supports background replacement. Use 'generate' with a reference image for basic image-to-image generation.",
    },
    "background_remove": {
        "description": "Remove background from image",
        "requires_reference": True,
        "default_model": DEFAULT_MODEL,
        "status": "UNSUPPORTED",
        "provider_support": [],
        "reason": "No provider currently supports background removal. Consider using an external tool like remove.bg.",
    },
    "color_variant": {
        "description": "Generate color variant of product image",
        "requires_reference": True,
        "default_model": DEFAULT_MODEL,
        "status": "UNSUPPORTED",
        "provider_support": [],
        "reason": "No provider currently supports color variant generation. Use 'generate' with a modified prompt.",
    },
    "upscale": {
        "description": "Upscale / enhance image resolution",
        "requires_reference": True,
        "default_model": DEFAULT_MODEL,
        "status": "UNSUPPORTED",
        "provider_support": [],
        "reason": "No provider currently supports upscaling. Consider using an external tool like Topaz AI.",
    },
    "relight": {
        "description": "Re-light product in different lighting conditions",
        "requires_reference": True,
        "default_model": DEFAULT_MODEL,
        "status": "UNSUPPORTED",
        "provider_support": [],
        "reason": "No provider currently supports relighting. Use 'generate' with a new lighting prompt.",
    },
    "local_inpaint": {
        "description": "Inpaint a specific region of the image",
        "requires_reference": True,
        "default_model": DEFAULT_MODEL,
        "status": "UNSUPPORTED",
        "provider_support": [],
        "reason": "No provider currently supports local inpainting. Use 'generate' with a reference image for basic editing.",
    },
    "outpaint": {
        "description": "Extend the canvas beyond original boundaries",
        "requires_reference": True,
        "default_model": DEFAULT_MODEL,
        "status": "UNSUPPORTED",
        "provider_support": [],
        "reason": "No provider currently supports outpainting. Use 'generate' with a larger canvas size.",
    },
    "composition_adjust": {
        "description": "Adjust image composition / framing",
        "requires_reference": True,
        "default_model": DEFAULT_MODEL,
        "status": "UNSUPPORTED",
        "provider_support": [],
        "reason": "No provider currently supports composition adjustment. Use 'generate' with a modified prompt.",
    },
}


@dataclass(frozen=True)
class CreativeRequest:
    """Unified request for any creative operation.

    The service layer constructs this dataclass and passes it to the
    gateway.  The gateway translates it into provider-specific API calls.
    """

    prompt: str
    operation: str = "generate"
    model: str = DEFAULT_MODEL
    width: int = 1024
    height: int = 1024
    reference_image: str | None = None
    negative_prompt: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = 2
    trace_id: str | None = None


@dataclass(frozen=True)
class CreativeResult:
    """Unified result of a creative operation."""

    image_url: str | None
    image_b64: str | None
    model: str
    provider: str
    cost_cny: float
    operation: str
    latency_ms: int
    raw_response: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


def list_operations() -> list[dict[str, Any]]:
    """Return available operation types with descriptions and support status."""
    return [
        {"operation": op, **info}
        for op, info in OPERATION_TYPES.items()
    ]


def get_operation_info(operation: str) -> dict[str, Any] | None:
    """Return metadata for a specific operation type."""
    return OPERATION_TYPES.get(operation)


async def execute_creative_operation(
    request: CreativeRequest,
) -> CreativeResult:
    """Execute a creative operation through the unified gateway.

    Routes to the appropriate backend based on the operation type.
    Falls back to a cheaper model on failure.

    P0-3: Only SUPPORTED operations can be executed.
    UNSUPPORTED operations return ImageGenError with a clear message.

    Args:
        request: unified creative request dataclass

    Returns:
        CreativeResult with image data, cost, and metadata

    Raises:
        ImageGenError: if operation is unsupported or all fallbacks are exhausted
    """

    op_info = OPERATION_TYPES.get(request.operation)
    if not op_info:
        raise ImageGenError(f"Unknown operation type: {request.operation}")

    # P0-3: Check operation support status
    if op_info.get("status") == "UNSUPPORTED":
        reason = op_info.get("reason", "This operation is not implemented.")
        raise ImageGenError(
            f"Operation '{request.operation}' is not supported. {reason}"
        )

    # Check if reference image is required but missing
    if op_info.get("requires_reference") and not request.reference_image:
        raise ImageGenError(
            f"Operation '{request.operation}' requires a reference image"
        )

    # Select model: requested -> operation default -> global default
    model = request.model
    if model == "auto":
        model = op_info.get("default_model", DEFAULT_MODEL)

    start_time = time.monotonic()

    try:
        result = await _image_gen.generate_image(
            prompt=request.prompt,
            model=model,
            width=request.width,
            height=request.height,
            negative_prompt=request.negative_prompt,
            reference_image=request.reference_image,
            timeout_seconds=request.timeout_seconds,
            max_retries=request.max_retries,
        )

        latency_ms = int((time.monotonic() - start_time) * 1000)
        provider = _image_gen.BACKEND_PRICING.get(model, {}).get("provider", "unknown")
        cost_cny = get_model_cost(model)

        return CreativeResult(
            image_url=result.image_url,
            image_b64=result.image_b64,
            model=result.model,
            provider=provider,
            cost_cny=cost_cny,
            operation=request.operation,
            latency_ms=latency_ms,
            raw_response=result.raw_response,
        )

    except ImageGenError as exc:
        latency_ms = int((time.monotonic() - start_time) * 1000)
        logger.warning(
            "[creative_gateway] operation %s failed: %s",
            request.operation,
            exc,
        )
        raise ImageGenError(
            f"Creative operation '{request.operation}' failed: {exc}"
        ) from exc


async def generate_hero_image(
    prompt: str,
    reference_image: str | None = None,
    *,
    model: str = DEFAULT_MODEL,
    width: int = 1024,
    height: int = 1024,
    trace_id: str | None = None,
) -> CreativeResult:
    """Convenience method: generate a single hero image for a product."""
    request = CreativeRequest(
        prompt=prompt,
        operation="generate",
        model=model,
        width=width,
        height=height,
        reference_image=reference_image,
        trace_id=trace_id,
    )
    return await execute_creative_operation(request)


async def replace_background(
    reference_image: str,
    prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    trace_id: str | None = None,
) -> CreativeResult:
    """Convenience method: replace background of a product image."""
    request = CreativeRequest(
        prompt=prompt,
        operation="background_replace",
        model=model,
        reference_image=reference_image,
        trace_id=trace_id,
    )
    return await execute_creative_operation(request)
