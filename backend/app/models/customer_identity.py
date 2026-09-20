"""Cross-channel customer identity, consent, and privacy request models.

Raw identity values never enter these tables. The service layer normalizes a
value in memory and stores only a workspace-derived HMAC-SHA256 fingerprint.
Consent and request action rows are append-only audit ledgers.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AI_JSON, Base, CreatedAtMixin, TimestampMixin, WorkspaceMixin

IDENTITY_CHANNELS: tuple[str, ...] = (
    "b2c_store",
    "b2b_portal",
    "email",
    "support",
    "crm",
    "other",
)
IDENTITY_TYPES: tuple[str, ...] = (
    "email",
    "phone",
    "woocommerce_customer_id",
    "company_tax_id",
    "other",
)
IDENTITY_VERIFICATION_STATUSES: tuple[str, ...] = (
    "pending",
    "verified",
    "conflict",
    "rejected",
    "revoked",
    "merged",
)
MERGE_STATUSES: tuple[str, ...] = (
    "pending",
    "approved",
    "rejected",
    "completed",
    "cancelled",
)
CONSENT_PURPOSES: tuple[str, ...] = (
    "marketing_email",
    "transactional_email",
    "analytics",
    "personalization",
    "ai_processing",
)
CONSENT_STATUSES: tuple[str, ...] = ("granted", "withdrawn")
DATA_SUBJECT_REQUEST_TYPES: tuple[str, ...] = (
    "access",
    "export",
    "delete",
    "correct",
    "restrict",
)
DATA_SUBJECT_REQUEST_STATUSES: tuple[str, ...] = (
    "received",
    "verifying",
    "approved",
    "processing",
    "completed",
    "rejected",
    "cancelled",
)
PRIVACY_ACTION_TYPES: tuple[str, ...] = (
    "received",
    "verified",
    "approved",
    "rejected",
    "export_generated",
    "identity_links_revoked",
    "consent_withdrawn",
    "profile_erased",
    "b2b_contact_anonymized",
    "account_anonymized",
    "completed",
    "manual_review",
)


class CustomerIdentityLink(Base, TimestampMixin, WorkspaceMixin):
    """One channel identity fingerprint linked to a unified account."""

    __tablename__ = "customer_identity_links"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    customer_account_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("customer_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    external_system: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    identity_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    identity_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    hash_key_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    fingerprint: Mapped[str] = mapped_column(String(32), nullable=False)
    verification_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="verified",
        index=True,
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="manual")
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    disabled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        AI_JSON,
        nullable=False,
        default=dict,
    )
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "customer_account_id",
            "channel",
            "external_system",
            "identity_type",
            "identity_hash",
            name="uq_customer_identity_links_account_identity",
        ),
        CheckConstraint(
            "channel IN ("
            "'b2c_store','b2b_portal','email','support','crm','other'"
            ")",
            name="ck_customer_identity_link_channel",
        ),
        CheckConstraint(
            "identity_type IN ("
            "'email','phone','woocommerce_customer_id','company_tax_id','other'"
            ")",
            name="ck_customer_identity_link_type",
        ),
        CheckConstraint(
            "verification_status IN ("
            "'pending','verified','conflict','rejected','revoked','merged'"
            ")",
            name="ck_customer_identity_link_status",
        ),
        Index(
            "ix_customer_identity_links_workspace_hash",
            "workspace_id",
            "identity_type",
            "identity_hash",
        ),
        Index(
            "ix_customer_identity_links_workspace_account_status",
            "workspace_id",
            "customer_account_id",
            "verification_status",
        ),
    )


class CustomerAccountMerge(Base, TimestampMixin, WorkspaceMixin):
    """Human-reviewed merge of two customer accounts using deterministic evidence."""

    __tablename__ = "customer_account_merges"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    source_account_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("customer_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_account_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("customer_accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="pending",
        index=True,
    )
    match_type: Mapped[str] = mapped_column(String(32), nullable=False)
    match_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(
        AI_JSON,
        nullable=False,
        default=dict,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    requested_by: Mapped[str] = mapped_column(String(128), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    result_summary: Mapped[dict[str, Any]] = mapped_column(
        AI_JSON,
        nullable=False,
        default=dict,
    )
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','approved','rejected','completed','cancelled')",
            name="ck_customer_account_merge_status",
        ),
        CheckConstraint(
            "source_account_id <> target_account_id",
            name="ck_customer_account_merge_distinct_accounts",
        ),
        Index(
            "ix_customer_account_merges_workspace_status",
            "workspace_id",
            "status",
        ),
        Index(
            "ix_customer_account_merges_source_status",
            "workspace_id",
            "source_account_id",
            "status",
        ),
    )


class CustomerConsentEvent(Base, CreatedAtMixin, WorkspaceMixin):
    """Append-only consent grant or withdrawal for one purpose and channel."""

    __tablename__ = "customer_consent_events"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    customer_account_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("customer_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    purpose: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    recorded_by: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(
        AI_JSON,
        nullable=False,
        default=dict,
    )
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "idempotency_key",
            name="uq_customer_consent_events_workspace_idempotency",
        ),
        CheckConstraint(
            "purpose IN ("
            "'marketing_email','transactional_email','analytics',"
            "'personalization','ai_processing'"
            ")",
            name="ck_customer_consent_event_purpose",
        ),
        CheckConstraint(
            "channel IN ("
            "'b2c_store','b2b_portal','email','support','crm','other'"
            ")",
            name="ck_customer_consent_event_channel",
        ),
        CheckConstraint(
            "status IN ('granted','withdrawn')",
            name="ck_customer_consent_event_status",
        ),
        Index(
            "ix_customer_consent_events_workspace_account_purpose",
            "workspace_id",
            "customer_account_id",
            "purpose",
            "channel",
            "occurred_at",
        ),
    )


class DataSubjectRequest(Base, TimestampMixin, WorkspaceMixin):
    """GDPR-style customer request with verification, decision, and deadline."""

    __tablename__ = "data_subject_requests"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    request_number: Mapped[str] = mapped_column(String(48), nullable=False)
    customer_account_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("customer_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    request_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="received",
        index=True,
    )
    identity_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    verification_method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verified_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    handled_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_summary: Mapped[dict[str, Any]] = mapped_column(
        AI_JSON,
        nullable=False,
        default=dict,
    )
    evidence_json: Mapped[dict[str, Any]] = mapped_column(
        AI_JSON,
        nullable=False,
        default=dict,
    )
    requested_by: Mapped[str] = mapped_column(String(128), nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "request_number",
            name="uq_data_subject_requests_workspace_number",
        ),
        CheckConstraint(
            "request_type IN ('access','export','delete','correct','restrict')",
            name="ck_data_subject_request_type",
        ),
        CheckConstraint(
            "status IN ("
            "'received','verifying','approved','processing','completed',"
            "'rejected','cancelled'"
            ")",
            name="ck_data_subject_request_status",
        ),
        Index(
            "ix_data_subject_requests_workspace_status_due",
            "workspace_id",
            "status",
            "due_at",
        ),
    )


class DataSubjectRequestAction(Base, CreatedAtMixin, WorkspaceMixin):
    """Append-only execution history for a data subject request."""

    __tablename__ = "data_subject_request_actions"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    request_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("data_subject_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[dict[str, Any]] = mapped_column(
        AI_JSON,
        nullable=False,
        default=dict,
    )
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "action_type IN ("
            "'received','verified','approved','rejected','export_generated',"
            "'identity_links_revoked','consent_withdrawn','profile_erased',"
            "'b2b_contact_anonymized','account_anonymized','completed',"
            "'manual_review'"
            ")",
            name="ck_data_subject_request_action_type",
        ),
        Index(
            "ix_data_subject_request_actions_workspace_request",
            "workspace_id",
            "request_id",
            "created_at",
        ),
    )
