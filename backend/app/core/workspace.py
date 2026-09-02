"""Workspace helpers.

M1 uses a single seeded default workspace; the ``X-Workspace-Id`` header is
accepted already so the schema does not need changes when multi-market
workspaces are enabled (roadmap Phase 2+).
"""

from uuid import UUID

from fastapi import Header

DEFAULT_WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000001")


async def get_workspace_id(
    x_workspace_id: str | None = Header(default=None),
) -> UUID:
    """Return the workspace id from the header or the default workspace."""
    if x_workspace_id:
        return UUID(x_workspace_id)
    return DEFAULT_WORKSPACE_ID
