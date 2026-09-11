"""M5.14 identity foundation (STAGING ONLY).

Turns a trusted RS256 JWT (Clerk, injected by Cloudflare Access / a trusted
proxy) into a normalized :class:`Identity`:

    CF-Access-Jwt-Assertion
        -> cryptographic verification (JWKS, iss/aud/exp/nbf/sub)
        -> identity normalization (sub -> actor_id, org -> organization_id)
        -> Identity

Hard boundaries (never relaxed):

- The token must be verified with the configured Clerk JWKS. decode-only /
  base64-only / trusting raw headers is forbidden.
- Any claim or signature failure raises :class:`JwtAuthenticationError`
  (mapped to 401). There is NO fallback to a request body actor.
- ``email`` (when present) is display metadata only - it is never used as
  the actor primary key.
- The JWT payload is never persisted; only ``actor_id`` / ``organization_id``
  / ``email`` are carried in memory and the audit layer writes only
  non-sensitive fields.

Workspace mapping + RBAC + audit live in ``app/api/deps.py`` and
``app/services/workspace_identity.py``; this module stays database-free so it
can be unit-tested without a session.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import jwt
from fastapi import Request

from app.core.actor import _SAFE_ACTOR_RE, validate_actor
from app.core.config import Settings, get_settings
from app.services.clerk_jwks import ClerkJwksClient, JwksError, get_jwks_client

logger = logging.getLogger(__name__)

__all__ = [
    "Identity",
    "JwtAuthenticationError",
    "PermissionDeniedError",
    "WorkspaceAccessError",
    "authenticate_request",
    "authenticate_request_sync",
]

#: Maximum length of a normalized organization id (Clerk ``org_...``).
MAX_ORGANIZATION_LENGTH = 128


class JwtAuthenticationError(Exception):
    """Missing / malformed / unverifiable identity token (mapped to 401)."""


class WorkspaceAccessError(Exception):
    """Authenticated but the identity has no workspace access (mapped to 403)."""


class PermissionDeniedError(Exception):
    """Authenticated but the actor lacks a required permission (mapped to 403)."""


@dataclass(frozen=True)
class Identity:
    """Normalized verified identity for one request.

    ``actor_id`` is the normalized JWT ``sub`` and is the only accepted
    primary identity. ``email`` is display metadata only. ``organization_id``
    is the raw Clerk ``org`` claim used for workspace mapping.
    """

    actor_id: str
    organization_id: str | None = None
    email: str | None = None
    authentication_method: str = "jwt"


def _provider_configured(settings: Settings) -> bool:
    return bool(settings.clerk_jwks_url and settings.clerk_issuer and settings.clerk_audience)


def _build_client(settings: Settings) -> ClerkJwksClient:
    return get_jwks_client(
        jwks_url=settings.clerk_jwks_url,
        cache_ttl_seconds=settings.jwks_cache_ttl_seconds,
        timeout_seconds=settings.jwks_fetch_timeout_seconds,
    )


def _header(token: str) -> dict:
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as exc:
        raise JwtAuthenticationError("malformed identity token") from exc
    if header.get("alg") != "RS256":
        raise JwtAuthenticationError("unsupported token algorithm")
    kid = header.get("kid")
    if not kid:
        raise JwtAuthenticationError("identity token missing kid")
    return header


def _decode(token: str, pem: str, settings: Settings) -> dict:
    try:
        payload = jwt.decode(
            token,
            key=pem,
            algorithms=["RS256"],
            issuer=settings.clerk_issuer,
            leeway=settings.jwt_clock_skew_seconds,
            options={
                "require": ["sub", "exp", "iat"],
                # Clerk v2 session JWTs do not carry an ``aud`` claim (the
                # audience is implicit in the issuer); when ``aud`` IS present
                # it must still match our configured audience exactly.
                "verify_aud": False,
            },
        )
    except jwt.ExpiredSignatureError:
        raise JwtAuthenticationError("identity token expired") from None
    except jwt.ImmatureSignatureError:
        raise JwtAuthenticationError("identity token not yet valid") from None
    except jwt.InvalidTokenError as exc:
        raise JwtAuthenticationError("identity token verification failed") from exc
    audience = payload.get("aud")
    if audience is not None and audience != settings.clerk_audience:
        raise JwtAuthenticationError("identity token audience mismatch")
    return payload


def _normalize(payload: dict) -> Identity:
    """Normalize verified claims into an Identity (never trusts raw values)."""
    sub = payload.get("sub")
    try:
        actor_id = validate_actor(str(sub)) if sub is not None else None
    except ValueError as exc:
        raise JwtAuthenticationError("identity token sub invalid") from exc
    if actor_id is None:
        raise JwtAuthenticationError("identity token missing sub")

    # Clerk v2 keeps the organization under the compact ``o`` claim
    # (``o.id`` / ``o.rol``); v1 used the top-level ``org`` claim. Accept
    # both so the same identity layer works across Clerk versions.
    org_obj = payload.get("o")
    org = (
        org_obj.get("id") if isinstance(org_obj, dict) and org_obj.get("id") else payload.get("org")
    )
    if org is None or not str(org).strip():
        raise JwtAuthenticationError("identity token missing organization claim")
    organization_id = str(org).strip()
    if len(organization_id) > MAX_ORGANIZATION_LENGTH or not _SAFE_ACTOR_RE.match(organization_id):
        raise JwtAuthenticationError("identity token organization invalid")

    email = payload.get("email")
    if not isinstance(email, str):
        email = None
    return Identity(
        actor_id=actor_id,
        organization_id=organization_id,
        email=email,
        authentication_method="jwt",
    )


def _pem_sync(token: str, client: ClerkJwksClient) -> str:
    kid = _header(token)["kid"]
    try:
        return client.get_signing_key_sync(kid)
    except JwksError as exc:
        raise JwtAuthenticationError("signing key unavailable") from exc


async def _pem(token: str, client: ClerkJwksClient) -> str:
    kid = _header(token)["kid"]
    try:
        return await client.get_signing_key(kid)
    except JwksError as exc:
        raise JwtAuthenticationError("signing key unavailable") from exc


def authenticate_request_sync(request: Request, *, header_name: str | None = None) -> Identity:
    """Verify the identity header synchronously (used by ``resolve_actor``)."""
    settings = get_settings()
    if not _provider_configured(settings):
        raise JwtAuthenticationError("identity provider not configured")
    token = request.headers.get(header_name or settings.trusted_identity_header)
    if not token:
        raise JwtAuthenticationError("missing identity token")
    client = _build_client(settings)
    payload = _decode(token, _pem_sync(token, client), settings)
    return _normalize(payload)


async def authenticate_request(request: Request) -> Identity:
    """Verify the identity header (async path used by FastAPI dependencies)."""
    settings = get_settings()
    if not _provider_configured(settings):
        raise JwtAuthenticationError("identity provider not configured")
    token = request.headers.get(settings.trusted_identity_header)
    if not token:
        raise JwtAuthenticationError("missing identity token")
    client = _build_client(settings)
    payload = _decode(token, await _pem(token, client), settings)
    return _normalize(payload)
