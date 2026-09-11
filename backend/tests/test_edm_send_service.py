"""EDM send service tests (M3.2 GDPR compliance).

Tests cover:
- Default send disabled (edm_send_enabled=false) -> skipped
- No consent -> skipped
- Unsubscribed -> skipped
- Campaign not approved (draft) -> skipped
- 24-hour dedup -> skipped
- Dry-run default -> dry_run status, no real send
- Failed send retry with max_retries
- Idempotent send (same key returns existing log)
- Subscription create and unsubscribe
- Provider not configured -> failed, never fakes success
"""

from uuid import UUID, uuid4

import pytest
import pytest_asyncio

from app.models.content_marketing import EDMCampaign
from app.models.edm_subscription import EDMSendLog, EmailSubscription
from app.services import edm_send_service

DEFAULT_WORKSPACE = UUID("00000000-0000-0000-0000-000000000001")
TEST_EMAIL = "test@example.com"
TEST_EMAIL_HASH = edm_send_service._hash_email(TEST_EMAIL)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest_asyncio.fixture
async def approved_campaign(db_session):
    """Create an approved EDM campaign with content."""
    campaign = EDMCampaign(
        workspace_id=DEFAULT_WORKSPACE,
        name="Test Campaign",
        campaign_type="newsletter",
        status="scheduled",  # not draft = approved
        subject="Test Subject",
        from_name="Test",
        from_email="test@example.com",
        content_json={"body": "Test content"},
    )
    db_session.add(campaign)
    await db_session.flush()
    return campaign


@pytest_asyncio.fixture
async def draft_campaign(db_session):
    """Create a draft EDM campaign (not approved)."""
    campaign = EDMCampaign(
        workspace_id=DEFAULT_WORKSPACE,
        name="Draft Campaign",
        campaign_type="newsletter",
        status="draft",
        subject="Draft Subject",
        content_json={"body": "Draft content"},
    )
    db_session.add(campaign)
    await db_session.flush()
    return campaign


@pytest_asyncio.fixture
async def subscribed_user(db_session):
    """Create a subscribed user with consent."""
    sub = await edm_send_service.create_or_update_subscription(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        email=TEST_EMAIL, consent_given=True, consent_source="signup_form",
    )
    return sub


@pytest_asyncio.fixture
async def unsubscribed_user(db_session):
    """Create an unsubscribed user."""
    sub = await edm_send_service.create_or_update_subscription(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        email=TEST_EMAIL, consent_given=True, consent_source="signup_form",
    )
    sub = await edm_send_service.unsubscribe(
        db_session, workspace_id=DEFAULT_WORKSPACE, email=TEST_EMAIL, reason="user request",
    )
    return sub


# --------------------------------------------------------------------------- #
# Test 1: Default send disabled
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_default_send_disabled(db_session, approved_campaign, subscribed_user):
    """edm_send_enabled=false (default) -> send skipped with send_disabled reason."""
    log = await edm_send_service.send_edm_email(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        email=TEST_EMAIL, campaign_id=approved_campaign.id,
        dry_run=False,  # even if dry_run=false, send_disabled takes precedence
    )
    assert log.status == "skipped"
    assert log.skip_reason == "send_disabled"
    assert log.is_dry_run is False


# --------------------------------------------------------------------------- #
# Test 2: No consent -> skipped
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_no_consent_skipped(db_session, approved_campaign, monkeypatch):
    """User without consent -> send skipped with no_consent reason."""
    # Enable send but user has no consent
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "edm_send_enabled", True)

    # Create user WITHOUT consent
    await edm_send_service.create_or_update_subscription(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        email="noconsent@example.com", consent_given=False,
    )

    log = await edm_send_service.send_edm_email(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        email="noconsent@example.com", campaign_id=approved_campaign.id,
        dry_run=True,
    )
    assert log.status == "skipped"
    assert log.skip_reason == "no_consent"


# --------------------------------------------------------------------------- #
# Test 3: Unsubscribed -> skipped
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_unsubscribed_skipped(db_session, approved_campaign, unsubscribed_user, monkeypatch):
    """Unsubscribed user -> send skipped with unsubscribed reason."""
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "edm_send_enabled", True)

    log = await edm_send_service.send_edm_email(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        email=TEST_EMAIL, campaign_id=approved_campaign.id,
        dry_run=True,
    )
    assert log.status == "skipped"
    assert log.skip_reason == "unsubscribed"


# --------------------------------------------------------------------------- #
# Test 4: Campaign not approved (draft) -> skipped
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_draft_campaign_skipped(db_session, draft_campaign, subscribed_user, monkeypatch):
    """Draft campaign -> send skipped with campaign_not_approved reason."""
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "edm_send_enabled", True)

    log = await edm_send_service.send_edm_email(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        email=TEST_EMAIL, campaign_id=draft_campaign.id,
        dry_run=True,
    )
    assert log.status == "skipped"
    assert log.skip_reason == "campaign_not_approved"


# --------------------------------------------------------------------------- #
# Test 5: 24-hour dedup -> skipped
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_24h_dedup_skipped(db_session, approved_campaign, subscribed_user, monkeypatch):
    """Second send within 24h -> skipped with dedup_24h reason."""
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "edm_send_enabled", True)

    # First send (dry-run)
    log1 = await edm_send_service.send_edm_email(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        email=TEST_EMAIL, campaign_id=approved_campaign.id,
        dry_run=True, idempotency_key="dedup-test-1",
    )
    assert log1.status == "dry_run"

    # Second send (different idempotency key, same email+campaign) -> dedup block
    log2 = await edm_send_service.send_edm_email(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        email=TEST_EMAIL, campaign_id=approved_campaign.id,
        dry_run=True, idempotency_key="dedup-test-2",
    )
    assert log2.status == "skipped"
    assert log2.skip_reason == "dedup_24h"


