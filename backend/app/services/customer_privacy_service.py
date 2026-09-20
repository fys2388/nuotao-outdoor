"""Data-subject request workflow, export, restriction, and anonymization."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.privacy import assert_no_pii
from app.models.b2b import B2BAgent, B2BOrder
from app.models.b2b_finance import B2BInvoice, B2BReceipt
from app.models.customer import (
    CustomerAccount,
    CustomerInteraction,
    CustomerKnowledgeEntry,
    CustomerProfile,
)
from app.models.customer_identity import (
    CONSENT_PURPOSES,
    IDENTITY_CHANNELS,
    CustomerConsentEvent,
    CustomerIdentityLink,
    DATA_SUBJECT_REQUEST_TYPES,
    DataSubjectRequest,
    DataSubjectRequestAction,
)
from app.models.customer_learning import CustomerAiEvaluation, CustomerPatternRun
from app.models.edm_subscription import EmailSubscription
from app.models.event import EventLog
from app.models.order import Order
from app.services import customer_consent_service, customer_identity_service

NON_ESSENTIAL_CONSENT_PURPOSES = (
    "marketing_email",
    "analytics",
    "personalization",
    "ai_processing",
)


class CustomerPrivacyError(ValueError):
    """Base class for privacy workflow errors."""


class CustomerPrivacyNotFoundError(CustomerPrivacyError):
    """Raised when a request or account does not exist."""


class CustomerPrivacyStateError(CustomerPrivacyError):
    """Raised when a request state transition is invalid."""


def _now() -> datetime:
    return datetime.now(UTC)


def _request_number() -> str:
    now = _now()
    return f"DSR-{now.strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}"


async def _get_account(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    account_id: UUID,
) -> CustomerAccount:
    account = (
        await session.execute(
            select(CustomerAccount).where(
                CustomerAccount.workspace_id == workspace_id,
                CustomerAccount.id == account_id,
            )
        )
    ).scalar_one_or_none()
    if account is None:
        raise CustomerPrivacyNotFoundError("customer account not found")
    return await customer_identity_service.resolve_canonical_account(
        session,
        workspace_id=workspace_id,
        account=account,
    )


async def _get_request(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    request_id: UUID,
    for_update: bool = False,
) -> DataSubjectRequest:
    query = select(DataSubjectRequest).where(
        DataSubjectRequest.workspace_id == workspace_id,
        DataSubjectRequest.id == request_id,
    )
    if for_update:
        query = query.with_for_update()
    request = (await session.execute(query)).scalar_one_or_none()
    if request is None:
        raise CustomerPrivacyNotFoundError("data subject request not found")
    return request


def _append_action(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    request_id: UUID,
    action_type: str,
    actor: str,
    note: str | None = None,
    result: dict | None = None,
    trace_id: str | None = None,
) -> DataSubjectRequestAction:
    action = DataSubjectRequestAction(
        workspace_id=workspace_id,
        request_id=request_id,
        action_type=action_type,
        actor=actor,
        note=note,
        result_json=result or {},
        trace_id=trace_id,
    )
    session.add(action)
    return action


async def create_request(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    request_type: str,
    requested_by: str,
    customer_account_id: UUID | None = None,
    identity_type: str | None = None,
    identity_value: str | None = None,
    request_details: str | None = None,
    verification_method: str | None = None,
    evidence: dict | None = None,
    trace_id: str | None = None,
) -> DataSubjectRequest:
    """Register a privacy request without persisting raw identity values."""
    if evidence:
        assert_no_pii(evidence, field_name="privacy request evidence")
    if request_type not in DATA_SUBJECT_REQUEST_TYPES:
        raise CustomerPrivacyError(f"unsupported request type: {request_type}")
    account: CustomerAccount | None = None
    identity_hash: str | None = None
    if customer_account_id is not None:
        account = await _get_account(
            session,
            workspace_id=workspace_id,
            account_id=customer_account_id,
        )
    if identity_type and identity_value:
        identity_hash, _fingerprint, _version = (
            customer_identity_service.build_identity_hash(
                workspace_id=workspace_id,
                identity_type=identity_type,
                identity_value=identity_value,
            )
        )
        resolved = await customer_identity_service.resolve_identity(
            session,
            workspace_id=workspace_id,
            identity_type=identity_type,
            identity_value=identity_value,
        )
        if account is not None and resolved is not None and account.id != resolved.id:
            raise customer_identity_service.CustomerIdentityConflictError(
                "identity does not belong to the selected account"
            )
        account = account or resolved
    if account is None and identity_hash is None:
        raise CustomerPrivacyError("customer_account_id or verified identity is required")

    due_days = max(1, int(get_settings().data_subject_request_due_days))
    request = DataSubjectRequest(
        workspace_id=workspace_id,
        request_number=_request_number(),
        customer_account_id=account.id if account else None,
        request_type=request_type,
        status="received",
        identity_hash=identity_hash,
        verification_method=verification_method,
        due_at=_now() + timedelta(days=due_days),
        request_details=request_details,
        result_summary={},
        evidence_json=evidence or {},
        requested_by=requested_by,
        trace_id=trace_id,
    )
    session.add(request)
    await session.flush()
    _append_action(
        session,
        workspace_id=workspace_id,
        request_id=request.id,
        action_type="received",
        actor=requested_by,
        note=request_details,
        result={"request_type": request_type},
        trace_id=trace_id,
    )
    session.add(
        EventLog(
            workspace_id=workspace_id,
            event_type="customer.privacy_request_received",
            entity_type="data_subject_request",
            entity_id=str(request.id),
            payload={
                "request_number": request.request_number,
                "request_type": request_type,
                "customer_account_id": str(account.id) if account else None,
            },
            trace_id=trace_id,
        )
    )
    await session.commit()
    await session.refresh(request)
    return request


async def list_requests(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    status: str | None = None,
    request_type: str | None = None,
    limit: int = 200,
) -> list[DataSubjectRequest]:
    query = select(DataSubjectRequest).where(
        DataSubjectRequest.workspace_id == workspace_id
    )
    if status:
        query = query.where(DataSubjectRequest.status == status)
    if request_type:
        query = query.where(DataSubjectRequest.request_type == request_type)
    rows = (
        await session.execute(
            query.order_by(DataSubjectRequest.created_at.desc()).limit(limit)
        )
    ).scalars().all()
    return list(rows)


async def request_detail(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    request_id: UUID,
) -> tuple[DataSubjectRequest, list[DataSubjectRequestAction]]:
    request = await _get_request(
        session,
        workspace_id=workspace_id,
        request_id=request_id,
    )
    actions = (
        await session.execute(
            select(DataSubjectRequestAction)
            .where(
                DataSubjectRequestAction.workspace_id == workspace_id,
                DataSubjectRequestAction.request_id == request.id,
            )
            .order_by(DataSubjectRequestAction.created_at.asc())
        )
    ).scalars().all()
    return request, list(actions)


async def verify_request(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    request_id: UUID,
    actor: str,
    verification_method: str,
    note: str | None = None,
    trace_id: str | None = None,
) -> DataSubjectRequest:
    request = await _get_request(
        session,
        workspace_id=workspace_id,
        request_id=request_id,
        for_update=True,
    )
    if request.status != "received":
        raise CustomerPrivacyStateError("only received requests can be verified")
    request.status = "verifying"
    request.verification_method = verification_method
    request.verified_by = actor
    request.verified_at = _now()
    _append_action(
        session,
        workspace_id=workspace_id,
        request_id=request.id,
        action_type="verified",
        actor=actor,
        note=note,
        result={"verification_method": verification_method},
        trace_id=trace_id,
    )
    session.add(
        EventLog(
            workspace_id=workspace_id,
            event_type="customer.privacy_request_verified",
            entity_type="data_subject_request",
            entity_id=str(request.id),
            payload={"verification_method": verification_method, "actor": actor},
            trace_id=trace_id,
        )
    )
    await session.commit()
    await session.refresh(request)
    return request


async def approve_request(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    request_id: UUID,
    actor: str,
    note: str | None = None,
    trace_id: str | None = None,
) -> DataSubjectRequest:
    request = await _get_request(
        session,
        workspace_id=workspace_id,
        request_id=request_id,
        for_update=True,
    )
    if request.status != "verifying":
        raise CustomerPrivacyStateError("request must be verified before approval")
    request.status = "approved"
    request.handled_by = actor
    request.decided_at = _now()
    _append_action(
        session,
        workspace_id=workspace_id,
        request_id=request.id,
        action_type="approved",
        actor=actor,
        note=note,
        trace_id=trace_id,
    )
    session.add(
        EventLog(
            workspace_id=workspace_id,
            event_type="customer.privacy_request_approved",
            entity_type="data_subject_request",
            entity_id=str(request.id),
            payload={"actor": actor},
            trace_id=trace_id,
        )
    )
    await session.commit()
    await session.refresh(request)
    return request


async def reject_request(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    request_id: UUID,
    actor: str,
    reason: str,
    trace_id: str | None = None,
) -> DataSubjectRequest:
    if len(reason.strip()) < 2:
        raise CustomerPrivacyError("rejection reason is required")
    request = await _get_request(
        session,
        workspace_id=workspace_id,
        request_id=request_id,
        for_update=True,
    )
    if request.status not in {"received", "verifying", "approved"}:
        raise CustomerPrivacyStateError("request can no longer be rejected")
    request.status = "rejected"
    request.handled_by = actor
    request.decided_at = _now()
    request.rejection_reason = reason.strip()
    _append_action(
        session,
        workspace_id=workspace_id,
        request_id=request.id,
        action_type="rejected",
        actor=actor,
        note=request.rejection_reason,
        trace_id=trace_id,
    )
    session.add(
        EventLog(
            workspace_id=workspace_id,
            event_type="customer.privacy_request_rejected",
            entity_type="data_subject_request",
            entity_id=str(request.id),
            payload={"actor": actor, "reason": request.rejection_reason},
            trace_id=trace_id,
        )
    )
    await session.commit()
    await session.refresh(request)
    return request


async def cancel_request(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    request_id: UUID,
    actor: str,
    reason: str | None = None,
    trace_id: str | None = None,
) -> DataSubjectRequest:
    request = await _get_request(
        session,
        workspace_id=workspace_id,
        request_id=request_id,
        for_update=True,
    )
    if request.status not in {"received", "verifying", "approved"}:
        raise CustomerPrivacyStateError("request can no longer be cancelled")
    request.status = "cancelled"
    request.handled_by = actor
    _append_action(
        session,
        workspace_id=workspace_id,
        request_id=request.id,
        action_type="manual_review",
        actor=actor,
        note=reason,
        result={"cancelled": True},
        trace_id=trace_id,
    )
    session.add(
        EventLog(
            workspace_id=workspace_id,
            event_type="customer.privacy_request_cancelled",
            entity_type="data_subject_request",
            entity_id=str(request.id),
            payload={"actor": actor, "reason": reason},
            trace_id=trace_id,
        )
    )
    await session.commit()
    await session.refresh(request)
    return request


async def execute_request(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    request_id: UUID,
    actor: str,
    note: str | None = None,
    trace_id: str | None = None,
) -> DataSubjectRequest:
    request = await _get_request(
        session,
        workspace_id=workspace_id,
        request_id=request_id,
        for_update=True,
    )
    if request.status != "approved":
        raise CustomerPrivacyStateError("request must be approved before execution")
    request.status = "processing"
    await session.flush()

    if request.request_type in {"access", "export"}:
        result = await _build_export_snapshot(
            session,
            workspace_id=workspace_id,
            request=request,
        )
        _append_action(
            session,
            workspace_id=workspace_id,
            request_id=request.id,
            action_type="export_generated",
            actor=actor,
            note=note,
            result={"record_counts": result.get("record_counts", {})},
            trace_id=trace_id,
        )
    elif request.request_type == "delete":
        result = await _anonymize_account(
            session,
            workspace_id=workspace_id,
            request=request,
            actor=actor,
            trace_id=trace_id,
        )
    elif request.request_type == "restrict":
        result = await _restrict_account(
            session,
            workspace_id=workspace_id,
            request=request,
            actor=actor,
            trace_id=trace_id,
        )
    else:
        result = {
            "manual_correction_required": True,
            "note": note or "correction completed by administrator",
        }
        _append_action(
            session,
            workspace_id=workspace_id,
            request_id=request.id,
            action_type="manual_review",
            actor=actor,
            note=note,
            result=result,
            trace_id=trace_id,
        )

    request.status = "completed"
    request.handled_by = actor
    request.completed_at = _now()
    request.result_summary = result
    _append_action(
        session,
        workspace_id=workspace_id,
        request_id=request.id,
        action_type="completed",
        actor=actor,
        note=note,
        result=result,
        trace_id=trace_id,
    )
    session.add(
        EventLog(
            workspace_id=workspace_id,
            event_type="customer.privacy_request_completed",
            entity_type="data_subject_request",
            entity_id=str(request.id),
            payload={
                "request_number": request.request_number,
                "request_type": request.request_type,
                "actor": actor,
                "result_summary": result,
            },
            trace_id=trace_id,
        )
    )
    await session.commit()
    await session.refresh(request)
    return request


async def _build_export_snapshot(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    request: DataSubjectRequest,
) -> dict:
    if request.customer_account_id is None:
        return {
            "request_number": request.request_number,
            "identity_hash_prefix": (
                request.identity_hash[:16] if request.identity_hash else None
            ),
            "account": None,
            "record_counts": {},
        }
    account = await _get_account(
        session,
        workspace_id=workspace_id,
        account_id=request.customer_account_id,
    )
    links = await customer_identity_service.list_identity_links(
        session,
        workspace_id=workspace_id,
        account_id=account.id,
        limit=2000,
    )
    consent = await customer_consent_service.consent_summary(
        session,
        workspace_id=workspace_id,
        customer_account_id=account.id,
    )
    consent_snapshot = [
        {
            **item,
            "occurred_at": (
                item["occurred_at"].isoformat()
                if hasattr(item.get("occurred_at"), "isoformat")
                else item.get("occurred_at")
            ),
        }
        for item in consent
    ]
    order_count = (
        await session.execute(
            select(func.count(Order.id)).where(
                Order.workspace_id == workspace_id,
                Order.customer_account_id == account.id,
            )
        )
    ).scalar_one()
    b2b_order_count = (
        await session.execute(
            select(func.count(B2BOrder.id)).where(
                B2BOrder.workspace_id == workspace_id,
                B2BOrder.customer_account_id == account.id,
            )
        )
    ).scalar_one()
    invoice_count = (
        await session.execute(
            select(func.count(B2BInvoice.id)).where(
                B2BInvoice.workspace_id == workspace_id,
                B2BInvoice.customer_account_id == account.id,
            )
        )
    ).scalar_one()
    return {
        "request_number": request.request_number,
        "account": {
            "id": str(account.id),
            "customer_number": account.customer_number,
            "customer_type": account.customer_type,
            "business_model": account.business_model,
            "status": account.status,
            "country": account.country,
            "default_currency": account.default_currency,
        },
        "identity_links": [
            {
                "id": str(link.id),
                "channel": link.channel,
                "external_system": link.external_system,
                "identity_type": link.identity_type,
                "fingerprint": link.fingerprint,
                "verification_status": link.verification_status,
                "last_seen_at": (
                    link.last_seen_at.isoformat() if link.last_seen_at else None
                ),
            }
            for link in links
        ],
        "consent": consent_snapshot,
        "record_counts": {
            "b2c_orders": int(order_count),
            "b2b_orders": int(b2b_order_count),
            "b2b_invoices": int(invoice_count),
            "identity_links": len(links),
            "consent_events": len(consent_snapshot),
        },
        "retention_note": (
            "Orders, invoices, receipts and accounting facts are retained as "
            "required for tax, audit and contractual obligations."
        ),
    }


async def _withdraw_all_non_essential_consent(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    account_id: UUID,
    request: DataSubjectRequest,
    actor: str,
    trace_id: str | None,
) -> int:
    created = 0
    for purpose in NON_ESSENTIAL_CONSENT_PURPOSES:
        for channel in IDENTITY_CHANNELS:
            status, _event, _subscription = (
                await customer_consent_service.current_consent_status(
                    session,
                    workspace_id=workspace_id,
                    customer_account_id=account_id,
                    purpose=purpose,
                    channel=channel,
                )
            )
            if status != "granted":
                continue
            await customer_consent_service.append_consent_event(
                session,
                workspace_id=workspace_id,
                customer_account_id=account_id,
                purpose=purpose,
                channel=channel,
                status="withdrawn",
                policy_version="privacy-request-v1",
                source="data_subject_request",
                recorded_by=actor,
                idempotency_key=f"{request.id}-{purpose}-{channel}-withdrawn",
                evidence={"request_number": request.request_number},
                trace_id=trace_id,
                commit=False,
            )
            created += 1
    return created


async def _restrict_account(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    request: DataSubjectRequest,
    actor: str,
    trace_id: str | None,
) -> dict:
    if request.customer_account_id is None:
        raise CustomerPrivacyStateError("request is not linked to a customer account")
    account = await _get_account(
        session,
        workspace_id=workspace_id,
        account_id=request.customer_account_id,
    )
    account.status = "restricted"
    withdrawn = await _withdraw_all_non_essential_consent(
        session,
        workspace_id=workspace_id,
        account_id=account.id,
        request=request,
        actor=actor,
        trace_id=trace_id,
    )
    _append_action(
        session,
        workspace_id=workspace_id,
        request_id=request.id,
        action_type="consent_withdrawn",
        actor=actor,
        result={"withdrawn_events": withdrawn},
        trace_id=trace_id,
    )
    return {
        "account_status": "restricted",
        "withdrawn_consent_events": withdrawn,
        "retained_processing": ["order_fulfillment", "tax", "accounting"],
    }


async def _anonymize_account(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    request: DataSubjectRequest,
    actor: str,
    trace_id: str | None,
) -> dict:
    if request.customer_account_id is None:
        raise CustomerPrivacyStateError("request is not linked to a customer account")
    account = await _get_account(
        session,
        workspace_id=workspace_id,
        account_id=request.customer_account_id,
    )
    now = _now()
    links = (
        await session.execute(
            select(CustomerIdentityLink).where(
                CustomerIdentityLink.workspace_id == workspace_id,
                CustomerIdentityLink.customer_account_id == account.id,
            )
        )
    ).scalars().all()
    for link in links:
        link.verification_status = "revoked"
        link.disabled_at = now
        link.metadata_json = {"redacted": True}
    _append_action(
        session,
        workspace_id=workspace_id,
        request_id=request.id,
        action_type="identity_links_revoked",
        actor=actor,
        result={"identity_links": len(links)},
        trace_id=trace_id,
    )

    withdrawn = await _withdraw_all_non_essential_consent(
        session,
        workspace_id=workspace_id,
        account_id=account.id,
        request=request,
        actor=actor,
        trace_id=trace_id,
    )
    _append_action(
        session,
        workspace_id=workspace_id,
        request_id=request.id,
        action_type="consent_withdrawn",
        actor=actor,
        result={"withdrawn_events": withdrawn},
        trace_id=trace_id,
    )

    profiles = (
        await session.execute(
            select(CustomerProfile).where(
                CustomerProfile.workspace_id == workspace_id,
                CustomerProfile.customer_account_id == account.id,
            )
        )
    ).scalars().all()
    profile_ids = [profile.id for profile in profiles]
    deleted_interactions = 0
    deleted_knowledge = 0
    deleted_evaluations = 0
    deleted_patterns = 0
    if profile_ids:
        deleted_interactions = (
            await session.execute(
                delete(CustomerInteraction).where(
                    CustomerInteraction.workspace_id == workspace_id,
                    CustomerInteraction.customer_id.in_(profile_ids),
                )
            )
        ).rowcount or 0
        deleted_knowledge = (
            await session.execute(
                delete(CustomerKnowledgeEntry).where(
                    CustomerKnowledgeEntry.workspace_id == workspace_id,
                    CustomerKnowledgeEntry.customer_id.in_(profile_ids),
                )
            )
        ).rowcount or 0
        deleted_evaluations = (
            await session.execute(
                delete(CustomerAiEvaluation).where(
                    CustomerAiEvaluation.workspace_id == workspace_id,
                    CustomerAiEvaluation.customer_id.in_(profile_ids),
                )
            )
        ).rowcount or 0
        deleted_patterns = (
            await session.execute(
                delete(CustomerPatternRun).where(
                    CustomerPatternRun.workspace_id == workspace_id,
                    CustomerPatternRun.customer_id.in_(profile_ids),
                )
            )
        ).rowcount or 0
    for profile in profiles:
        profile.country = None
        profile.language = None
        profile.segment = None
        profile.tags = []
        profile.first_order_at = None
        profile.total_orders = 0
        profile.total_revenue = 0
        profile.trace_id = None
    _append_action(
        session,
        workspace_id=workspace_id,
        request_id=request.id,
        action_type="profile_erased",
        actor=actor,
        result={
            "profiles_anonymized": len(profiles),
            "interactions_deleted": deleted_interactions,
            "knowledge_deleted": deleted_knowledge,
            "evaluations_deleted": deleted_evaluations,
            "patterns_deleted": deleted_patterns,
        },
        trace_id=trace_id,
    )

    agents = (
        await session.execute(
            select(B2BAgent).where(
                B2BAgent.workspace_id == workspace_id,
                B2BAgent.customer_account_id == account.id,
            )
        )
    ).scalars().all()
    for agent in agents:
        agent.contact_name = "Anonymized"
        agent.email = f"deleted+{agent.id.hex}@invalid.local"
        agent.phone = None
        agent.city = None
        agent.address = None
        agent.notes = None
    _append_action(
        session,
        workspace_id=workspace_id,
        request_id=request.id,
        action_type="b2b_contact_anonymized",
        actor=actor,
        result={"b2b_contacts": len(agents)},
        trace_id=trace_id,
    )

    subscriptions = (
        await session.execute(
            select(EmailSubscription).where(
                EmailSubscription.workspace_id == workspace_id,
                EmailSubscription.customer_account_id == account.id,
            )
        )
    ).scalars().all()
    for subscription in subscriptions:
        subscription.subscription_status = "unsubscribed"
        subscription.consent_given = False
        subscription.unsubscribe_timestamp = now
        subscription.unsubscribe_reason = "data_subject_delete"
        subscription.consent_ip = None
        subscription.consent_user_agent = None
        subscription.tags = []
        subscription.metadata_json = {"redacted": True}

    orders = (
        await session.execute(
            select(Order).where(
                Order.workspace_id == workspace_id,
                Order.customer_account_id == account.id,
            )
        )
    ).scalars().all()
    for order in orders:
        order.customer_reference_id = None
        order.country = None

    account.status = "anonymized"
    account.display_name = "Anonymized Customer"
    account.country = None
    account.trace_id = None
    _append_action(
        session,
        workspace_id=workspace_id,
        request_id=request.id,
        action_type="account_anonymized",
        actor=actor,
        result={"subscriptions_suppressed": len(subscriptions)},
        trace_id=trace_id,
    )
    return {
        "account_status": "anonymized",
        "identity_links_revoked": len(links),
        "withdrawn_consent_events": withdrawn,
        "profiles_anonymized": len(profiles),
        "interactions_deleted": deleted_interactions,
        "b2b_contacts_anonymized": len(agents),
        "subscriptions_suppressed": len(subscriptions),
        "orders_retained": len(orders),
        "financial_records_retained": True,
    }


async def privacy_stats(
    session: AsyncSession,
    *,
    workspace_id: UUID,
) -> dict[str, int]:
    counts = {}
    for status in ("received", "verifying", "approved", "processing", "completed"):
        counts[status] = int(
            (
                await session.execute(
                    select(func.count(DataSubjectRequest.id)).where(
                        DataSubjectRequest.workspace_id == workspace_id,
                        DataSubjectRequest.status == status,
                    )
                )
            ).scalar_one()
        )
    counts["overdue"] = int(
        (
            await session.execute(
                select(func.count(DataSubjectRequest.id)).where(
                    DataSubjectRequest.workspace_id == workspace_id,
                    DataSubjectRequest.status.not_in(
                        ["completed", "rejected", "cancelled"]
                    ),
                    DataSubjectRequest.due_at < _now(),
                )
            )
        ).scalar_one()
    )
    return counts
