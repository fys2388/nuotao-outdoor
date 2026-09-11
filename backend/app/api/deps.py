"""Unified identity dependencies (M5.14, staging only).

New endpoints compose the chain instead of parsing actors themselves:

    request
      -> require_authenticated_actor  (JWT verification, 401)
      -> require_workspace_context    (org -> workspace mapping, 403)
      -> require_permission           (RBAC, 403)
      -> business service

The dependencies are only usable with ``ACTOR_PROVIDER=header``; in the
legacy ``body`` mode the existing endpoints keep using ``resolve_actor``.
Every decision is audited through ``event_log`` (``identity.*`` events) with
only non-sensitive fields - never the JWT, credentials or PII.
"""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.identity import Identity, JwtAuthenticationError, authenticate_request
from app.core.tracing import get_trace_id
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.services import approval_rbac, event_service, workspace_identity

logger = logging.getLogger(__name__)

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def _safe_event(db: AsyncSession, **kwargs) -> None:
    """Record an identity audit event; audit must never block a decision."""
    try:
        await event_service.create_event(db, **kwargs)
    except Exception:
        logger.warning("identity audit event could not be recorded", exc_info=True)


async def require_authenticated_actor(request: Request, db: DbSession) -> Identity:
    """Verify the trusted identity header and return the normalized identity.

    Raises 401 on any authentication failure (no body-actor fallback).
    """
    settings = get_settings()
    if settings.actor_provider != "header":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="identity dependencies require ACTOR_PROVIDER=header",
        )
    try:
        return await authenticate_request(request)
    except JwtAuthenticationError as exc:
        await _safe_event(
            db,
            workspace_id=DEFAULT_WORKSPACE_ID,
            event_type="identity.authentication_failed",
            entity_type="identity",
            entity_id="unknown",
            payload={
                "result": "failed",
                "reason": str(exc),
                "trace_id": get_trace_id(),
            },
            trace_id=get_trace_id(),
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


async def require_workspace_context(
    identity: Annotated[Identity, Depends(require_authenticated_actor)],
    db: DbSession,
    x_workspace_id: Annotated[str | None, Header(alias="X-Workspace-Id")] = None,
) -> UUID:
    """Resolve the workspace from the verified identity mapping.

    ``X-Workspace-Id`` is only a routing hint: a header that disagrees with
    the identity mapping is rejected (403), and a missing mapping is a 403.
    """
    if identity.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="identity has no organization claim",
        )
    mapped = await workspace_identity.resolve_workspace_from_identity(
        db, organization_id=identity.organization_id
    )
    if mapped is None:
        await _safe_event(
            db,
            workspace_id=DEFAULT_WORKSPACE_ID,
            event_type="identity.authorization_denied",
            entity_type="identity",
            entity_id=identity.actor_id,
            payload={
                "result": "denied",
                "reason": "no workspace mapping",
                "actor_id": identity.actor_id,
                "organization_id": identity.organization_id,
                "authentication_method": identity.authentication_method,
                "trace_id": get_trace_id(),
            },
            trace_id=get_trace_id(),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="identity has no workspace mapping",
        )
    if x_workspace_id is not None:
        try:
            requested = UUID(x_workspace_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="invalid X-Workspace-Id",
            ) from exc
        if requested != mapped:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="workspace header mismatch",
            )
    await _safe_event(
        db,
        workspace_id=mapped,
        event_type="identity.authenticated",
        entity_type="identity",
        entity_id=identity.actor_id,
        payload={
            "result": "success",
            "actor_id": identity.actor_id,
            "organization_id": identity.organization_id,
            "authentication_method": identity.authentication_method,
            "trace_id": get_trace_id(),
        },
        trace_id=get_trace_id(),
    )
    await _safe_event(
        db,
        workspace_id=mapped,
        event_type="identity.workspace_resolved",
        entity_type="identity",
        entity_id=identity.actor_id,
        payload={
            "result": "success",
            "actor_id": identity.actor_id,
            "organization_id": identity.organization_id,
            "workspace_id": str(mapped),
            "trace_id": get_trace_id(),
        },
        trace_id=get_trace_id(),
    )
    return mapped


def require_permission(permission: str):
    """Return a dependency enforcing one business permission (403 on deny)."""

    async def _require_permission(
        identity: Annotated[Identity, Depends(require_authenticated_actor)],
        workspace_id: Annotated[UUID, Depends(require_workspace_context)],
        db: DbSession,
    ) -> Identity:
        try:
            await approval_rbac.check_actor_permission(
                db,
                workspace_id=workspace_id,
                actor=identity.actor_id,
                permission=permission,
            )
        except approval_rbac.ApprovalRBACError as exc:
            await _safe_event(
                db,
                workspace_id=workspace_id,
                event_type="identity.authorization_denied",
                entity_type="identity",
                entity_id=identity.actor_id,
                payload={
                    "result": "denied",
                    "reason": "missing permission",
                    "permission": permission,
                    "actor_id": identity.actor_id,
                    "organization_id": identity.organization_id,
                    "workspace_id": str(workspace_id),
                    "authentication_method": identity.authentication_method,
                    "trace_id": get_trace_id(),
                },
                trace_id=get_trace_id(),
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
        return identity

    return _require_permission
