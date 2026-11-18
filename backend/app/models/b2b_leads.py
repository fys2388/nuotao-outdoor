"""B2B public-website lead domain model.

Separates inbound public enquiries (``b2b_leads``) from approved partner
accounts (``b2b_agents``). A public ``Request a Quote`` submission creates a
lead, never an agent account. A qualified lead is converted into a formal B2B
partner application by an internal operator as an explicit action.

Spec source: reports/b2b/CHATGPT_M1_M2_SPEC.md (M1.1 / M1.4 / M1.5).
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
    String,
    Text,
    UniqueConstraint,
    Uuid,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AI_JSON, Base, TimestampMixin, WorkspaceMixin

# Public lead lifecycle (distinct from b2b_agents account statuses).
# M2.5.1: split terminal "closed" into converted / closed_lost / spam so that
# commercial reporting can distinguish won, lost and junk enquiries.
# M440-02: expand to the full sales-workflow state machine required by the
# M4.4 instruction (NEW/ASSIGNED/CONTACTED/QUALIFIED/QUOTING/QUOTED/
# NEGOTIATING/CONVERTED/CLOSED_WON/CLOSED_LOST/SPAM). "reviewing" is dropped
# (replaced by ASSIGNED) and the quoting/negotiating/closed_won states are added.
B2B_LEAD_STATUSES = [
    "new",
    "assigned",
    "contacted",
    "qualified",
    "quoting",
    "quoted",
    "negotiating",
    "converted",
    "closed_won",
    "closed_lost",
    "spam",
]

# Where the lead came from. Public website leads are stamped server-side.
B2B_LEAD_SOURCES = [
    "b2b_public_website",
    "manual",
]

# Business type options offered on the public Request a Quote form.
B2B_LEAD_BUSINESS_TYPES = [
    "retailer",
    "distributor",
    "wholesaler",
    "ecommerce_seller",
    "brand",
    "other",
]


class B2BLead(Base, TimestampMixin, WorkspaceMixin):
    """A public B2B enquiry submitted from the no-price showcase website.

    Deliberately separate from :class:`b2b_agents` so that anonymous public
    traffic can never create a partner account. Internal notes and conversion
    tracking live here and are never exposed through public routes.
    """

    __tablename__ = "b2b_leads"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    reference_number: Mapped[str] = mapped_column(String(32), nullable=False)

    # Required enquiry fields (public Request a Quote form).
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    contact_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str] = mapped_column(String(64), nullable=False)
    business_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # Public product slugs / labels the enquirer is interested in.
    products_of_interest: Mapped[list[Any] | None] = mapped_column(AI_JSON, nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    privacy_consent: Mapped[bool] = mapped_column(Boolean, nullable=False)
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Optional enquiry fields.
    company_website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    whatsapp: Mapped[str | None] = mapped_column(String(64), nullable=True)
    wechat: Mapped[str | None] = mapped_column(String(64), nullable=True)
    estimated_order_quantity: Mapped[str | None] = mapped_column(String(64), nullable=True)
    annual_purchase_range: Mapped[str | None] = mapped_column(String(64), nullable=True)
    destination_market: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # Provenance + lifecycle (server-controlled).
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="b2b_public_website")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="new", index=True)

    # Internal-only management fields (never exposed publicly).
    assigned_to: Mapped[str | None] = mapped_column(String(128), nullable=True)
    internal_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    follow_ups: Mapped[list[Any] | None] = mapped_column(AI_JSON, nullable=True)

    # Conversion to a formal partner application (explicit internal action).
    converted_application_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("b2b_agents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    converted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # M2.5.1: documented reasons for the new terminal states. Required by the
    # service layer when a lead moves to closed_lost or spam.
    closed_lost_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    spam_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # M440-02/M440-05/M440-07: full sales-workflow state machine additions.
    # - closed_won_reason: documented win note for the closed_won terminal state.
    # - trace_id: provenance trace for the lead request chain.
    # - is_test: validation/test lead marker (excluded from real commercial stats).
    # - notify_status/notify_attempts/notify_last_error/notified_at:
    #   notification reliability (M440-05) - track, retry, never double-notify.
    closed_won_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_test: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    notify_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    notify_attempts: Mapped[int | None] = mapped_column(nullable=True)
    notify_last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- PII 加密字段（APR-M440-PII-001 设计/Staging 阶段；生产未批）------
    # email_hash：HMAC-SHA-256 摘要，唯一索引（等值检索用，不用明文查库）。
    # email_encrypted / contact_name_encrypted：AES-256-GCM base64(iv||ct||tag)。
    # pii_key_version：轮换版本标签。
    email_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    email_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_name_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    pii_key_version: Mapped[str | None] = mapped_column(String(16), nullable=True)

    __table_args__ = (
        UniqueConstraint("reference_number", name="uq_b2b_leads_reference_number"),
        CheckConstraint(
            "status IN ('new','assigned','contacted','qualified','quoting',"
            "'quoted','negotiating','converted','closed_won','closed_lost','spam')",
            name="ck_b2b_leads_status",
        ),
        CheckConstraint(
            "source IN ('b2b_public_website','manual')",
            name="ck_b2b_leads_source",
        ),
        Index("ix_b2b_leads_status_created", "status", "created_at"),
        Index("ix_b2b_leads_email", "email"),
        Index("ix_b2b_leads_country", "country"),
    )