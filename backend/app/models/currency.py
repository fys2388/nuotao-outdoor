"""Auditable exchange-rate snapshots used by reporting and profit calculations."""

from __future__ import annotations

from datetime import date  # noqa: TC003 - SQLAlchemy resolves annotations
from decimal import Decimal  # noqa: TC003 - SQLAlchemy resolves annotations
from uuid import uuid4

from sqlalchemy import CheckConstraint, Date, Index, Numeric, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin, WorkspaceMixin


class ExchangeRate(Base, CreatedAtMixin, WorkspaceMixin):
    """One workspace-scoped daily rate.

    ``rate`` means one unit of ``base_currency`` equals ``rate`` units of
    ``quote_currency``. Rows are treated as immutable evidence; a correction
    is stored as a new row on its effective date.
    """

    __tablename__ = "exchange_rates"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    base_currency: Mapped[str] = mapped_column(String(8), nullable=False)
    quote_currency: Mapped[str] = mapped_column(String(8), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(20, 12), nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="manual")
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "base_currency",
            "quote_currency",
            "effective_date",
            name="uq_exchange_rates_workspace_pair_date",
        ),
        CheckConstraint(
            "base_currency <> quote_currency",
            name="ck_exchange_rates_distinct_currency",
        ),
        CheckConstraint("rate > 0", name="ck_exchange_rates_positive"),
        Index(
            "ix_exchange_rates_workspace_pair_date",
            "workspace_id",
            "base_currency",
            "quote_currency",
            "effective_date",
        ),
    )
