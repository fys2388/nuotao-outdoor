"""Customer intelligence models (M3.3): profiles, interactions, reviews, refunds, knowledge.

Builds the customer-awareness data layer for the future Customer Agent.
**PII policy**: profiles store only a non-identifying ``customer_reference_id``
plus market/behavioral fields - never names, emails, addresses or phone
numbers. Every write is workspace-scoped and must emit an event_log entry.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AI_JSON, Base, CreatedAtMixin, TimestampMixin, WorkspaceMixin

# Customer knowledge entry types (Phase 1).
CUSTOMER_ENTRY_TYPES: tuple[str, ...] = (
    "purchase_pattern",
    "pain_point",
    "segment_pattern",
    "refund_pattern",
    "loyalty_pattern",
    "churn_pattern",
    "bundle_pattern",
    "pain_pattern",
)

# Interaction channels (Phase 1).
INTERACTION_CHANNELS: tuple[str, ...] = ("email", "chat", "review", "social")


class CustomerProfile(Base, TimestampMixin, WorkspaceMixin):
    """Non-PII customer profile (M3.3).

    ``customer_reference_id`` is the external identifier (e.g. WooCommerce
    customer id) - it is a key, not PII. Behavioral/aggregate fields only.
    """

    __tablename__ = "customer_profiles"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    customer_reference_id: Mapped[str] = mapped_column(String(128), nullable=False)
    country: Mapped[str | None] = mapped_column(String(8), nullable=True)
    language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    segment: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tags: Mapped[list[Any]] = mapped_column(AI_JSON, nullable=False, default=list)
    first_order_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_orders: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_revenue: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "customer_reference_id",
            name="uq_customer_profiles_workspace_reference",
        ),
        Index("ix_customer_profiles_workspace_segment", "workspace_id", "segment"),
    )


class CustomerInteraction(Base, CreatedAtMixin, WorkspaceMixin):
    """Append-only customer interaction record (M3.3).

    Email/chat/review/social interactions are logs: content is immutable and
    only classification fields (sentiment) may be updated later.
    """

    __tablename__ = "customer_interactions"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    customer_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("customer_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    product_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    channel: Mapped[str] = mapped_column(String(16), nullable=False, default="other")
    interaction_type: Mapped[str] = mapped_column(String(32), nullable=False, default="message")
    content: Mapped[str] = mapped_column(String(4000), nullable=False)
    sentiment: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", AI_JSON, nullable=False, default=dict
    )
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index(
            "ix_customer_interactions_workspace_customer",
            "workspace_id",
            "customer_id",
        ),
        Index(
            "ix_customer_interactions_workspace_channel",
            "workspace_id",
            "channel",
        ),
    )


class ProductReview(Base, CreatedAtMixin, WorkspaceMixin):
    """Append-only product review (M3.3).

    Reviews are external records (platform + rating + content); sentiment and
    issue classification may be refined later without rewriting the content.
    """

    __tablename__ = "product_reviews"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    product_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    platform: Mapped[str] = mapped_column(String(16), nullable=False, default="other")
    rating: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    content: Mapped[str] = mapped_column(String(4000), nullable=False)
    sentiment: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    issue_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    keywords: Mapped[list[Any]] = mapped_column(AI_JSON, nullable=False, default=list)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_product_reviews_workspace_product", "workspace_id", "product_id"),
        Index("ix_product_reviews_workspace_sentiment", "workspace_id", "sentiment"),
    )


class RefundCase(Base, TimestampMixin, WorkspaceMixin):
    """Refund/return case with full lifecycle (M1 refund flow).

    State machine:
      requested -> pending_approval -> approved -> processing -> succeeded
      requested -> pending_approval -> rejected
      requested -> cancelled
      processing -> failed (retryable up to max_retries)

    Monetary amounts use Numeric/Decimal. Idempotency enforced by
    (workspace_id, order_id, idempotency_key) unique constraint.
    Refund amount cannot exceed order.total - order.refunded_amount.
    """

    __tablename__ = "refund_cases"

    # Refund status state machine.
    REFUND_STATUSES = (
        "requested", "pending_approval", "approved",
        "processing", "succeeded", "rejected", "failed", "cancelled",
    )
    REFUND_TYPES = ("full", "partial")
    PAYMENT_PROVIDERS = ("stripe", "paypal", "woocommerce", "manual")

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    order_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    customer_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("customer_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    product_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # --- Refund request fields ---
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False, default="other")
    refund_type: Mapped[str] = mapped_column(String(16), nullable=False, default="partial")
    requested_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    # Legacy amount field kept for backward compat; equals requested_amount.
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)

    # --- Lifecycle / status ---
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="requested", index=True)
    # Legacy resolution field kept for backward compat.
    resolution: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # --- Approval ---
    approved_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # --- Execution ---
    executed_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payment_provider: Mapped[str] = mapped_column(String(32), nullable=False, default="woocommerce")
    payment_refund_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    woocommerce_refund_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # --- Retry / failure ---
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    last_failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Idempotency & audit ---
    idempotency_key: Mapped[str] = mapped_column(
        String(128), nullable=False, default=lambda: f"auto-{uuid4()}"
    )
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "order_id", "idempotency_key",
            name="uq_refund_cases_workspace_order_idempotency",
        ),
        Index("ix_refund_cases_workspace_status", "workspace_id", "status"),
        Index("ix_refund_cases_workspace_category", "workspace_id", "category"),
        Index("ix_refund_cases_workspace_product", "workspace_id", "product_id"),
        Index("ix_refund_cases_payment_refund_id", "payment_refund_id"),
    )


class CustomerKnowledgeEntry(Base, TimestampMixin, WorkspaceMixin):
    """Customer knowledge memory (M3.3).

    Entry types: ``purchase_pattern`` / ``pain_point`` / ``segment_pattern`` /
    ``refund_pattern`` / ``loyalty_pattern``. Queryable by category, customer
    or product so the future Customer Agent can ground replies in evidence.
    """

    __tablename__ = "customer_knowledge_entries"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    customer_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("customer_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    product_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    category: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    entry_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(String(4000), nullable=False)
    tags: Mapped[list[Any]] = mapped_column(AI_JSON, nullable=False, default=list)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=0)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index(
            "ix_customer_knowledge_workspace_cat",
            "workspace_id",
            "category",
        ),
        Index(
            "ix_customer_knowledge_workspace_customer",
            "workspace_id",
            "customer_id",
        ),
    )
