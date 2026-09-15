"""Append-only customer consent ledger and marketing send gate."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.privacy import assert_no_pii
from app.models.customer import CustomerAccount
from app.models.customer_identity import (
    CONSENT_PURPOSES,
    IDENTITY_CHANNELS,
    CustomerConsentEvent,
)
from app.models.edm_subscription import EmailSubscription
from app.models.event import EventLog
from app.services import customer_identity_service


class CustomerConsentError(ValueError):
    """Base class for consent ledger errors."""


class CustomerConsentNotFoundError(CustomerConsentError):
    """Raised when an account or consent event does not exist."""


def _now() -> datetime:
    return datetime.now(UTC)


async def append_consent_event(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    customer_account_id: UUID,
    purpose: str,
    channel: str,
    status: str,
    policy_version: str,
    source: str,
    recorded_by: str,
    idempotency_key: str,
    evidence: dict | None = None,
    occurred_at: datetime | None = None,
    trace_id: str | None = None,
    commit: bool = True,
) -> CustomerConsentEvent:
    """Append one consent event idempotently."""
    if evidence:
        assert_no_pii(evidence, field_name="consent evidence")
    if purpose not in CONSENT_PURPOSES:
        raise CustomerConsentError(f"unsupported consent purpose: {purpose}")
    if channel not in IDENTITY_CHANNELS:
        raise CustomerConsentError(f"unsupported consent channel: {channel}")
    if status not in {"granted", "withdrawn"}:
        raise CustomerConsentError("consent status must be granted or withdrawn")
    account = (
        await session.execute(
            select(CustomerAccount).where(
                CustomerAccount.workspace_id == workspace_id,
                CustomerAccount.id == customer_account_id,
            )
        )
    ).scalar_one_or_none()
    if account is None:
        raise CustomerConsentNotFoundError("customer account not found")
    canonical = await customer_identity_service.resolve_canonical_account(
        session,
        workspace_id=workspace_id,
        account=account,
    )
    existing = (
        await session.execute(
            select(CustomerConsentEvent).where(
                CustomerConsentEvent.workspace_id == workspace_id,
                CustomerConsentEvent.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    event = CustomerConsentEvent(
        workspace_id=workspace_id,
        customer_account_id=canonical.id,
        purpose=purpose,
        channel=channel,
        status=status,
        policy_version=policy_version,
        source=source,
        occurred_at=occurred_at or _now(),
        recorded_by=recorded_by,
        idempotency_key=idempotency_key,
        evidence_json=evidence or {},
        trace_id=trace_id,
    )
    session.add(event)
    await session.flush()
    session.add(
        EventLog(
            workspace_id=workspace_id,
            event_type=f"customer.consent_{status}",
            entity_type="customer_consent_event",
            entity_id=str(event.id),
            payload={
                "customer_account_id": str(canonical.id),
                "purpose": purpose,
                "channel": channel,
                "policy_version": policy_version,
                "source": source,
                "recorded_by": recorded_by,
            },
            trace_id=trace_id,
        )
    )
    if commit:
        await session.commit()
        await session.refresh(event)
    else:
        await session.flush()
    return event


async def current_consent_status(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    customer_account_id: UUID,
    purpose: str,
    channel: str,
) -> tuple[str | None, CustomerConsentEvent | None, EmailSubscription | None]:
    """Return the effective consent, falling back to legacy EDM consent."""
    if purpose not in CONSENT_PURPOSES:
        raise CustomerConsentError(f"unsupported consent purpose: {purpose}")
    if channel not in IDENTITY_CHANNELS:
        raise CustomerConsentError(f"unsupported consent channel: {channel}")
    account = (
        await session.execute(
            select(CustomerAccount).where(
                CustomerAccount.workspace_id == workspace_id,
                CustomerAccount.id == customer_account_id,
            )
        )
    ).scalar_one_or_none()
    if account is None:
        raise CustomerConsentNotFoundError("customer account not found")
    canonical = await customer_identity_service.resolve_canonical_account(
        session,
        workspace_id=workspace_id,
        account=account,
    )
    event = (
        await session.execute(
            select(CustomerConsentEvent)
            .where(
                CustomerConsentEvent.workspace_id == workspace_id,
                CustomerConsentEvent.customer_account_id == canonical.id,
                CustomerConsentEvent.purpose == purpose,
                CustomerConsentEvent.channel == channel,
            )
            .order_by(
                CustomerConsentEvent.occurred_at.desc(),
                CustomerConsentEvent.created_at.desc(),
                CustomerConsentEvent.id.desc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if event is not None:
        return event.status, event, None

    subscription = None
    if purpose == "marketing_email":
        subscription = (
            await session.execute(
                select(EmailSubscription)
                .where(
                    EmailSubscription.workspace_id == workspace_id,
                    EmailSubscription.customer_account_id == canonical.id,
                )
                .order_by(
                    EmailSubscription.updated_at.desc(),
                    EmailSubscription.created_at.desc(),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
    if subscription is None:
        return None, None, None
    granted = (
        subscription.consent_given
        and subscription.subscription_status == "subscribed"
    )
    return ("granted" if granted else "withdrawn"), None, subscription


async def consent_summary(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    customer_account_id: UUID,
) -> list[dict]:
    """Return the latest event for every purpose/channel pair."""
    account = (
        await session.execute(
            select(CustomerAccount).where(
                CustomerAccount.workspace_id == workspace_id,
                CustomerAccount.id == customer_account_id,
            )
        )
    ).scalar_one_or_none()
    if account is None:
        raise CustomerConsentNotFoundError("customer account not found")
    canonical = await customer_identity_service.resolve_canonical_account(
        session,
        workspace_id=workspace_id,
        account=account,
    )
    events = (
        await session.execute(
            select(CustomerConsentEvent)
            .where(
                CustomerConsentEvent.workspace_id == workspace_id,
                CustomerConsentEvent.customer_account_id == canonical.id,
            )
            .order_by(
                CustomerConsentEvent.occurred_at.desc(),
                CustomerConsentEvent.created_at.desc(),
                CustomerConsentEvent.id.desc(),
            )
            .limit(2000)
        )
    ).scalars().all()
    latest: dict[tuple[str, str], CustomerConsentEvent] = {}
    for event in events:
        latest.setdefault((event.purpose, event.channel), event)
    return [
        {
            "purpose": purpose,
            "channel": channel,
            "status": event.status,
            "policy_version": event.policy_version,
            "source": event.source,
            "occurred_at": event.occurred_at,
            "recorded_by": event.recorded_by,
            "event_id": str(event.id),
        }
        for (purpose, channel), event in sorted(latest.items())
    ]


async def list_consent_history(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    customer_account_id: UUID,
    purpose: str | None = None,
    channel: str | None = None,
    limit: int = 500,
) -> list[CustomerConsentEvent]:
    query = select(CustomerConsentEvent).where(
        CustomerConsentEvent.workspace_id == workspace_id,
        CustomerConsentEvent.customer_account_id == customer_account_id,
    )
    if purpose:
        query = query.where(CustomerConsentEvent.purpose == purpose)
    if channel:
        query = query.where(CustomerConsentEvent.channel == channel)
    rows = (
        await session.execute(
            query.order_by(CustomerConsentEvent.occurred_at.desc()).limit(limit)
        )
    ).scalars().all()
    return list(rows)


async def marketing_email_allowed(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    customer_account_id: UUID,
    channel: str = "email",
) -> tuple[bool, str]:
    """Return a deterministic send decision for marketing email."""
    status, _event, subscription = await current_consent_status(
        session,
        workspace_id=workspace_id,
        customer_account_id=customer_account_id,
        purpose="marketing_email",
        channel=channel,
    )
    if status == "withdrawn":
        return False, "withdrawn"
    if status == "granted":
        return True, "granted"
    if subscription is None or not subscription.consent_given:
        return False, "no_consent"
    if subscription.subscription_status == "unsubscribed":
        return False, "unsubscribed"
    return False, "no_consent"
