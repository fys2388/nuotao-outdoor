"""B2B credit policy, risk assessment, hold events, and credit insurance."""

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
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AI_JSON, Base, CreatedAtMixin, TimestampMixin, WorkspaceMixin

B2B_CREDIT_POLICY_STATUSES = [
    "draft",
    "pending_approval",
    "active",
    "rejected",
    "superseded",
]
B2B_CREDIT_STATUSES = ["normal", "watch", "hold", "frozen"]
B2B_RISK_LEVELS = ["low", "medium", "high", "critical"]
B2B_CREDIT_ACTIONS = ["none", "watch", "hold", "freeze"]
B2B_INSURANCE_POLICY_STATUSES = ["draft", "active", "expired", "cancelled"]
B2B_INSURANCE_CLAIM_STATUSES = [
    "draft",
    "submitted",
    "approved",
    "rejected",
    "settled",
]


class B2BCreditPolicy(Base, TimestampMixin, WorkspaceMixin):
    """Versioned policy approved before deterministic credit actions."""

    __tablename__ = "b2b_credit_policies"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="draft",
        index=True,
    )
    watch_score: Mapped[int] = mapped_column(Integer, nullable=False, default=35)
    hold_score: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    freeze_score: Mapped[int] = mapped_column(Integer, nullable=False, default=80)
    max_utilization_percent: Mapped[Decimal] = mapped_column(
        Numeric(7, 2),
        nullable=False,
        default=100,
    )
    max_overdue_days: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    auto_hold_enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    auto_freeze_enabled: Mapped[bool] = mapped_column(nullable=False, default=False)
    insurance_required_above: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        default=0,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    submitted_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "version_number",
            name="uq_b2b_credit_policies_workspace_version",
        ),
        CheckConstraint(
            "status IN ('draft', 'pending_approval', 'active', 'rejected', 'superseded')",
            name="ck_b2b_credit_policy_status",
        ),
        CheckConstraint(
            "watch_score >= 0 AND watch_score < hold_score "
            "AND hold_score < freeze_score AND freeze_score <= 100",
            name="ck_b2b_credit_policy_score_order",
        ),
        CheckConstraint(
            "max_utilization_percent >= 0",
            name="ck_b2b_credit_policy_utilization",
        ),
        CheckConstraint("max_overdue_days >= 0", name="ck_b2b_credit_policy_overdue"),
        CheckConstraint(
            "insurance_required_above >= 0",
            name="ck_b2b_credit_policy_insurance_required",
        ),
        Index(
            "uq_b2b_credit_policy_active_workspace",
            "workspace_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
        Index("ix_b2b_credit_policies_workspace_status", "workspace_id", "status"),
    )


class B2BCreditRiskAssessment(Base, CreatedAtMixin, WorkspaceMixin):
    """Immutable credit-risk assessment snapshot."""

    __tablename__ = "b2b_credit_risk_assessments"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    agent_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("b2b_agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    policy_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("b2b_credit_policies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    recommended_action: Mapped[str] = mapped_column(String(16), nullable=False)
    applied_action: Mapped[str] = mapped_column(String(16), nullable=False, default="none")
    credit_status_before: Mapped[str] = mapped_column(String(16), nullable=False)
    credit_status_after: Mapped[str] = mapped_column(String(16), nullable=False)
    exposure_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    overdue_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    utilization_percent: Mapped[Decimal] = mapped_column(Numeric(9, 2), nullable=False)
    overdue_ratio_percent: Mapped[Decimal] = mapped_column(Numeric(9, 2), nullable=False)
    max_days_overdue: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    past_due_invoice_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    written_off_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        default=0,
    )
    insurance_coverage_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        default=0,
    )
    insurance_coverage_percent: Mapped[Decimal] = mapped_column(
        Numeric(7, 2),
        nullable=False,
        default=0,
    )
    net_exposure_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    factors: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    assessed_by: Mapped[str] = mapped_column(String(128), nullable=False)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("score >= 0 AND score <= 100", name="ck_b2b_credit_score"),
        CheckConstraint(
            "risk_level IN ('low', 'medium', 'high', 'critical')",
            name="ck_b2b_credit_risk_level",
        ),
        CheckConstraint(
            "recommended_action IN ('none', 'watch', 'hold', 'freeze')",
            name="ck_b2b_credit_recommended_action",
        ),
        CheckConstraint(
            "applied_action IN ('none', 'watch', 'hold', 'freeze')",
            name="ck_b2b_credit_applied_action",
        ),
        Index(
            "ix_b2b_credit_assessments_workspace_agent",
            "workspace_id",
            "agent_id",
        ),
        Index(
            "ix_b2b_credit_assessments_workspace_assessed",
            "workspace_id",
            "assessed_at",
        ),
    )


