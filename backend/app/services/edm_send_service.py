"""EDM send service with GDPR compliance and safety controls (M3.2).

Rules (enforced before every send):
1. EDM_SEND_ENABLED must be true (default: false)
2. Recipient must have valid subscription consent
3. Recipient must not be unsubscribed
4. Campaign must be approved (status != draft)
5. Recipient must not be blocked by 24-hour dedup rule
6. Send content must be approved

Additional safety:
- Default dry-run: records send attempt but does not actually send
- Idempotency key prevents duplicate sends
- Failed sends can be retried up to max_retries
- Every send attempt (success/failure/skip/dry-run) recorded in edm_send_logs
- Provider not configured -> skipped, never fakes success
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.content_marketing import EDMCampaign
from app.models.edm_subscription import EDMSendLog, EmailSubscription
from app.services import event_service

logger = logging.getLogger(__name__)


class EDMSendError(Exception):
    """Base EDM send error."""


class EDMSendBlocked(EDMSendError):
    """Send blocked by safety check."""

    def __init__(self, reason: str, skip_reason: str):
        super().__init__(reason)
        self.skip_reason = skip_reason


class EDMProviderNotConfigured(EDMSendError):
    """Email provider not configured."""


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _hash_email(email: str) -> str:
    """Hash email for PII-minimized storage (SHA-256)."""
    return hashlib.sha256(email.lower().strip().encode("utf-8")).hexdigest()


def _get_email_domain(email: str) -> str | None:
    """Extract domain from email."""
    if "@" in email:
        return email.split("@")[-1].lower()
    return None


async def _load_subscription(
    session: AsyncSession, *, workspace_id: UUID, email_hash: str
) -> EmailSubscription | None:
    result = await session.execute(
        select(EmailSubscription).where(
            EmailSubscription.workspace_id == workspace_id,
            EmailSubscription.email_hash == email_hash,
        )
    )
    return result.scalar_one_or_none()


async def _load_campaign(
    session: AsyncSession, *, workspace_id: UUID, campaign_id: UUID
) -> EDMCampaign | None:
    result = await session.execute(
        select(EDMCampaign).where(
            EDMCampaign.id == campaign_id,
            EDMCampaign.workspace_id == workspace_id,
        )
    )
    return result.scalar_one_or_none()


async def _check_dedup_24h(
    session: AsyncSession, *, workspace_id: UUID, email_hash: str, campaign_id: UUID
) -> bool:
    """Check if recipient has received this campaign in the last 24 hours.

    Returns True if dedup block applies (should skip), False if OK to send.
    """
    settings = get_settings()
    window_hours = settings.edm_dedup_window_hours
    cutoff = datetime.now(UTC) - timedelta(hours=window_hours)

    result = await session.execute(
        select(EDMSendLog).where(
            EDMSendLog.workspace_id == workspace_id,
            EDMSendLog.email_hash == email_hash,
            EDMSendLog.campaign_id == campaign_id,
            EDMSendLog.status.in_(["sent", "dry_run"]),
            EDMSendLog.created_at >= cutoff,
        )
    )
    return result.scalar_one_or_none() is not None


# --------------------------------------------------------------------------- #
# Subscription management
# --------------------------------------------------------------------------- #


async def create_or_update_subscription(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    email: str,
    consent_given: bool = False,
    consent_source: str = "manual",
    consent_ip: str | None = None,
    consent_user_agent: str | None = None,
    tags: list[str] | None = None,
    trace_id: str | None = None,
) -> EmailSubscription:
    """Create or update email subscription. Idempotent by (workspace_id, email_hash)."""
    email_hash = _hash_email(email)
    existing = await _load_subscription(session, workspace_id=workspace_id, email_hash=email_hash)

    if existing:
        if consent_given and not existing.consent_given:
            existing.consent_given = True
            existing.consent_timestamp = datetime.now(UTC)
            existing.consent_source = consent_source
            existing.subscription_status = "subscribed"
            if consent_ip:
                existing.consent_ip = consent_ip
            if consent_user_agent:
                existing.consent_user_agent = consent_user_agent
        if tags:
            existing.tags = list(set(existing.tags + tags))
        await session.flush()
        return existing

    sub = EmailSubscription(
        workspace_id=workspace_id,
        email_hash=email_hash,
        email_domain=_get_email_domain(email),
        subscription_status="subscribed" if consent_given else "pending_confirmation",
        consent_given=consent_given,
        consent_timestamp=datetime.now(UTC) if consent_given else None,
        consent_source=consent_source,
        consent_ip=consent_ip,
        consent_user_agent=consent_user_agent,
        tags=tags or [],
        trace_id=trace_id,
    )
    session.add(sub)
    await session.flush()

    await event_service.create_event(
        session, workspace_id=workspace_id, event_type="edm.subscription_created",
        entity_type="email_subscription", entity_id=str(sub.id),
        payload={"consent_given": consent_given, "consent_source": consent_source},
        trace_id=trace_id,
    )
    return sub


async def unsubscribe(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    email: str,
    reason: str | None = None,
    trace_id: str | None = None,
) -> EmailSubscription:
    """Unsubscribe email. Honored immediately per GDPR."""
    email_hash = _hash_email(email)
    sub = await _load_subscription(session, workspace_id=workspace_id, email_hash=email_hash)
    if sub is None:
        # Create a record marking as unsubscribed to prevent future sends
        sub = EmailSubscription(
            workspace_id=workspace_id,
            email_hash=email_hash,
            email_domain=_get_email_domain(email),
            subscription_status="unsubscribed",
            consent_given=False,
            trace_id=trace_id,
        )
        session.add(sub)

    sub.subscription_status = "unsubscribed"
    sub.consent_given = False
    sub.unsubscribe_timestamp = datetime.now(UTC)
    sub.unsubscribe_reason = reason
    await session.flush()

    await event_service.create_event(
        session, workspace_id=workspace_id, event_type="edm.unsubscribed",
        entity_type="email_subscription", entity_id=str(sub.id),
        payload={"reason": reason}, trace_id=trace_id,
    )
    logger.info("email unsubscribed: workspace=%s hash=%s", workspace_id, email_hash[:16])
    return sub


# --------------------------------------------------------------------------- #
# Send pre-flight checks
# --------------------------------------------------------------------------- #


async def validate_send_preconditions(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    email: str,
    campaign_id: UUID,
) -> tuple[EmailSubscription, EDMCampaign]:
    """Validate all 6 preconditions before sending.

    Raises EDMSendBlocked with skip_reason if any check fails.
    Returns (subscription, campaign) if all pass.
    """
    settings = get_settings()

    # Check 1: EDM_SEND_ENABLED must be true
    if not settings.edm_send_enabled:
        raise EDMSendBlocked(
            "EDM send is disabled (edm_send_enabled=false). Set to true to enable.",
            skip_reason="send_disabled",
        )

    email_hash = _hash_email(email)

    # Check 2: Recipient must not be unsubscribed (GDPR: honored immediately)
    sub = await _load_subscription(session, workspace_id=workspace_id, email_hash=email_hash)
    if sub is not None and sub.subscription_status == "unsubscribed":
        raise EDMSendBlocked(
            f"Recipient is unsubscribed: {email_hash[:16]}",
            skip_reason="unsubscribed",
        )

    # Check 3: Recipient must have valid subscription consent
    if sub is None or not sub.consent_given:
        raise EDMSendBlocked(
            f"Recipient has no valid subscription consent: {email_hash[:16]}",
            skip_reason="no_consent",
        )

    # Check 4: Campaign must be approved (not draft)
    campaign = await _load_campaign(session, workspace_id=workspace_id, campaign_id=campaign_id)
    if campaign is None:
        raise EDMSendBlocked(f"Campaign not found: {campaign_id}", skip_reason="campaign_not_approved")
    if campaign.status == "draft":
        raise EDMSendBlocked(
            f"Campaign is in draft status, not approved: {campaign.name}",
            skip_reason="campaign_not_approved",
        )

    # Check 5: 24-hour dedup
    if await _check_dedup_24h(session, workspace_id=workspace_id, email_hash=email_hash, campaign_id=campaign_id):
        raise EDMSendBlocked(
            f"Recipient received this campaign within {settings.edm_dedup_window_hours}h (dedup)",
            skip_reason="dedup_24h",
        )

    # Check 6: Send content must be approved (campaign content_json not empty)
    if not campaign.content_json or not campaign.subject:
        raise EDMSendBlocked(
            "Campaign content is not approved/complete (missing subject or content)",
            skip_reason="content_not_approved",
        )

    return sub, campaign


# --------------------------------------------------------------------------- #
# Send execution
# --------------------------------------------------------------------------- #


async def send_edm_email(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    email: str,
    campaign_id: UUID,
    idempotency_key: str | None = None,
    dry_run: bool | None = None,
    trace_id: str | None = None,
) -> EDMSendLog:
    """Send EDM email with all safety checks.

    Default dry-run if not explicitly overridden and edm_dry_run_default=true.
    Idempotent: same idempotency_key returns existing log.
    Provider not configured -> skipped, never fakes success.
    """
    settings = get_settings()
    is_dry_run = dry_run if dry_run is not None else settings.edm_dry_run_default
    email_hash = _hash_email(email)
    idem_key = idempotency_key or f"edm-{campaign_id}-{email_hash}-{datetime.now(UTC).strftime('%Y%m%d')}"

    # Idempotency: return existing log if same key
    existing = await session.execute(
        select(EDMSendLog).where(
            EDMSendLog.workspace_id == workspace_id,
            EDMSendLog.idempotency_key == idem_key,
        )
    )
    existing_log = existing.scalar_one_or_none()
    if existing_log:
        logger.info("EDM send idempotent hit: key=%s status=%s", idem_key, existing_log.status)
        return existing_log

    # Create pending log
    log = EDMSendLog(
        workspace_id=workspace_id,
        campaign_id=campaign_id,
        email_hash=email_hash,
        idempotency_key=idem_key,
        status="pending",
        is_dry_run=is_dry_run,
        max_retries=settings.edm_max_retries,
        trace_id=trace_id,
    )
    session.add(log)

    try:
        # Run pre-flight checks
        sub, campaign = await validate_send_preconditions(
            session, workspace_id=workspace_id, email=email, campaign_id=campaign_id,
        )
        log.subscription_id = sub.id
        log.subject = campaign.subject
        log.from_email = campaign.from_email

        # Dry-run: record as dry_run, do not actually send (before provider check)
        if is_dry_run:
            # Dry-run: record as dry_run, do not actually send
            log.status = "dry_run"
            log.provider_response = {"dry_run": True, "would_send_to": email_hash[:16]}
            await session.flush()
            await event_service.create_event(
                session, workspace_id=workspace_id, event_type="edm.send_dry_run",
                entity_type="edm_send_log", entity_id=str(log.id),
                payload={"campaign_id": str(campaign_id), "email_hash": email_hash[:16]},
                trace_id=trace_id,
            )
            logger.info("EDM dry-run: campaign=%s email=%s", campaign_id, email_hash[:16])
            return log

        # Check provider configuration (only for real sends)
        if not settings.edm_provider:
            raise EDMProviderNotConfigured(
                "EDM provider not configured (edm_provider is empty). "
                "Configure SMTP/SendGrid/Mailgun/Resend to send real emails."
            )

        # Real send: call provider (integration point)
        # For now, provider integration is not implemented; raise to indicate
        # This is where SMTP/SendGrid/Mailgun/Resend API call would go
        raise EDMProviderNotConfigured(
            f"EDM provider '{settings.edm_provider}' integration not implemented. "
            "Send remains in pending state for manual execution."
        )

    except EDMSendBlocked as exc:
        log.status = "skipped"
        log.skip_reason = exc.skip_reason
        log.error_message = str(exc)
        await session.flush()
        await event_service.create_event(
            session, workspace_id=workspace_id, event_type="edm.send_skipped",
            entity_type="edm_send_log", entity_id=str(log.id),
            payload={"skip_reason": exc.skip_reason, "reason": str(exc)},
            trace_id=trace_id,
        )
        logger.info("EDM send skipped: reason=%s email=%s", exc.skip_reason, email_hash[:16])
        return log

    except EDMProviderNotConfigured as exc:
        log.status = "failed"
        log.error_message = str(exc)
        log.last_attempt_at = datetime.now(UTC)
        await session.flush()
        await event_service.create_event(
            session, workspace_id=workspace_id, event_type="edm.send_failed",
            entity_type="edm_send_log", entity_id=str(log.id),
            payload={"error": str(exc), "provider": settings.edm_provider},
            trace_id=trace_id,
        )
        logger.warning("EDM send failed (provider): %s", exc)
        return log

    except Exception as exc:
        log.status = "failed"
        log.error_message = str(exc)[:1000]
        log.last_attempt_at = datetime.now(UTC)
        log.retry_count += 1
        await session.flush()
        logger.error("EDM send failed: %s", exc)
        return log


async def retry_failed_send(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    send_log_id: UUID,
    trace_id: str | None = None,
) -> EDMSendLog:
    """Retry a failed send. Respects max_retries. Idempotent if already sent."""
    result = await session.execute(
        select(EDMSendLog).where(
            EDMSendLog.id == send_log_id,
            EDMSendLog.workspace_id == workspace_id,
        )
    )
    log = result.scalar_one_or_none()
    if log is None:
        raise EDMSendError(f"Send log not found: {send_log_id}")

    if log.status in ("sent", "dry_run"):
        logger.info("Send already succeeded, skip retry: id=%s", send_log_id)
        return log

    if log.status != "failed":
        raise EDMSendError(f"Can only retry failed sends, current status: {log.status}")

    if log.retry_count >= log.max_retries:
        raise EDMSendError(
            f"Max retries ({log.max_retries}) exceeded; manual intervention required"
        )

    # Re-run send with same idempotency key
    # Note: email is not stored in raw form, so we retry via the log's context
    # In production, would need to store encrypted email or retrieve from subscription
    log.retry_count += 1
    log.last_attempt_at = datetime.now(UTC)
    log.error_message = f"Retry attempt {log.retry_count}/{log.max_retries}: provider integration pending"
    await session.flush()

    await event_service.create_event(
        session, workspace_id=workspace_id, event_type="edm.send_retried",
        entity_type="edm_send_log", entity_id=str(log.id),
        payload={"retry_count": log.retry_count, "max_retries": log.max_retries},
        trace_id=trace_id,
    )
    return log


# --------------------------------------------------------------------------- #
# Queries
# --------------------------------------------------------------------------- #


async def get_send_log(
    session: AsyncSession, *, workspace_id: UUID, send_log_id: UUID
) -> EDMSendLog:
    result = await session.execute(
        select(EDMSendLog).where(
            EDMSendLog.id == send_log_id,
            EDMSendLog.workspace_id == workspace_id,
        )
    )
    log = result.scalar_one_or_none()
    if log is None:
        raise EDMSendError(f"Send log not found: {send_log_id}")
    return log


async def list_send_logs(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    campaign_id: UUID | None = None,
    status: str | None = None,
    email_hash: str | None = None,
    limit: int = 50,
) -> list[EDMSendLog]:
    query = select(EDMSendLog).where(EDMSendLog.workspace_id == workspace_id)
    if campaign_id:
        query = query.where(EDMSendLog.campaign_id == campaign_id)
    if status:
        query = query.where(EDMSendLog.status == status)
    if email_hash:
        query = query.where(EDMSendLog.email_hash == email_hash)
    query = query.order_by(EDMSendLog.created_at.desc()).limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())
