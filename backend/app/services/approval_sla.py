"""Approval SLA (M5.5): pending -> warning -> expired for the Approval Center.

Per-approval-type thresholds come from ``agent_approval_slas`` (workspace
rows) with config-driven fallbacks:

- past ``warning_after_seconds``  -> status ``warning`` (still decidable)
- past ``expire_after_seconds``   -> status ``expired`` (immutable)

An expired approval NEVER executes its underlying action and is never
auto-approved. The transition is audited (``agent.approval.warned`` /
``agent.approval.expired``) with a ``trace_id`` and raises an
``approval_expired`` alert (deduped like every other alert). The original
proposal row keeps its actor/action/note/metadata untouched.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.agent_operations import AgentApproval
from app.models.agent_platform import AgentApprovalSla
from app.services import alert_service, event_service

logger = logging.getLogger(__name__)

APPROVAL_PENDING = "pending"
APPROVAL_WARNING = "warning"
APPROVAL_EXPIRED = "expired"


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


async def _sla_config(session: AsyncSession, *, workspace_id: UUID) -> dict[str, tuple[int, int]]:
    """Return ``{approval_type: (warning_seconds, expire_seconds)}``.

    Rows in ``agent_approval_slas`` override the config defaults; a disabled
    row is skipped (falls back to the defaults).
    """
    settings = get_settings()
    defaults: dict[str, tuple[int, int]] = {}
    rows = (
        (
            await session.execute(
                select(AgentApprovalSla).where(AgentApprovalSla.workspace_id == workspace_id)
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        if row.enabled:
            defaults[row.approval_type] = (row.warning_after_seconds, row.expire_after_seconds)
    result: dict[str, tuple[int, int]] = {}
    for approval_type in set(defaults) | {
        "L3_TOOL",
        "RECOMMENDATION",
        "CALIBRATION",
        "DLQ_REPLAY",
        "AGENT_LIFECYCLE",
    }:
        warning_s, expire_s = defaults.get(
            approval_type,
            (
                settings.approval_default_warning_seconds,
                settings.approval_default_expire_seconds,
            ),
        )
        result[approval_type] = (warning_s, expire_s)
    return result


async def apply_approval_slas(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    trace_id: str | None = None,
) -> tuple[int, int]:
    """Scan pending/warning approvals and apply their SLA transitions.

    Returns ``(warned_count, expired_count)``. Called by the sweeper and by
    the manual ``POST /approvals/sla-scan`` endpoint. No auto-approval ever
    happens here.
    """
    settings = get_settings()
    if not settings.approval_sla_enabled:
        return 0, 0
    now = _now()
    config = await _sla_config(session, workspace_id=workspace_id)
    rows = (
        (
            await session.execute(
                select(AgentApproval).where(
                    AgentApproval.workspace_id == workspace_id,
                    AgentApproval.status.in_((APPROVAL_PENDING, APPROVAL_WARNING)),
                )
            )
        )
        .scalars()
        .all()
    )
    warned = 0
    expired = 0
    for approval in rows:
        warning_s, expire_s = config.get(approval.approval_type, (3600, 86400))
        created = _aware(approval.created_at) or now
        expires_at = _aware(approval.expires_at)
        if expires_at is None:
            expires_at = created + timedelta(seconds=expire_s)

        # Expired first (only when truly past the deadline).
        if now >= expires_at and approval.status != APPROVAL_EXPIRED:
            approval.status = APPROVAL_EXPIRED
            approval.expires_at = expires_at
            await session.flush()
            await event_service.create_event(
                session,
                workspace_id=workspace_id,
                event_type="agent.approval.expired",
                entity_type="agent_approval",
                entity_id=str(approval.id),
                payload={
                    "approval_type": approval.approval_type,
                    "entity_type": approval.entity_type,
                    "entity_id": approval.entity_id,
                    "expires_at": expires_at.isoformat(),
                },
                trace_id=trace_id,
            )
            await alert_service.open_alert(
                session,
                workspace_id=workspace_id,
                agent_id=approval.agent_id,
                alert_type="approval_expired",
                severity="warning",
                resource=f"approval:{approval.id}",
                message=(
                    f"{approval.approval_type} approval expired; the proposed action "
                    f"was NOT executed"
                ),
                metadata_={
                    "approval_id": str(approval.id),
                    "approval_type": approval.approval_type,
                    "entity_id": approval.entity_id,
                },
                threshold_snapshot={"expire_after_seconds": expire_s},
                trace_id=trace_id,
            )
            expired += 1
            continue

        # Warning (still decidable).
        warning_at = created + timedelta(seconds=warning_s)
        if approval.status == APPROVAL_PENDING and now >= warning_at:
            approval.status = APPROVAL_WARNING
            approval.sla_warning_at = now
            approval.expires_at = expires_at
            await session.flush()
            await event_service.create_event(
                session,
                workspace_id=workspace_id,
                event_type="agent.approval.warned",
                entity_type="agent_approval",
                entity_id=str(approval.id),
                payload={
                    "approval_type": approval.approval_type,
                    "warning_after_seconds": warning_s,
                    "expires_at": expires_at.isoformat(),
                },
                trace_id=trace_id,
            )
            warned += 1
    if warned or expired:
        await session.flush()
    return warned, expired
