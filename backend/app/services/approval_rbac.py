"""Approval Center RBAC (M5.5): server-side permission checks for human
approval decisions.

Every approve/reject call is checked as:

    actor -> workspace roles -> permission -> approval type/action

Permissions are stored per role in ``agent_approval_roles.permissions``
(e.g. ``tool.approve``, ``calibration.reject``, ``dlq_replay.approve``,
``agent.lifecycle.approve``). The API never trusts the frontend: when RBAC
is enabled and the workspace has configured roles, a missing permission is a
hard 403 even if the UI hides the button.

Compatibility rule: a workspace with NO enabled roles is treated as "RBAC
not configured yet" and stays in the legacy open-operator mode so the
platform does not lock itself out during rollout. Production must configure
at least one role per workspace (documented in ``docs/development.md``).
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.agent_platform import AgentApprovalRole

logger = logging.getLogger(__name__)

# approval_type -> permission prefix (M5.5 permission namespaces).
APPROVAL_PERMISSION_PREFIX: dict[str, str] = {
    "L3_TOOL": "tool",
    "RECOMMENDATION": "recommendation",
    "CALIBRATION": "calibration",
    "DLQ_REPLAY": "dlq_replay",
    "AGENT_LIFECYCLE": "agent.lifecycle",
    "PRODUCT_DECISION": "product.decision",
}

# lifecycle actions need an explicit action discriminator.
LIFECYCLE_ACTIONS: tuple[str, ...] = ("retire", "rollback")


class ApprovalRBACError(Exception):
    """Raised when an actor is not permitted to decide an approval."""


def _normalize_action(action: str) -> str:
    """Map decision verbs to permission verbs (``approved`` -> ``approve``)."""
    return {"approved": "approve", "rejected": "reject"}.get(action, action)


def permission_name(approval_type: str, action: str) -> str:
    """Return the permission string for one approval decision."""
    prefix = APPROVAL_PERMISSION_PREFIX.get(approval_type, approval_type.lower())
    return f"{prefix}.{_normalize_action(action)}"


async def _enabled_roles(session: AsyncSession, *, workspace_id: UUID) -> list[AgentApprovalRole]:
    """Return the enabled roles of a workspace (newest last)."""
    rows = (
        (
            await session.execute(
                select(AgentApprovalRole).where(
                    AgentApprovalRole.workspace_id == workspace_id,
                    AgentApprovalRole.enabled.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def check_approval_permission(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    actor: str,
    approval_type: str,
    action: str,
) -> bool:
    """Return True when the actor may decide this approval type.

    Raises :class:`ApprovalRBACError` when RBAC is enabled and the actor is
    not allowed (the API layer maps this to 403). When the workspace has no
    enabled roles the legacy open-operator mode applies (returns True).
    """
    settings = get_settings()
    if not settings.approval_rbac_enabled:
        return True
    roles = await _enabled_roles(session, workspace_id=workspace_id)
    if not roles:
        logger.info(
            "approval RBAC: workspace %s has no enabled roles - legacy open mode",
            workspace_id,
        )
        return True
    required = permission_name(approval_type, action)
    for role in roles:
        if actor not in (role.actors or []):
            continue
        if required in (role.permissions or []):
            return True
    raise ApprovalRBACError(
        f"actor '{actor}' lacks permission '{required}' for approval type "
        f"'{approval_type}' (workspace {workspace_id})"
    )


# --------------------------------------------------------------------------- #
# Role CRUD (workspace-scoped, audit-light: used by ops and tests)
# --------------------------------------------------------------------------- #


async def create_role(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    role_name: str,
    permissions: list[str],
    actors: list[str],
    enabled: bool = True,
    trace_id: str | None = None,
) -> AgentApprovalRole:
    """Create (or replace) one approval role; conflicts are overwritten."""
    existing = (
        await session.execute(
            select(AgentApprovalRole).where(
                AgentApprovalRole.workspace_id == workspace_id,
                AgentApprovalRole.role_name == role_name,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.permissions = permissions
        existing.actors = actors
        existing.enabled = enabled
        role = existing
    else:
        role = AgentApprovalRole(
            workspace_id=workspace_id,
            role_name=role_name,
            permissions=permissions,
            actors=actors,
            enabled=enabled,
            trace_id=trace_id,
        )
        session.add(role)
    await session.flush()
    await session.refresh(role)
    return role


async def list_roles(session: AsyncSession, *, workspace_id: UUID) -> list[AgentApprovalRole]:
    """List the approval roles of a workspace."""
    rows = (
        (
            await session.execute(
                select(AgentApprovalRole)
                .where(AgentApprovalRole.workspace_id == workspace_id)
                .order_by(AgentApprovalRole.role_name)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def delete_role(session: AsyncSession, *, workspace_id: UUID, role_name: str) -> bool:
    """Delete a role; returns False when it did not exist."""
    row = (
        await session.execute(
            select(AgentApprovalRole).where(
                AgentApprovalRole.workspace_id == workspace_id,
                AgentApprovalRole.role_name == role_name,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.flush()
    return True
