"""M5.8 staging-safe actor resolution extension point.

AUTHENTICATION_GAP: approval/audit actors are currently declared in the
request body. Server-side RBAC is never bypassed: the resolved actor must
still pass the workspace-scoped role/permission checks (403 otherwise). This
module is the explicit seam where a real SSO/JWT identity layer can replace
the body provider without touching endpoint code.

Providers (``settings.actor_provider``):

- ``body``   (default, staging-safe): actor comes from the request body and is
             validated (non-empty, bounded length, safe charset, no reserved
             system/agent identity).
- ``header`` (SSO/JWT seam): actor comes from ``settings.actor_header_name``
             when the header is present, otherwise falls back to the
             validated body actor so staging keeps working.

Endpoints call ``resolve_actor(request, body.actor)`` instead of trusting the
body directly; swapping providers later requires no endpoint changes.
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


class HeaderActorProvider:
    """SSO/JWT seam: prefer the identity header, fall back to the body."""

    def __init__(self, header_name: str) -> None:
        self.header_name = header_name

    def resolve(self, request: Request, body_actor: str | None) -> str:
        header_value = request.headers.get(self.header_name)
        if header_value:
            return _validate_actor(header_value)
        if body_actor is None:
            raise ActorResolutionError("actor is required")
        return _validate_actor(body_actor)


def get_actor_provider() -> ActorProvider:
    """Return the configured provider (``settings.actor_provider``)."""
    settings = get_settings()
    if settings.actor_provider == "header":
        return HeaderActorProvider(settings.actor_header_name)
    return BodyActorProvider()


def resolve_actor(request: Request, body_actor: str | None = None) -> str:
    """Resolve + validate the acting principal (RBAC still applies)."""
    return get_actor_provider().resolve(request, body_actor)
