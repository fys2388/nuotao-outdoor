"""Product intelligence request/response schemas (M2.1)."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.product import ProductOut


class ProductIntakeRequest(BaseModel):
    """Manual product intake payload (Phase 1: 人工输入).

    All monetary fields are Decimal; required data is validated before any
    write. No LLM is invoked in this phase.
    """

    sku: str | None = Field(default=None, max_length=64)
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    source_type: Literal["1688", "MANUAL", "OTHER"] = "MANUAL"
    source_url: str | None = Field(default=None, max_length=512)
    supplier_code: str | None = Field(default=None, max_length=64)
    purchase_cost: Decimal = Field(default=Decimal("0"), ge=0)
    domestic_shipping: Decimal = Field(default=Decimal("0"), ge=0)
    first_leg_shipping: Decimal = Field(default=Decimal("0"), ge=0)
    last_leg_shipping: Decimal = Field(default=Decimal("0"), ge=0)
    international_shipping: Decimal | None = Field(default=None, ge=0)
    packaging: Decimal = Field(default=Decimal("0"), ge=0)
    tax_estimate: Decimal = Field(default=Decimal("0"), ge=0)
    handling: Decimal = Field(default=Decimal("0"), ge=0)
    weight_kg: Decimal | None = Field(default=None, gt=0)
    dimensions: dict[str, Any] | None = None
    target_market: str = Field(default="US", max_length=16)
    currency: str = Field(default="USD", max_length=8)

    @field_validator("source_url")
    @classmethod
    def _validate_source_url(cls, value: str | None) -> str | None:
        if value and not value.startswith(("http://", "https://")):
            raise ValueError("source_url must be an http(s) URL")
        return value

    @field_validator("dimensions")
    @classmethod
    def _validate_dimensions(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return None
        for key in ("length", "width", "height"):
            raw = value.get(key)
            try:
                number = float(raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"dimensions.{key} must be a positive number (cm)") from exc
            if number <= 0:
                raise ValueError(f"dimensions.{key} must be positive")
            value[key] = number
        return value


class ProductIntakeResult(BaseModel):
    """Result of a product intake (product + source + cost snapshot)."""

    product: ProductOut
    source_id: UUID
    cost_snapshot_id: UUID
    score_id: UUID


class ProductSourceOut(BaseModel):
    """Product source as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    product_id: UUID | None
    source_type: str
    source_url: str | None
    supplier_id: UUID | None
    supplier_code: str | None
    captured_at: datetime
    raw_data: dict[str, Any]
    trace_id: str | None
    created_at: datetime


class ProductCostSnapshotOut(BaseModel):
    """One append-only cost history row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID
    currency: str
    purchase_cost: Decimal
    domestic_shipping: Decimal
    first_leg_shipping: Decimal
    last_leg_shipping: Decimal
    international_shipping: Decimal
    packaging: Decimal
    tax_estimate: Decimal
    handling: Decimal
    total_landed_cost: Decimal
    version: str
    payment_fee: Decimal
    marketing_amortization: Decimal
    after_sales_loss: Decimal
    total_cost: Decimal
    weight_kg: Decimal | None
    source: str
    valid_from: datetime
    trace_id: str | None
    created_at: datetime


class ProductScoreEvidenceOut(BaseModel):
    """Per-dimension score evidence."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_score_id: UUID
    dimension: str
    score: Decimal
    source: str
    evidence: list[Any]
    confidence: Decimal
    version: str
    trace_id: str | None
    created_at: datetime


class ProductScoreOut(BaseModel):
    """One product score row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID
    profit: Decimal
    logistics: Decimal
    demand: Decimal
    competition: Decimal
    differentiation: Decimal
    compliance: Decimal
    total: Decimal
    model_version: str
    rule_version: str
    scored_at: datetime
    trace_id: str | None
    created_at: datetime
    evidence: list[ProductScoreEvidenceOut] = Field(default_factory=list)


class ProductAnalysisRunOut(BaseModel):
    """One analysis run audit row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID | None
    provider: str
    model: str
    prompt_version: str | None
    input_snapshot: dict[str, Any]
    output: dict[str, Any]
    token_usage: dict[str, Any]
    estimated_cost: Decimal
    latency_ms: int
    status: str
    trace_id: str | None
    created_at: datetime