# --------------------------------------------------------------------------- #
# Test 6: Dry-run default -> dry_run status
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_dry_run_default(db_session, approved_campaign, subscribed_user, monkeypatch):
    """Default dry_run=true -> dry_run status, no real send."""
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "edm_send_enabled", True)
    monkeypatch.setattr(settings, "edm_dry_run_default", True)

    log = await edm_send_service.send_edm_email(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        email=TEST_EMAIL, campaign_id=approved_campaign.id,
        # dry_run not specified -> uses default (True)
    )
    assert log.status == "dry_run"
    assert log.is_dry_run is True
    assert log.provider_response.get("dry_run") is True


# --------------------------------------------------------------------------- #
# Test 7: Provider not configured -> failed, never fakes success
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_provider_not_configured_failed(db_session, approved_campaign, subscribed_user, monkeypatch):
    """Provider not configured -> failed status, never fakes success."""
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "edm_send_enabled", True)
    monkeypatch.setattr(settings, "edm_dry_run_default", False)
    monkeypatch.setattr(settings, "edm_provider", "")  # not configured

    log = await edm_send_service.send_edm_email(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        email=TEST_EMAIL, campaign_id=approved_campaign.id,
        dry_run=False,
    )
    assert log.status == "failed"
    assert "provider" in log.error_message.lower() or "not configured" in log.error_message.lower()
    assert log.is_dry_run is False


# --------------------------------------------------------------------------- #
# Test 8: Idempotent send
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_idempotent_send(db_session, approved_campaign, subscribed_user, monkeypatch):
    """Same idempotency_key returns existing log, no duplicate."""
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "edm_send_enabled", True)

    log1 = await edm_send_service.send_edm_email(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        email=TEST_EMAIL, campaign_id=approved_campaign.id,
        dry_run=True, idempotency_key="idem-test-key",
    )
    log2 = await edm_send_service.send_edm_email(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        email=TEST_EMAIL, campaign_id=approved_campaign.id,
        dry_run=True, idempotency_key="idem-test-key",
    )
    assert log1.id == log2.id
    assert log1.status == log2.status


# --------------------------------------------------------------------------- #
# Test 9: Failed send retry
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_failed_send_retry(db_session, approved_campaign, subscribed_user, monkeypatch):
    """Failed send can be retried, retry_count increments."""
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "edm_send_enabled", True)
    monkeypatch.setattr(settings, "edm_dry_run_default", False)
    monkeypatch.setattr(settings, "edm_provider", "")

    # Create a failed send
    log = await edm_send_service.send_edm_email(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        email=TEST_EMAIL, campaign_id=approved_campaign.id,
        dry_run=False, idempotency_key="retry-test-1",
    )
    assert log.status == "failed"
    initial_retry_count = log.retry_count

    # Retry
    log = await edm_send_service.retry_failed_send(
        db_session, workspace_id=DEFAULT_WORKSPACE, send_log_id=log.id,
    )
    assert log.retry_count == initial_retry_count + 1


@pytest.mark.asyncio
async def test_retry_respects_max_retries(db_session, approved_campaign, subscribed_user, monkeypatch):
    """Retry beyond max_retries raises error."""
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "edm_send_enabled", True)
    monkeypatch.setattr(settings, "edm_dry_run_default", False)
    monkeypatch.setattr(settings, "edm_provider", "")
    monkeypatch.setattr(settings, "edm_max_retries", 1)

    log = await edm_send_service.send_edm_email(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        email=TEST_EMAIL, campaign_id=approved_campaign.id,
        dry_run=False, idempotency_key="max-retry-test",
    )
    assert log.status == "failed"

    # First retry (retry_count becomes 1, which equals max_retries=1)
    log = await edm_send_service.retry_failed_send(
        db_session, workspace_id=DEFAULT_WORKSPACE, send_log_id=log.id,
    )
    assert log.retry_count == 1

    # Second retry should fail (exceeds max_retries)
    with pytest.raises(edm_send_service.EDMSendError, match="Max retries"):
        await edm_send_service.retry_failed_send(
            db_session, workspace_id=DEFAULT_WORKSPACE, send_log_id=log.id,
        )


# --------------------------------------------------------------------------- #
# Test 10: Subscription and unsubscribe
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_create_subscription_with_consent(db_session):
    """Create subscription with consent."""
    sub = await edm_send_service.create_or_update_subscription(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        email="newuser@example.com", consent_given=True, consent_source="checkout",
    )
    assert sub.consent_given is True
    assert sub.subscription_status == "subscribed"
    assert sub.consent_source == "checkout"
    assert sub.consent_timestamp is not None


@pytest.mark.asyncio
async def test_unsubscribe_honored_immediately(db_session):
    """Unsubscribe is honored immediately per GDPR."""
    await edm_send_service.create_or_update_subscription(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        email="unsub@example.com", consent_given=True,
    )
    sub = await edm_send_service.unsubscribe(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        email="unsub@example.com", reason="user clicked unsubscribe link",
    )
    assert sub.subscription_status == "unsubscribed"
    assert sub.consent_given is False
    assert sub.unsubscribe_timestamp is not None
    assert sub.unsubscribe_reason == "user clicked unsubscribe link"


@pytest.mark.asyncio
async def test_subscription_idempotent(db_session):
    """Same email creates one subscription (idempotent)."""
    sub1 = await edm_send_service.create_or_update_subscription(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        email="idem@example.com", consent_given=False,
    )
    sub2 = await edm_send_service.create_or_update_subscription(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        email="idem@example.com", consent_given=True, consent_source="signup_form",
    )
    assert sub1.id == sub2.id
    assert sub2.consent_given is True  # updated on second call
