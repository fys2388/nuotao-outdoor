"""M5.14 JWT verification unit tests (ephemeral RS256 keys, no network).

Covers cryptographic verification, claims validation (iss/aud/exp/nbf/sub),
identity normalization (sub -> actor_id, org -> organization_id, email is
display-only), reserved identities and the fail-closed behavior when the
identity provider is not configured.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import Request
from starlette.datastructures import Headers, QueryParams

from app.core.actor import JwtActorProvider
from app.core.config import get_settings
from app.core.identity import (
    Identity,
    JwtAuthenticationError,
    authenticate_request_sync,
)
from app.services.clerk_jwks import ClerkJwksClient
from tests.identity_helpers import (
    AUDIENCE,
    ISSUER,
    KID,
    jwks_payload,
    make_key_pair,
    mint_token,
    public_key_pem,
)

TRUSTED_HEADER = "CF-Access-Jwt-Assertion"


def _request(headers: dict | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/test",
            "headers": Headers(headers or {}).raw,
            "query_string": b"",
            "client": ("127.0.0.1", 1234),
            "server": ("test", 80),
            "scheme": "http",
            "query_params": QueryParams(""),
            "path_params": {},
        }
    )


def _configure(monkeypatch, *, private_pem: str, **overrides) -> None:
    """Point the identity layer at a preloaded key client (no network)."""
    settings = get_settings()
    monkeypatch.setattr(settings, "actor_provider", "header")
    monkeypatch.setattr(
        settings, "clerk_jwks_url", "https://staging.clerk.accounts.dev/.well-known/jwks.json"
    )
    monkeypatch.setattr(settings, "clerk_issuer", ISSUER)
    monkeypatch.setattr(settings, "clerk_audience", AUDIENCE)
    monkeypatch.setattr(settings, "jwt_clock_skew_seconds", 30)
    for key, value in overrides.items():
        monkeypatch.setattr(settings, key, value)
    client = ClerkJwksClient.from_keys({KID: public_key_pem(private_pem)})
    monkeypatch.setattr(
        "app.core.identity.get_jwks_client",
        lambda **kw: client,
    )


def _auth(request: Request, *, private_pem: str, monkeypatch, **overrides) -> Identity:
    _configure(monkeypatch, private_pem=private_pem, **overrides)
    return authenticate_request_sync(request)


def _token(private_pem: str, **kwargs) -> str:
    return mint_token(private_pem=private_pem, **kwargs)


# --------------------------------------------------------------------------- #
# Happy path + normalization
# --------------------------------------------------------------------------- #


def test_valid_rs256_token_authenticates(monkeypatch) -> None:
    private_pem, _ = make_key_pair()
    token = _token(private_pem)
    identity = _auth(
        _request({TRUSTED_HEADER: token}), private_pem=private_pem, monkeypatch=monkeypatch
    )
    assert identity.actor_id == "user_2abc123"
    assert identity.organization_id == "org_2abc123"
    assert identity.authentication_method == "jwt"


def test_email_is_display_metadata_only(monkeypatch) -> None:
    """actor_id comes from sub - the email claim never becomes the identity."""
    private_pem, _ = make_key_pair()
    token = _token(private_pem, email="ops@nuotao.example", sub="user_abc")
    identity = _auth(
        _request({TRUSTED_HEADER: token}), private_pem=private_pem, monkeypatch=monkeypatch
    )
    assert identity.actor_id == "user_abc"
    assert identity.email == "ops@nuotao.example"


def test_email_absent_is_none(monkeypatch) -> None:
    private_pem, _ = make_key_pair()
    token = _token(private_pem, email=None)
    identity = _auth(
        _request({TRUSTED_HEADER: token}), private_pem=private_pem, monkeypatch=monkeypatch
    )
    assert identity.email is None


def test_jwt_actor_provider_returns_actor_id(monkeypatch) -> None:
    """JwtActorProvider.resolve() feeds existing endpoints (ignores body)."""
    private_pem, _ = make_key_pair()
    token = _token(private_pem)
    _configure(monkeypatch, private_pem=private_pem)
    provider = JwtActorProvider(TRUSTED_HEADER)
    assert provider.resolve(_request({TRUSTED_HEADER: token}), "attacker-body") == "user_2abc123"


# --------------------------------------------------------------------------- #
# Signature / algorithm / structure
# --------------------------------------------------------------------------- #


def test_invalid_signature_rejected(monkeypatch) -> None:
    private_pem, _ = make_key_pair()
    other_pem, _ = make_key_pair()
    token = _token(other_pem)
    with pytest.raises(JwtAuthenticationError):
        _auth(_request({TRUSTED_HEADER: token}), private_pem=private_pem, monkeypatch=monkeypatch)


def test_unsigned_token_rejected(monkeypatch) -> None:
    private_pem, _ = make_key_pair()
    _configure(monkeypatch, private_pem=private_pem)
    token = "eyJhbGciOiJub25lIn0.eyJzdWIiOiJ4In0."
    with pytest.raises(JwtAuthenticationError):
        authenticate_request_sync(_request({TRUSTED_HEADER: token}))


def test_hs256_token_rejected(monkeypatch) -> None:
    private_pem, _ = make_key_pair()
    _configure(monkeypatch, private_pem=private_pem)
    import jwt as pyjwt

    token = pyjwt.encode({"sub": "user_x"}, "s" * 40, algorithm="HS256")
    with pytest.raises(JwtAuthenticationError):
        authenticate_request_sync(_request({TRUSTED_HEADER: token}))


def test_malformed_token_rejected(monkeypatch) -> None:
    private_pem, _ = make_key_pair()
    _configure(monkeypatch, private_pem=private_pem)
    with pytest.raises(JwtAuthenticationError):
        authenticate_request_sync(_request({TRUSTED_HEADER: "not-a-jwt"}))


def test_missing_token_header(monkeypatch) -> None:
    private_pem, _ = make_key_pair()
    _configure(monkeypatch, private_pem=private_pem)
    with pytest.raises(JwtAuthenticationError):
        authenticate_request_sync(_request())


# --------------------------------------------------------------------------- #
# Claims validation
# --------------------------------------------------------------------------- #


def test_expired_token_rejected(monkeypatch) -> None:
    private_pem, _ = make_key_pair()
    token = _token(private_pem, exp_delta=timedelta(minutes=-10))
    with pytest.raises(JwtAuthenticationError):
        _auth(_request({TRUSTED_HEADER: token}), private_pem=private_pem, monkeypatch=monkeypatch)


def test_nbf_future_rejected(monkeypatch) -> None:
    private_pem, _ = make_key_pair()
    token = _token(private_pem, nbf_delta=timedelta(minutes=10))
    with pytest.raises(JwtAuthenticationError):
        _auth(_request({TRUSTED_HEADER: token}), private_pem=private_pem, monkeypatch=monkeypatch)


def test_invalid_issuer_rejected(monkeypatch) -> None:
    private_pem, _ = make_key_pair()
    token = _token(private_pem, issuer="https://evil.example")
    with pytest.raises(JwtAuthenticationError):
        _auth(_request({TRUSTED_HEADER: token}), private_pem=private_pem, monkeypatch=monkeypatch)


def test_invalid_audience_rejected(monkeypatch) -> None:
    private_pem, _ = make_key_pair()
    token = _token(private_pem, audience="other-app")
    with pytest.raises(JwtAuthenticationError):
        _auth(_request({TRUSTED_HEADER: token}), private_pem=private_pem, monkeypatch=monkeypatch)


def test_missing_sub_rejected(monkeypatch) -> None:
    private_pem, _ = make_key_pair()
    token = _token(private_pem, extra={"sub": None})
    with pytest.raises(JwtAuthenticationError):
        _auth(_request({TRUSTED_HEADER: token}), private_pem=private_pem, monkeypatch=monkeypatch)


def test_missing_org_rejected(monkeypatch) -> None:
    private_pem, _ = make_key_pair()
    token = _token(private_pem, extra={"org": None})
    with pytest.raises(JwtAuthenticationError):
        _auth(_request({TRUSTED_HEADER: token}), private_pem=private_pem, monkeypatch=monkeypatch)


def test_clerk_v2_token_without_aud_authenticates(monkeypatch) -> None:
    """Real Clerk v2 JWTs omit ``aud`` and carry org under ``o.id``."""
    private_pem, _ = make_key_pair()
    token = _token(private_pem, clerk_v2=True, org="org_3I2BX9YWjD3F7756kiOsEA5KmYj")
    identity = _auth(
        _request({TRUSTED_HEADER: token}), private_pem=private_pem, monkeypatch=monkeypatch
    )
    assert identity.actor_id == "user_2abc123"
    assert identity.organization_id == "org_3I2BX9YWjD3F7756kiOsEA5KmYj"


def test_clerk_v2_token_with_wrong_aud_rejected(monkeypatch) -> None:
    """When ``aud`` IS present it must match the configured audience."""
    private_pem, _ = make_key_pair()
    token = _token(
        private_pem,
        clerk_v2=True,
        extra={"aud": "some-other-app"},
    )
    with pytest.raises(JwtAuthenticationError):
        _auth(_request({TRUSTED_HEADER: token}), private_pem=private_pem, monkeypatch=monkeypatch)


def test_clerk_v2_missing_org_object_rejected(monkeypatch) -> None:
    """No ``o.id`` and no legacy ``org`` means no workspace mapping - 401."""
    private_pem, _ = make_key_pair()
    token = _token(private_pem, clerk_v2=True, extra={"o": {}})
    with pytest.raises(JwtAuthenticationError):
        _auth(_request({TRUSTED_HEADER: token}), private_pem=private_pem, monkeypatch=monkeypatch)


# --------------------------------------------------------------------------- #
# Reserved identities
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("reserved", ["agent", "system"])
def test_reserved_sub_rejected(monkeypatch, reserved: str) -> None:
    private_pem, _ = make_key_pair()
    token = _token(private_pem, sub=reserved)
    with pytest.raises(JwtAuthenticationError):
        _auth(_request({TRUSTED_HEADER: token}), private_pem=private_pem, monkeypatch=monkeypatch)


# --------------------------------------------------------------------------- #
# Fail closed
# --------------------------------------------------------------------------- #


def test_provider_not_configured_fails_closed(monkeypatch) -> None:
    """Empty Clerk config means 401 for everyone - never a body fallback."""
    private_pem, _ = make_key_pair()
    _configure(monkeypatch, private_pem=private_pem)
    settings = get_settings()
    monkeypatch.setattr(settings, "clerk_jwks_url", "")
    with pytest.raises(JwtAuthenticationError):
        authenticate_request_sync(_request())


def test_unknown_kid_refresh_via_transport(monkeypatch) -> None:
    """Unknown kid is resolved through a real (mock transport) JWKS fetch."""
    import httpx

    private_pem, public_jwk = make_key_pair()
    settings = get_settings()
    monkeypatch.setattr(settings, "actor_provider", "header")
    monkeypatch.setattr(settings, "clerk_jwks_url", "https://staging.clerk.accounts.dev/jwks")
    monkeypatch.setattr(settings, "clerk_issuer", ISSUER)
    monkeypatch.setattr(settings, "clerk_audience", AUDIENCE)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=jwks_payload(public_jwk))

    from app.services import clerk_jwks as jwks_module

    client = jwks_module.ClerkJwksClient(
        jwks_url="https://staging.clerk.accounts.dev/jwks",
        cache_ttl_seconds=300,
        timeout_seconds=2.0,
        transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr("app.core.identity.get_jwks_client", lambda **kw: client)
    token = _token(private_pem)
    identity = authenticate_request_sync(_request({TRUSTED_HEADER: token}))
    assert identity.actor_id == "user_2abc123"
