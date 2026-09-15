"""B2B accounts receivable: invoices, receipts, and immutable ledger entries."""

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
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import AI_JSON, Base, CreatedAtMixin, TimestampMixin, WorkspaceMixin

B2B_INVOICE_STATUSES = [
    "draft",
    "issued",
    "partially_paid",
    "paid",
    "overdue",
    "written_off",
    "void",
]
B2B_RECEIPT_STATUSES = [
    "unapplied",
    "partially_applied",
    "applied",
]
B2B_RECEIVABLE_ENTRY_TYPES = [
    "charge",
    "payment",
    "write_off",
    "adjustment",
]


class B2BInvoice(Base, TimestampMixin, WorkspaceMixin):
    """Invoice generated from one B2B order."""

    __tablename__ = "b2b_invoices"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    invoice_number: Mapped[str] = mapped_column(String(32), nullable=False)
    order_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("b2b_orders.id", ondelete="RESTRICT"),
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
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="draft",
        index=True,
    )
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    shipping_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    amount_written_off: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=0,
    )
    balance_due: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    items_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(
        AI_JSON,
        nullable=False,
        default=list,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    entries: Mapped[list["B2BReceivableEntry"]] = relationship(
        back_populates="invoice",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "invoice_number",
            name="uq_b2b_invoices_workspace_number",
        ),
        CheckConstraint("subtotal >= 0", name="ck_b2b_invoice_subtotal"),
        CheckConstraint("discount_amount >= 0", name="ck_b2b_invoice_discount"),
        CheckConstraint("shipping_amount >= 0", name="ck_b2b_invoice_shipping"),
        CheckConstraint("tax_amount >= 0", name="ck_b2b_invoice_tax"),
        CheckConstraint("total > 0", name="ck_b2b_invoice_total"),
        CheckConstraint("amount_paid >= 0", name="ck_b2b_invoice_paid"),
        CheckConstraint("amount_written_off >= 0", name="ck_b2b_invoice_write_off"),
        CheckConstraint("balance_due >= 0", name="ck_b2b_invoice_balance"),
        Index("ix_b2b_invoices_workspace_status", "workspace_id", "status"),
        Index("ix_b2b_invoices_workspace_due", "workspace_id", "due_date"),
        Index("ix_b2b_invoices_workspace_agent", "workspace_id", "agent_id"),
    )


class B2BReceipt(Base, TimestampMixin, WorkspaceMixin):
    """Cash receipt that may be allocated across invoices."""

    __tablename__ = "b2b_receipts"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    receipt_number: Mapped[str] = mapped_column(String(32), nullable=False)
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
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="unapplied",
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    unapplied_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    payment_method: Mapped[str] = mapped_column(String(32), nullable=False, default="bank_transfer")
    bank_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)

    entries: Mapped[list["B2BReceivableEntry"]] = relationship(
        back_populates="receipt",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "receipt_number",
            name="uq_b2b_receipts_workspace_number",
        ),
        UniqueConstraint(
            "workspace_id",
            "idempotency_key",
            name="uq_b2b_receipts_workspace_idempotency",
        ),
        CheckConstraint("amount > 0", name="ck_b2b_receipt_amount"),
        CheckConstraint(
            "unapplied_amount >= 0 AND unapplied_amount <= amount",
            name="ck_b2b_receipt_unapplied",
        ),
        Index("ix_b2b_receipts_workspace_status", "workspace_id", "status"),
        Index("ix_b2b_receipts_workspace_agent", "workspace_id", "agent_id"),
        Index("ix_b2b_receipts_workspace_received", "workspace_id", "received_at"),
    )


class B2BReceivableEntry(Base, CreatedAtMixin, WorkspaceMixin):
    """Append-only receivable ledger entry.

    Positive amounts increase the receivable; negative amounts reduce it.
    ``entry_key`` makes charge, allocation, and write-off idempotent.
    """

    __tablename__ = "b2b_receivable_entries"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    agent_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("b2b_agents.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    invoice_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("b2b_invoices.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    receipt_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("b2b_receipts.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    entry_type: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    entry_key: Mapped[str] = mapped_column(String(192), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)

    invoice: Mapped[B2BInvoice] = relationship(back_populates="entries")
    receipt: Mapped[B2BReceipt | None] = relationship(back_populates="entries")

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "entry_key",
            name="uq_b2b_receivable_entries_workspace_key",
        ),
        CheckConstraint("amount <> 0", name="ck_b2b_receivable_entry_nonzero"),
        Index("ix_b2b_receivable_entries_workspace_type", "workspace_id", "entry_type"),
        Index("ix_b2b_receivable_entries_workspace_agent", "workspace_id", "agent_id"),
    )
