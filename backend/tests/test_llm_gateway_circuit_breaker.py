"""LLM 网关熔断器测试（P2-8）：连续失败开启熔断、熔断期跳过 primary、成功复位。"""

import json

import httpx
import pytest

from app.services import llm_gateway
from app.services.llm_gateway import LLMRequest


class _FakeSettings:
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


def _completion_body(content: str) -> dict:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15},
    }


def _reset_circuit() -> None:
    llm_gateway._circuit_state.clear()


@pytest.fixture(autouse=True)
def _reset():
    _reset_circuit()
    yield
    _reset_circuit()


@pytest.mark.asyncio
async def test_three_failures_open_circuit(monkeypatch) -> None:
    """连续 3 次 provider 错误 -> 熔断开启。"""
    monkeypatch.setattr(llm_gateway, "get_settings", lambda: _FakeSettings())

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="service unavailable")

    transport = httpx.MockTransport(handler)
    request = LLMRequest(messages=[{"role": "user", "content": "hi"}])
    for _ in range(2):
        with pytest.raises(llm_gateway.LLMError):
            async with httpx.AsyncClient(transport=transport) as client:
                await llm_gateway.complete(request, client=client)
    # 第 3 次失败触发熔断（openai 熔断开启，deepseek 仍失败 -> 整体失败）
    with pytest.raises(llm_gateway.LLMError):
        async with httpx.AsyncClient(transport=transport) as client:
            await llm_gateway.complete(request, client=client)

    status = llm_gateway.circuit_status()
    assert status["openai"]["open"] is True
    assert status["openai"]["failures"] >= 3


@pytest.mark.asyncio
async def test_open_circuit_skips_primary(monkeypatch) -> None:
    """熔断开启后 primary 被跳过，请求直接走 fallback 且成功。"""
    monkeypatch.setattr(llm_gateway, "get_settings", lambda: _FakeSettings())
    calls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        if request.url.host == "api.openai.com":
            return httpx.Response(503, text="unavailable")
        return httpx.Response(200, json=_completion_body(json.dumps({"ok": True})))

    transport = httpx.MockTransport(handler)
    request = LLMRequest(messages=[{"role": "user", "content": "hi"}])

    # 手动触发 3 次失败 -> openai 熔断开启
    for _ in range(3):
        llm_gateway._circuit_record_failure("openai")
    assert llm_gateway.circuit_status()["openai"]["open"] is True

    # 熔断期内：openai 不再被请求，直接 deepseek 成功
    calls.clear()
    async with httpx.AsyncClient(transport=transport) as client:
        response = await llm_gateway.complete(request, client=client)
    assert response.provider == "deepseek"
    assert calls == ["api.deepseek.com"]


@pytest.mark.asyncio
async def test_success_resets_failure_count(monkeypatch) -> None:
    """成功调用复位失败计数（未达阈值前成功即清零）。"""
    monkeypatch.setattr(llm_gateway, "get_settings", lambda: _FakeSettings())

    async def fail_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="unavailable")

    async def ok_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_completion_body("ok"))

    request = LLMRequest(messages=[{"role": "user", "content": "hi"}])

    # 2 次失败（openai failures=2，未达阈值 3）
    async with httpx.AsyncClient(transport=httpx.MockTransport(fail_handler)) as client:
        for _ in range(2):
            with pytest.raises(llm_gateway.LLMError):
                await llm_gateway.complete(request, client=client)
    assert llm_gateway.circuit_status()["openai"]["failures"] == 2
    assert llm_gateway.circuit_status()["openai"]["open"] is False

    # 一次成功（openai）复位
    async with httpx.AsyncClient(transport=httpx.MockTransport(ok_handler)) as client:
        await llm_gateway.complete(request, client=client)

    assert llm_gateway.circuit_status()["openai"]["failures"] == 0
    assert llm_gateway.circuit_status()["openai"]["open"] is False


@pytest.mark.asyncio
async def test_auth_error_does_not_open_circuit(monkeypatch) -> None:
    """认证错误直接抛出且不触发熔断。"""
    monkeypatch.setattr(llm_gateway, "get_settings", lambda: _FakeSettings())

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    transport = httpx.MockTransport(handler)
    request = LLMRequest(messages=[{"role": "user", "content": "hi"}])
    for _ in range(5):
        with pytest.raises(llm_gateway.LLMError) as excinfo:
            async with httpx.AsyncClient(transport=transport) as client:
                await llm_gateway.complete(request, client=client)
        assert excinfo.value.kind == "auth"

    assert llm_gateway.circuit_status() == {}
