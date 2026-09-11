"""M5.8/M5.14 actor resolution.

AUTHENTICATION_GAP history: approval/audit actors used to be declared in the
request body. Server-side RBAC is never bypassed - the resolved actor must
still pass the workspace-scoped role/permission checks (403 otherwise).

Providers (``settings.actor_provider``):

- ``body``   (default, staging-safe): actor comes from the request body and is
             validated (non-empty, bounded length, safe charset, no reserved
             system/agent identity).
- ``header`` (M5.14 identity foundation): actor comes ONLY from a
             cryptographically verified RS256 JWT carried in
             ``settings.trusted_identity_header`` (Clerk JWKS). Raw headers
             like ``X-Actor`` and request body actors are never accepted, and
             there is NO fallback to the body actor.

Endpoints call ``resolve_actor(request, body.actor)``; swapping providers
later requires no endpoint changes. The richer identity (actor + organization
+ workspace mapping + permissions) lives in ``app/core/identity.py`` and
``app/api/deps.py`` for new endpoints.
"""

from __future__ import annotations

import re
from typing import Protocol

from fastapi import Request

from app.core.config import get_settings

#: Actors that may never impersonate a human operator.
RESERVED_ACTOR_IDS = frozenset({"agent", "system"})

#: Safe charset: letters, digits and common identity separators.
_SAFE_ACTOR_RE = re.compile(r"^[A-Za-z0-9_.@+-]+$")

MAX_ACTOR_LENGTH = 64


class ActorResolutionError(ValueError):
    """The actor could not be resolved from the configured identity source."""


def _validate_actor(raw: str) -> str:
    actor = raw.strip()
    if not actor:
        raise ActorResolutionError("actor is required")
    if len(actor) > MAX_ACTOR_LENGTH:
        raise ActorResolutionError(f"actor exceeds {MAX_ACTOR_LENGTH} characters")
    if not _SAFE_ACTOR_RE.match(actor):
        raise ActorResolutionError("actor contains unsupported characters")
    if actor in RESERVED_ACTOR_IDS:
        raise ActorResolutionError(
            f"actor '{actor}' is reserved and cannot impersonate a human operator"
        )
    return actor


class ActorProvider(Protocol):
    """Resolve the identity of the acting principal for one request."""

    def resolve(self, request: Request, body_actor: str | None) -> str: ...


class BodyActorProvider:
    """Staging default: actor is declared in the request body."""

    def resolve(self, request: Request, body_actor: str | None) -> str:
        if body_actor is None:
            raise ActorResolutionError("actor is required")
        return _validate_actor(body_actor)


class JwtActorProvider:
    """M5.14: the actor comes from a verified RS256 JWT identity header.

    ``settings.trusted_identity_header`` (default ``CF-Access-Jwt-Assertion``)
    must carry a Clerk-signed JWT. Missing/invalid tokens raise
    :class:`app.core.identity.JwtAuthenticationError` (mapped to 401 by the
    API layer); the request body actor is always ignored.
    """

    def __init__(self, header_name: str) -> None:
        self.header_name = header_name

    def resolve(self, request: Request, body_actor: str | None) -> str:
        # Local import breaks the actor <-> identity import cycle.
        from app.core.identity import authenticate_request_sync

        identity = authenticate_request_sync(request, header_name=self.header_name)
        return identity.actor_id


def get_actor_provider() -> ActorProvider:
    """Return the configured provider (``settings.actor_provider``)."""
    settings = get_settings()
    if settings.actor_provider == "header":
        return JwtActorProvider(settings.trusted_identity_header)
    return BodyActorProvider()


def resolve_actor(request: Request, body_actor: str | None = None) -> str:
    """Resolve + validate the acting principal (RBAC still applies)."""
    return get_actor_provider().resolve(request, body_actor)


def validate_actor(raw: str) -> str:
    """Public alias used by the identity layer to normalize actor ids."""
    return _validate_actor(raw)