class ProductDecisionOut(BaseModel):
    """One product decision row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID
    decision: str
    score: Decimal | None
    confidence: Decimal | None
    reasons: list[Any]
    risks: list[Any]
    recommended_price: Decimal | None
    max_cac: Decimal | None
    test_quantity: int | None
    test_days: int | None
    approval_status: str
    approved_by: str | None
    approved_at: datetime | None
    trace_id: str | None
    created_at: datetime
    updated_at: datetime


class ProductIntelligenceOut(BaseModel):
    """Aggregated product intelligence view."""

    product: ProductOut
    score: ProductScoreOut | None = None
    analysis: ProductAnalysisRunOut | None = None
    decision: ProductDecisionOut | None = None


class DecisionApproveRequest(BaseModel):
    """Human approval of a pending product decision."""

    actor: str = Field(min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=500)


class SourcingCandidateCreate(BaseModel):
    """Create a supplier candidate for a product."""

    supplier_code: str | None = Field(default=None, max_length=64)
    source_type: Literal["1688", "MANUAL", "OTHER"] = "1688"
    source_url: str | None = Field(default=None, max_length=512)
    title: str | None = Field(default=None, max_length=255)
    purchase_price: Decimal = Field(default=Decimal("0"), ge=0)
    moq: int | None = Field(default=None, ge=0)
    lead_time_days: int | None = Field(default=None, ge=0)
    trend_score: Decimal | None = Field(default=None, ge=0, le=10)
    profit_model: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("source_url")
    @classmethod
    def _validate_source_url(cls, value: str | None) -> str | None:
        if value and not value.startswith(("http://", "https://")):
            raise ValueError("source_url must be an http(s) URL")
        return value


class SourcingCandidateOut(BaseModel):
    """A supplier candidate as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    product_id: UUID | None
    supplier_id: UUID | None
    supplier_code: str | None
    source_type: str
    source_url: str | None
    title: str | None
    status: str
    purchase_price: Decimal
    moq: int | None
    lead_time_days: int | None
    trend_score: Decimal | None
    profit_model: dict[str, Any]
    notes: str | None
    version: str
    trace_id: str | None
    created_at: datetime
    updated_at: datetime


class ProductExperimentOut(BaseModel):
    """A product testing-loop record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID
    decision_id: UUID | None = None
    experiment_type: str
    status: str
    hypothesis: str | None = None
    expected_metrics: dict[str, Any] | None = None
    baseline: dict[str, Any] | None = None
    target_metrics: dict[str, Any] | None = None
    prediction: dict[str, Any]
    experiment: dict[str, Any]
    actual_result: dict[str, Any]
    result_history: list[dict[str, Any]] | None = None
    calibration: dict[str, Any]
    version: str
    source_trace_id: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    started_by: str | None = None
    trace_id: str | None
    created_at: datetime
    updated_at: datetime


class ExperimentStartRequest(BaseModel):
    """Start an experiment with the executed test plan.

    ``started_by`` is the M5.6 second human control point: a decision-linked
    experiment may only be started by a human actor (agents are rejected).
    """

    quantity: int = Field(default=30, ge=1)
    channels: list[str] = Field(default_factory=list)
    budget: Decimal = Field(default=Decimal("0"), ge=0)
    targets: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    started_by: str | None = Field(default=None, min_length=1, max_length=64)


class ExperimentCompleteRequest(BaseModel):
    """Complete an experiment with measured results (M5.7).

    ``source`` must be an explicit provenance: ``manual`` (human-entered),
    ``external`` (business platform) or ``connector`` (synced pipeline).
    ``ai`` / ``predicted`` are rejected - a model prediction can never be
    an actual_result. ``actor`` is the human operator who backfills the
    outcome; ``observed_at`` is when the outcome was observed.
    """

    units_sold: int = Field(default=0, ge=0)
    revenue: Decimal = Field(default=Decimal("0"), ge=0)
    orders: int = Field(default=0, ge=0)
    conversion_rate: Decimal | None = Field(default=None, ge=0, le=1)
    roas: Decimal | None = Field(default=None, ge=0)
    return_rate: Decimal | None = Field(default=None, ge=0, le=1)
    margin_rate: Decimal | None = Field(default=None)
    completed_at: datetime | None = None
    actor: str | None = Field(default=None, min_length=1, max_length=64)
    source: Literal["manual", "external", "connector"] | None = None
    observed_at: datetime | None = None
    trace_id: str | None = Field(default=None, max_length=64)


# --------------------------------------------------------------------------- #
# M5.6 Product Analyst pilot
# --------------------------------------------------------------------------- #


class ExperimentProposeFromDecisionRequest(BaseModel):
    """Create an experiment proposal from an approved decision."""

    note: str | None = Field(default=None, max_length=500)


class ExperimentProposalOut(ProductExperimentOut):
    """An experiment proposal (decision-linked) as returned by the API."""

    decision_id: UUID
    source_trace_id: str | None = None
