"""M5.10 activation gate unit tests (no network, no real infrastructure).

The gate must never fabricate PASS: without real credentials/URLs every
production item stays BLOCKED/FAILED and the final state is
``ENVIRONMENT_BLOCKED``. These tests only exercise the local decision logic;
real provider connections are covered by the gate itself in staging.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from app.core.config import get_settings
from app.pilot import activation_gate

WORKSPACE = UUID("00000000-0000-0000-0000-000000000001")

_REAL_ENV_NAMES = (
    "DATABASE_URL",
    "REDIS_URL",
    "OPENAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "WOOCOMMERCE_BASE_URL",
    "WOOCOMMERCE_CONSUMER_KEY",
    "WOOCOMMERCE_CONSUMER_SECRET",
)


@pytest.fixture(autouse=True)
def _clean_real_env(monkeypatch) -> None:
    """Keep every test free of real credentials/URLs so no network is hit."""
    for name in _REAL_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    settings = get_settings()
    monkeypatch.setattr(settings, "database_url", activation_gate._DEFAULT_DATABASE_URL)
    monkeypatch.setattr(settings, "redis_url", activation_gate._DEFAULT_REDIS_URL)
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "deepseek_api_key", "")


@pytest.mark.asyncio
async def test_gate_environment_blocked_without_real_env(monkeypatch) -> None:
    """No real env -> every production item BLOCKED, final ENVIRONMENT_BLOCKED."""
    monkeypatch.setattr(get_settings(), "actor_provider", "body")
    result = await activation_gate.run_gate(WORKSPACE)
    assert result["final_state"] == "ENVIRONMENT_BLOCKED"
    assert result["production_env"] == "ENVIRONMENT_BLOCKED"
    assert result["technical_infra"] == "TECHNICAL_INFRA_PASS"
    for gate_id in ("postgres", "redis", "llm", "woocommerce", "operator"):
        assert gate_id in result["blocked"], gate_id
    assert result["checks"]["worker"]["status"] == "PASS"
    assert result["checks"]["scheduler"]["status"] == "PASS"
    assert result["checks"]["pii"]["status"] == "PASS"
    assert result["checks"]["secret_guard"]["status"] == "PASS"
    assert result["checks"]["workspace_isolation"]["status"] == "PASS"


@pytest.mark.asyncio
async def test_gate_explicit_db_tries_connection_and_fails(monkeypatch) -> None:
    """Explicit DATABASE_URL -> real connection attempted; unreachable = FAILED."""
    settings = get_settings()
    monkeypatch.setattr(settings, "database_url", "postgresql+asyncpg://n:n@127.0.0.1:1/n")
    result = await activation_gate.run_gate(WORKSPACE)
    assert result["final_state"] == "ENVIRONMENT_BLOCKED"
    assert result["checks"]["postgres"]["status"] == "FAILED"
    assert "postgres" in result["failed"]
    assert result["checks"]["redis"]["status"] == "BLOCKED"


@pytest.mark.asyncio
async def test_gate_real_llm_requires_key(monkeypatch) -> None:
    """Without any key the LLM gate is BLOCKED, never PASSed."""
    check = await activation_gate._check_real_llm(get_settings())
    assert check["status"] == "BLOCKED"
    assert "BLOCKED_REAL_LLM" in check["detail"]


@pytest.mark.asyncio
async def test_gate_real_llm_provider_call(monkeypatch) -> None:
    """With a key the gate performs a live read-only /models call (faked here)."""

    class _FakeResponse:
        status_code = 200

    class _FakeClient:
        async def __aenter__(self) -> _FakeClient:
            return self

        async def __aexit__(self, *exc: object) -> bool:
            return False

        async def get(self, url: str, headers: dict | None = None) -> _FakeResponse:
            return _FakeResponse()

    monkeypatch.setattr(activation_gate.httpx, "AsyncClient", lambda **kwargs: _FakeClient())
    settings = get_settings()
    monkeypatch.setattr(settings, "openai_api_key", "test-key-not-real")
    check = await activation_gate._check_real_llm(settings)
    assert check["status"] == "PASS"
    assert "openai" in check["detail"]


def test_gate_operator_body_blocked(monkeypatch) -> None:
    """ACTOR_PROVIDER=body is a declared identity gap -> BLOCKED_REAL_OPERATOR."""
    monkeypatch.setattr(get_settings(), "actor_provider", "body")
    check = activation_gate._check_operator(get_settings())
    assert check["status"] == "BLOCKED"
    assert "BLOCKED_REAL_OPERATOR" in check["detail"]


def test_gate_operator_header_passes(monkeypatch) -> None:
    """A server-side actor provider is required for a production identity."""
    monkeypatch.setattr(get_settings(), "actor_provider", "header")
    check = activation_gate._check_operator(get_settings())
    assert check["status"] == "PASS"


@pytest.mark.asyncio
async def test_gate_woocommerce_blocked_without_credentials(monkeypatch) -> None:
    """Missing WooCommerce credentials -> BLOCKED_REAL_PRODUCT."""
    check = await activation_gate._check_real_woocommerce()
    assert check["status"] == "BLOCKED"
    assert "BLOCKED_REAL_PRODUCT" in check["detail"]


@pytest.mark.asyncio
async def test_gate_redis_blocked_without_explicit_url(monkeypatch) -> None:
    """The built-in local-dev Redis URL never counts as production config."""
    check = await activation_gate._check_redis(get_settings())
    assert check["status"] == "BLOCKED"
    assert "BLOCKED_REAL_REDIS" in check["detail"]
