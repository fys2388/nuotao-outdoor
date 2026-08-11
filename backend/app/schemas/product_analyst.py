"""Product Analyst Agent schemas (M2.2).

The agent must return structured output that validates against
:class:`ProductAnalysisOutput`; anything else is treated as a failed run
(recorded, never acted upon).
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

DECISIONS = ("test", "hold", "reject")


class PricingRecommendation(BaseModel):
    """AI pricing suggestion (never applied automatically)."""

    recommended_price: Decimal | None = Field(default=None, ge=0)
    price_range: list[Decimal] | None = None
    max_cac: Decimal | None = Field(default=None, ge=0)
    rationale: str | None = Field(default=None, max_length=2000)


class TestPlan(BaseModel):
    """Proposed test plan; execution requires human approval."""

    quantity: int = Field(default=30, ge=1, le=10000)
    days: int = Field(default=30, ge=1, le=365)
    channels: list[str] = Field(default_factory=list, max_length=20)
    budget: Decimal | None = Field(default=None, ge=0)
    kpis: dict[str, Any] = Field(default_factory=dict)


class ProductAnalysisOutput(BaseModel):
    """Structured output contract for the Product Analyst Agent v1.

    Fields follow docs/product_strategy.md §6: decision is one of
    test/hold/reject, confidence is 0-1, pricing and test_plan are proposals
    only (the agent cannot approve or execute anything).
    """

    decision: Literal["test", "hold", "reject"]
    confidence: Decimal = Field(ge=0, le=1)
    market_reasoning: str = Field(min_length=1, max_length=4000)
    risks: list[str] = Field(default_factory=list, max_length=20)
    pricing: PricingRecommendation
    test_plan: TestPlan

    @field_validator("risks")
    @classmethod
    def _trim_risks(cls, value: list[str]) -> list[str]:
        return [item[:500] for item in value]

    @field_validator("pricing")
    @classmethod
    def _validate_pricing(cls, value: PricingRecommendation) -> PricingRecommendation:
        if value.price_range:
            if value.price_range[0] > value.price_range[-1]:
                raise ValueError("price_range must be ascending")
        return value


class ProductAnalysisResultOut(BaseModel):
    """Result of one agent analyze call (audit + proposal)."""

    analysis_run_id: UUID
    provider: str
    model: str
    prompt_version: str
    decision_proposal_id: UUID | None = None
    decision: str | None = None
    confidence: Decimal | None = None
    recommended_price: Decimal | None = None
    max_cac: Decimal | None = None
    test_quantity: int | None = None
    test_days: int | None = None
    tokens: dict[str, int] = Field(default_factory=dict)
    estimated_cost: Decimal
    latency_ms: int
    trace_id: str | None = None
    status: str
    approval_status: str | None = None


class EvaluationCreate(BaseModel):
    """Record an evaluation of a past AI prediction against actuals."""

    product_id: UUID
    analysis_run_id: UUID | None = None
    experiment_id: UUID | None = None
    actual_result: dict[str, Any] = Field(default_factory=dict)
    human_rating: int | None = Field(default=None, ge=1, le=5)
    notes: str | None = Field(default=None, max_length=500)


class EvaluationOut(BaseModel):
    """An AI evaluation row as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    product_id: UUID | None
    analysis_run_id: UUID | None
    experiment_id: UUID | None
    prediction: dict[str, Any]
    actual_result: dict[str, Any]
    accuracy: dict[str, Any]
    prediction_result: str | None
    error_type: str | None
    confidence_bucket: str | None
    success_flag: bool | None
    metric_snapshot: dict[str, Any]
    human_rating: int | None
    notes: str | None
    trace_id: str | None
    created_at: datetime


class CalibrationApproveRequest(BaseModel):
    """Human approval/rejection of a score calibration proposal."""

    actor: str = Field(min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=500)


class ConfidenceCalibrationOut(BaseModel):
    """One confidence calibration bucket in a report."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    bucket: str
    sample_count: int
    success_count: int
    success_rate: Decimal
    avg_confidence: Decimal
    computed_at: datetime
    trace_id: str | None
    created_at: datetime


class ScoreCalibrationRunOut(BaseModel):
    """A score calibration run as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    status: str
    model_version: str
    current_weights: dict[str, Any]
    suggested_weights: dict[str, Any]
    input_snapshot: dict[str, Any]
    metrics: dict[str, Any]
    sample_size: int
    rationale: str | None
    approved_by: str | None
    approved_at: datetime | None
    trace_id: str | None
    created_at: datetime
    updated_at: datetime


class KnowledgeEntryCreate(BaseModel):
    """Create a product knowledge memory entry."""

    product_id: UUID | None = None
    category: str | None = Field(default=None, max_length=64)
    entry_type: Literal["success_pattern", "failure_pattern", "category_insight"]
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=4000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    source: str = Field(default="manual", max_length=32)


class KnowledgeEntryOut(BaseModel):
    """A knowledge entry as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    product_id: UUID | None
    category: str | None
    entry_type: str
    title: str
    content: str
    tags: list[Any]
    source: str
    trace_id: str | None
    created_at: datetime
    updated_at: datetime