class B2BCreditStatusEvent(Base, CreatedAtMixin, WorkspaceMixin):
    """Append-only customer credit-status transition event."""

    __tablename__ = "b2b_credit_status_events"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    agent_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("b2b_agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assessment_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("b2b_credit_risk_assessments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    previous_status: Mapped[str] = mapped_column(String(16), nullable=False)
    new_status: Mapped[str] = mapped_column(String(16), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)

    __table_args__ = (
        CheckConstraint(
            "previous_status IN ('normal', 'watch', 'hold', 'frozen')",
            name="ck_b2b_credit_event_previous_status",
        ),
        CheckConstraint(
            "new_status IN ('normal', 'watch', 'hold', 'frozen')",
            name="ck_b2b_credit_event_new_status",
        ),
        Index(
            "ix_b2b_credit_events_workspace_agent",
            "workspace_id",
            "agent_id",
        ),
    )


class B2BCreditInsurancePolicy(Base, TimestampMixin, WorkspaceMixin):
    """Credit-insurance policy attached to a B2B customer."""

    __tablename__ = "b2b_credit_insurance_policies"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    agent_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("b2b_agents.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    policy_number: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="draft",
        index=True,
    )
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    coverage_limit: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    coverage_percent: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(128), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "policy_number",
            name="uq_b2b_credit_insurance_workspace_number",
        ),
        CheckConstraint(
            "status IN ('draft', 'active', 'expired', 'cancelled')",
            name="ck_b2b_credit_insurance_status",
        ),
        CheckConstraint("coverage_limit > 0", name="ck_b2b_credit_insurance_limit"),
        CheckConstraint(
            "coverage_percent > 0 AND coverage_percent <= 100",
            name="ck_b2b_credit_insurance_percent",
        ),
        CheckConstraint(
            "effective_to >= effective_from",
            name="ck_b2b_credit_insurance_period",
        ),
        Index(
            "ix_b2b_credit_insurance_workspace_agent",
            "workspace_id",
            "agent_id",
        ),
        Index(
            "ix_b2b_credit_insurance_workspace_effective",
            "workspace_id",
            "effective_from",
            "effective_to",
        ),
    )


class B2BCreditInsuranceClaim(Base, TimestampMixin, WorkspaceMixin):
    """Insurance claim linked to one policy and invoice."""

    __tablename__ = "b2b_credit_insurance_claims"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    policy_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("b2b_credit_insurance_policies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    invoice_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("b2b_invoices.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    agent_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("b2b_agents.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    claim_number: Mapped[str] = mapped_column(String(48), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="draft",
        index=True,
    )
    claimed_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    recovered_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        default=0,
    )
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    submitted_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    settled_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    settlement_reference: Mapped[str | None] = mapped_column(String(160), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "claim_number",
            name="uq_b2b_credit_claims_workspace_number",
        ),
        CheckConstraint(
            "status IN ('draft', 'submitted', 'approved', 'rejected', 'settled')",
            name="ck_b2b_credit_claim_status",
        ),
        CheckConstraint("claimed_amount > 0", name="ck_b2b_credit_claim_amount"),
        CheckConstraint(
            "recovered_amount >= 0 AND recovered_amount <= claimed_amount",
            name="ck_b2b_credit_claim_recovered",
        ),
        Index(
            "ix_b2b_credit_claims_workspace_agent",
            "workspace_id",
            "agent_id",
        ),
        Index(
            "ix_b2b_credit_claims_workspace_status",
            "workspace_id",
            "status",
        ),
    )
