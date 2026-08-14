"""Workspace identity mapping service (M5.14, staging only).

The mapping table ``workspace_identity_links`` binds a verified identity
organization (Clerk ``org`` claim) to one Nuotao workspace. The API layer
uses :func:`resolve_workspace_from_identity` as the server-side source of
truth for the request workspace; the ``X-Workspace-Id`` header is only a
routing hint and never overrides the mapping.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import WorkspaceIdentityLink


async def resolve_workspace_from_identity(
    session: AsyncSession,
    *,
    organization_id: str,
) -> UUID | None:
    """Return the enabled workspace bound to ``organization_id`` (or None)."""
    row = (
        await session.execute(
            select(WorkspaceIdentityLink).where(
                WorkspaceIdentityLink.organization_id == organization_id,
                WorkspaceIdentityLink.enabled.is_(True),
            )
        )
    ).scalar_one_or_none()
    return row.workspace_id if row is not None else None


async def link_workspace_identity(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    organization_id: str,
    role: str | None = None,
    mapping_metadata: dict | None = None,
    enabled: bool = True,
    trace_id: str | None = None,
) -> WorkspaceIdentityLink:
    """Create or update one organization -> workspace mapping (upsert)."""
    row = (
        await session.execute(
            select(WorkspaceIdentityLink).where(
                WorkspaceIdentityLink.workspace_id == workspace_id,
                WorkspaceIdentityLink.organization_id == organization_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = WorkspaceIdentityLink(
            workspace_id=workspace_id,
            organization_id=organization_id,
            role=role,
            mapping_metadata=mapping_metadata,
            enabled=enabled,
            trace_id=trace_id,
        )
        session.add(row)
    else:
        row.role = role
        row.mapping_metadata = mapping_metadata
        row.enabled = enabled
    await session.flush()
    await session.refresh(row)
    return row
