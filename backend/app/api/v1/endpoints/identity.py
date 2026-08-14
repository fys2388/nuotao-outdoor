"""Identity foundation endpoints (M5.14, staging only).

``GET /api/v1/identity/me`` walks the full identity chain
(authentication -> workspace mapping) and returns the verified identity. It
is infrastructure for operators/tests, not a business agent.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.deps import require_authenticated_actor, require_workspace_context
from app.core.identity import Identity

router = APIRouter(prefix="/identity", tags=["identity"])


@router.get(
    "/me",
    response_model=dict,
    summary="Resolve the verified identity + mapped workspace",
)
async def whoami(
    identity: Annotated[Identity, Depends(require_authenticated_actor)],
    workspace_id: Annotated[UUID, Depends(require_workspace_context)],
) -> dict:
    """Return the verified actor, organization and mapped workspace.

    Only reachable with a valid RS256 JWT in the trusted identity header
    (``ACTOR_PROVIDER=header``); the request body is never an identity source.
    """
    return {
        "actor_id": identity.actor_id,
        "organization_id": identity.organization_id,
        "email": identity.email,
        "authentication_method": identity.authentication_method,
        "workspace_id": str(workspace_id),
    }
