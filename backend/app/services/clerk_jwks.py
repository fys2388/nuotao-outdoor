"""Clerk JWKS adapter (M5.14, staging only).

Fetches the Clerk JSON Web Key Set over HTTPS, caches signing keys with a
configurable TTL and refreshes once when the token's ``kid`` is unknown so
key rotation keeps working without a deployment. Key material is only ever
held in memory; nothing is written to the database, event log or trace.

Failure semantics (all mapped to 401 by the identity layer, never to a body
actor fallback):

- JWKS endpoint unreachable / non-200 / malformed -> ``JwksUnavailableError``
- kid still missing after one refresh                     -> ``JwksKeyNotFoundError``
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import httpx
import jwt
from cryptography.hazmat.primitives import serialization

__all__ = [
    "ClerkJwksClient",
    "JwksError",
    "JwksKeyNotFoundError",
    "JwksUnavailableError",
    "get_jwks_client",
]


class JwksError(Exception):
    """Base class for JWKS failures."""


class JwksUnavailableError(JwksError):
    """The JWKS endpoint could not be reached or returned an invalid payload."""


class JwksKeyNotFoundError(JwksError):
    """No signing key matched the requested ``kid`` after one refresh."""


@dataclass
class ClerkJwksClient:
    """Cached JWKS client with explicit refresh-on-unknown-kid semantics.

    ``transport`` is only used by tests to serve a local JWKS (never in
    production). Keys are stored as PEM strings keyed by ``kid``; every entry
    expires after ``cache_ttl_seconds`` so rotated keys are re-fetched.
    """

    jwks_url: str
    cache_ttl_seconds: int = 300
    timeout_seconds: float = 5.0
    transport: httpx.BaseTransport | None = None
    _keys: dict[str, tuple[str, float]] = field(default_factory=dict)

    def _fresh(self, kid: str) -> str | None:
        cached = self._keys.get(kid)
        if cached is None:
            return None
        pem, fetched_at = cached
        if time.monotonic() - fetched_at >= self.cache_ttl_seconds:
            return None
        return pem

    def _store(self, jwks_payload: dict) -> None:
        now = time.monotonic()
        for jwk in jwks_payload.get("keys") or []:
            kid = jwk.get("kid")
            if not kid or jwk.get("kty") != "RSA":
                continue
            try:
                rsa_key = jwt.PyJWK(jwk).key
                pem = rsa_key.public_bytes(
                    serialization.Encoding.PEM,
                    serialization.PublicFormat.SubjectPublicKeyInfo,
                ).decode("utf-8")
            except (TypeError, ValueError, KeyError, AttributeError):
                continue
            self._keys[kid] = (pem, now)

    async def get_signing_key(self, kid: str) -> str:
        """Return the PEM signing key for ``kid`` (async fetch on miss)."""
        cached = self._fresh(kid)
        if cached is not None:
            return cached
        await self._fetch()
        return self._require(kid)

    def get_signing_key_sync(self, kid: str) -> str:
        """Return the PEM signing key for ``kid`` (sync fetch on miss)."""
        cached = self._fresh(kid)
        if cached is not None:
            return cached
        self._fetch_sync()
        return self._require(kid)

    def _require(self, kid: str) -> str:
        pem, _fetched_at = self._keys.get(kid, (None, 0.0))
        if pem is None:
            raise JwksKeyNotFoundError(f"no signing key for kid={kid}")
        return pem

    async def _fetch(self) -> None:
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds, transport=self.transport
            ) as client:
                response = await client.get(self.jwks_url)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise JwksUnavailableError("JWKS endpoint unavailable") from exc
        if not isinstance(payload, dict):
            raise JwksUnavailableError("JWKS endpoint returned a malformed payload")
        self._store(payload)

    def _fetch_sync(self) -> None:
        try:
            with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
                response = client.get(self.jwks_url)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise JwksUnavailableError("JWKS endpoint unavailable") from exc
        if not isinstance(payload, dict):
            raise JwksUnavailableError("JWKS endpoint returned a malformed payload")
        self._store(payload)

    @classmethod
    def from_keys(cls, keys: dict[str, str], *, cache_ttl_seconds: int = 300) -> ClerkJwksClient:
        """Build a client preloaded with PEM keys (tests / staging mock issuer)."""
        client = cls(jwks_url="", cache_ttl_seconds=cache_ttl_seconds)
        now = time.monotonic()
        client._keys = {kid: (pem, now) for kid, pem in keys.items()}
        return client


def get_jwks_client(
    *,
    jwks_url: str,
    cache_ttl_seconds: int,
    timeout_seconds: float,
    transport: httpx.BaseTransport | None = None,
) -> ClerkJwksClient:
    """Build a JWKS client for one configuration tuple.

    The identity layer calls this with the current settings; tests may pass a
    ``transport`` or preload keys via :meth:`ClerkJwksClient.from_keys`.
    """
    return ClerkJwksClient(
        jwks_url=jwks_url,
        cache_ttl_seconds=cache_ttl_seconds,
        timeout_seconds=timeout_seconds,
        transport=transport,
    )
