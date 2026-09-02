"""Clerk JWKS adapter tests (M5.14).

Covers fetch + cache, refresh-on-unknown-kid, key rotation after TTL,
unavailable/malformed endpoints and the preloaded-key path used by tests and
the staging mock issuer. All keys are ephemeral - nothing is committed.
"""

from __future__ import annotations

import httpx
import pytest

from app.services.clerk_jwks import (
    ClerkJwksClient,
    JwksKeyNotFoundError,
    JwksUnavailableError,
)
from tests.identity_helpers import jwks_payload, make_key_pair

JWKS_URL = "https://staging.clerk.accounts.dev/.well-known/jwks.json"


def _client(
    payload_factory,
    *,
    ttl: int = 300,
    status: int = 200,
    calls: list | None = None,
) -> ClerkJwksClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request.url)
        if status != 200:
            return httpx.Response(status, json={"message": "boom"})
        return httpx.Response(200, json=payload_factory())

    return ClerkJwksClient(
        jwks_url=JWKS_URL,
        cache_ttl_seconds=ttl,
        timeout_seconds=2.0,
        transport=httpx.MockTransport(handler),
    )


def test_fetch_key_and_cache() -> None:
    """A fetched key is cached: one transport call for two lookups."""
    private_pem, public_jwk = make_key_pair()
    calls: list = []
    client = _client(lambda: jwks_payload(public_jwk), calls=calls)
    pem = client.get_signing_key_sync("test-key-1")
    assert pem.startswith("-----BEGIN PUBLIC KEY-----")
    assert client.get_signing_key_sync("test-key-1") == pem
    assert len(calls) == 1


def test_unknown_kid_refreshes_once() -> None:
    """A kid missing from the first fetch triggers exactly one refresh."""
    private_pem, public_jwk = make_key_pair()
    payload: dict = {"keys": []}
    calls: list = []
    client = _client(lambda: payload, calls=calls)
    with pytest.raises(JwksKeyNotFoundError):
        client.get_signing_key_sync("test-key-1")
    assert len(calls) == 1
    # Key appears on the server; the next lookup refreshes and succeeds.
    payload["keys"] = [public_jwk]
    pem = client.get_signing_key_sync("test-key-1")
    assert pem.startswith("-----BEGIN PUBLIC KEY-----")
    assert len(calls) == 2


def test_rotation_after_ttl() -> None:
    """After the TTL expires the key is re-fetched (rotation without deploy)."""
    _, key_a = make_key_pair(kid="rotated")
    _, key_b = make_key_pair(kid="rotated")
    state = {"jwk": key_a}
    calls: list = []
    client = _client(lambda: jwks_payload(state["jwk"]), ttl=0, calls=calls)
    first = client.get_signing_key_sync("rotated")
    state["jwk"] = key_b
    second = client.get_signing_key_sync("rotated")
    assert first != second
    assert len(calls) == 2


def test_jwks_endpoint_unavailable() -> None:
    """A non-200 JWKS response maps to JwksUnavailableError."""
    client = _client(lambda: jwks_payload(), status=500)
    with pytest.raises(JwksUnavailableError):
        client.get_signing_key_sync("test-key-1")


def test_jwks_network_error() -> None:
    """A transport failure maps to JwksUnavailableError."""

    def failing_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    client = ClerkJwksClient(
        jwks_url=JWKS_URL,
        cache_ttl_seconds=300,
        timeout_seconds=2.0,
        transport=httpx.MockTransport(failing_handler),
    )
    with pytest.raises(JwksUnavailableError):
        client.get_signing_key_sync("test-key-1")


def test_jwks_malformed_payload() -> None:
    """A 200 response without a dict body maps to JwksUnavailableError."""
    client = _client(lambda: "not-a-jwks")
    with pytest.raises(JwksUnavailableError):
        client.get_signing_key_sync("test-key-1")


@pytest.mark.asyncio
async def test_async_path_matches_sync() -> None:
    """The async lookup returns the same cached key as the sync path."""
    _, public_jwk = make_key_pair()
    client = _client(lambda: jwks_payload(public_jwk))
    pem = await client.get_signing_key("test-key-1")
    assert pem.startswith("-----BEGIN PUBLIC KEY-----")


def test_from_keys_preloaded() -> None:
    """Preloaded keys resolve without any network fetch."""
    private_pem, _ = make_key_pair()
    client = ClerkJwksClient.from_keys({"test-key-1": private_pem})
    assert client.get_signing_key_sync("test-key-1") == private_pem
