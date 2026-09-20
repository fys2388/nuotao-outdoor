"""Customer identity, consent, merge, and privacy workflow tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.privacy import PIIPayloadError, assert_no_pii
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.customer import CustomerAccount
from app.models.customer_identity import CustomerConsentEvent, CustomerIdentityLink
from app.models.event import EventLog
from app.models.order import Order
from app.services import (
    customer_consent_service,
    customer_identity_service,
    customer_privacy_service,
)

WORKSPACE = DEFAULT_WORKSPACE_ID


def test_identity_normalization_and_workspace_scoped_hmac() -> None:
    assert (
        customer_identity_service.normalize_identity_value(
            "email", " Buyer@Example.COM "
        )
        == "buyer@example.com"
    )
    assert (
        customer_identity_service.normalize_identity_value(
            "phone", "+86 (138) 0013-8000"
        )
        == "+8613800138000"
    )

    first = customer_identity_service.build_identity_hash(
        workspace_id=WORKSPACE,
        identity_type="email",
        identity_value="buyer@example.com",
    )
    repeated = customer_identity_service.build_identity_hash(
        workspace_id=WORKSPACE,
        identity_type="email",
        identity_value="BUYER@example.com",
    )
    other_workspace = customer_identity_service.build_identity_hash(
        workspace_id=uuid4(),
        identity_type="email",
        identity_value="buyer@example.com",
    )
    assert first[:2] == repeated[:2]
    assert first[0] != other_workspace[0]


def test_identity_metadata_rejects_direct_identifiers() -> None:
    with pytest.raises(PIIPayloadError, match="PII field key"):
        assert_no_pii(
            {"customer": {"email_address": "buyer@example.com"}},
            field_name="identity metadata",
        )
    with pytest.raises(PIIPayloadError, match="direct identifiers"):
        assert_no_pii(
            {"note": "buyer@example.com"},
            field_name="identity metadata",
        )


@pytest.mark.asyncio
async def test_identity_conflict_is_flagged_not_auto_merged(db_session) -> None:
    first = await customer_identity_service.ensure_account_for_identity(
        db_session,
        workspace_id=WORKSPACE,
        identity_type="email",
        identity_value="shared@example.com",
        channel="email",
        external_system="store",
        customer_type="CONSUMER",
        business_model="B2C",
    )
    second = CustomerAccount(
        workspace_id=WORKSPACE,
        customer_number="CUS-CONFLICT-2",
        customer_type="RETAILER",
        business_model="B2B",
        status="active",
    )
    db_session.add(second)
    await db_session.flush()

    link, conflict_account_id = (
        await customer_identity_service.link_identity_to_account(
            db_session,
            workspace_id=WORKSPACE,
            account_id=second.id,
            identity_type="email",
            identity_value="shared@example.com",
            channel="email",
            external_system="store",
            source="test",
        )
    )
    await db_session.commit()

    assert conflict_account_id == first.id
    assert link.verification_status == "conflict"
    assert second.merged_into_account_id is None
    event_types = (
        await db_session.execute(select(EventLog.event_type))
    ).scalars().all()
    assert "customer.identity_conflict_detected" in event_types


@pytest.mark.asyncio
async def test_reviewed_merge_redirects_links_consent_and_business_rows(
    db_session,
) -> None:
    source = await customer_identity_service.ensure_account_for_identity(
        db_session,
        workspace_id=WORKSPACE,
        identity_type="email",
        identity_value="merge-source@example.com",
        channel="email",
        external_system="store",
        customer_type="CONSUMER",
        business_model="B2C",
    )
    target = await customer_identity_service.ensure_account_for_identity(
        db_session,
        workspace_id=WORKSPACE,
        identity_type="phone",
        identity_value="+14155550123",
        channel="crm",
        external_system="crm",
        customer_type="CONSUMER",
        business_model="B2C",
    )
    moved_phone, _ = await customer_identity_service.link_identity_to_account(
        db_session,
        workspace_id=WORKSPACE,
        account_id=source.id,
        identity_type="phone",
        identity_value="+14155550999",
        channel="support",
        external_system="support",
        source="test",
    )
    matching_link, _ = await customer_identity_service.link_identity_to_account(
        db_session,
        workspace_id=WORKSPACE,
        account_id=target.id,
        identity_type="email",
        identity_value="merge-source@example.com",
        channel="email",
        external_system="store",
        source="test",
    )
    await customer_consent_service.append_consent_event(
        db_session,
        workspace_id=WORKSPACE,
        customer_account_id=source.id,
        purpose="marketing_email",
        channel="email",
        status="withdrawn",
        policy_version="test-v1",
        source="test",
        recorded_by="operator@example.com",
        idempotency_key="source-withdrawn",
        occurred_at=datetime.now(UTC),
    )
    older_consent = CustomerConsentEvent(
        workspace_id=WORKSPACE,
        customer_account_id=target.id,
        purpose="marketing_email",
        channel="email",
        status="granted",
        policy_version="test-v1",
        source="test",
        recorded_by="operator@example.com",
        idempotency_key="target-granted",
        occurred_at=datetime.now(UTC) - timedelta(days=1),
    )
    db_session.add(older_consent)
    order = Order(
        workspace_id=WORKSPACE,
        external_order_id="ORDER-MERGE-1",
        customer_account_id=source.id,
        status="pending",
        total=10,
        currency="USD",
    )
    db_session.add(order)
    await db_session.commit()

    merge = await customer_identity_service.create_merge_request(
        db_session,
        workspace_id=WORKSPACE,
        source_account_id=source.id,
        target_account_id=target.id,
        requested_by="operator@example.com",
        reason="Verified same customer in two channels",
    )
    await customer_identity_service.transition_merge_request(
        db_session,
        workspace_id=WORKSPACE,
        merge_id=merge.id,
        new_status="approved",
        actor="admin@example.com",
    )
    merge = await customer_identity_service.transition_merge_request(
        db_session,
        workspace_id=WORKSPACE,
        merge_id=merge.id,
        new_status="completed",
        actor="admin@example.com",
    )

    await db_session.refresh(source)
    await db_session.refresh(target)
    await db_session.refresh(order)
    await db_session.refresh(matching_link)
    await db_session.refresh(moved_phone)
    assert source.status == "merged"
    assert source.merged_into_account_id == target.id
    assert order.customer_account_id == target.id
    assert matching_link.verification_status == "verified"
    assert moved_phone.customer_account_id == target.id

    canonical = await customer_identity_service.resolve_identity(
        db_session,
        workspace_id=WORKSPACE,
        identity_type="email",
        identity_value="merge-source@example.com",
    )
    assert canonical is not None and canonical.id == target.id
    allowed, reason = await customer_consent_service.marketing_email_allowed(
        db_session,
        workspace_id=WORKSPACE,
        customer_account_id=target.id,
    )
    assert allowed is False
    assert reason == "withdrawn"
    assert merge.result_summary["canonical_account_id"] == str(target.id)


@pytest.mark.asyncio
async def test_delete_anonymizes_identity_but_retains_order(db_session) -> None:
    account = await customer_identity_service.ensure_account_for_identity(
        db_session,
        workspace_id=WORKSPACE,
        identity_type="email",
        identity_value="delete-me@example.com",
        channel="email",
        external_system="store",
        customer_type="CONSUMER",
        business_model="B2C",
        display_name="Delete Me",
    )
    order = Order(
        workspace_id=WORKSPACE,
        external_order_id="ORDER-RETAIN-1",
        customer_account_id=account.id,
        status="completed",
        total=20,
        currency="USD",
    )
    db_session.add(order)
    await db_session.commit()
    request = await customer_privacy_service.create_request(
        db_session,
        workspace_id=WORKSPACE,
        request_type="delete",
        requested_by="operator@example.com",
        customer_account_id=account.id,
    )
    await customer_privacy_service.verify_request(
        db_session,
        workspace_id=WORKSPACE,
        request_id=request.id,
        actor="admin@example.com",
        verification_method="account_email",
    )
    await customer_privacy_service.approve_request(
        db_session,
        workspace_id=WORKSPACE,
        request_id=request.id,
        actor="admin@example.com",
    )
    completed = await customer_privacy_service.execute_request(
        db_session,
        workspace_id=WORKSPACE,
        request_id=request.id,
        actor="admin@example.com",
        note="Identity verified and anonymized",
    )

    await db_session.refresh(account)
    await db_session.refresh(order)
    links = (
        await db_session.execute(
            select(CustomerIdentityLink).where(
                CustomerIdentityLink.customer_account_id == account.id
            )
        )
    ).scalars().all()
    assert completed.status == "completed"
    assert account.status == "anonymized"
    assert order.customer_account_id == account.id
    assert order.external_order_id == "ORDER-RETAIN-1"
    assert links and all(link.verification_status == "revoked" for link in links)


@pytest.mark.asyncio
async def test_privacy_request_state_machine_and_workspace_scope(db_session) -> None:
    account = await customer_identity_service.ensure_account_for_identity(
        db_session,
        workspace_id=WORKSPACE,
        identity_type="email",
        identity_value="request@example.com",
        channel="email",
        external_system="store",
        customer_type="CONSUMER",
        business_model="B2C",
    )
    request = await customer_privacy_service.create_request(
        db_session,
        workspace_id=WORKSPACE,
        request_type="access",
        requested_by="operator@example.com",
        customer_account_id=account.id,
    )
    with pytest.raises(customer_privacy_service.CustomerPrivacyStateError):
        await customer_privacy_service.approve_request(
            db_session,
            workspace_id=WORKSPACE,
            request_id=request.id,
            actor="admin@example.com",
        )
    with pytest.raises(customer_privacy_service.CustomerPrivacyNotFoundError):
        await customer_privacy_service.request_detail(
            db_session,
            workspace_id=uuid4(),
            request_id=request.id,
        )


@pytest.mark.asyncio
async def test_export_request_snapshot_is_json_serializable(db_session) -> None:
    account = await customer_identity_service.ensure_account_for_identity(
        db_session,
        workspace_id=WORKSPACE,
        identity_type="email",
        identity_value="export@example.com",
        channel="email",
        external_system="store",
        customer_type="CONSUMER",
        business_model="B2C",
    )
    await customer_consent_service.append_consent_event(
        db_session,
        workspace_id=WORKSPACE,
        customer_account_id=account.id,
        purpose="analytics",
        channel="b2c_store",
        status="granted",
        policy_version="test-v1",
        source="test",
        recorded_by="operator@example.com",
        idempotency_key="export-consent",
    )
    request = await customer_privacy_service.create_request(
        db_session,
        workspace_id=WORKSPACE,
        request_type="export",
        requested_by="operator@example.com",
        customer_account_id=account.id,
    )
    await customer_privacy_service.verify_request(
        db_session,
        workspace_id=WORKSPACE,
        request_id=request.id,
        actor="admin@example.com",
        verification_method="account_email",
    )
    await customer_privacy_service.approve_request(
        db_session,
        workspace_id=WORKSPACE,
        request_id=request.id,
        actor="admin@example.com",
    )
    completed = await customer_privacy_service.execute_request(
        db_session,
        workspace_id=WORKSPACE,
        request_id=request.id,
        actor="admin@example.com",
    )
    exported_at = completed.result_summary["consent"][0]["occurred_at"]
    assert isinstance(exported_at, str)


@pytest.mark.asyncio
async def test_edm_ledger_grant_can_authorize_without_legacy_subscription(
    db_session,
    monkeypatch,
) -> None:
    from app.models.content_marketing import EDMCampaign
    from app.services import edm_send_service

    settings = get_settings()
    monkeypatch.setattr(settings, "edm_send_enabled", True)
    account = await customer_identity_service.ensure_account_for_identity(
        db_session,
        workspace_id=WORKSPACE,
        identity_type="email",
        identity_value="ledger-only@example.com",
        channel="email",
        external_system="store",
        customer_type="CONSUMER",
        business_model="B2C",
    )
    await customer_consent_service.append_consent_event(
        db_session,
        workspace_id=WORKSPACE,
        customer_account_id=account.id,
        purpose="marketing_email",
        channel="email",
        status="granted",
        policy_version="test-v1",
        source="checkout",
        recorded_by="operator@example.com",
        idempotency_key="ledger-only-grant",
    )
    campaign = EDMCampaign(
        workspace_id=WORKSPACE,
        name="Ledger-only campaign",
        campaign_type="newsletter",
        status="scheduled",
        subject="Ledger consent",
        from_name="Nuotao",
        from_email="noreply@example.com",
        content_json={"body": "Hello"},
    )
    db_session.add(campaign)
    await db_session.commit()

    log = await edm_send_service.send_edm_email(
        db_session,
        workspace_id=WORKSPACE,
        email="ledger-only@example.com",
        campaign_id=campaign.id,
        dry_run=True,
        idempotency_key="ledger-only-send",
    )
    assert log.status == "dry_run"


@pytest.mark.asyncio
async def test_edm_ledger_withdrawal_cannot_be_bypassed_by_legacy_subscription(
    db_session,
    monkeypatch,
) -> None:
    from app.models.content_marketing import EDMCampaign
    from app.services import edm_send_service

    settings = get_settings()
    monkeypatch.setattr(settings, "edm_send_enabled", True)
    subscription = await edm_send_service.create_or_update_subscription(
        db_session,
        workspace_id=WORKSPACE,
        email="withdraw-ledger@example.com",
        consent_given=True,
        consent_source="checkout",
    )
    await customer_consent_service.append_consent_event(
        db_session,
        workspace_id=WORKSPACE,
        customer_account_id=subscription.customer_account_id,
        purpose="marketing_email",
        channel="email",
        status="withdrawn",
        policy_version="test-v1",
        source="privacy_request",
        recorded_by="operator@example.com",
        idempotency_key="withdraw-ledger",
    )
    campaign = EDMCampaign(
        workspace_id=WORKSPACE,
        name="Withdrawal campaign",
        campaign_type="newsletter",
        status="scheduled",
        subject="Should not send",
        from_name="Nuotao",
        from_email="noreply@example.com",
        content_json={"body": "Hello"},
    )
    db_session.add(campaign)
    await db_session.commit()
    assert subscription.consent_given is True

    log = await edm_send_service.send_edm_email(
        db_session,
        workspace_id=WORKSPACE,
        email="withdraw-ledger@example.com",
        campaign_id=campaign.id,
        dry_run=True,
        idempotency_key="withdraw-ledger-send",
    )
    assert log.status == "skipped"
    assert log.skip_reason == "consent_withdrawn"
