"""Settlement domain model: cash-in ledger for COD / clearance / fees.

The ledger makes the cash loop auditable: every expected receipt (COD payout,
customs bill) is registered with an amount, carrier and due date; receipts
advance the status machine expected -> partial -> received. Disputed entries
are kept open for follow-up instead of being silently written off.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, WorkspaceMixin


class Settlement(Base, TimestampMixin, WorkspaceMixin):
    """A single expected or received cash settlement (COD, clearance, fee)."""

    __tablename__ = "settlements"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    order_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    external_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    carrier: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    settlement_kind: Mapped[str] = mapped_column(String(24), nullable=False, default="cod")
    expected_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    received_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    fees: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="expected", index=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
