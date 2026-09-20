"""B2B pre-sales domain: RFQ, versioned quotes, and contracts."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import AI_JSON, Base, TimestampMixin, WorkspaceMixin

B2B_RFQ_STATUSES = [
    "draft",
    "submitted",
    "in_review",
    "quoted",
    "won",
    "lost",
    "cancelled",
]
B2B_QUOTE_STATUSES = [
    "draft",
    "pending_approval",
    "sent",
    "accepted",
    "rejected",
    "expired",
    "converted",
    "cancelled",
]
B2B_CONTRACT_STATUSES = [
    "draft",
    "pending_signature",
    "active",
    "expired",
    "terminated",
    "cancelled",
]


class B2BRFQ(Base, TimestampMixin, WorkspaceMixin):
    """Customer request for quotation."""

    __tablename__ = "b2b_rfqs"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    rfq_number: Mapped[str] = mapped_column(String(32), nullable=False)
    agent_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("b2b_agents.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    customer_account_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("customer_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft", index=True)
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="manual")
    requested_currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    destination_country: Mapped[str | None] = mapped_column(String(8), nullable=True)
    incoterm: Mapped[str | None] = mapped_column(String(16), nullable=True)
    requested_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    assigned_to: Mapped[str | None] = mapped_column(String(128), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[list["B2BRFQItem"]] = relationship(
        back_populates="rfq",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    quotes: Mapped[list["B2BQuote"]] = relationship(back_populates="rfq")

    __table_args__ = (
        UniqueConstraint("workspace_id", "rfq_number", name="uq_b2b_rfqs_workspace_number"),
        Index("ix_b2b_rfqs_workspace_status", "workspace_id", "status"),
        Index("ix_b2b_rfqs_workspace_agent", "workspace_id", "agent_id"),
    )


class B2BRFQItem(Base, WorkspaceMixin):
    """Requested product and quantity in an RFQ."""

    __tablename__ = "b2b_rfq_items"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    rfq_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("b2b_rfqs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    sku_snapshot: Mapped[str] = mapped_column(String(64), nullable=False)
    product_name_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    requested_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    target_unit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    specifications: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    rfq: Mapped["B2BRFQ"] = relationship(back_populates="items")

    __table_args__ = (
        CheckConstraint("requested_quantity > 0", name="ck_b2b_rfq_item_quantity"),
        CheckConstraint(
            "target_unit_price IS NULL OR target_unit_price > 0",
            name="ck_b2b_rfq_item_target_price",
        ),
    )


class B2BQuote(Base, TimestampMixin, WorkspaceMixin):
    """Versioned quotation. Approved or sent versions are immutable."""

    __tablename__ = "b2b_quotes"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    quote_number: Mapped[str] = mapped_column(String(32), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    rfq_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("b2b_rfqs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    agent_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("b2b_agents.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    customer_account_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("customer_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft", index=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    base_currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    exchange_rate_to_base: Mapped[Decimal] = mapped_column(
        Numeric(18, 8),
        nullable=False,
        default=1,
    )
    price_book_version_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("b2b_price_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    valid_until: Mapped[date] = mapped_column(Date, nullable=False)
    payment_terms_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    incoterm: Mapped[str | None] = mapped_column(String(16), nullable=True)
    shipping_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    shipping_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    rfq: Mapped["B2BRFQ | None"] = relationship(back_populates="quotes")
    items: Mapped[list["B2BQuoteItem"]] = relationship(
        back_populates="quote",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    contract: Mapped["B2BContract | None"] = relationship(
        back_populates="quote",
        uselist=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "quote_number",
            "version_number",
            name="uq_b2b_quotes_workspace_number_version",
        ),
        CheckConstraint("version_number >= 1", name="ck_b2b_quote_version"),
        CheckConstraint("exchange_rate_to_base > 0", name="ck_b2b_quote_exchange_rate"),
        Index("ix_b2b_quotes_workspace_status", "workspace_id", "status"),
        Index("ix_b2b_quotes_workspace_agent", "workspace_id", "agent_id"),
    )


class B2BQuoteItem(Base, WorkspaceMixin):
    """Immutable quote line item snapshot."""

    __tablename__ = "b2b_quote_items"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    quote_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("b2b_quotes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rfq_item_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("b2b_rfq_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    product_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    sku_snapshot: Mapped[str] = mapped_column(String(64), nullable=False)
    product_name_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    line_subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    price_tier_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("b2b_price_tiers.id", ondelete="SET NULL"),
        nullable=True,
    )
    price_source: Mapped[str] = mapped_column(String(16), nullable=False, default="TIER")
    cost_snapshot: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    specifications: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    quote: Mapped["B2BQuote"] = relationship(back_populates="items")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_b2b_quote_item_quantity"),
        CheckConstraint("unit_price > 0", name="ck_b2b_quote_item_unit_price"),
        CheckConstraint(
            "discount_percent >= 0 AND discount_percent <= 100",
            name="ck_b2b_quote_item_discount",
        ),
    )


class B2BContract(Base, TimestampMixin, WorkspaceMixin):
    """Contract created from an accepted quote."""

    __tablename__ = "b2b_contracts"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    contract_number: Mapped[str] = mapped_column(String(32), nullable=False)
    quote_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("b2b_quotes.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )
    agent_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("b2b_agents.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    customer_account_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("customer_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft", index=True)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    document_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    terms: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    customer_signed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    customer_signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    company_signed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    company_signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    terminated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    quote: Mapped["B2BQuote"] = relationship(back_populates="contract")

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "contract_number",
            name="uq_b2b_contracts_workspace_number",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_b2b_contract_effective_period",
        ),
        Index("ix_b2b_contracts_workspace_status", "workspace_id", "status"),
        Index("ix_b2b_contracts_workspace_agent", "workspace_id", "agent_id"),
    )
