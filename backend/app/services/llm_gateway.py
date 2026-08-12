"""LLM Gateway: the single entry point for all model calls (M2.2).

Business code MUST NOT call model providers directly; it goes through
:func:`complete`, which returns a unified :class:`LLMResponse` containing:

- provider / model (what actually served the request)
- tokens (prompt / completion / total)
- cost (estimated USD, Decimal)
- latency_ms
- trace_id (correlation id for the whole request)

Routing is multi-provider by design (OpenAI primary, DeepSeek fallback) so
the system never depends on a single vendor. Failover happens on network /
5xx / rate-limit errors only; authentication and malformed-response errors
are raised immediately.

The transport is OpenAI-compatible ``/chat/completions`` for both providers;
``httpx`` is used directly so the gateway stays SDK-independent.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import uuid4

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Estimated USD price per 1,000 tokens, keyed by "provider:model".
# Cost estimation only (not a billing source); kept explicit so budget
# controls can be layered on top later.
PRICING: dict[str, tuple[Decimal, Decimal]] = {
    "openai:gpt-4o-mini": (Decimal("0.000150"), Decimal("0.000600")),
    "openai:gpt-4o": (Decimal("0.002500"), Decimal("0.010000")),
    "deepseek:deepseek-chat": (Decimal("0.000270"), Decimal("0.001100")),
    "deepseek:deepseek-reasoner": (Decimal("0.000550"), Decimal("0.002190")),
}
# Fallback pricing for models without an explicit entry (conservative).
DEFAULT_INPUT_PRICE = Decimal("0.000300")
DEFAULT_OUTPUT_PRICE = Decimal("0.001200")

SUPPORTED_PROVIDERS = ("openai", "deepseek")


class LLMError(Exception):
    """Raised when a model call fails.

    ``kind`` classifies the failure: ``auth``, ``invalid_response``,
    ``provider`` (5xx / rate limit), ``network``, or ``timeout``.
    """

    def __init__(self, message: str, *, kind: str) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True)
class LLMRequest:
    """A single model invocation request.

    ``provider``/``model`` default to the configured primary; explicit
    values (including ``api_key``/``base_url``) are used by tests or by
    callers that need a specific route.
    """

    messages: list[dict[str, str]]
    provider: str | None = None
    model: str | None = None
    task_type: str = "default"
    temperature: float = 0.2
    max_tokens: int | None = None
    response_format: str | None = None  # "json_object" when structured output
    api_key: str | None = None
    base_url: str | None = None


@dataclass(frozen=True)
class LLMResponse:
    """Unified result of a model call (provider-agnostic)."""

    provider: str
    model: str
    content: str
    tokens: dict[str, int] = field(default_factory=dict)
    cost: Decimal = Decimal("0")
    latency_ms: int = 0
    trace_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


def estimate_cost(
    provider: str,
    model: str,
    tokens: dict[str, int],
) -> Decimal:
    """Estimate USD cost from a token usage dict (prompt/completion/total)."""
    input_rate, output_rate = PRICING.get(
        f"{provider}:{model}", (DEFAULT_INPUT_PRICE, DEFAULT_OUTPUT_PRICE)
    )
    prompt_tokens = Decimal(tokens.get("prompt_tokens", 0))
    completion_tokens = Decimal(tokens.get("completion_tokens", 0))
    cost = (prompt_tokens * input_rate + completion_tokens * output_rate) / Decimal("1000")
    return cost.quantize(Decimal("0.000001"))


def _provider_config(provider: str) -> tuple[str, str, str]:
    """Resolve (api_key, base_url, default_model) for a provider."""
    settings = get_settings()
    if provider == "openai":
        return (
            settings.openai_api_key,
            settings.openai_base_url,
            settings.openai_default_model,
        )
    if provider == "deepseek":
        return (
            settings.deepseek_api_key,
            settings.deepseek_base_url,
            settings.deepseek_default_model,
        )
    raise LLMError(f"unsupported provider '{provider}'", kind="invalid_response")


def _provider_chain(request: LLMRequest, *, allow_fallback: bool) -> list[tuple[str, dict]]:
    """Ordered provider candidates: explicit/primary first, fallback second."""
    settings = get_settings()
    primary = request.provider or settings.llm_provider
    chain: list[tuple[str, dict]] = []
    seen: set[str] = set()

    def add(provider: str, api_key: str | None, base_url: str | None) -> None:
        if provider in seen:
            return
        seen.add(provider)
        chain.append((provider, {"api_key": api_key, "base_url": base_url}))

    add(primary, request.api_key, request.base_url)
    if allow_fallback:
        fallback = settings.llm_fallback_provider
        if fallback and fallback != primary:
            add(fallback, None, None)
    return chain


async def complete(
    request: LLMRequest,
    *,
    trace_id: str | None = None,
    client: httpx.AsyncClient | None = None,
    allow_fallback: bool = True,
) -> LLMResponse:
    """Execute a model call with provider failover and unified metrics.

    Args:
        request: the model invocation (messages, routing, format).
        trace_id: correlation id; generated when omitted.
        client: optional httpx client (tests inject a MockTransport).
        allow_fallback: when True, retry on the fallback provider for
            network/5xx/rate-limit failures.

    Returns:
        A unified :class:`LLMResponse` with provider/model/tokens/cost/
        latency/trace_id.

    Raises:
        LLMError: auth errors, malformed responses, or failure of every
            provider in the chain.
    """
    trace_id = trace_id or uuid4().hex
    last_error: LLMError | None = None
    for provider, overrides in _provider_chain(request, allow_fallback=allow_fallback):
        api_key = overrides["api_key"]
        base_url = overrides["base_url"]
        try:
            return await _post(
                request,
                provider=provider,
                api_key=api_key,
                base_url=base_url,
                trace_id=trace_id,
                client=client,
            )
        except LLMError as exc:
            # Auth / malformed responses are not worth a failover attempt.
            if exc.kind in ("auth", "invalid_response"):
                raise
            logger.warning("llm provider %s failed (%s): %s", provider, exc.kind, exc)
            last_error = exc
    raise LLMError(
        f"all LLM providers failed: {last_error}" if last_error else "no providers configured",
        kind="provider",
    )


async def _post(
    request: LLMRequest,
    *,
    provider: str,
    api_key: str | None,
    base_url: str | None,
    trace_id: str,
    client: httpx.AsyncClient | None,
) -> LLMResponse:
    """POST one chat completion request and build the unified response."""
    settings = get_settings()
    resolved_key, resolved_base, resolved_model = _provider_config(provider)
    api_key = api_key or resolved_key
    base_url = base_url or resolved_base
    model = request.model or resolved_model

    if not api_key:
        raise LLMError(f"provider '{provider}' has no API key configured", kind="auth")

    payload: dict[str, Any] = {
        "model": model,
        "messages": request.messages,
        "temperature": request.temperature,
        "max_tokens": request.max_tokens or settings.llm_max_tokens,
    }
    if request.response_format == "json_object":
        payload["response_format"] = {"type": "json_object"}

    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-Trace-Id": trace_id,
    }
    started = time.perf_counter()
    try:
        if client is not None:
            response = await client.post(url, headers=headers, json=payload)
        else:
            timeout = httpx.Timeout(settings.llm_timeout_seconds)
            async with httpx.AsyncClient(timeout=timeout) as http_client:
                response = await http_client.post(url, headers=headers, json=payload)
    except httpx.TimeoutException as exc:
        raise LLMError(f"provider '{provider}' timed out", kind="timeout") from exc
    except httpx.HTTPError as exc:
        raise LLMError(f"provider '{provider}' network error: {exc}", kind="network") from exc
    finally:
        latency_ms = int((time.perf_counter() - started) * 1000)

    if response.status_code == 401 or response.status_code == 403:
        raise LLMError(
            f"provider '{provider}' authentication failed ({response.status_code})",
            kind="auth",
        )
    if response.status_code >= 500 or response.status_code == 429:
        raise LLMError(f"provider '{provider}' returned {response.status_code}", kind="provider")
    if response.status_code >= 400:
        raise LLMError(
            f"provider '{provider}' returned {response.status_code}: {response.text[:200]}",
            kind="provider",
        )

    try:
        raw = response.json()
    except ValueError as exc:
        raise LLMError(
            f"provider '{provider}' returned non-JSON body", kind="invalid_response"
        ) from exc

    try:
        content = raw["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(
            f"provider '{provider}' response missing choices[0].message.content",
            kind="invalid_response",
        ) from exc

    usage = raw.get("usage") or {}
    tokens = {
        "prompt_tokens": int(usage.get("prompt_tokens", 0)),
        "completion_tokens": int(usage.get("completion_tokens", 0)),
        "total_tokens": int(usage.get("total_tokens", 0)),
    }
    cost = estimate_cost(provider, model, tokens)
    logger.info(
        "llm provider=%s model=%s tokens=%s cost=%s latency_ms=%s trace=%s",
        provider,
        model,
        tokens,
        cost,
        latency_ms,
        trace_id,
    )
    return LLMResponse(
        provider=provider,
        model=model,
        content=content,
        tokens=tokens,
        cost=cost,
        latency_ms=latency_ms,
        trace_id=trace_id,
        raw=raw,
    )


def parse_json_content(content: str) -> dict[str, Any]:
    """Parse JSON content returned by a model (with code-fence tolerance)."""
    cleaned = content.strip()
    if cleaned.startswith("```"):
        # Strip a ```json ... ``` fence if the model wrapped the payload.
        lines = cleaned.splitlines()
        lines = [line for line in lines if not line.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()
    try:
        parsed = json.loads(cleaned)
    except ValueError as exc:
        raise LLMError("model returned invalid JSON", kind="invalid_response") from exc
    if not isinstance(parsed, dict):
        raise LLMError("model JSON must be an object", kind="invalid_response")
    return parsed
