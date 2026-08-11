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
    purchase_price: Decimal
    domestic_shipping: Decimal
    first_leg_shipping: Decimal
    last_leg_shipping: Decimal
    payment_fee: Decimal
    marketing_amortization: Decimal
    after_sales_loss: Decimal
    total_cost: Decimal
    weight_kg: Decimal | None
    source: str
    valid_from: datetime
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
