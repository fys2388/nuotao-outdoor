"""B2B agent agreements, rebate tiers, and rebate accruals."""

from __future__ import annotations

from datetime import date, datetime  # noqa: TC003 - SQLAlchemy resolves annotations
from decimal import Decimal  # noqa: TC003 - SQLAlchemy resolves annotations
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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import AI_JSON, Base, TimestampMixin, WorkspaceMixin

B2B_AGREEMENT_STATUSES = [
    "draft",
    "pending_approval",
    "active",
    "rejected",
    "expired",
    "terminated",
]
B2B_REBATE_QUALIFICATION_BASES = ["ordered", "invoiced", "paid"]
B2B_REBATE_CALCULATION_METHODS = ["retroactive"]
B2B_REBATE_ACCRUAL_STATUSES = [
    "draft",
    "pending_approval",
    "approved",
    "rejected",
    "settled",
]


class B2BAgentAgreement(Base, TimestampMixin, WorkspaceMixin):
    """Annual or custom-period agreement for one B2B agent."""

    __tablename__ = "b2b_agent_agreements"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    agreement_number: Mapped[str] = mapped_column(String(32), nullable=False)
    agent_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("b2b_agents.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft", index=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date] = mapped_column(Date, nullable=False)
    target_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    qualification_basis: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="invoiced",
    )
    calculation_method: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="retroactive",
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    submitted_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    terminated_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    terminated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    termination_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    tiers: Mapped[list[B2BRebateTier]] = relationship(
        back_populates="agreement",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="B2BRebateTier.min_sales_amount",
    )
    accruals: Mapped[list[B2BRebateAccrual]] = relationship(
        back_populates="agreement",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "agreement_number",
            name="uq_b2b_agent_agreements_workspace_number",
        ),
        CheckConstraint(
            "status IN ('draft', 'pending_approval', 'active', 'rejected', 'expired', 'terminated')",
            name="ck_b2b_agent_agreement_status",
        ),
        CheckConstraint(
            "qualification_basis IN ('ordered', 'invoiced', 'paid')",
            name="ck_b2b_agent_agreement_qualification_basis",
        ),
        CheckConstraint(
            "calculation_method = 'retroactive'",
            name="ck_b2b_agent_agreement_calculation_method",
        ),
        CheckConstraint(
            "effective_to > effective_from",
            name="ck_b2b_agent_agreement_period",
        ),
        CheckConstraint(
            "target_amount > 0",
            name="ck_b2b_agent_agreement_target",
        ),
        Index("ix_b2b_agent_agreements_workspace_status", "workspace_id", "status"),
        Index("ix_b2b_agent_agreements_workspace_agent", "workspace_id", "agent_id"),
        Index(
            "ix_b2b_agent_active_agreement",
            "workspace_id",
            "agent_id",
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
    )


class B2BRebateTier(Base, TimestampMixin, WorkspaceMixin):
    """A contiguous retroactive rebate tier."""

    __tablename__ = "b2b_rebate_tiers"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    agreement_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("b2b_agent_agreements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    min_sales_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    max_sales_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    rebate_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)

    agreement: Mapped[B2BAgentAgreement] = relationship(back_populates="tiers")

    __table_args__ = (
        CheckConstraint(
            "min_sales_amount >= 0",
            name="ck_b2b_rebate_tier_min",
        ),
        CheckConstraint(
            "max_sales_amount IS NULL OR max_sales_amount > min_sales_amount",
            name="ck_b2b_rebate_tier_range",
        ),
        CheckConstraint(
            "rebate_percent >= 0 AND rebate_percent <= 100",
            name="ck_b2b_rebate_tier_percent",
        ),
        Index(
            "ix_b2b_rebate_tiers_workspace_agreement",
            "workspace_id",
            "agreement_id",
        ),
    )


class B2BRebateAccrual(Base, TimestampMixin, WorkspaceMixin):
    """Period rebate snapshot with approval and settlement audit."""

    __tablename__ = "b2b_rebate_accruals"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    accrual_number: Mapped[str] = mapped_column(String(32), nullable=False)
    agreement_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("b2b_agent_agreements.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    agent_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("b2b_agents.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft", index=True)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    qualification_basis: Mapped[str] = mapped_column(String(16), nullable=False)
    calculation_method: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="retroactive",
    )
    qualifying_sales: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    rebate_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    rebate_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    submitted_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    settled_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    settlement_reference: Mapped[str | None] = mapped_column(String(160), nullable=True)

    agreement: Mapped[B2BAgentAgreement] = relationship(back_populates="accruals")

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "accrual_number",
            name="uq_b2b_rebate_accruals_workspace_number",
        ),
        UniqueConstraint(
            "workspace_id",
            "agreement_id",
            "period_start",
            "period_end",
            name="uq_b2b_rebate_accruals_workspace_period",
        ),
        CheckConstraint(
            "status IN ('draft', 'pending_approval', 'approved', 'rejected', 'settled')",
            name="ck_b2b_rebate_accrual_status",
        ),
        CheckConstraint(
            "qualification_basis IN ('ordered', 'invoiced', 'paid')",
            name="ck_b2b_rebate_accrual_qualification_basis",
        ),
        CheckConstraint(
            "period_end >= period_start",
            name="ck_b2b_rebate_accrual_period",
        ),
        CheckConstraint(
            "qualifying_sales >= 0",
            name="ck_b2b_rebate_accrual_sales",
        ),
        CheckConstraint(
            "rebate_percent >= 0 AND rebate_percent <= 100",
            name="ck_b2b_rebate_accrual_percent",
        ),
        CheckConstraint(
            "rebate_amount >= 0",
            name="ck_b2b_rebate_accrual_amount",
        ),
        Index("ix_b2b_rebate_accruals_workspace_status", "workspace_id", "status"),
        Index(
            "ix_b2b_rebate_accruals_workspace_agent",
            "workspace_id",
            "agent_id",
        ),
        Index(
            "ix_b2b_rebate_accruals_workspace_period",
            "workspace_id",
            "period_start",
            "period_end",
        ),
    )
