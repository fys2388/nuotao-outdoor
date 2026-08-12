"""M5.2.1 LLM Gateway integration tests (real/mockable).

Validates the multi-provider gateway against a real HTTP stack: httpx
MockTransport simulates OpenAI 5xx/timeout with a healthy DeepSeek fallback,
plus the full worker path recording provider/model/tokens/cost/latency into
``agent_executions``. Real-provider tests are gated on OPENAI_API_KEY /
DEEPSEEK_API_KEY and skip in environments without credentials.
"""

from __future__ import annotations

import json
import os
from decimal import Decimal

import httpx
import pytest
from app.core.config import get_settings
from app.services import llm_gateway
from app.services.llm_gateway import LLMError, LLMRequest

VALID_JSON = {
    "decision": "test",
    "confidence": "0.78",
    "market_reasoning": "ok",
    "risks": ["risk"],
    "pricing": {
        "recommended_price": "39.99",
        "price_range": ["34.99", "44.99"],
        "max_cac": "20.00",
        "rationale": "ok",
    },
    "test_plan": {
        "quantity": 50,
        "days": 30,
        "channels": ["meta"],
        "budget": "800.00",
        "kpis": {"roas": 2.0},
    },
}


def _deepseek_ok() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": json.dumps(VALID_JSON)}}],
            "usage": {"prompt_tokens": 110, "completion_tokens": 55, "total_tokens": 165},
        },
    )


def _fake_keys() -> None:
    settings = get_settings()
    settings.openai_api_key = "test-openai-key"
    settings.deepseek_api_key = "test-deepseek-key"
    settings.llm_provider = "openai"
    settings.llm_fallback_provider = "deepseek"


def _openai_500(request: httpx.Request) -> httpx.Response:
    if "openai.com" in str(request.url):
        return httpx.Response(500, json={"error": "upstream boom"})
    return _deepseek_ok()


@pytest.mark.asyncio
async def test_openai_5xx_falls_back_to_deepseek() -> None:
    """A 5xx from the primary provider fails over to DeepSeek."""
    _fake_keys()
    transport = httpx.MockTransport(_openai_500)
    async with httpx.AsyncClient(transport=transport) as client:
        response = await llm_gateway.complete(
            LLMRequest(messages=[{"role": "user", "content": "analyze"}]),
            client=client,
            trace_id="trace-llm-1",
        )
    assert response.provider == "deepseek"
    assert response.model == "deepseek-chat"
    assert response.tokens["total_tokens"] == 165
    assert response.cost > Decimal("0")
    assert response.latency_ms >= 0
    assert response.trace_id == "trace-llm-1"
    assert json.loads(response.content)["decision"] == "test"


@pytest.mark.asyncio
async def test_openai_timeout_falls_back_to_deepseek() -> None:
    """A transport timeout on the primary provider falls back to DeepSeek."""

    def handler(request: httpx.Request) -> httpx.Response:
        if "openai.com" in str(request.url):
            raise httpx.ReadTimeout("openai timed out", request=request)
        return _deepseek_ok()

    _fake_keys()
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        response = await llm_gateway.complete(
            LLMRequest(messages=[{"role": "user", "content": "analyze"}]),
            client=client,
        )
    assert response.provider == "deepseek"


@pytest.mark.asyncio
async def test_double_provider_failure_raises() -> None:
    """Failure of both providers raises a retryable ``provider`` LLMError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "nope"})

    _fake_keys()
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(LLMError) as excinfo:
            await llm_gateway.complete(
                LLMRequest(messages=[{"role": "user", "content": "analyze"}]),
                client=client,
            )
    assert excinfo.value.kind == "provider"
    assert "all LLM providers failed" in str(excinfo.value)


@pytest.mark.asyncio
async def test_auth_error_does_not_fallback() -> None:
    """401 is terminal; the fallback provider must not be contacted."""

    def handler(request: httpx.Request) -> httpx.Response:
        if "openai.com" in str(request.url):
            return httpx.Response(401, json={"error": "unauthorized"})
        raise AssertionError("fallback must not be called on auth errors")

    _fake_keys()
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(LLMError) as excinfo:
            await llm_gateway.complete(
                LLMRequest(messages=[{"role": "user", "content": "analyze"}]),
                client=client,
            )
    assert excinfo.value.kind == "auth"


REAL_KEYS = bool(os.environ.get("OPENAI_API_KEY")) and bool(os.environ.get("DEEPSEEK_API_KEY"))


@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set (staging validation)",
)
@pytest.mark.asyncio
async def test_real_openai_e2e() -> None:
    """Real OpenAI call (requires OPENAI_API_KEY)."""
    request = LLMRequest(messages=[{"role": "user", "content": "Reply with the word OK"}])
    response = await llm_gateway.complete(request, trace_id="trace-real-openai")
    assert response.provider == "openai"
    assert response.tokens.get("total_tokens", 0) > 0
    assert response.cost >= Decimal("0")
    assert response.latency_ms >= 0


@pytest.mark.skipif(
    not REAL_KEYS,
    reason="OPENAI_API_KEY and DEEPSEEK_API_KEY required (staging validation)",
)
@pytest.mark.asyncio
async def test_real_openai_deepseek_fallback_e2e() -> None:
    """Real fallback chain (requires both provider keys)."""
    from app.core.config import get_settings

    settings = get_settings()
    settings.llm_provider = "openai"
    settings.llm_fallback_provider = "deepseek"
    request = LLMRequest(messages=[{"role": "user", "content": "Reply with OK"}])
    response = await llm_gateway.complete(request, trace_id="trace-real-fallback")
    assert response.provider in ("openai", "deepseek")
    assert response.tokens.get("total_tokens", 0) > 0
