"""Schemas for B2B agent agreements, targets, and rebates."""

from __future__ import annotations

from datetime import date, datetime  # noqa: TC003 - Pydantic resolves annotations
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, PlainSerializer, model_validator

DecimalFloat = Annotated[
    Decimal,
    PlainSerializer(lambda value: float(value), return_type=float, when_used="json"),
]

QualificationBasis = Literal["ordered", "invoiced", "paid"]
CalculationMethod = Literal["retroactive"]


class B2BAgreementCreate(BaseModel):
    agent_id: str
    name: str = Field(min_length=1, max_length=160)
    currency: str = Field(default="USD", min_length=3, max_length=8)
    effective_from: date
    effective_to: date
    target_amount: DecimalFloat = Field(gt=0)
    qualification_basis: QualificationBasis = "invoiced"
    calculation_method: CalculationMethod = "retroactive"
    notes: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def validate_period(self) -> B2BAgreementCreate:
        if self.effective_to <= self.effective_from:
            raise ValueError("effective_to must be after effective_from")
        return self


class B2BAgreementUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    currency: str | None = Field(default=None, min_length=3, max_length=8)
    effective_from: date | None = None
    effective_to: date | None = None
    target_amount: DecimalFloat | None = Field(default=None, gt=0)
    qualification_basis: QualificationBasis | None = None
    calculation_method: CalculationMethod | None = None
    notes: str | None = Field(default=None, max_length=5000)


class B2BRebateTierCreate(BaseModel):
    min_sales_amount: DecimalFloat = Field(ge=0)
    max_sales_amount: DecimalFloat | None = Field(default=None, gt=0)
    rebate_percent: DecimalFloat = Field(ge=0, le=100)

    @model_validator(mode="after")
    def validate_range(self) -> B2BRebateTierCreate:
        if (
            self.max_sales_amount is not None
            and self.max_sales_amount <= self.min_sales_amount
        ):
            raise ValueError("max_sales_amount must be greater than min_sales_amount")
        return self


class B2BRebateTierUpdate(BaseModel):
    min_sales_amount: DecimalFloat | None = Field(default=None, ge=0)
    max_sales_amount: DecimalFloat | None = Field(default=None, gt=0)
    rebate_percent: DecimalFloat | None = Field(default=None, ge=0, le=100)


class B2BAgreementDecision(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)


class B2BRebateAccrualCreate(BaseModel):
    period_start: date
    period_end: date

    @model_validator(mode="after")
    def validate_period(self) -> B2BRebateAccrualCreate:
        if self.period_end < self.period_start:
            raise ValueError("period_end cannot be before period_start")
        return self


class B2BRebateAccrualSettle(BaseModel):
    settlement_reference: str = Field(min_length=1, max_length=160)


class B2BRebateTierResponse(BaseModel):
    id: str
    agreement_id: str
    min_sales_amount: DecimalFloat
    max_sales_amount: DecimalFloat | None = None
    rebate_percent: DecimalFloat
    created_at: datetime
    updated_at: datetime


class B2BAgreementResponse(BaseModel):
    id: str
    agreement_number: str
    agent_id: str
    agent_company: str = ""
    agent_number: str = ""
    name: str
    status: str
    effective_status: str
    currency: str
    effective_from: date
    effective_to: date
    target_amount: DecimalFloat
    qualification_basis: QualificationBasis
    calculation_method: CalculationMethod
    notes: str | None = None
    created_by: str
    submitted_by: str | None = None
    submitted_at: datetime | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    rejection_reason: str | None = None
    terminated_by: str | None = None
    terminated_at: datetime | None = None
    termination_reason: str | None = None
    tiers: list[B2BRebateTierResponse] = Field(default_factory=list)
    accrual_count: int = 0
    created_at: datetime
    updated_at: datetime


class B2BAgreementListResponse(BaseModel):
    items: list[B2BAgreementResponse]
    total: int
    page: int
    page_size: int


class B2BRebateProgressResponse(BaseModel):
    agreement_id: str
    as_of: date
    period_start: date
    period_end: date
    currency: str
    qualification_basis: QualificationBasis
    target_amount: DecimalFloat
    qualifying_sales: DecimalFloat
    achievement_percent: DecimalFloat
    remaining_amount: DecimalFloat
    current_tier_id: str | None = None
    current_rebate_percent: DecimalFloat
    projected_rebate_amount: DecimalFloat
    next_tier_min_sales: DecimalFloat | None = None
    amount_to_next_tier: DecimalFloat | None = None
    days_remaining: int
    included_record_count: int
    excluded_record_count: int
    missing_rate_currencies: list[str] = Field(default_factory=list)


class B2BRebateAccrualResponse(BaseModel):
    id: str
    accrual_number: str
    agreement_id: str
    agreement_number: str = ""
    agent_id: str
    agent_company: str = ""
    status: str
    period_start: date
    period_end: date
    qualification_basis: QualificationBasis
    calculation_method: CalculationMethod
    qualifying_sales: DecimalFloat
    rebate_percent: DecimalFloat
    rebate_amount: DecimalFloat
    currency: str
    evidence: dict = Field(default_factory=dict)
    created_by: str
    submitted_by: str | None = None
    submitted_at: datetime | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    rejected_by: str | None = None
    rejected_at: datetime | None = None
    rejection_reason: str | None = None
    settled_by: str | None = None
    settled_at: datetime | None = None
    settlement_reference: str | None = None
    created_at: datetime
    updated_at: datetime


class B2BRebateAccrualListResponse(BaseModel):
    items: list[B2BRebateAccrualResponse]
    total: int
    page: int
    page_size: int
