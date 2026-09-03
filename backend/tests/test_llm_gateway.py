"""Tests for the LLM Gateway (M2.2): unified response, failover, costs."""

import json
from decimal import Decimal

import httpx
import pytest

from app.services import llm_gateway
from app.services.llm_gateway import (
    LLMError,
    LLMRequest,
    LLMResponse,
    estimate_cost,
    parse_json_content,
)


class _FakeSettings:
    """Minimal settings stub for gateway routing tests."""

    def __init__(self, **overrides) -> None:
        defaults = {
            "llm_provider": "openai",
            "llm_fallback_provider": "deepseek",
            "openai_api_key": "test-openai-key",
            "openai_base_url": "https://api.openai.com/v1",
            "openai_default_model": "gpt-4o-mini",
            "deepseek_api_key": "test-deepseek-key",
            "deepseek_base_url": "https://api.deepseek.com/v1",
            "deepseek_default_model": "deepseek-chat",
            "llm_timeout_seconds": 5.0,
            "llm_max_tokens": 1500,
        }
        defaults.update(overrides)
        for key, value in defaults.items():
            setattr(self, key, value)


def _completion_body(content: str, **usage) -> dict:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
        "usage": {
            "prompt_tokens": usage.get("prompt_tokens", 10),
            "completion_tokens": usage.get("completion_tokens", 20),
            "total_tokens": usage.get("total_tokens", 30),
        },
    }


@pytest.mark.asyncio
async def test_complete_returns_unified_response(monkeypatch) -> None:
    """A successful call returns provider/model/tokens/cost/latency/trace_id."""
    monkeypatch.setattr(llm_gateway, "get_settings", lambda: _FakeSettings())
    expected = json.dumps({"decision": "test"})

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-openai-key"
        return httpx.Response(
            200, json=_completion_body(expected, prompt_tokens=12, completion_tokens=8)
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        response = await llm_gateway.complete(
            LLMRequest(
                messages=[{"role": "user", "content": "hi"}],
                response_format="json_object",
            ),
            trace_id="trace-abc",
            client=client,
        )

    assert response.provider == "openai"
    assert response.model == "gpt-4o-mini"
    assert response.content == expected
    assert response.tokens == {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 30}
    assert response.cost > Decimal("0")
    assert response.latency_ms >= 0
    assert response.trace_id == "trace-abc"
    assert response.raw["id"] == "chatcmpl-test"


@pytest.mark.asyncio
async def test_complete_falls_back_to_secondary_provider(monkeypatch) -> None:
    """A 5xx on the primary provider triggers the DeepSeek fallback."""
    monkeypatch.setattr(llm_gateway, "get_settings", lambda: _FakeSettings())
    calls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        if "openai" in request.url.host:
            return httpx.Response(500, json={"error": "boom"})
        return httpx.Response(200, json=_completion_body('{"decision": "hold"}'))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        response = await llm_gateway.complete(
            LLMRequest(messages=[{"role": "user", "content": "hi"}]),
            client=client,
        )

    assert calls == ["api.openai.com", "api.deepseek.com"]
    assert response.provider == "deepseek"
    assert response.model == "deepseek-chat"


@pytest.mark.asyncio
async def test_complete_does_not_fallback_on_auth_error(monkeypatch) -> None:
    """Auth failures are raised immediately (no failover on bad credentials)."""
    monkeypatch.setattr(llm_gateway, "get_settings", lambda: _FakeSettings())

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "unauthorized"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(LLMError) as exc_info:
            await llm_gateway.complete(
                LLMRequest(messages=[{"role": "user", "content": "hi"}]),
                client=client,
            )
    assert exc_info.value.kind == "auth"


@pytest.mark.asyncio
async def test_complete_missing_api_key_raises_auth(monkeypatch) -> None:
    """No configured key on both providers -> auth error."""
    monkeypatch.setattr(
        llm_gateway,
        "get_settings",
        lambda: _FakeSettings(openai_api_key="", deepseek_api_key=""),
    )
    with pytest.raises(LLMError) as exc_info:
        await llm_gateway.complete(
            LLMRequest(messages=[{"role": "user", "content": "hi"}]),
            allow_fallback=False,
        )
    assert exc_info.value.kind == "auth"


def test_estimate_cost_uses_provider_pricing() -> None:
    """Cost is derived from the pricing table in USD."""
    cost = estimate_cost(
        "openai", "gpt-4o-mini", {"prompt_tokens": 1000, "completion_tokens": 1000}
    )
    # 1000 * 0.000150 + 1000 * 0.000600, per 1K -> USD.
    assert cost == Decimal("0.000750")
    unknown = estimate_cost(
        "openai", "unknown-model", {"prompt_tokens": 1000, "completion_tokens": 1000}
    )
    assert unknown == Decimal("0.001500")


def test_parse_json_content_handles_fences() -> None:
    """Fenced and plain JSON both parse; invalid JSON raises LLMError."""
    assert parse_json_content('{"a": 1}') == {"a": 1}
    fenced = '```json\n{"a": 1}\n```'
    assert parse_json_content(fenced) == {"a": 1}
    with pytest.raises(LLMError):
        parse_json_content("not json")
    with pytest.raises(LLMError):
        parse_json_content("[1, 2]")


def test_llm_response_defaults() -> None:
    """Unified response dataclass defaults are provider-agnostic."""
    response = LLMResponse(provider="openai", model="m", content="c")
    assert response.tokens == {}
    assert response.cost == Decimal("0")
    assert response.latency_ms == 0
