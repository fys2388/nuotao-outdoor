"""Tests for the M5.5 Approval SLA (pending -> warning -> expired).

Covers the transition timing, the immutability of expired proposals (never
decided, never auto-approved), per-type SLA rows, the config-level kill
switch, event/alert side effects and workspace isolation. The original
proposal row (actor/action/note/metadata) is never modified by the SLA.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from app.core.config import get_settings
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.agent_operations import AgentAlert, AgentApproval
from app.models.agent_platform import AgentApprovalSla
from app.models.event import EventLog
from app.services import approval_service, approval_sla, task_queue
from sqlalchemy import select

WORKSPACE = DEFAULT_WORKSPACE_ID
OTHER_WORKSPACE = UUID("00000000-0000-0000-0000-000000000099")


def _now() -> datetime:
    return datetime.now(UTC)


async def _seed_approval(
    db_session,
    *,
    workspace_id: UUID = WORKSPACE,
    age_seconds: int = 0,
    approval_type: str = "DLQ_REPLAY",
) -> AgentApproval:
    approval = await approval_service.ensure_approval(
        db_session,
        workspace_id=workspace_id,
        approval_type=approval_type,
        entity_type="agent_task",
        entity_id=f"00000000-0000-0000-0000-00000000aa{age_seconds % 100:02d}",
        trace_id="test",
    )
    if age_seconds:
        approval.created_at = _now() - timedelta(seconds=age_seconds)
    await db_session.flush()
    return approval


async def _sla_settings(db_session, *, workspace_id: UUID, warning: int, expire: int) -> None:
    db_session.add(
        AgentApprovalSla(
            workspace_id=workspace_id,
            approval_type="DLQ_REPLAY",
            warning_after_seconds=warning,
            expire_after_seconds=expire,
            enabled=True,
            trace_id="test",
        )
    )
    await db_session.flush()


@pytest.mark.asyncio
async def test_pending_before_warning_unchanged(db_session) -> None:
    await _seed_approval(db_session, age_seconds=100)
    warned, expired = await approval_sla.apply_approval_slas(
        db_session, workspace_id=WORKSPACE, trace_id="test"
    )
    assert (warned, expired) == (0, 0)
    row = (await db_session.execute(select(AgentApproval))).scalars().first()
    assert row.status == "pending"


@pytest.mark.asyncio
async def test_pending_to_warning(db_session) -> None:
    await _seed_approval(db_session, age_seconds=7200)  # older than warning 3600
    warned, expired = await approval_sla.apply_approval_slas(
        db_session, workspace_id=WORKSPACE, trace_id="test"
    )
    assert warned == 1
    assert expired == 0
    row = (await db_session.execute(select(AgentApproval))).scalars().first()
    assert row.status == "warning"
    assert row.sla_warning_at is not None
    assert row.expires_at is not None


@pytest.mark.asyncio
async def test_warning_to_expired(db_session) -> None:
    await _seed_approval(db_session, age_seconds=100000)  # past expire 86400
    warned, expired = await approval_sla.apply_approval_slas(
        db_session, workspace_id=WORKSPACE, trace_id="test"
    )
    assert expired == 1
    row = (await db_session.execute(select(AgentApproval))).scalars().first()
    assert row.status == "expired"


@pytest.mark.asyncio
async def test_expired_cannot_be_decided(db_session) -> None:
    approval = await _seed_approval(db_session, age_seconds=100000)
    await approval_sla.apply_approval_slas(db_session, workspace_id=WORKSPACE, trace_id="test")
    backend = task_queue.get_queue_backend()
    with pytest.raises(approval_service.ApprovalError, match="expired"):
        await approval_service.approve_approval(
            db_session,
            backend,
            workspace_id=WORKSPACE,
            approval_id=approval.id,
            actor="alice",
            trace_id="test",
        )


@pytest.mark.asyncio
async def test_custom_sla_row_overrides_defaults(db_session) -> None:
    await _sla_settings(db_session, workspace_id=WORKSPACE, warning=60, expire=600)
    await _seed_approval(db_session, age_seconds=120)  # > 60, < 600 -> warning only
    warned, expired = await approval_sla.apply_approval_slas(
        db_session, workspace_id=WORKSPACE, trace_id="test"
    )
    assert (warned, expired) == (1, 0)
    row = (await db_session.execute(select(AgentApproval))).scalars().first()
    assert row.status == "warning"


@pytest.mark.asyncio
async def test_disabled_sla_skips_everything(db_session) -> None:
    await _seed_approval(db_session, age_seconds=100000)
    settings = get_settings()
    original = settings.approval_sla_enabled
    settings.approval_sla_enabled = False
    try:
        warned, expired = await approval_sla.apply_approval_slas(
            db_session, workspace_id=WORKSPACE, trace_id="test"
        )
    finally:
        settings.approval_sla_enabled = original
    assert (warned, expired) == (0, 0)
    row = (await db_session.execute(select(AgentApproval))).scalars().first()
    assert row.status == "pending"


@pytest.mark.asyncio
async def test_expired_writes_event(db_session) -> None:
    await _seed_approval(db_session, age_seconds=100000)
    await approval_sla.apply_approval_slas(
        db_session, workspace_id=WORKSPACE, trace_id="trace-sla-1"
    )
    rows = (
        (
            await db_session.execute(
                select(EventLog).where(
                    EventLog.workspace_id == WORKSPACE,
                    EventLog.event_type == "agent.approval.expired",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(list(rows)) == 1


@pytest.mark.asyncio
async def test_expired_opens_alert(db_session) -> None:
    await _seed_approval(db_session, age_seconds=100000)
    await approval_sla.apply_approval_slas(
        db_session, workspace_id=WORKSPACE, trace_id="trace-sla-2"
    )
    alerts = (
        (
            await db_session.execute(
                select(AgentAlert).where(
                    AgentAlert.workspace_id == WORKSPACE,
                    AgentAlert.alert_type == "approval_expired",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(list(alerts)) == 1
    # Second scan does not open a duplicate (dedup).
    await approval_sla.apply_approval_slas(
        db_session, workspace_id=WORKSPACE, trace_id="trace-sla-3"
    )
    alerts = (
        (
            await db_session.execute(
                select(AgentAlert).where(
                    AgentAlert.workspace_id == WORKSPACE,
                    AgentAlert.alert_type == "approval_expired",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(list(alerts)) == 1


@pytest.mark.asyncio
async def test_workspace_isolation(db_session) -> None:
    await _seed_approval(db_session, workspace_id=WORKSPACE, age_seconds=100000)
    await _seed_approval(
        db_session,
        workspace_id=OTHER_WORKSPACE,
        age_seconds=100,
        approval_type="L3_TOOL",
    )
    warned, expired = await approval_sla.apply_approval_slas(
        db_session, workspace_id=WORKSPACE, trace_id="test"
    )
    assert expired == 1
    other = (
        (
            await db_session.execute(
                select(AgentApproval).where(AgentApproval.workspace_id == OTHER_WORKSPACE)
            )
        )
        .scalars()
        .first()
    )
    assert other.status == "pending"
