"""Schemas for B2B credit risk, holds, and credit insurance."""

from __future__ import annotations

from datetime import date, datetime  # noqa: TC003 - Pydantic resolves annotations
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, PlainSerializer, model_validator

DecimalFloat = Annotated[
    Decimal,
    PlainSerializer(lambda value: float(value), return_type=float, when_used="json"),
]

CreditStatus = Literal["normal", "watch", "hold", "frozen"]
RiskAction = Literal["none", "watch", "hold", "freeze"]


class B2BCreditPolicyCreate(BaseModel):
    watch_score: int = Field(default=35, ge=0, le=100)
    hold_score: int = Field(default=60, ge=0, le=100)
    freeze_score: int = Field(default=80, ge=0, le=100)
    max_utilization_percent: DecimalFloat = Field(default=Decimal("100"), ge=0)
    max_overdue_days: int = Field(default=60, ge=0, le=3650)
    auto_hold_enabled: bool = True
    auto_freeze_enabled: bool = False
    insurance_required_above: DecimalFloat = Field(default=Decimal("0"), ge=0)
    notes: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def validate_scores(self) -> B2BCreditPolicyCreate:
        if not (
            0
            <= self.watch_score
            < self.hold_score
            < self.freeze_score
            <= 100
        ):
            raise ValueError(
                "watch_score, hold_score, and freeze_score must increase"
            )
        return self


class B2BCreditPolicyDecision(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class B2BCreditPolicyResponse(BaseModel):
    id: str
    version_number: int
    status: str
    watch_score: int
    hold_score: int
    freeze_score: int
    max_utilization_percent: DecimalFloat
    max_overdue_days: int
    auto_hold_enabled: bool
    auto_freeze_enabled: bool
    insurance_required_above: DecimalFloat
    notes: str | None = None
    created_by: str
    submitted_by: str | None = None
    submitted_at: datetime | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    rejected_by: str | None = None
    rejected_at: datetime | None = None
    rejection_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class B2BCreditPolicyListResponse(BaseModel):
    items: list[B2BCreditPolicyResponse]
    active_policy: B2BCreditPolicyResponse | None = None


class B2BRiskAssessmentResponse(BaseModel):
    id: str
    agent_id: str
    policy_id: str
    score: int
    risk_level: str
    recommended_action: RiskAction
    applied_action: RiskAction
    credit_status_before: CreditStatus
    credit_status_after: CreditStatus
    exposure_amount: DecimalFloat
    overdue_amount: DecimalFloat
    utilization_percent: DecimalFloat
    overdue_ratio_percent: DecimalFloat
    max_days_overdue: int
    past_due_invoice_count: int
    written_off_amount: DecimalFloat
    insurance_coverage_amount: DecimalFloat
    insurance_coverage_percent: DecimalFloat
    net_exposure_amount: DecimalFloat
    factors: dict = Field(default_factory=dict)
    message: str | None = None
    assessed_by: str
    assessed_at: datetime
    created_at: datetime


class B2BCreditAgentRiskResponse(BaseModel):
    id: str
    agent_number: str
    company_name: str
    contact_name: str
    email: str
    country: str | None = None
    status: str
    credit_status: CreditStatus
    credit_status_reason: str | None = None
    credit_status_updated_by: str | None = None
    credit_status_updated_at: datetime | None = None
    credit_limit: DecimalFloat
    current_balance: DecimalFloat
    currency: str
    latest_assessment: B2BRiskAssessmentResponse | None = None


class B2BCreditRiskOverviewResponse(BaseModel):
    items: list[B2BCreditAgentRiskResponse]
    total: int
    active_policy: B2BCreditPolicyResponse | None = None


class B2BCreditStatusUpdate(BaseModel):
    status: CreditStatus
    reason: str = Field(min_length=2, max_length=2000)


class B2BCreditStatusEventResponse(BaseModel):
    id: str
    agent_id: str
    assessment_id: str | None = None
    previous_status: CreditStatus
    new_status: CreditStatus
    action: str
    reason: str
    actor: str
    evidence: dict = Field(default_factory=dict)
    created_at: datetime


class B2BInsurancePolicyCreate(BaseModel):
    agent_id: str
    policy_number: str = Field(min_length=1, max_length=64)
    provider: str = Field(min_length=1, max_length=160)
    currency: str = Field(default="USD", min_length=3, max_length=8)
    coverage_limit: DecimalFloat = Field(gt=0)
    coverage_percent: DecimalFloat = Field(gt=0, le=100)
    effective_from: date
    effective_to: date
    status: Literal["draft", "active"] = "draft"
    notes: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def validate_period(self) -> B2BInsurancePolicyCreate:
        if self.effective_to < self.effective_from:
            raise ValueError("effective_to cannot be before effective_from")
        return self


class B2BInsurancePolicyUpdate(BaseModel):
    provider: str | None = Field(default=None, min_length=1, max_length=160)
    status: Literal["draft", "active", "expired", "cancelled"] | None = None
    coverage_limit: DecimalFloat | None = Field(default=None, gt=0)
    coverage_percent: DecimalFloat | None = Field(default=None, gt=0, le=100)
    effective_from: date | None = None
    effective_to: date | None = None
    notes: str | None = Field(default=None, max_length=5000)


class B2BInsurancePolicyResponse(BaseModel):
    id: str
    agent_id: str
    agent_company: str = ""
    policy_number: str
    provider: str
    status: str
    currency: str
    coverage_limit: DecimalFloat
    coverage_percent: DecimalFloat
    effective_from: date
    effective_to: date
    notes: str | None = None
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime


class B2BInsurancePolicyListResponse(BaseModel):
    items: list[B2BInsurancePolicyResponse]
    total: int


class B2BInsuranceClaimCreate(BaseModel):
    policy_id: str
    invoice_id: str
    claimed_amount: DecimalFloat = Field(gt=0)
    reason: str = Field(min_length=2, max_length=5000)
    evidence: dict = Field(default_factory=dict)


class B2BInsuranceClaimDecision(BaseModel):
    reason: str | None = Field(default=None, max_length=5000)


class B2BInsuranceClaimSettle(BaseModel):
    recovered_amount: DecimalFloat | None = Field(default=None, gt=0)
    settlement_reference: str = Field(min_length=1, max_length=160)


class B2BInsuranceClaimResponse(BaseModel):
    id: str
    claim_number: str
    policy_id: str
    policy_number: str = ""
    invoice_id: str
    invoice_number: str = ""
    agent_id: str
    agent_company: str = ""
    status: str
    claimed_amount: DecimalFloat
    recovered_amount: DecimalFloat
    currency: str
    reason: str
    evidence: dict = Field(default_factory=dict)
    created_by: str
    submitted_by: str | None = None
    submitted_at: datetime | None = None
    decided_by: str | None = None
    decided_at: datetime | None = None
    rejection_reason: str | None = None
    settled_by: str | None = None
    settled_at: datetime | None = None
    settlement_reference: str | None = None
    created_at: datetime
    updated_at: datetime


class B2BInsuranceClaimListResponse(BaseModel):
    items: list[B2BInsuranceClaimResponse]
    total: int
