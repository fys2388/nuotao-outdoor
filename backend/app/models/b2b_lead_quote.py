"""B2B lead quote domain model (M440-04).

A quote is versioned and immutable once approved: an approved quote is never
overwritten in place - a new version is created instead. Quotes are internal
only; they are never returned by public routes and are never auto-sent to a
lead without an explicit human approval.

Spec: reports/b2b/CHATGPT_M1_M2_SPEC.md (M1.x) + M4.4 M440-04 instruction.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, WorkspaceMixin

# Quote approval lifecycle (internal). Never sent to a lead unless approved.
B2B_QUOTE_APPROVAL_STATUSES = ["draft", "pending", "approved", "rejected"]


class B2BLeadQuote(Base, TimestampMixin, WorkspaceMixin):
    """A versioned quote attached to a public B2B lead.

    Immutable once approved: a new version (``quote_version`` + 1) is created
    instead of mutating the approved row. Never exposed through public routes.
    """

    __tablename__ = "b2b_lead_quotes"

    id: Mapped[Any] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    lead_id: Mapped[Any] = mapped_column(
        Uuid,
        ForeignKey("b2b_leads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    quote_number: Mapped[str] = mapped_column(String(32), nullable=False)
    quote_version: Mapped[int] = mapped_column(nullable=False, default=1)

    # Commercial terms. Currency is explicit; no implicit conversion is made.
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    unit_price: Mapped[Any] = mapped_column(Numeric(12, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False, default=1)
    shipping_cost: Mapped[Any] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    estimated_total: Mapped[Any] = mapped_column(Numeric(14, 2), nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payment_terms: Mapped[str | None] = mapped_column(String(64), nullable=True)
    shipping_terms: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Internal approval gate (human-in-the-loop). Never auto-sent without it.
    approval_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft"
    )
    approved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "approval_status IN ('draft','pending','approved','rejected')",
            name="ck_b2b_lead_quotes_approval",
        ),
        Index("ix_b2b_lead_quotes_lead_version", "lead_id", "quote_version"),
    )
