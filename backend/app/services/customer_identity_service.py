"""Cross-channel customer identity resolution and reviewed account merges.

Raw identity values are normalized and converted to a workspace-scoped
HMAC-SHA256 value in memory. Only the resulting hash and a short audit
fingerprint are persisted in ``customer_identity_links``.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from collections import defaultdict
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.privacy import assert_no_pii
from app.models.base import Base
from app.models.customer import CustomerAccount
from app.models.customer_identity import (
    IDENTITY_CHANNELS,
    IDENTITY_TYPES,
    CustomerAccountMerge,
    CustomerConsentEvent,
    CustomerIdentityLink,
)
from app.models.event import EventLog

IDENTITY_KEY_DEFAULT = "nuotao-dev-identity-key-change-me"


class CustomerIdentityError(ValueError):
    """Base class for identity governance errors."""


class CustomerIdentityNotFoundError(CustomerIdentityError):
    """Raised when an account, link, or merge request does not exist."""


class CustomerIdentityConflictError(CustomerIdentityError):
    """Raised when one identity resolves to more than one account."""


class CustomerIdentityStateError(CustomerIdentityError):
    """Raised when an identity or merge state transition is invalid."""


def _now() -> datetime:
    return datetime.now(UTC)


def _identity_secret() -> str:
    settings = get_settings()
    secret = settings.customer_identity_hmac_key.strip()
    if secret:
        return secret
    if settings.is_production:
        raise CustomerIdentityError(
            "CUSTOMER_IDENTITY_HMAC_KEY must be configured in production"
        )
    return settings.woocommerce_webhook_secret or IDENTITY_KEY_DEFAULT


def normalize_identity_value(identity_type: str, value: str) -> str:
    """Normalize an identity without storing the original value."""
    if identity_type not in IDENTITY_TYPES:
        raise CustomerIdentityError(f"unsupported identity_type: {identity_type}")
    if not isinstance(value, str) or not value.strip():
        raise CustomerIdentityError("identity value is required")

    text = value.strip()
    if identity_type == "email":
        normalized = text.casefold()
        if "@" not in normalized:
            raise CustomerIdentityError("invalid email identity")
        return normalized
    if identity_type == "phone":
        prefix = "+" if text.startswith("+") else ""
        digits = re.sub(r"\D", "", text)
        if len(digits) < 6:
            raise CustomerIdentityError("invalid phone identity")
        return f"{prefix}{digits}"
    if identity_type == "company_tax_id":
        normalized = re.sub(r"[^A-Za-z0-9]", "", text).upper()
        if not normalized:
            raise CustomerIdentityError("invalid company tax identity")
        return normalized
    if identity_type == "woocommerce_customer_id":
        return text
    return re.sub(r"\s+", " ", text).casefold()


def build_identity_hash(
    *,
    workspace_id: UUID,
    identity_type: str,
    identity_value: str,
) -> tuple[str, str, str]:
    """Return ``(hash, fingerprint, key_version)`` for an identity."""
    normalized = normalize_identity_value(identity_type, identity_value)
    settings = get_settings()
    message = f"{workspace_id}:{identity_type}:{normalized}".encode("utf-8")
    digest = hmac.new(
        _identity_secret().encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()
    fingerprint = hashlib.sha256(f"fingerprint:{digest}".encode("ascii")).hexdigest()[:32]
    return digest, fingerprint, settings.customer_identity_key_version


async def _get_account(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    account_id: UUID,
) -> CustomerAccount | None:
    return (
        await session.execute(
            select(CustomerAccount).where(
                CustomerAccount.workspace_id == workspace_id,
                CustomerAccount.id == account_id,
            )
        )
    ).scalar_one_or_none()


async def resolve_canonical_account(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    account: CustomerAccount,
) -> CustomerAccount:
    """Follow merged-account pointers and reject cycles."""
    current = account
    visited: set[UUID] = set()
    while current.merged_into_account_id is not None:
        if current.id in visited:
            raise CustomerIdentityStateError("merged account cycle detected")
        visited.add(current.id)
        target = await _get_account(
            session,
            workspace_id=workspace_id,
            account_id=current.merged_into_account_id,
        )
        if target is None:
            raise CustomerIdentityStateError("merged account target not found")
        current = target
    return current


async def resolve_identity(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    identity_type: str,
    identity_value: str,
) -> CustomerAccount | None:
    """Resolve one verified identity to its canonical account."""
    identity_hash, _fingerprint, _version = build_identity_hash(
        workspace_id=workspace_id,
        identity_type=identity_type,
        identity_value=identity_value,
    )
    links = (
        await session.execute(
            select(CustomerIdentityLink).where(
                CustomerIdentityLink.workspace_id == workspace_id,
                CustomerIdentityLink.identity_type == identity_type,
                CustomerIdentityLink.identity_hash == identity_hash,
                CustomerIdentityLink.verification_status == "verified",
                CustomerIdentityLink.disabled_at.is_(None),
            )
        )
    ).scalars().all()
    accounts: dict[UUID, CustomerAccount] = {}
    for link in links:
        account = await _get_account(
            session,
            workspace_id=workspace_id,
            account_id=link.customer_account_id,
        )
        if account is None or account.status == "anonymized":
            continue
        canonical = await resolve_canonical_account(
            session,
            workspace_id=workspace_id,
            account=account,
        )
        accounts[canonical.id] = canonical
    if len(accounts) > 1:
        raise CustomerIdentityConflictError(
            "identity resolves to multiple customer accounts; manual review required"
        )
    return next(iter(accounts.values()), None)


async def _upsert_link(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    account: CustomerAccount,
    channel: str,
    external_system: str,
    identity_type: str,
    identity_value: str,
    source: str,
    metadata: dict | None,
    trace_id: str | None,
    allow_reactivate: bool,
) -> tuple[CustomerIdentityLink, UUID | None]:
    if metadata:
        assert_no_pii(metadata, field_name="identity metadata")
    identity_hash, fingerprint, key_version = build_identity_hash(
        workspace_id=workspace_id,
        identity_type=identity_type,
        identity_value=identity_value,
    )
    exact = (
        await session.execute(
            select(CustomerIdentityLink).where(
                CustomerIdentityLink.workspace_id == workspace_id,
                CustomerIdentityLink.customer_account_id == account.id,
                CustomerIdentityLink.channel == channel,
                CustomerIdentityLink.external_system == external_system,
                CustomerIdentityLink.identity_type == identity_type,
                CustomerIdentityLink.identity_hash == identity_hash,
            )
        )
    ).scalar_one_or_none()
    if exact is not None:
        if exact.verification_status in {"revoked", "merged"} and not allow_reactivate:
            raise CustomerIdentityStateError(
                "identity link was revoked; explicit privacy review is required"
            )
        exact.last_seen_at = _now()
        if exact.verification_status == "revoked" and allow_reactivate:
            exact.verification_status = "verified"
            exact.disabled_at = None
            exact.verified_at = _now()
        if metadata:
            exact.metadata_json = {**(exact.metadata_json or {}), **metadata}
        return exact, None

    conflicting = (
        await session.execute(
            select(CustomerIdentityLink).where(
                CustomerIdentityLink.workspace_id == workspace_id,
                CustomerIdentityLink.identity_type == identity_type,
                CustomerIdentityLink.identity_hash == identity_hash,
                CustomerIdentityLink.verification_status == "verified",
                CustomerIdentityLink.disabled_at.is_(None),
                CustomerIdentityLink.customer_account_id != account.id,
            )
        )
    ).scalars().first()
    now = _now()
    link_metadata = dict(metadata or {})
    status = "verified"
    if conflicting is not None:
        status = "conflict"
        link_metadata["conflict_customer_account_id"] = str(
            conflicting.customer_account_id
        )
        link_metadata["conflict_link_id"] = str(conflicting.id)
    link = CustomerIdentityLink(
        workspace_id=workspace_id,
        customer_account_id=account.id,
        channel=channel,
        external_system=external_system,
        identity_type=identity_type,
        identity_hash=identity_hash,
        hash_key_version=key_version,
        fingerprint=fingerprint,
        verification_status=status,
        source=source,
        verified_at=now if status == "verified" else None,
        last_seen_at=now,
        metadata_json=link_metadata,
        trace_id=trace_id,
    )
    session.add(link)
    await session.flush()
    return link, conflicting.customer_account_id if conflicting else None


async def ensure_account_for_identity(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    identity_type: str,
    identity_value: str,
    channel: str,
    external_system: str,
    customer_type: str,
    business_model: str,
    country: str | None = None,
    default_currency: str = "USD",
    display_name: str | None = None,
    source: str = "manual",
    trace_id: str | None = None,
    existing_account_id: UUID | None = None,
) -> CustomerAccount:
    """Resolve an identity to one account, creating or linking it if needed."""
    if channel not in IDENTITY_CHANNELS:
        raise CustomerIdentityError(f"unsupported identity channel: {channel}")
    canonical = await resolve_identity(
        session,
        workspace_id=workspace_id,
        identity_type=identity_type,
        identity_value=identity_value,
    )
    if canonical is not None:
        if existing_account_id is not None and existing_account_id != canonical.id:
            raise CustomerIdentityConflictError(
                "identity belongs to a different account; manual merge required"
            )
        await _upsert_link(
            session,
            workspace_id=workspace_id,
            account=canonical,
            channel=channel,
            external_system=external_system,
            identity_type=identity_type,
            identity_value=identity_value,
            source=source,
            metadata=None,
            trace_id=trace_id,
            allow_reactivate=False,
        )
        return canonical

    if existing_account_id is not None:
        account = await _get_account(
            session,
            workspace_id=workspace_id,
            account_id=existing_account_id,
        )
        if account is None:
            raise CustomerIdentityNotFoundError("existing customer account not found")
        canonical = await resolve_canonical_account(
            session,
            workspace_id=workspace_id,
            account=account,
        )
        if canonical.status == "anonymized":
            raise CustomerIdentityStateError("cannot link an anonymized account")
        link, conflict_account_id = await _upsert_link(
            session,
            workspace_id=workspace_id,
            account=canonical,
            channel=channel,
            external_system=external_system,
            identity_type=identity_type,
            identity_value=identity_value,
            source=source,
            metadata=None,
            trace_id=trace_id,
            allow_reactivate=False,
        )
        if conflict_account_id is not None:
            session.add(
                EventLog(
                    workspace_id=workspace_id,
                    event_type="customer.identity_conflict_detected",
                    entity_type="customer_identity_link",
                    entity_id=str(link.id),
                    payload={
                        "identity_type": identity_type,
                        "account_id": str(canonical.id),
                        "conflicting_account_id": str(conflict_account_id),
                    },
                    trace_id=trace_id,
                )
            )
        return canonical

    identity_hash, fingerprint, key_version = build_identity_hash(
        workspace_id=workspace_id,
        identity_type=identity_type,
        identity_value=identity_value,
    )
    account = CustomerAccount(
        workspace_id=workspace_id,
        customer_number=f"CUS-{identity_hash[:24].upper()}",
        customer_type=customer_type,
        business_model=business_model,
        display_name=display_name,
        status="active",
        country=country,
        default_currency=default_currency,
        trace_id=trace_id,
    )
    try:
        async with session.begin_nested():
            session.add(account)
            await session.flush()
    except IntegrityError:
        account = await resolve_identity(
            session,
            workspace_id=workspace_id,
            identity_type=identity_type,
            identity_value=identity_value,
        )
        if account is None:
            raise
        return account

    link = CustomerIdentityLink(
        workspace_id=workspace_id,
        customer_account_id=account.id,
        channel=channel,
        external_system=external_system,
        identity_type=identity_type,
        identity_hash=identity_hash,
        hash_key_version=key_version,
        fingerprint=fingerprint,
        verification_status="verified",
        source=source,
        verified_at=_now(),
        last_seen_at=_now(),
        metadata_json={},
        trace_id=trace_id,
    )
    session.add(link)
    await session.flush()
    session.add(
        EventLog(
            workspace_id=workspace_id,
            event_type="customer.identity_linked",
            entity_type="customer_identity_link",
            entity_id=str(link.id),
            payload={
                "customer_account_id": str(account.id),
                "channel": channel,
                "external_system": external_system,
                "identity_type": identity_type,
            },
            trace_id=trace_id,
        )
    )
    return account


async def link_identity_to_account(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    account_id: UUID,
    identity_type: str,
    identity_value: str,
    channel: str,
    external_system: str,
    source: str,
    metadata: dict | None = None,
    trace_id: str | None = None,
) -> tuple[CustomerIdentityLink, UUID | None]:
    """Attach an identity to an explicit account and surface conflicts."""
    if channel not in IDENTITY_CHANNELS:
        raise CustomerIdentityError(f"unsupported identity channel: {channel}")
    account = await _get_account(
        session,
        workspace_id=workspace_id,
        account_id=account_id,
    )
    if account is None:
        raise CustomerIdentityNotFoundError("customer account not found")
    canonical = await resolve_canonical_account(
        session,
        workspace_id=workspace_id,
        account=account,
    )
    if canonical.status == "anonymized":
        raise CustomerIdentityStateError("cannot link an anonymized account")
    link, conflict_account_id = await _upsert_link(
        session,
        workspace_id=workspace_id,
        account=canonical,
        channel=channel,
        external_system=external_system,
        identity_type=identity_type,
        identity_value=identity_value,
        source=source,
        metadata=metadata,
        trace_id=trace_id,
        allow_reactivate=True,
    )
    session.add(
        EventLog(
            workspace_id=workspace_id,
            event_type=(
                "customer.identity_conflict_detected"
                if conflict_account_id is not None
                else "customer.identity_linked"
            ),
            entity_type="customer_identity_link",
            entity_id=str(link.id),
            payload={
                "customer_account_id": str(canonical.id),
                "channel": channel,
                "external_system": external_system,
                "identity_type": identity_type,
                "conflicting_account_id": (
                    str(conflict_account_id) if conflict_account_id else None
                ),
            },
            trace_id=trace_id,
        )
    )
    await session.flush()
    return link, conflict_account_id


async def list_accounts(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    status: str | None = None,
    business_model: str | None = None,
    limit: int = 200,
) -> list[CustomerAccount]:
    query = select(CustomerAccount).where(CustomerAccount.workspace_id == workspace_id)
    if status:
        query = query.where(CustomerAccount.status == status)
    if business_model:
        query = query.where(CustomerAccount.business_model == business_model)
    rows = (
        await session.execute(
            query.order_by(CustomerAccount.created_at.desc()).limit(limit)
        )
    ).scalars().all()
    return list(rows)


async def list_identity_links(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    status: str | None = None,
    account_id: UUID | None = None,
    limit: int = 500,
) -> list[CustomerIdentityLink]:
    query = select(CustomerIdentityLink).where(
        CustomerIdentityLink.workspace_id == workspace_id
    )
    if status:
        query = query.where(CustomerIdentityLink.verification_status == status)
    if account_id:
        query = query.where(CustomerIdentityLink.customer_account_id == account_id)
    rows = (
        await session.execute(
            query.order_by(CustomerIdentityLink.created_at.desc()).limit(limit)
        )
    ).scalars().all()
    return list(rows)


async def create_merge_request(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    source_account_id: UUID,
    target_account_id: UUID,
    requested_by: str,
    reason: str,
    trace_id: str | None = None,
) -> CustomerAccountMerge:
    if source_account_id == target_account_id:
        raise CustomerIdentityStateError("source and target accounts must differ")
    source = await _get_account(
        session,
        workspace_id=workspace_id,
        account_id=source_account_id,
    )
    target = await _get_account(
        session,
        workspace_id=workspace_id,
        account_id=target_account_id,
    )
    if source is None:
        raise CustomerIdentityNotFoundError("source customer account not found")
    if target is None:
        raise CustomerIdentityNotFoundError("target customer account not found")
    if source.status in {"merged", "anonymized"}:
        raise CustomerIdentityStateError("source account cannot be merged")
    if target.status == "anonymized":
        raise CustomerIdentityStateError("target account cannot be anonymized")
    source = await resolve_canonical_account(
        session,
        workspace_id=workspace_id,
        account=source,
    )
    target = await resolve_canonical_account(
        session,
        workspace_id=workspace_id,
        account=target,
    )
    if source.id == target.id:
        raise CustomerIdentityStateError("accounts already resolve to the same canonical account")

    source_links = await list_identity_links(
        session,
        workspace_id=workspace_id,
        account_id=source.id,
        limit=1000,
    )
    target_links = await list_identity_links(
        session,
        workspace_id=workspace_id,
        account_id=target.id,
        limit=1000,
    )
    target_by_key = {
        (link.identity_type, link.identity_hash): link
        for link in target_links
        if link.verification_status in {"verified", "conflict"}
        and link.disabled_at is None
    }
    evidence = next(
        (
            (link, target_by_key[(link.identity_type, link.identity_hash)])
            for link in source_links
            if link.verification_status in {"verified", "conflict"}
            and link.disabled_at is None
            and (link.identity_type, link.identity_hash) in target_by_key
            and (
                link.verification_status == "verified"
                or target_by_key[
                    (link.identity_type, link.identity_hash)
                ].verification_status
                == "verified"
            )
        ),
        None,
    )
    if evidence is None:
        raise CustomerIdentityStateError(
            "merge requires at least one deterministic identity match on both accounts"
        )
    source_link, target_link = evidence
    existing = (
        await session.execute(
            select(CustomerAccountMerge).where(
                CustomerAccountMerge.workspace_id == workspace_id,
                CustomerAccountMerge.source_account_id == source.id,
                CustomerAccountMerge.target_account_id == target.id,
                CustomerAccountMerge.status.in_(["pending", "approved"]),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise CustomerIdentityConflictError("an active merge request already exists")

    merge = CustomerAccountMerge(
        workspace_id=workspace_id,
        source_account_id=source.id,
        target_account_id=target.id,
        status="pending",
        match_type=source_link.identity_type,
        match_hash=source_link.identity_hash,
        evidence_json={
            "source_link_id": str(source_link.id),
            "target_link_id": str(target_link.id),
            "identity_type": source_link.identity_type,
            "hash_prefix": source_link.identity_hash[:16],
        },
        reason=reason,
        requested_by=requested_by,
        trace_id=trace_id,
    )
    session.add(merge)
    await session.flush()
    session.add(
        EventLog(
            workspace_id=workspace_id,
            event_type="customer.merge_requested",
            entity_type="customer_account_merge",
            entity_id=str(merge.id),
            payload={
                "source_account_id": str(source.id),
                "target_account_id": str(target.id),
                "match_type": merge.match_type,
            },
            trace_id=trace_id,
        )
    )
    await session.commit()
    await session.refresh(merge)
    return merge


async def list_merge_requests(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    status: str | None = None,
    limit: int = 200,
) -> list[CustomerAccountMerge]:
    query = select(CustomerAccountMerge).where(
        CustomerAccountMerge.workspace_id == workspace_id
    )
    if status:
        query = query.where(CustomerAccountMerge.status == status)
    rows = (
        await session.execute(
            query.order_by(CustomerAccountMerge.created_at.desc()).limit(limit)
        )
    ).scalars().all()
    return list(rows)


async def transition_merge_request(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    merge_id: UUID,
    new_status: str,
    actor: str,
    reason: str | None = None,
    trace_id: str | None = None,
) -> CustomerAccountMerge:
    merge = (
        await session.execute(
            select(CustomerAccountMerge)
            .where(
                CustomerAccountMerge.workspace_id == workspace_id,
                CustomerAccountMerge.id == merge_id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if merge is None:
        raise CustomerIdentityNotFoundError("merge request not found")
    allowed: dict[str, set[str]] = {
        "pending": {"approved", "rejected", "cancelled"},
        "approved": {"completed", "cancelled"},
        "rejected": set(),
        "completed": set(),
        "cancelled": set(),
    }
    if new_status not in allowed.get(merge.status, set()):
        raise CustomerIdentityStateError(
            f"invalid merge transition: {merge.status} -> {new_status}"
        )
    if new_status == "completed":
        return await _complete_merge(
            session,
            workspace_id=workspace_id,
            merge=merge,
            actor=actor,
            trace_id=trace_id,
        )

    merge.status = new_status
    if new_status in {"approved", "rejected"}:
        merge.reviewed_by = actor
        merge.reviewed_at = _now()
    if new_status == "rejected":
        merge.rejection_reason = reason or "rejected"
    session.add(
        EventLog(
            workspace_id=workspace_id,
            event_type=f"customer.merge_{new_status}",
            entity_type="customer_account_merge",
            entity_id=str(merge.id),
            payload={"actor": actor, "reason": reason},
            trace_id=trace_id,
        )
    )
    await session.commit()
    await session.refresh(merge)
    return merge


async def _complete_merge(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    merge: CustomerAccountMerge,
    actor: str,
    trace_id: str | None,
) -> CustomerAccountMerge:
    source = await _get_account(
        session,
        workspace_id=workspace_id,
        account_id=merge.source_account_id,
    )
    target = await _get_account(
        session,
        workspace_id=workspace_id,
        account_id=merge.target_account_id,
    )
    if source is None or target is None:
        raise CustomerIdentityNotFoundError("merge account not found")
    source = await resolve_canonical_account(
        session,
        workspace_id=workspace_id,
        account=source,
    )
    target = await resolve_canonical_account(
        session,
        workspace_id=workspace_id,
        account=target,
    )
    if source.id == target.id:
        raise CustomerIdentityStateError("merge accounts already canonical")

    redirected: dict[str, int] = defaultdict(int)

    source_links = await list_identity_links(
        session,
        workspace_id=workspace_id,
        account_id=source.id,
        limit=2000,
    )
    target_links = await list_identity_links(
        session,
        workspace_id=workspace_id,
        account_id=target.id,
        limit=2000,
    )
    target_links_by_key = {
        (
            link.channel,
            link.external_system,
            link.identity_type,
            link.identity_hash,
        ): link
        for link in target_links
    }
    for link in source_links:
        key = (
            link.channel,
            link.external_system,
            link.identity_type,
            link.identity_hash,
        )
        target_link = target_links_by_key.get(key)
        if target_link is not None:
            link.verification_status = "merged"
            link.disabled_at = _now()
            if target_link.verification_status == "conflict":
                target_link.verification_status = "verified"
                target_link.verified_at = _now()
                target_link.disabled_at = None
                target_link.metadata_json = {
                    key: value
                    for key, value in (target_link.metadata_json or {}).items()
                    if key not in {
                        "conflict_customer_account_id",
                        "conflict_link_id",
                    }
                }
            continue
        link.customer_account_id = target.id
        target_links_by_key[key] = link

    consent_events = (
        await session.execute(
            select(CustomerConsentEvent)
            .where(
                CustomerConsentEvent.workspace_id == workspace_id,
                CustomerConsentEvent.customer_account_id == source.id,
            )
            .order_by(CustomerConsentEvent.occurred_at.asc())
        )
    ).scalars().all()
    latest: dict[tuple[str, str], CustomerConsentEvent] = {}
    for event in consent_events:
        latest[(event.purpose, event.channel)] = event
    for (purpose, channel), event in latest.items():
        idempotency_key = f"merge-{merge.id}-{purpose}-{channel}"
        exists = (
            await session.execute(
                select(CustomerConsentEvent.id).where(
                    CustomerConsentEvent.workspace_id == workspace_id,
                    CustomerConsentEvent.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if exists is None:
            session.add(
                CustomerConsentEvent(
                    workspace_id=workspace_id,
                    customer_account_id=target.id,
                    purpose=purpose,
                    channel=channel,
                    status=event.status,
                    policy_version=event.policy_version,
                    source="account_merge",
                    occurred_at=event.occurred_at,
                    recorded_by=actor,
                    idempotency_key=idempotency_key,
                    evidence_json={"source_consent_event_id": str(event.id)},
                    trace_id=trace_id,
                )
            )

    for table in Base.metadata.tables.values():
        if table.name in {
            "customer_accounts",
            "customer_identity_links",
            "customer_consent_events",
        }:
            continue
        column = table.c.get("customer_account_id")
        if column is None:
            continue
        result = await session.execute(
            update(table)
            .where(column == source.id)
            .values(customer_account_id=target.id)
        )
        if result.rowcount:
            redirected[table.name] += result.rowcount

    target_models = {source.business_model, target.business_model}
    if "B2C" in target_models and "B2B" in target_models:
        target.business_model = "BOTH"
    if target.customer_type == "CONSUMER" and source.customer_type != "CONSUMER":
        target.customer_type = source.customer_type
    source.status = "merged"
    source.merged_into_account_id = target.id
    source.merged_at = _now()
    merge.status = "completed"
    merge.completed_by = actor
    merge.completed_at = _now()
    merge.result_summary = {
        "redirected_rows": dict(redirected),
        "identity_links": len(source_links),
        "canonical_account_id": str(target.id),
    }
    session.add(
        EventLog(
            workspace_id=workspace_id,
            event_type="customer.merge_completed",
            entity_type="customer_account_merge",
            entity_id=str(merge.id),
            payload={
                "actor": actor,
                "source_account_id": str(source.id),
                "target_account_id": str(target.id),
                "redirected_rows": dict(redirected),
            },
            trace_id=trace_id,
        )
    )
    await session.commit()
    await session.refresh(merge)
    return merge


async def identity_governance_stats(
    session: AsyncSession,
    *,
    workspace_id: UUID,
) -> dict[str, int]:
    account_count = (
        await session.execute(
            select(func.count(CustomerAccount.id)).where(
                CustomerAccount.workspace_id == workspace_id
            )
        )
    ).scalar_one()
    conflict_count = (
        await session.execute(
            select(func.count(CustomerIdentityLink.id)).where(
                CustomerIdentityLink.workspace_id == workspace_id,
                CustomerIdentityLink.verification_status == "conflict",
            )
        )
    ).scalar_one()
    pending_merges = (
        await session.execute(
            select(func.count(CustomerAccountMerge.id)).where(
                CustomerAccountMerge.workspace_id == workspace_id,
                CustomerAccountMerge.status == "pending",
            )
        )
    ).scalar_one()
    return {
        "accounts": int(account_count),
        "conflicts": int(conflict_count),
        "pending_merges": int(pending_merges),
    }
