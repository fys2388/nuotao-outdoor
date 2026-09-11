"""EDM subscription and send log models (M3.2 GDPR compliance).

email_subscriptions tracks consent, unsubscribe status, and send history.
edm_send_logs records every send attempt with idempotency key, status,
and skip reason for audit and retry.

GDPR baseline:
- Explicit consent required before any marketing email
- Unsubscribe honored immediately
- 24-hour dedup window per recipient
- Send disabled by default (EDM_SEND_ENABLED=false)
- Dry-run by default; real send requires explicit config switch
"""

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AI_JSON, Base, TimestampMixin, WorkspaceMixin

# Subscription statuses.
SUBSCRIPTION_STATUSES: tuple[str, ...] = (
    "subscribed",
    "unsubscribed",
    "bounced",
    "complained",
    "pending_confirmation",
)

# Consent sources.
CONSENT_SOURCES: tuple[str, ...] = (
    "checkout",
    "signup_form",
    "import",
    "manual",
    "api",
)

# EDM send statuses.
SEND_STATUSES: tuple[str, ...] = (
    "pending",
    "sent",
    "failed",
    "skipped",
    "dry_run",
)

# Skip reasons.
SKIP_REASONS: tuple[str, ...] = (
    "send_disabled",
    "no_consent",
    "unsubscribed",
    "campaign_not_approved",
    "content_not_approved",
    "dedup_24h",
    "invalid_email",
    "provider_not_configured",
)


class EmailSubscription(Base, TimestampMixin, WorkspaceMixin):
    """Email subscription with GDPR consent tracking (M3.2).

    Stores email_hash (not raw email) for PII minimization. Raw email
    should be stored in a separate encrypted PII store if needed.
    """

    __tablename__ = "email_subscriptions"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    email_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    email_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subscription_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending_confirmation", index=True
    )

    # Consent tracking.
    consent_given: Mapped[bool] = mapped_column(nullable=False, default=False, index=True)
    consent_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consent_source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    consent_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    consent_user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Unsubscribe tracking.
    unsubscribe_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    unsubscribe_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Send history.
    last_email_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_emails_sent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_opened: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_clicked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Metadata.
    tags: Mapped[list[str]] = mapped_column(AI_JSON, nullable=False, default=list)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint("workspace_id", "email_hash", name="uq_email_subscriptions_workspace_hash"),
        Index("ix_email_subscriptions_workspace_status", "workspace_id", "subscription_status"),
        Index("ix_email_subscriptions_workspace_consent", "workspace_id", "consent_given"),
    )


class EDMSendLog(Base, TimestampMixin, WorkspaceMixin):
    """EDM send attempt log with idempotency and audit (M3.2).

    Records every send attempt: success, failure, skip, or dry-run.
    Idempotency key prevents duplicate sends. Retry count and max retries
    support failure recovery.
    """

    __tablename__ = "edm_send_logs"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    campaign_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("edm_campaigns.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    subscription_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("email_subscriptions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    email_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    # Idempotency.
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)

    # Send status.
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    skip_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Retry.
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Provider response.
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_response: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)

    # Content snapshot (for audit).
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    from_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Metadata.
    is_dry_run: Mapped[bool] = mapped_column(nullable=False, default=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "idempotency_key",
            name="uq_edm_send_logs_workspace_idempotency",
        ),
        Index("ix_edm_send_logs_workspace_status", "workspace_id", "status"),
        Index("ix_edm_send_logs_workspace_campaign", "workspace_id", "campaign_id"),
        Index("ix_edm_send_logs_workspace_email", "workspace_id", "email_hash"),
    )
